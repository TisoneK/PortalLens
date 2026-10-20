"""Authorized default-credential audit for exposed gateway admin logins.

ADR-16 lifted the assess/exploit boundary; ADR-26 records this action's own
risk assessment. The action is deliberately narrow:

- **Well-known vendor defaults only.** The candidate list is a short, fixed
  tuple of published defaults (RouterOS ships ``admin`` with a blank
  password on many firmware images). There is no wordlist, no mutation, no
  spraying from a corpus, and no credential captured from a third party.
- **Bounded.** At most :data:`MAX_CREDENTIAL_ATTEMPTS` attempts per host,
  with a delay between them, and the audit stops at the first accepted
  login or the first transport failure (which is what a lockout or a
  firewall drop looks like).
- **Gated.** :func:`probe_default_credentials` calls
  :func:`assert_policy` first, so it only runs under the single
  ``AcquisitionPolicy.authorized`` flag (ADR-15).
- **Evidence-first.** An accepted default is recorded as one
  ``SERVICE_REACHABLE`` record with the key ``admin_credential:<port>``;
  the ``gateway_admin_default_credential`` check turns that into a finding.

The transport is a minimal Telnet client: enough IAC stripping to read a
login prompt, not a terminal emulator. Network access is injectable
(``login``) so tests never touch a socket.
"""

from __future__ import annotations

import contextlib
import re
import socket
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from portallens.acquisition import assert_policy
from portallens.evidence import Evidence, EvidenceType
from portallens.portal import AcquisitionPolicy

#: Published vendor defaults worth trying. RouterOS first: the analyzer's
#: gateway fingerprint is MikroTik more often than anything else, and
#: ``admin`` + blank password is the documented factory default.
DEFAULT_CREDENTIALS: tuple[tuple[str, str], ...] = (
    ("admin", ""),
    ("admin", "admin"),
    ("admin", "password"),
)

#: Requests are capped so a misconfiguration cannot turn this into a spray.
MAX_CREDENTIAL_ATTEMPTS = 3
HARD_CREDENTIAL_ATTEMPT_CAP = 5

DEFAULT_ATTEMPT_TIMEOUT_SECONDS = 4.0
DEFAULT_ATTEMPT_DELAY_SECONDS = 0.75

_IAC = 0xFF
_WILL, _WONT, _DO, _DONT, _SB, _SE = 0xFB, 0xFC, 0xFD, 0xFE, 0xFA, 0xF0

_SUCCESS_PROMPT = re.compile(r"\[[^\]]*@[^\]]*\]\s*>|[\w./-]+\s*[>#]\s*$", re.MULTILINE)
_FAILURE_MARKERS = ("login failed", "incorrect", "invalid password", "access denied", "denied")

LoginAttempt = Callable[[str, int, str, str, float], bool]


@dataclass(frozen=True)
class CredentialAttempt:
    """One bounded login attempt and what the device did with it."""

    username: str
    password: str
    accepted: bool

    @property
    def label(self) -> str:
        """Human-readable label that never hides a blank password."""

        return f"{self.username}/{'<blank>' if not self.password else self.password}"


def probe_default_credentials(
    host: str,
    policy: AcquisitionPolicy,
    *,
    port: int = 23,
    candidates: Sequence[tuple[str, str]] = DEFAULT_CREDENTIALS,
    max_attempts: int = MAX_CREDENTIAL_ATTEMPTS,
    attempt_timeout: float = DEFAULT_ATTEMPT_TIMEOUT_SECONDS,
    attempt_delay: float = DEFAULT_ATTEMPT_DELAY_SECONDS,
    login: LoginAttempt | None = None,
) -> list[Evidence]:
    """Try the well-known defaults against ``host``'s admin login.

    Returns one evidence record for the outcome: ``default_accepted`` when a
    default logged in (the note names which one), or ``default_rejected``
    when every bounded attempt was refused. Raises
    :class:`AcquisitionDenied` without authorization; the caller is
    responsible for having authorization for the target.
    """

    assert_policy(policy, "admin_credentials")
    attempt_login = login or _telnet_login
    limit = max(1, min(max_attempts, HARD_CREDENTIAL_ATTEMPT_CAP))
    source = f"admin_login://{host}:{port}"
    attempts: list[CredentialAttempt] = []

    for index, (username, password) in enumerate(candidates[:limit]):
        if index and attempt_delay > 0:
            time.sleep(attempt_delay)
        try:
            accepted = attempt_login(host, port, username, password, attempt_timeout)
        except (OSError, TimeoutError) as exc:
            # A refused/reset connection after failures is what a lockout or
            # a management-ACL drop looks like — stop, do not retry blind.
            attempts.append(CredentialAttempt(username, password, False))
            return [
                _evidence(
                    source,
                    port,
                    "default_rejected",
                    f"Stopped after {len(attempts)} attempt(s): the login service "
                    f"became unreachable ({type(exc).__name__}); no default was accepted.",
                )
            ]
        attempts.append(CredentialAttempt(username, password, accepted))
        if accepted:
            return [
                _evidence(
                    source,
                    port,
                    "default_accepted",
                    f"Port {port} accepted the well-known default login "
                    f"{attempts[-1].label} after {len(attempts)} attempt(s).",
                )
            ]

    return [
        _evidence(
            source,
            port,
            "default_rejected",
            f"Tried {len(attempts)} well-known default login(s) on port {port}; all were refused.",
        )
    ]


def _evidence(source: str, port: int, value: str, note: str) -> Evidence:
    return Evidence(
        type=EvidenceType.SERVICE_REACHABLE,
        source=source,
        key=f"admin_credential:{port}",
        value=value,
        note=note,
    )


# ---------------------------------------------------------------------------
# Minimal Telnet login — enough to read a prompt and answer it.
# ---------------------------------------------------------------------------


class _TelnetStream:
    """A bounded telnet reader that strips IAC negotiation."""

    def __init__(self, sock: socket.socket) -> None:
        self._sock = sock
        self._buffer = ""

    def read_until(self, markers: Sequence[str], timeout: float) -> str:
        """Read until one of ``markers`` appears (case-insensitive) or timeout."""

        deadline = time.monotonic() + timeout
        lowered = tuple(m.lower() for m in markers)
        while not any(m in self._buffer.lower() for m in lowered):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            self._sock.settimeout(remaining)
            try:
                chunk = self._sock.recv(1024)
            except OSError:
                # Timeout or reset — either way the bounded read is over.
                break
            if not chunk:
                break
            self._buffer += self._strip(chunk)
        return self._buffer

    def send_line(self, text: str) -> None:
        self._sock.sendall(text.encode("utf-8", errors="replace") + b"\r\n")

    def _strip(self, data: bytes) -> str:
        reply: bytearray = bytearray()
        text: bytearray = bytearray()
        index, size = 0, len(data)
        while index < size:
            byte = data[index]
            if byte != _IAC:
                text.append(byte)
                index += 1
                continue
            if index + 1 >= size:
                break
            command = data[index + 1]
            if command == _SB:
                end = data.find(bytes((_IAC, _SE)), index)
                index = size if end == -1 else end + 2
                continue
            if command in (_WILL, _WONT, _DO, _DONT) and index + 2 < size:
                option = data[index + 2]
                if command == _WILL:
                    reply += bytes((_IAC, _DONT, option))
                elif command == _DO:
                    reply += bytes((_IAC, _WONT, option))
                index += 3
                continue
            index += 2
        if reply:
            with contextlib.suppress(OSError):
                self._sock.sendall(bytes(reply))
        return text.decode("utf-8", errors="replace")


def _telnet_login(host: str, port: int, username: str, password: str, timeout: float) -> bool:
    """Attempt one telnet login; True only when a shell prompt is observed.

    Conservative by construction: a failure marker anywhere in the reply
    wins over a prompt-looking string, and no prompt means "not accepted".
    """

    with socket.create_connection((host, port), timeout=timeout) as sock:
        sock.settimeout(timeout)
        stream = _TelnetStream(sock)
        prompt = stream.read_until(("login:", "username:", "password:"), timeout)
        if "password:" in prompt.lower():
            # Some devices ask for the password with no username step.
            stream.send_line(password)
        else:
            stream.send_line(username)
            stream.read_until(("password:",), timeout)
            stream.send_line(password)
        reply = stream.read_until((*_FAILURE_MARKERS, ">", "#", "$"), timeout)
    return _login_accepted(reply)


def _login_accepted(reply: str) -> bool:
    """Interpret the post-password window; refusal always beats a prompt."""

    lowered = reply.lower()
    if any(marker in lowered for marker in _FAILURE_MARKERS):
        return False
    return bool(_SUCCESS_PROMPT.search(reply))


__all__ = [
    "DEFAULT_ATTEMPT_DELAY_SECONDS",
    "DEFAULT_ATTEMPT_TIMEOUT_SECONDS",
    "DEFAULT_CREDENTIALS",
    "HARD_CREDENTIAL_ATTEMPT_CAP",
    "MAX_CREDENTIAL_ATTEMPTS",
    "CredentialAttempt",
    "probe_default_credentials",
]

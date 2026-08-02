"""Small, injectable command boundary for platform Wi-Fi adapters."""

from __future__ import annotations

import subprocess
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from portallens.wifi.errors import (
    WifiAdapterUnavailable,
    WifiOperationCancelled,
    WifiOperationTimeout,
    WifiPermissionError,
)
from portallens.wifi.models import CancellationToken


@dataclass(frozen=True)
class CommandResult:
    """The allow-listed output needed by a platform parser."""

    stdout: str
    stderr: str = ""
    returncode: int = 0


class CommandRunner(Protocol):
    """Injectable command runner used by adapters and fixture tests."""

    def run(
        self,
        args: Sequence[str],
        *,
        timeout_seconds: float,
        cancel: CancellationToken | None = None,
    ) -> CommandResult:
        """Run one bounded command without shell interpolation."""
        ...


class SubprocessCommandRunner:
    """Run a platform command without a shell or credential-bearing input."""

    def run(
        self,
        args: Sequence[str],
        *,
        timeout_seconds: float,
        cancel: CancellationToken | None = None,
    ) -> CommandResult:
        if not args:
            raise ValueError("command must not be empty")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if cancel is not None:
            cancel.raise_if_cancelled()
        try:
            process = subprocess.Popen(
                list(args),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                shell=False,
            )
        except FileNotFoundError as exc:
            raise WifiAdapterUnavailable(f"required Wi-Fi command is unavailable: {args[0]}") from exc
        except PermissionError as exc:
            raise WifiPermissionError(f"permission denied while running Wi-Fi command: {args[0]}") from exc

        deadline = time.monotonic() + timeout_seconds
        while process.poll() is None:
            if cancel is not None and cancel.is_cancelled:
                process.kill()
                process.communicate()
                raise WifiOperationCancelled("Wi-Fi operation cancelled")
            if time.monotonic() >= deadline:
                process.kill()
                process.communicate()
                raise WifiOperationTimeout(f"Wi-Fi command timed out: {args[0]}")
            time.sleep(0.02)

        stdout, stderr = process.communicate()
        if cancel is not None:
            cancel.raise_if_cancelled()
        if process.returncode != 0:
            lowered_stderr = stderr.lower()
            if any(marker in lowered_stderr for marker in ("permission denied", "access denied", "not permitted")):
                raise WifiPermissionError(f"permission denied by Wi-Fi command: {args[0]}")
            raise WifiAdapterUnavailable(
                f"Wi-Fi command failed with status {process.returncode}: {args[0]}"
            )
        return CommandResult(stdout=stdout, stderr=stderr, returncode=process.returncode)


__all__ = ["CommandResult", "CommandRunner", "SubprocessCommandRunner"]

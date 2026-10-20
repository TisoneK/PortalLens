# Session-budget write path — design (ADR-27)

**Status:** proposed — design only. No code, no CLI verb, nothing reachable at runtime.
**Scope:** one mutation, on a gateway the operator administers, with credentials they supply.

## Why this exists

The assessment showed who really decides session length on `maz.wifi`: the router. A
30-minute KES 8 purchase ran for 2h25m, and the gateway renewed a 4-hour budget at
01:09:53 with no purchase, no portal request, and no click. The portal's role is to sell
and to display; the router's session state is what keeps a device online.

That makes two operator needs symmetrical:

- **cap** — a session is running longer than what was sold; end it or shorten it.
- **extend** — a session needs more time than the router granted; lengthen it.

PortalLens cannot do either today. It has no mutating call, and on this gateway no usable
admin channel either: Telnet 23 accepts connections but refused the published defaults,
and WebFig 8291 / API 8728 / API-SSL 8729 are filtered.

## Interface

```
portallens session cap   --host maz.wifi --mac 04:ED:33:76:D9:A0 --ip 10.111.78.164 \
                         --minutes 30 --credentials-file ~/.portallens/gw.cred [--apply]
portallens session extend --host maz.wifi --mac 04:ED:33:76:D9:A0 --ip 10.111.78.164 \
                         --minutes 60 --credentials-file ~/.portallens/gw.cred [--apply]
portallens session show   --host maz.wifi --mac 04:ED:33:76:D9:A0 \
                         --credentials-file ~/.portallens/gw.cred
```

- `show` is read-only and useful on its own: it resolves the active session and prints its
  budget without changing anything.
- `cap` and `extend` are dry runs unless `--apply` is present. `--authorized` is required
  for all three; without it the command exits before opening a socket (ADR-15).
- `--mac` is mandatory and must agree with `--ip` on the resolved session. There is no
  "all sessions" form and no wildcard.

## Transport

| Transport | Port | Use |
|---|---|---|
| RouterOS REST over HTTPS | 443 (or configured) | **preferred** — reuses the project's existing `httpx` dependency |
| API-SSL | 8729 | optional later; needs a binary API client, no stdlib-only path |
| Telnet | 23 | **refused** for authentication — cleartext password to an admin account |

Refusing Telnet is a deliberate asymmetry with ADR-26: reading a prompt to see whether a
default works is a bounded test; sending an operator's real admin password in clear text
is not something this tool should do, even to a network the operator owns.

## Credential handling

- Accepted as a file path only. Never a CLI argument (visible in process lists and shell
  history), never an inline value, never an env var echoed into logs.
- The file must live outside the repository or be covered by `.gitignore`; the command
  refuses to proceed if the path is tracked by git.
- The secret is read once, used for the request, and never written to evidence, the audit
  log, the report, or an exception message. Authentication failures are logged by status
  code and endpoint only.
- Secrets still live only under `memory/secrets/` for this project's own bookkeeping. A
  gateway password is the operator's, not the project's, and must not be committed.

## Sequence

```
1. resolve   POST/GET  /rest/ip/hotspot/active        -> match MAC + IP -> session id, uptime, limit
2. compute   local                                    -> current expiry, requested expiry, delta
3. print     local                                    -> resolved target, commands, effect, rollback
   --- dry run stops here; zero mutating calls ---
4. apply     POST      /rest/ip/hotspot/user/set      -> limit-uptime (the real lever)
             POST      /rest/ip/hotspot/active/remove -> force re-authorization under the new limit
5. verify    GET       /rest/ip/hotspot/active        -> re-read; confirm the session state changed
6. record    local                                    -> before/after evidence + audit entry (redacted)
```

RouterOS has no "add time" verb, so both operations resolve to the same two levers: change
the account's `limit-uptime`, and drop the active session so the gateway re-authorizes.
Which lever was used is recorded — an operator reading the log must be able to tell whether
traffic was interrupted.

## Dry-run output

```
Target     maz.wifi (10.111.0.1) - REST over HTTPS
Session    *3  04:ED:33:76:D9:A0  10.111.78.164
           uptime 1h12m   limit 4h   expires 02:48:15
Action     cap --minutes 30
Would run  POST /rest/ip/hotspot/user/set     {".id":"*1","limit-uptime":"1h42m"}
           POST /rest/ip/hotspot/active/remove {".id":"*3"}
Effect     session ends at 02:42:15 - the device drops to the portal, ~6m of access removed
Rollback   restore limit-uptime = 4h                    (--rollback after apply)
No changes made. Re-run with --apply to execute.
```

## Rails

| Rail | Rule |
|---|---|
| Single target | one MAC per invocation; MAC and IP must both match the resolved session |
| Extend bound | default 60 minutes, hard cap 240; `extend` above the cap is refused, not clamped |
| Cap bound | refuses below 1 minute; refuses to cap a session already expired |
| Confirmation | `--apply` only; no interactive prompt to auto-accept |
| No bulk / no schedule | no wildcard MACs, no loop over sessions, no cron-like mode |
| Rollback | prior `limit-uptime` recorded; `--rollback` restores it and records that it did |
| No credential discovery | this path never guesses, retries, or sprays; one attempt, then stop |
| Audit | commands, endpoint, status codes, before/after budget, operator-supplied reason string |

## Failure modes

| Failure | Behaviour |
|---|---|
| 401 / auth rejected | record negative evidence, exit non-zero, **no retry** |
| REST disabled or unreachable | explain which endpoints were tried, suggest API-SSL, change nothing |
| Session not found (MAC/IP mismatch) | list the active sessions' MACs (no IPs of other clients), exit |
| Read succeeded, write failed | report the partial state explicitly; do not claim success |
| Write succeeded, verify failed | report as unverified with the command that was sent; do not retry blindly |
| Rollback unavailable | the prior limit is printed; operator restores manually |

## Testing

- Injected transport recording every call; the dry run asserts **zero** mutating calls.
- Apply asserts exactly the two writes plus one verify read.
- Cap below 1 minute, extend above 240, missing `--authorized`, tracked credential file,
  MAC/IP mismatch, 401, partial apply, and rollback each get a test.
- No test talks to a real gateway. A recorded fixture of `/rest/ip/hotspot/active` output
  drives the parser.

## Docs the implementation must touch

- `README.md` — "read-only" becomes "read-only by default; one gated mutation".
- `docs/TUTORIAL.md` — a section on `session show|cap|extend`, with the dry run first.
- `docs/ARCHITECTURE.md` — the mutation class, next to NetAudit.
- `CHANGELOG.md` — plain-language entry when it ships.

## Open questions

1. RouterOS version on this gateway, and whether REST is enabled on 443 (443 answers, but
   that may be the hotspot portal rather than REST).
2. Cap by session or by account — the cheap package's over-service is account-shaped, so
   a session cap fixes one session and not the pattern.
3. Whether "cap" should shorten `limit-uptime` (graceful) or remove the session (immediate
   disconnect). The design supports both; the default should be chosen by the operator.
4. Whether the operator wants a supervised interactive mode rather than one-shot flags.

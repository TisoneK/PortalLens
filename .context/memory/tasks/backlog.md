---
- [ ] **Wi-Fi platform adapters** (added 2026-08-02 by Buffy / Session 17) — implement deterministic, capability-gated desktop adapters behind the `portallens.wifi.WifiAdapter` contract: Windows Native WLAN/API or structured `netsh` fallback, macOS CoreWLAN-backed discovery/status, and Linux NetworkManager `nmcli` discovery/status. Use captured localized/platform fixtures for parser tests; do not accept credentials or add packet-level operations.

- [ ] **Wi-Fi TUI picker and live session orchestration** (added 2026-08-02 by Buffy / Session 17) — extend the live console with network list/rescan/select/connect/stop/switch controls, cancellation tokens, session-generation guards, and serialized live event delivery. Keep acquisition and platform logic out of `tui/`; persist network/connection context through the core investigation aggregate.

- [ ] **Captive-portal detection for live Wi-Fi sessions** (added 2026-08-02 by Buffy / Session 17) — add standards-aware RFC 8908/8910 metadata handling plus platform connectivity-probe profiles. Capture bounded redirect/status evidence and feed the existing passive captive-Wi-Fi analyzer; do not open a browser or automatically invoke bypass probes.

- [ ] **Wi-Fi live-event persistence** (added 2026-08-02 by Buffy / Session 17) — append a SQLite migration and serialized event path for scan snapshots, connection states, portal detection, cancellation, target switching, and worker failures. Redact credentials, tokens, raw command output, and sensitive URL values before persistence.

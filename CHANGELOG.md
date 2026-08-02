# Changelog

All notable changes to PortalLens are listed here in plain language.

## Unreleased

### Added

- **A new starting screen.** Running `portallens` now opens the main setup screen instead of printing help. Users can choose investigation options, scan for nearby Wi-Fi networks, select a target, and press **Start investigation**. Wi-Fi-only sessions are clearly labelled as read-only host monitoring.
- **Clear investigation choices.** The setup screen explains passive mode, authorized active checks, automatic follow-up steps, and monitoring before the session starts.
- **Read-only Wi-Fi target monitoring.** After selecting a network and enabling monitoring, PortalLens can show the connection status reported by your computer without entering credentials, changing the Wi-Fi connection, opening a browser, or submitting anything to the network.
- **A more direct live investigation flow.** A portal URL entered in the setup screen opens the existing live console, where users can follow activity, review evidence, save the investigation, export a report, and run follow-up steps.
- **Captive-portal detection.** PortalLens can read common connectivity checks and record response or redirect information without automatically opening a browser or following the redirect.
- **Wi-Fi discovery across desktop systems.** PortalLens can list nearby networks using the operating system's available Wi-Fi tools on Windows, macOS, and Linux.

### Changed

- **The README is now a user guide.** It focuses on installing PortalLens, starting an investigation, and understanding the results. Technical development history belongs in the project records instead.
- **The public changelog is now plain language.** It describes changes in terms of what users can do, without internal architecture labels or development-session notes.

### Existing capabilities

- Portal URL analysis with platform identification and confidence levels.
- Reports that distinguish observed facts, supported conclusions, and possibilities that need more evidence.
- Saved investigations with an activity history.
- Human-readable reports and machine-readable report output.
- Optional checks that require the user to confirm authorization.

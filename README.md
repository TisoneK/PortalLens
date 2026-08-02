# PortalLens

PortalLens helps you understand captive Wi-Fi portals and keep a clear record of an investigation. It shows what was observed, what the evidence suggests, and what still needs checking.

## Install

PortalLens requires Python 3.10 or newer.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[tui]"
```

On Windows, activate the environment with `.venv\Scripts\activate`.

## Start here

Run PortalLens without arguments:

```bash
portallens
```

This opens the main setup screen. From there you can:

1. Choose whether the investigation is passive or authorized for active checks.
2. Turn on recommended follow-up steps or continuous monitoring.
3. Paste a captive-portal URL, or scan and select a nearby Wi-Fi network.
4. Review the choices and press **Start investigation**. For a Wi-Fi-only target, enable **Enable continuous monitoring**; this starts read-only monitoring. Automatic connection and portal detection are not available yet.

The setup screen is designed to be the normal PortalLens experience. It keeps the important choices visible, explains what each option does, and shows live activity while the session runs.

Wi-Fi discovery is read-only in the current release. Selecting a network does not enter a password, change the computer's connection, open a browser, or submit anything to the network. The operating system remains responsible for connecting to Wi-Fi. The Wi-Fi-only setup path currently shows status reported by your computer; it does not yet turn a selected network into a portal investigation automatically.

## What happens during an investigation?

For a portal URL, PortalLens opens the live investigation console. The console shows:

- the target and current mode;
- detected portal platforms;
- observations and confidence levels;
- relationships between the portal and other services;
- captured evidence;
- unanswered questions and suggested next steps;
- a live activity feed.

You can save the investigation, export a Markdown report, run an authorized follow-up step, or stop monitoring at any time.

## Direct commands

The setup screen is recommended, but the command line remains available for scripts and repeatable workflows:

| Command | Purpose |
|---|---|
| `portallens` | Open the main setup screen |
| `portallens analyze URL...` | Produce a report and exit |
| `portallens tui URL...` | Open the live console for known URL(s) |
| `portallens investigate URL...` | Analyze and save an investigation |
| `portallens investigations` | List saved investigations |
| `portallens show ID` | View a saved report |
| `portallens show ID --audit` | View the investigation activity history |
| `portallens step ID NAME --authorized` | Run an authorized follow-up step |
| `portallens wifi` | Open the read-only Wi-Fi picker |

A URL passed directly to `portallens` is still supported for scripts and continues to produce the traditional report:

```bash
portallens "http://portal.example/login"
```

## Passive by default

PortalLens does not access a target unless you explicitly enable active checks. The setup screen makes this an option; the command line uses `--authorized`.

```bash
portallens analyze --authorized "https://portal.example/login"
```

Only use active checks on networks and portals you own or are explicitly permitted to assess. Authorization is your responsibility; the software cannot verify it for you.

## Captive-portal detection

PortalLens can inspect standard connectivity checks used by Windows, Apple devices, Android, GNOME, and Firefox-style environments. It records response and redirect information without automatically following redirects. It can also read an RFC 8908 Captive Portal API response when the endpoint was supplied by the host system.

The current Wi-Fi flow does not open a browser, submit credentials, or automatically try to get around a portal. It records evidence for the investigation instead.

## Reports

Reports separate:

- **Observed facts** — information directly present in the supplied evidence.
- **Inferences** — conclusions supported by one or more signals.
- **Hypotheses** — possibilities that need more evidence.

Every conclusion has a confidence level. A low-confidence possibility is shown as a possibility, not presented as a fact.

Reports can be written as Markdown or SARIF:

```bash
portallens analyze "http://portal.example/login" --output report.md
portallens analyze "http://portal.example/login" --format sarif
```

## Learn more

See [`docs/TUTORIAL.md`](docs/TUTORIAL.md) for a full walkthrough, command reference, saved investigations, reports, and the live console.

## Responsible use

PortalLens is intended for network operators, auditors, and researchers working on systems they own or have permission to assess. Do not run active checks against networks without permission.

## License

MIT — see [`LICENSE`](LICENSE).

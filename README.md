# Claude Code workspace for Home Assistant + Node-RED

## Setup

Run the init script to configure your environment and verify the connection:

```bash
bash init.sh
```

This will prompt you for your Home Assistant URL and long-lived access token, save them to `.env`, set up the `mynodered/` submodule for flow tracking, and verify the MCP connection.

## Downloading flows

Before starting a Claude Code session to work on automations, download the latest flows from Home Assistant:

```bash
bash download-flows.sh
```

This downloads the current Node-RED flows into `mynodered/nodered.json` and commits them to the submodule, so you have a clean baseline to work from.

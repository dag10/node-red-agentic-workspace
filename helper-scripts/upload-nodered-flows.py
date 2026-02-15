"""Upload Node-RED flows to Home Assistant and deploy them.

Uses the HA websocket API to access the Supervisor (same as download), then
POSTs the flows via the ingress HTTP proxy to replace all current flows.

Usage: Called by upload-nodered-flows.sh, not directly.
"""

import asyncio
import json
import sys
import urllib.request

import websockets

ADDON_SLUG = "a0d7b954_nodered"


async def upload_flows(ha_url: str, token: str, input_file: str) -> None:
    ws_url = ha_url.replace("http://", "ws://").replace("https://", "wss://")
    ws_url += "/api/websocket"

    msg_id = 0

    def next_id() -> int:
        nonlocal msg_id
        msg_id += 1
        return msg_id

    with open(input_file) as f:
        flows = json.load(f)

    if not isinstance(flows, list):
        print("Error: flows file should contain a JSON array.", file=sys.stderr)
        sys.exit(1)

    async with websockets.connect(ws_url) as ws:
        # Authenticate
        msg = json.loads(await ws.recv())
        if msg["type"] != "auth_required":
            print(f"Unexpected initial message: {msg['type']}", file=sys.stderr)
            sys.exit(1)

        await ws.send(json.dumps({"type": "auth", "access_token": token}))
        msg = json.loads(await ws.recv())
        if msg["type"] != "auth_ok":
            print("Authentication failed. Check your HOMEASSISTANT_TOKEN.", file=sys.stderr)
            sys.exit(1)

        # Get Node-RED addon info
        req_id = next_id()
        await ws.send(json.dumps({
            "id": req_id,
            "type": "supervisor/api",
            "endpoint": f"/addons/{ADDON_SLUG}/info",
            "method": "get",
        }))
        msg = json.loads(await ws.recv())
        if not msg.get("success"):
            error = msg.get("error", {}).get("message", "unknown error")
            print(f"Failed to get addon info: {error}", file=sys.stderr)
            print("Is the Node-RED add-on installed?", file=sys.stderr)
            sys.exit(1)

        ingress_url = msg["result"]["ingress_url"]
        state = msg["result"].get("state", "unknown")
        if state != "started":
            print(f"Warning: Node-RED add-on state is '{state}', not 'started'.", file=sys.stderr)

        # Create an ingress session
        req_id = next_id()
        await ws.send(json.dumps({
            "id": req_id,
            "type": "supervisor/api",
            "endpoint": "/ingress/session",
            "method": "post",
        }))
        msg = json.loads(await ws.recv())
        if not msg.get("success"):
            error = msg.get("error", {}).get("message", "unknown error")
            print(f"Failed to create ingress session: {error}", file=sys.stderr)
            sys.exit(1)

        session = msg["result"]["session"]

    # Upload flows through the ingress proxy (full deploy replaces all nodes)
    flows_url = f"{ha_url}{ingress_url}flows"
    body = json.dumps({"flows": flows}).encode("utf-8")
    req = urllib.request.Request(
        flows_url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Node-RED-API-Version": "v2",
            "Node-RED-Deployment-Type": "full",
            "Cookie": f"ingress_session={session}",
        },
    )

    try:
        resp = urllib.request.urlopen(req)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace") if e.fp else ""
        print(f"Failed to upload flows (HTTP {e.code}): {e.reason}", file=sys.stderr)
        if detail:
            print(detail, file=sys.stderr)
        sys.exit(1)

    print(f"Uploaded {len(flows)} flow entries and triggered full deploy.")


def main() -> None:
    if len(sys.argv) != 4:
        print("Usage: upload-nodered-flows.py <ha_url> <token> <input_file>", file=sys.stderr)
        sys.exit(1)

    ha_url = sys.argv[1].rstrip("/")
    token = sys.argv[2]
    input_file = sys.argv[3]

    asyncio.run(upload_flows(ha_url, token, input_file))


if __name__ == "__main__":
    main()

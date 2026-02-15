"""Download the full Node-RED flow export from Home Assistant.

Uses the HA websocket API to access the Supervisor, which lets us get the
Node-RED ingress URL and create an ingress session. Then fetches flows via
the ingress HTTP proxy using that session cookie.

Usage: Called by download-nodered-flows.sh, not directly.
"""

import asyncio
import json
import sys
import urllib.request

import websockets

ADDON_SLUG = "a0d7b954_nodered"


def _sort_keys_recursive(obj):
    if isinstance(obj, dict):
        return {k: _sort_keys_recursive(v) for k, v in sorted(obj.items())}
    if isinstance(obj, list):
        return [_sort_keys_recursive(item) for item in obj]
    return obj


def normalize_json(data):
    """Sort keys alphabetically and, for arrays of objects with ids, sort by id."""
    data = _sort_keys_recursive(data)
    if isinstance(data, list) and all(isinstance(e, dict) and "id" in e for e in data):
        data.sort(key=lambda e: e["id"])
    return data


async def download_flows(ha_url: str, token: str, output_file: str) -> None:
    ws_url = ha_url.replace("http://", "ws://").replace("https://", "wss://")
    ws_url += "/api/websocket"

    msg_id = 0

    def next_id() -> int:
        nonlocal msg_id
        msg_id += 1
        return msg_id

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

        # Get Node-RED addon info to find the ingress URL
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

    # Fetch flows through the ingress proxy
    flows_url = f"{ha_url}{ingress_url}flows"
    req = urllib.request.Request(
        flows_url,
        headers={
            "Accept": "application/json",
            "Node-RED-API-Version": "v2",
            "Cookie": f"ingress_session={session}",
        },
    )

    try:
        resp = urllib.request.urlopen(req)
    except urllib.error.HTTPError as e:
        print(f"Failed to fetch flows (HTTP {e.code}): {e.reason}", file=sys.stderr)
        sys.exit(1)

    data = json.loads(resp.read())

    # v2 API wraps flows in {"rev": "...", "flows": [...]}
    if isinstance(data, dict) and "flows" in data:
        flows = data["flows"]
    else:
        flows = data

    flows = normalize_json(flows)

    with open(output_file, "w") as f:
        json.dump(flows, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"Downloaded {len(flows)} flow entries to {output_file}")


def main() -> None:
    if len(sys.argv) != 4:
        print("Usage: download-nodered-flows.py <ha_url> <token> <output_file>", file=sys.stderr)
        sys.exit(1)

    ha_url = sys.argv[1].rstrip("/")
    token = sys.argv[2]
    output_file = sys.argv[3]

    asyncio.run(download_flows(ha_url, token, output_file))


if __name__ == "__main__":
    main()

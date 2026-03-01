"""Estimate rendered dimensions of Node-RED nodes and groups.

Replicates the exact sizing logic from Node-RED's editor (view.js)
to produce pixel-accurate width/height estimates for nodes, and
bounding-box dimensions for groups.

Usage: Called by estimate-node-size.sh, not directly.
"""

import importlib.util
import json
import math
import os
import sys
from collections import defaultdict

# Import shared utilities from query tool.
_dir = os.path.dirname(os.path.abspath(__file__))

_spec = importlib.util.spec_from_file_location(
    "_query", os.path.join(_dir, "query-nodered-flows.py"),
)
_query = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_query)
build_index = _query.build_index
collect_group_node_ids = _query.collect_group_node_ids

# ---------------------------------------------------------------------------
# Font measurement
# ---------------------------------------------------------------------------

# Measured from Helvetica Neue at 14px using Pillow getlength().
# Covers ASCII 32-126 plus common Node-RED unicode characters.
CHAR_WIDTHS_14PX = {
    ' ': 3.890625, '!': 3.625, '"': 5.96875, '#': 7.78125, '$': 7.78125,
    '%': 14.0, '&': 8.8125, "'": 3.890625, '(': 3.625, ')': 3.625,
    '*': 4.921875, '+': 8.40625, ',': 3.890625, '-': 5.453125, '.': 3.890625,
    '/': 4.65625, '0': 7.78125, '1': 7.78125, '2': 7.78125, '3': 7.78125,
    '4': 7.78125, '5': 7.78125, '6': 7.78125, '7': 7.78125, '8': 7.78125,
    '9': 7.78125, ':': 3.890625, ';': 3.890625, '<': 8.40625, '=': 8.40625,
    '>': 8.40625, '?': 7.78125, '@': 11.203125, 'A': 9.078125, 'B': 9.59375,
    'C': 10.109375, 'D': 9.859375, 'E': 8.546875, 'F': 8.03125,
    'G': 10.625, 'H': 10.109375, 'I': 3.625, 'J': 7.265625, 'K': 9.34375,
    'L': 7.78125, 'M': 12.1875, 'N': 10.109375, 'O': 10.640625,
    'P': 9.078125, 'Q': 10.640625, 'R': 9.59375, 'S': 9.078125,
    'T': 8.03125, 'U': 10.109375, 'V': 8.546875, 'W': 12.96875,
    'X': 8.546875, 'Y': 9.078125, 'Z': 8.546875, '[': 3.625,
    '\\': 4.65625, ']': 3.625, '^': 8.40625, '_': 7.0, '`': 3.109375,
    'a': 7.515625, 'b': 8.296875, 'c': 7.515625, 'd': 8.296875,
    'e': 7.515625, 'f': 4.140625, 'g': 8.03125, 'h': 7.78125,
    'i': 3.109375, 'j': 3.109375, 'k': 7.265625, 'l': 3.109375,
    'm': 11.9375, 'n': 7.78125, 'o': 8.03125, 'p': 8.296875,
    'q': 8.296875, 'r': 4.65625, 's': 7.0, 't': 4.40625, 'u': 7.78125,
    'v': 7.0, 'w': 10.609375, 'x': 7.25, 'y': 7.0, 'z': 6.71875,
    '{': 4.65625, '|': 3.109375, '}': 4.65625, '~': 8.40625,
    '\u21bb': 7.0,     # ↻ clockwise arrow (inject repeat suffix)
    '\u00b9': 4.65625, # ¹ superscript 1 (inject once suffix)
    '\u2026': 14.0,    # … ellipsis
    '\u2192': 7.0,     # → right arrow
    '\u2190': 7.0,     # ← left arrow
    '\u2193': 7.0,     # ↓ down arrow
    '\u2191': 7.0,     # ↑ up arrow
    '\t': 3.890625,    # tab (used in inject suffix)
}
DEFAULT_CHAR_WIDTH = 7.5

# Try to load Pillow for more accurate font measurement
_pillow_font = None
try:
    from PIL import ImageFont
    # macOS system font path
    _font_path = "/System/Library/Fonts/HelveticaNeue.ttc"
    if os.path.exists(_font_path):
        _pillow_font = ImageFont.truetype(_font_path, 14)
except ImportError:
    pass


def measure_text_width(text):
    """Measure text width in pixels at 14px Helvetica Neue."""
    if not text:
        return 0
    if _pillow_font:
        return _pillow_font.getlength(text)
    return sum(CHAR_WIDTHS_14PX.get(c, DEFAULT_CHAR_WIDTH) for c in text)


# ---------------------------------------------------------------------------
# Node type knowledge
# ---------------------------------------------------------------------------

NODE_WIDTH_MIN = 100
NODE_HEIGHT = 30

# Types with inputs=0 in their node definition.
# NOTE: This must stay in sync with _ENTRY_POINT_TYPES in query-nodered-flows.py.
NO_INPUT_TYPES = {
    "inject", "link in", "server-events", "server-state-changed",
    "ha-time", "poll-state", "trigger-state", "cronplus",
    "complete", "catch", "status", "ha-webhook",
}

# Button nodes for group bounding box calculations.
BUTTON_LEFT_TYPES = {"inject"}
BUTTON_RIGHT_TYPES = {"debug"}
BUTTON_EXTRA = 20

# Group padding from node edges to group boundary (from Node-RED group.js).
GROUP_NODE_PADDING = 25


def _get_subflow_defs(data):
    """Build a dict of subflow definition ID -> subflow node."""
    return {n["id"]: n for n in data if n.get("type") == "subflow"}


def has_inputs(node, subflow_defs):
    """Whether this node type has input ports."""
    ntype = node.get("type", "")
    if ntype in NO_INPUT_TYPES:
        return False
    if ntype.startswith("subflow:"):
        sf_id = ntype[8:]
        sf_def = subflow_defs.get(sf_id)
        if sf_def:
            return len(sf_def.get("in", [])) > 0
        return True
    return True


def is_label_hidden(node):
    """Whether the node's label is hidden (link in/out with no explicit l=true)."""
    ntype = node.get("type", "")
    is_link = ntype in ("link in", "link out")
    if "l" in node:
        return not node["l"]
    return is_link


def get_node_label(node, subflow_defs):
    """Determine the label text that Node-RED would display for a node."""
    ntype = node.get("type", "")
    name = node.get("name", "")

    if ntype == "junction":
        return ""

    if ntype in ("tab", "group"):
        return name or node.get("label", "")

    # Subflow instances
    if ntype.startswith("subflow:"):
        sf_id = ntype[8:]
        sf_def = subflow_defs.get(sf_id)
        if sf_def:
            return name or sf_def.get("name", ntype)
        return name or ntype

    # Inject nodes have a suffix indicating repeat/once behavior
    if ntype == "inject":
        suffix = ""
        if node.get("once"):
            suffix = " \u00b9"
        if (node.get("repeat") and node.get("repeat") != "0") or node.get("crontab"):
            suffix = "\t\u21bb"
        return (name or "inject") + suffix

    # Debug nodes show property path when unnamed
    if ntype == "debug":
        if name:
            return name
        target_type = node.get("targetType", "msg")
        if target_type == "msg":
            prop = node.get("property", "payload")
            return "msg." + prop
        return "debug"

    # HA nodes with entity-specific fallbacks
    if ntype == "api-call-service":
        return name or "API"
    if ntype == "api-current-state":
        return name or ("current_state: " + node.get("entity_id", ""))
    if ntype in ("server-state-changed", "trigger-state"):
        if not name:
            entities = node.get("entities", {})
            entity_ids = []
            for _key, ids in entities.items():
                if isinstance(ids, list):
                    entity_ids.extend(ids)
            if entity_ids:
                label = ", ".join(entity_ids[:3])
                if len(entity_ids) > 3:
                    label += "..."
                return label
            entity_id = node.get("entity_id", "")
            return entity_id or ntype
        return name
    if ntype == "poll-state":
        entity = node.get("entity_id", "")
        return name or ("poll state: " + entity)
    if ntype == "ha-time":
        entity = node.get("entityId", "")
        prop = node.get("property", "state")
        return name or (entity + "." + prop if entity else "time")

    return name or ntype


# ---------------------------------------------------------------------------
# Dimension calculation
# ---------------------------------------------------------------------------

def estimate_node_size(node, subflow_defs):
    """Return (width, height) in pixels for a node."""
    ntype = node.get("type", "")

    if ntype == "junction":
        return 10, 10

    outputs = node.get("outputs", len(node.get("wires", [])))

    if is_label_hidden(node):
        w = NODE_HEIGHT  # 30
        h = max(NODE_HEIGHT, outputs * 15)
        return w, h

    label = get_node_label(node, subflow_defs)

    # Handle multi-line labels (Node-RED splits on literal "\n " in the label text)
    lines = label.split("\n") if label else [""]
    text_width = max(measure_text_width(line) for line in lines) if lines else 0
    num_lines = len(lines)

    # Width: max(100, round up to nearest 20 of (textWidth + 50 + inputPortExtra))
    inputs_extra = 7 if has_inputs(node, subflow_defs) else 0
    w = max(NODE_WIDTH_MIN, 20 * math.ceil((text_width + 50 + inputs_extra) / 20))

    # Height: max(6 + 24 * lineCount, outputs * 15, 30)
    h = max(6 + 24 * num_lines, outputs * 15, 30)

    return w, h


def estimate_group_size(group, data, idx, subflow_defs):
    """Return (width, height) for a group, calculated from member node positions and sizes."""
    member_ids = collect_group_node_ids(group["id"], idx)

    min_x = float('inf')
    max_x = float('-inf')
    min_y = float('inf')
    max_y = float('-inf')

    for mid in member_ids:
        node = idx["by_id"].get(mid)
        if not node:
            continue
        ntype = node.get("type", "")
        if ntype in ("group", "comment"):
            continue

        x = node.get("x", 0)
        y = node.get("y", 0)
        w, h = estimate_node_size(node, subflow_defs)

        left_extra = BUTTON_EXTRA if ntype in BUTTON_LEFT_TYPES else 0
        right_extra = BUTTON_EXTRA if ntype in BUTTON_RIGHT_TYPES else 0

        left = x - w / 2 - GROUP_NODE_PADDING - left_extra
        right = x + w / 2 + GROUP_NODE_PADDING + right_extra
        top = y - h / 2 - GROUP_NODE_PADDING
        bottom = y + h / 2 + GROUP_NODE_PADDING

        min_x = min(min_x, left)
        max_x = max(max_x, right)
        min_y = min(min_y, top)
        max_y = max(max_y, bottom)

    if min_x == float('inf'):
        return 0, 0

    return int(max_x - min_x), int(max_y - min_y)


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

def die(msg):
    print(f"Error: {msg}", file=sys.stderr)
    sys.exit(1)


def cmd_node(data, idx, subflow_defs, args):
    if not args:
        die("node requires an <id> argument")
    nid = args[0]
    node = idx["by_id"].get(nid)
    if not node:
        die(f"node not found: {nid}")
    w, h = estimate_node_size(node, subflow_defs)
    print(f"{w} {h}")


def cmd_group(data, idx, subflow_defs, args):
    if not args:
        die("group requires an <id> argument")
    gid = args[0]
    group = idx["by_id"].get(gid)
    if not group or group.get("type") != "group":
        die(f"group not found: {gid}")
    w, h = estimate_group_size(group, data, idx, subflow_defs)
    print(f"{w} {h}")


def cmd_group_layout(data, idx, subflow_defs, args):
    if not args:
        die("group-layout requires an <id> argument")
    gid = args[0]
    group = idx["by_id"].get(gid)
    if not group or group.get("type") != "group":
        die(f"group-layout: group not found: {gid}")

    member_ids = collect_group_node_ids(gid, idx)
    nodes_out = {}

    for mid in member_ids:
        node = idx["by_id"].get(mid)
        if not node:
            continue
        ntype = node.get("type", "")
        if ntype in ("group", "comment"):
            continue
        w, h = estimate_node_size(node, subflow_defs)
        entry = {"w": w, "h": h}
        if ntype in BUTTON_LEFT_TYPES:
            entry["has_button"] = "left"
        elif ntype in BUTTON_RIGHT_TYPES:
            entry["has_button"] = "right"
        else:
            entry["has_button"] = None
        nodes_out[mid] = entry

    gw, gh = estimate_group_size(group, data, idx, subflow_defs)
    result = {
        "group": {"id": gid, "w": gw, "h": gh},
        "nodes": nodes_out,
    }
    print(json.dumps(result, indent=2))


def cmd_batch(data, idx, subflow_defs, args):
    raw = sys.stdin.read()
    try:
        ids = json.loads(raw)
    except json.JSONDecodeError as e:
        die(f"invalid JSON on stdin: {e}")
    if not isinstance(ids, list):
        die("batch expects a JSON array of IDs on stdin")

    result = {}
    for nid in ids:
        node = idx["by_id"].get(nid)
        if not node:
            continue
        ntype = node.get("type", "")
        if ntype == "group":
            w, h = estimate_group_size(node, data, idx, subflow_defs)
        else:
            w, h = estimate_node_size(node, subflow_defs)
        entry = {"w": w, "h": h}
        if ntype in BUTTON_LEFT_TYPES:
            entry["has_button"] = "left"
        elif ntype in BUTTON_RIGHT_TYPES:
            entry["has_button"] = "right"
        result[nid] = entry
    print(json.dumps(result, indent=2))


# ---------------------------------------------------------------------------
# Overlap detection
# ---------------------------------------------------------------------------

# Types that don't have a meaningful rendered bbox for overlap checking.
_SKIP_OVERLAP_TYPES = {"tab", "subflow", "group", "comment"}


def _node_bbox(node, subflow_defs):
    """Return (left, top, right, bottom, w, h) for a node, or None if not spatial."""
    ntype = node.get("type", "")
    if ntype in _SKIP_OVERLAP_TYPES:
        return None
    x = node.get("x")
    y = node.get("y")
    if x is None or y is None:
        return None
    w, h = estimate_node_size(node, subflow_defs)
    return (x - w / 2, y - h / 2, x + w / 2, y + h / 2, w, h)


def cmd_overlaps(data, idx, subflow_defs, args):
    """Find pairs of nodes whose rendered bounding boxes overlap or are too close."""
    gap = 0
    flow_filter = None
    group_filter = None
    json_output = False
    exit_code_mode = False

    i = 0
    while i < len(args):
        if args[i] == "--gap" and i + 1 < len(args):
            try:
                gap = float(args[i + 1])
            except ValueError:
                die(f"invalid gap: {args[i + 1]}")
            i += 2
        elif args[i] == "--flow" and i + 1 < len(args):
            flow_filter = args[i + 1]
            i += 2
        elif args[i] == "--group" and i + 1 < len(args):
            group_filter = args[i + 1]
            i += 2
        elif args[i] == "--json":
            json_output = True
            i += 1
        elif args[i] == "--exit-code":
            exit_code_mode = True
            i += 1
        else:
            die(f"unknown overlaps argument: {args[i]}")

    # Collect candidate nodes.
    if group_filter:
        gnode = idx["by_id"].get(group_filter)
        if not gnode or gnode.get("type") != "group":
            die(f"group not found: {group_filter}")
        member_ids = collect_group_node_ids(group_filter, idx)
        candidates = [idx["by_id"][mid] for mid in member_ids if mid in idx["by_id"]]
    elif flow_filter:
        candidates = idx["by_z"].get(flow_filter, [])
    else:
        candidates = list(idx["by_id"].values())

    # Compute bboxes, grouped by flow.
    half_gap = gap / 2
    by_z = defaultdict(list)
    for node in candidates:
        bb = _node_bbox(node, subflow_defs)
        if bb is None:
            continue
        left, top, right, bottom, w, h = bb
        # Expand bbox by half_gap for gap checking.
        entry = (node, w, h, left - half_gap, top - half_gap,
                 right + half_gap, bottom + half_gap,
                 left, top, right, bottom)  # actual edges (without gap)
        by_z[node.get("z", "")].append(entry)

    # Find overlapping pairs.
    pairs = []
    for z, entries in by_z.items():
        entries.sort(key=lambda e: e[3])  # sort by expanded left edge
        for i in range(len(entries)):
            n1, w1, h1, el1, et1, er1, eb1, al1, at1, ar1, ab1 = entries[i]
            for j in range(i + 1, len(entries)):
                n2, w2, h2, el2, et2, er2, eb2, al2, at2, ar2, ab2 = entries[j]
                if el2 > er1:
                    break  # sorted by left; no more possible overlaps with n1
                if et1 <= eb2 and eb1 >= et2:
                    # Bboxes overlap (considering gap). Compute actual gaps.
                    h_gap = max(al1, al2) - min(ar1, ar2)
                    v_gap = max(at1, at2) - min(ab1, ab2)
                    pairs.append((n1, w1, h1, n2, w2, h2, h_gap, v_gap))

    if not pairs:
        if json_output:
            print("[]")
        else:
            print("No overlaps found.")
        return

    # Sort by severity: most overlapping first (smallest gap sum).
    pairs.sort(key=lambda p: p[6] + p[7])

    if json_output:
        result = []
        for n1, w1, h1, n2, w2, h2, h_gap, v_gap in pairs:
            result.append({
                "node1": {
                    "id": n1["id"], "type": n1.get("type", ""),
                    "name": n1.get("name", ""),
                    "x": n1.get("x"), "y": n1.get("y"), "w": w1, "h": h1,
                    "g": n1.get("g", ""),
                },
                "node2": {
                    "id": n2["id"], "type": n2.get("type", ""),
                    "name": n2.get("name", ""),
                    "x": n2.get("x"), "y": n2.get("y"), "w": w2, "h": h2,
                    "g": n2.get("g", ""),
                },
                "h_gap": round(h_gap, 1),
                "v_gap": round(v_gap, 1),
            })
        print(json.dumps(result, indent=2))
    else:
        for n1, w1, h1, n2, w2, h2, h_gap, v_gap in pairs:
            id1 = n1["id"]
            type1 = n1.get("type", "")
            name1 = n1.get("name", "")
            x1, y1 = n1.get("x"), n1.get("y")
            id2 = n2["id"]
            type2 = n2.get("type", "")
            name2 = n2.get("name", "")
            x2, y2 = n2.get("x"), n2.get("y")
            print(f'{id1} {type1} "{name1}" {w1}x{h1} @{x1},{y1}'
                  f'  ↔  '
                  f'{id2} {type2} "{name2}" {w2}x{h2} @{x2},{y2}'
                  f'  h_gap:{h_gap:.0f} v_gap:{v_gap:.0f}')

    if exit_code_mode and pairs:
        sys.exit(1)


COMMANDS = {
    "node": cmd_node,
    "group": cmd_group,
    "group-layout": cmd_group_layout,
    "batch": cmd_batch,
    "overlaps": cmd_overlaps,
}

USAGE = """\
Usage: estimate-node-size.sh <flows.json> <command> [args...]

Commands:
  node <id>              Output: width height
  group <id>             Output: width height (bounding box of members + padding)
  group-layout <id>      Output: JSON with all member node sizes + group bbox
  batch                  Read JSON array of IDs from stdin, output JSON results
  overlaps [flags]       Find overlapping node pairs (uses actual rendered sizes)

overlaps flags:
  --gap PX       Minimum required edge-to-edge gap (default: 0 = actual overlaps only).
                 With --gap 30, finds any pair closer than 30px edge-to-edge.
  --flow ID      Only check nodes on this flow/tab.
  --group ID     Only check nodes in this group (recursive members).
  --json         Output as JSON array instead of one-liner-per-pair.
  --exit-code    Exit with code 1 when overlaps are found, 0 when clean.
                 Enables scripted gate checks (e.g., CI or pre-commit hooks).

  Output columns: id type "name" WxH @x,y  ↔  id type "name" WxH @x,y  h_gap:N v_gap:N
  Gaps: negative = overlap by that many px, positive = separated by that many px.
  Two nodes overlap visually when BOTH h_gap < 0 AND v_gap < 0.

Examples:
  bash helper-scripts/estimate-node-size.sh mynodered/nodered.json node abc123
  # Output: 160 30

  bash helper-scripts/estimate-node-size.sh mynodered/nodered.json group def456
  # Output: 800 400

  echo '["id1","id2"]' | bash helper-scripts/estimate-node-size.sh flows.json batch
  # Output: {"id1": {"w": 160, "h": 30}, ...}

  bash helper-scripts/estimate-node-size.sh mynodered/nodered.json overlaps --flow abc123
  # Find all overlapping node pairs on a specific flow

  bash helper-scripts/estimate-node-size.sh mynodered/nodered.json overlaps --gap 30 --group def456
  # Find nodes within a group that are closer than 30px edge-to-edge

  bash helper-scripts/estimate-node-size.sh mynodered/nodered.json overlaps --json
  # JSON output with full details for programmatic use"""


def main():
    if len(sys.argv) < 3:
        print(USAGE, file=sys.stderr)
        sys.exit(1)

    flows_file = sys.argv[1]
    command = sys.argv[2]
    cmd_args = sys.argv[3:]

    if command == "--help" or command == "-h":
        print(USAGE)
        sys.exit(0)

    if command not in COMMANDS:
        die(f"unknown command: {command}\n\n{USAGE}")

    with open(flows_file) as f:
        data = json.load(f)

    idx = build_index(data)
    subflow_defs = _get_subflow_defs(data)
    COMMANDS[command](data, idx, subflow_defs, cmd_args)


if __name__ == "__main__":
    main()

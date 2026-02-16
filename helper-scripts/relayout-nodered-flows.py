"""Auto-relayout Node-RED groups containing modified nodes using dagre.

Compares before/after flow JSON files, identifies groups whose member nodes
had wires/links/structural changes (not just position), runs dagre LR layout
on each affected group, and updates positions in-place.

Usage: Called by relayout-nodered-flows.sh, not directly.
"""

import argparse
import importlib.util
import json
import os
import subprocess
import sys
from collections import defaultdict

# Import shared utilities from sibling scripts.
_dir = os.path.dirname(os.path.abspath(__file__))

_spec = importlib.util.spec_from_file_location(
    "_query", os.path.join(_dir, "query-nodered-flows.py"),
)
_query = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_query)
build_index = _query.build_index
collect_group_node_ids = _query.collect_group_node_ids

DAGRE_SETTINGS = {
    "rankdir": "LR",
    "marginx": 10,
    "marginy": 10,
    "nodesep": 10,
    "ranksep": 30,
}

# Fields that only affect visual layout, not automation behavior.
COSMETIC_FIELDS = {"x", "y", "w", "h"}

DAGRE_DEPS_DIR = os.path.join(_dir, ".dagre-deps")
DAGRE_JS = os.path.join(_dir, "dagre-layout.js")

# Group label area and border padding (pixels).
GROUP_PAD_TOP = 35
GROUP_PAD_SIDE = 15
GROUP_PAD_BOTTOM = 15


# ---------------------------------------------------------------------------
# Change detection
# ---------------------------------------------------------------------------

def find_groups_needing_relayout(before_data, after_data, after_idx, verbose=False):
    """Return list of group IDs that need relayout.

    A group needs relayout if any member node was added, removed, or had
    wires/links changed. Position-only changes do NOT trigger relayout.
    Groups with < 2 layoutable member nodes are skipped.
    """
    before_by_id = {n["id"]: n for n in before_data if "id" in n}
    after_by_id = {n["id"]: n for n in after_data if "id" in n}

    # Collect all groups from after state.
    groups = [n for n in after_data if n.get("type") == "group"]
    result = []

    for group in groups:
        gid = group["id"]
        member_ids = collect_group_node_ids(gid, after_idx)
        layoutable = [
            mid for mid in member_ids
            if after_by_id.get(mid, {}).get("type") not in ("group", "comment")
        ]
        if len(layoutable) < 2:
            if verbose:
                name = group.get("name", "(unnamed)")
                print(f"  skip {name} id={gid}: <2 layoutable nodes", file=sys.stderr)
            continue

        needs = False
        reason = ""

        for mid in member_ids:
            after_node = after_by_id.get(mid)
            before_node = before_by_id.get(mid)

            if after_node and not before_node:
                needs = True
                reason = f"node {mid} added"
                break

            if not after_node:
                continue

            if before_node:
                # Check for non-cosmetic changes.
                changed = _diff_fields(before_node, after_node)
                if changed - COSMETIC_FIELDS:
                    needs = True
                    reason = f"node {mid} changed: {changed - COSMETIC_FIELDS}"
                    break

        if not needs:
            # Check for removed nodes that were in this group before.
            before_ids = set(before_by_id)
            after_ids = set(after_by_id)
            removed = before_ids - after_ids
            for rid in removed:
                before_node = before_by_id[rid]
                if before_node.get("g") == gid:
                    needs = True
                    reason = f"node {rid} removed from group"
                    break
                # Also check nested groups.
                if _was_in_group_recursive(rid, gid, before_by_id):
                    needs = True
                    reason = f"node {rid} removed from nested group"
                    break

        if needs:
            name = group.get("name", "(unnamed)")
            if verbose:
                print(f"  relayout {name} id={gid}: {reason}", file=sys.stderr)
            result.append(gid)
        elif verbose:
            name = group.get("name", "(unnamed)")
            print(f"  skip {name} id={gid}: no structural changes", file=sys.stderr)

    return result


def _was_in_group_recursive(node_id, target_group_id, by_id):
    """Check if a node was inside a group (possibly nested) in the before state."""
    node = by_id.get(node_id, {})
    g = node.get("g")
    if not g:
        return False
    if g == target_group_id:
        return True
    return _was_in_group_recursive(g, target_group_id, by_id)


def _diff_fields(before, after):
    """Return set of field names that differ between two node dicts."""
    all_keys = set(before) | set(after)
    return {k for k in all_keys if before.get(k) != after.get(k)}


# ---------------------------------------------------------------------------
# Node dimension estimation
# ---------------------------------------------------------------------------

def estimate_node_dimensions(node):
    """Heuristic width/height based on node type and label."""
    ntype = node.get("type", "")

    if ntype == "junction":
        return 10, 10

    if ntype in ("link in", "link out", "link call"):
        # Wider if label is shown (l: true).
        if node.get("l"):
            label = node.get("name", "")
            w = max(80, len(label) * 7 + 55)
            return w, 30
        return 30, 30

    label = node.get("name", "") or node.get("type", "")
    outputs = len(node.get("wires", []))
    width = max(100, len(label) * 7 + 55)
    height = max(30, outputs * 13 + 17)
    return width, height


# ---------------------------------------------------------------------------
# Dagre graph construction
# ---------------------------------------------------------------------------

def build_dagre_graph(group_id, after_idx):
    """Build dagre input for a group's member nodes.

    Includes intra-group wire edges and intra-group link-in/link-out edges.
    Cross-group edges are dropped (same as the Node-RED plugin).
    """
    by_id = after_idx["by_id"]
    member_ids = set(collect_group_node_ids(group_id, after_idx))

    # Filter to layoutable nodes (skip nested groups and comments).
    layoutable_ids = set()
    for mid in member_ids:
        node = by_id.get(mid, {})
        if node.get("type") not in ("group", "comment"):
            layoutable_ids.add(mid)

    nodes = []
    for mid in layoutable_ids:
        node = by_id[mid]
        w, h = estimate_node_dimensions(node)
        nodes.append({"id": mid, "width": w, "height": h})

    edges = []
    seen_edges = set()

    for mid in layoutable_ids:
        node = by_id[mid]

        # Wire edges.
        for targets in node.get("wires", []):
            for tid in targets:
                if tid in layoutable_ids and (mid, tid) not in seen_edges:
                    edges.append({"source": mid, "target": tid})
                    seen_edges.add((mid, tid))

        # Link-out -> link-in edges (within group).
        ntype = node.get("type", "")
        if ntype == "link out" and node.get("mode") == "link":
            for tid in node.get("links", []):
                if tid in layoutable_ids and (mid, tid) not in seen_edges:
                    edges.append({"source": mid, "target": tid})
                    seen_edges.add((mid, tid))
        elif ntype == "link call":
            for tid in node.get("links", []):
                if tid in layoutable_ids and (mid, tid) not in seen_edges:
                    edges.append({"source": mid, "target": tid})
                    seen_edges.add((mid, tid))

    return {"settings": DAGRE_SETTINGS, "nodes": nodes, "edges": edges}


# ---------------------------------------------------------------------------
# Dagre execution
# ---------------------------------------------------------------------------

def ensure_dagre_deps():
    """Install @dagrejs/dagre into .dagre-deps/ if not already present."""
    marker = os.path.join(DAGRE_DEPS_DIR, "node_modules", "@dagrejs", "dagre")
    if os.path.isdir(marker):
        return True

    print("Installing @dagrejs/dagre...", file=sys.stderr)
    try:
        subprocess.run(
            ["npm", "install", "--prefix", DAGRE_DEPS_DIR, "@dagrejs/dagre"],
            check=True,
            capture_output=True,
            text=True,
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"Warning: failed to install dagre: {e}", file=sys.stderr)
        return False


def run_dagre(graph):
    """Call dagre-layout.js via node subprocess."""
    env = os.environ.copy()
    env["NODE_PATH"] = os.path.join(DAGRE_DEPS_DIR, "node_modules")

    result = subprocess.run(
        ["node", DAGRE_JS],
        input=json.dumps(graph),
        capture_output=True,
        text=True,
        env=env,
    )
    if result.returncode != 0:
        print(f"Warning: dagre failed: {result.stderr}", file=sys.stderr)
        return None

    return json.loads(result.stdout)


# ---------------------------------------------------------------------------
# Position application
# ---------------------------------------------------------------------------

def apply_dagre_positions(group_id, dagre_result, after_idx):
    """Map dagre center coordinates to flow space, anchored to group top-left.

    Returns (old_y, old_bottom, new_bottom) for shift calculations.
    """
    by_id = after_idx["by_id"]
    group = by_id[group_id]

    # Current group position (anchor point).
    group_x = group.get("x", 0)
    group_y = group.get("y", 0)
    old_w = group.get("w", 0)
    old_h = group.get("h", 0)
    old_bottom = group_y + old_h

    dagre_nodes = dagre_result["nodes"]
    member_ids = collect_group_node_ids(group_id, after_idx)

    for mid in member_ids:
        node = by_id.get(mid, {})
        if node.get("type") in ("group", "comment"):
            continue
        if mid not in dagre_nodes:
            continue

        dn = dagre_nodes[mid]
        w, h = estimate_node_dimensions(node)

        # Dagre gives center coordinates. Convert to top-left and offset
        # relative to group position + padding.
        node["x"] = group_x + GROUP_PAD_SIDE + dn["x"] - w / 2
        node["y"] = group_y + GROUP_PAD_TOP + dn["y"] - h / 2

    # Update group dimensions.
    new_w = dagre_result["width"] + GROUP_PAD_SIDE * 2
    new_h = dagre_result["height"] + GROUP_PAD_TOP + GROUP_PAD_BOTTOM
    group["w"] = new_w
    group["h"] = new_h

    new_bottom = group_y + new_h
    return group_y, old_bottom, new_bottom


def shift_groups(relaid_info, after_data, after_idx):
    """Shift groups below resized groups to avoid overlap.

    relaid_info: list of (group_id, flow_id, old_y, old_bottom, new_bottom)
    sorted by old_y ascending.
    """
    by_id = after_idx["by_id"]

    # Process per flow tab.
    by_flow = defaultdict(list)
    for gid, flow_id, old_y, old_bottom, new_bottom in relaid_info:
        by_flow[flow_id].append((gid, old_y, old_bottom, new_bottom))

    for flow_id, changes in by_flow.items():
        # Sort by old_y so we process top-to-bottom, accumulating deltas.
        changes.sort(key=lambda c: c[1])
        cumulative_delta = 0

        for gid, old_y, old_bottom, new_bottom in changes:
            # Adjust this group's new_bottom for any prior shifts.
            adjusted_new_bottom = new_bottom + cumulative_delta
            delta = adjusted_new_bottom - (old_bottom + cumulative_delta)

            if delta == 0:
                continue

            # Shift all groups on this flow whose y >= old_bottom (the
            # original boundary), adjusted by cumulative shifts so far.
            threshold = old_bottom + cumulative_delta
            for node in after_data:
                if node.get("type") != "group":
                    continue
                if node.get("z") != flow_id:
                    continue
                if node["id"] == gid:
                    continue
                if node.get("y", 0) >= threshold:
                    node["y"] = node.get("y", 0) + delta
                    # Shift member nodes too.
                    for mid in collect_group_node_ids(node["id"], after_idx):
                        member = by_id.get(mid, {})
                        if "y" in member:
                            member["y"] = member["y"] + delta

            cumulative_delta += delta


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Auto-relayout Node-RED groups containing modified nodes",
    )
    parser.add_argument("flows", help="After (current) flows JSON file — modified in-place")
    parser.add_argument("before", help="Before (baseline) flows JSON file")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would change without modifying the file")
    parser.add_argument("--verbose", action="store_true",
                        help="Print detailed progress to stderr")
    args = parser.parse_args()

    with open(args.before) as f:
        before_data = json.load(f)
    with open(args.flows) as f:
        after_data = json.load(f)

    after_idx = build_index(after_data)
    by_id = after_idx["by_id"]

    if args.verbose:
        print("Checking groups for relayout...", file=sys.stderr)

    group_ids = find_groups_needing_relayout(
        before_data, after_data, after_idx, verbose=args.verbose
    )

    if not group_ids:
        if args.verbose:
            print("No groups need relayout.", file=sys.stderr)
        return

    if not ensure_dagre_deps():
        print("Warning: dagre not available, skipping relayout.", file=sys.stderr)
        sys.exit(0)

    relaid_info = []
    for gid in group_ids:
        group = by_id[gid]
        name = group.get("name", "(unnamed)")
        flow_id = group.get("z")

        graph = build_dagre_graph(gid, after_idx)
        if len(graph["nodes"]) < 2:
            if args.verbose:
                print(f"  skip {name}: <2 dagre nodes", file=sys.stderr)
            continue

        if args.verbose:
            print(f"  running dagre on {name} ({len(graph['nodes'])} nodes, "
                  f"{len(graph['edges'])} edges)...", file=sys.stderr)

        dagre_result = run_dagre(graph)
        if dagre_result is None:
            continue

        if args.dry_run:
            print(f"Would relayout: {name} id={gid} "
                  f"({len(graph['nodes'])} nodes, {len(graph['edges'])} edges)")
            print(f"  dagre result: {dagre_result['width']}x{dagre_result['height']}")
            continue

        old_y, old_bottom, new_bottom = apply_dagre_positions(
            gid, dagre_result, after_idx
        )
        relaid_info.append((gid, flow_id, old_y, old_bottom, new_bottom))

        if args.verbose:
            delta = new_bottom - old_bottom
            print(f"  {name}: height delta={int(delta):+d}px", file=sys.stderr)

    if args.dry_run:
        return

    # Shift groups below resized ones.
    if relaid_info:
        shift_groups(relaid_info, after_data, after_idx)

    # Write back.
    with open(args.flows, "w") as f:
        json.dump(after_data, f, indent=2)
        f.write("\n")

    count = len(relaid_info)
    s = "s" if count != 1 else ""
    print(f"Relaid out {count} group{s}.", file=sys.stderr)


if __name__ == "__main__":
    main()

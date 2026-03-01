"""Query and extract subsets of a Node-RED flows JSON file.

Supports extracting individual nodes, connected subgraphs, flow contents,
subflow instances, group contents, function source code, and flexible
search — so agents can inspect specific parts of a large flows file
without reading the whole thing.

Usage: Called by query-nodered-flows.sh, not directly.

# NOTE: If you change this script's commands, flags, output format, or
# behavior, update docs/exploring-nodered-json.md to match.
"""

import json
import re
import sys
from collections import defaultdict, deque


def build_index(data):
    by_id = {}
    by_z = defaultdict(list)
    forward = defaultdict(list)  # source_id -> [(target_id, port)]
    backward = defaultdict(list)  # target_id -> [(source_id, port)]
    link_out_to_in = defaultdict(list)  # link out (mode=link) id -> [link in ids]
    link_in_to_out = defaultdict(list)  # link in id -> [link out (mode=link) ids]
    link_call_to_in = defaultdict(list)  # link call id -> [link in ids]
    link_in_to_call = defaultdict(list)  # link in id -> [link call ids]
    subflow_instances = defaultdict(list)  # subflow def id -> [instance nodes]
    group_members = defaultdict(list)  # group id -> [node ids]

    for node in data:
        nid = node.get("id")
        if not nid:
            continue
        by_id[nid] = node

        z = node.get("z")
        if z:
            by_z[z].append(node)

        for port_idx, targets in enumerate(node.get("wires", [])):
            for target_id in targets:
                forward[nid].append((target_id, port_idx))
                backward[target_id].append((nid, port_idx))

        ntype = node.get("type", "")
        if ntype == "link out" and node.get("mode") == "link":
            for target_id in node.get("links", []):
                link_out_to_in[nid].append(target_id)
                link_in_to_out[target_id].append(nid)
        elif ntype == "link call":
            for target_id in node.get("links", []):
                link_call_to_in[nid].append(target_id)
                link_in_to_call[target_id].append(nid)
        elif ntype.startswith("subflow:"):
            sf_id = ntype[len("subflow:"):]
            subflow_instances[sf_id].append(node)

        if ntype == "group":
            for member_id in node.get("nodes", []):
                group_members[nid].append(member_id)

    return {
        "by_id": by_id,
        "by_z": by_z,
        "forward": forward,
        "backward": backward,
        "link_out_to_in": link_out_to_in,
        "link_in_to_out": link_in_to_out,
        "link_call_to_in": link_call_to_in,
        "link_in_to_call": link_in_to_call,
        "subflow_instances": subflow_instances,
        "group_members": group_members,
    }


def collect_group_node_ids(group_id, idx):
    """All node IDs in a group, recursively including nested groups."""
    ids = []
    for member_id in idx["group_members"].get(group_id, []):
        ids.append(member_id)
        member = idx["by_id"].get(member_id, {})
        if member.get("type") == "group":
            ids.extend(collect_group_node_ids(member_id, idx))
    return ids


def bfs_forward(start_id, idx, follow_links):
    visited = {start_id}
    queue = deque()
    result = []

    for target_id, _port in idx["forward"].get(start_id, []):
        if target_id not in visited:
            visited.add(target_id)
            queue.append(target_id)

    if follow_links:
        node = idx["by_id"].get(start_id, {})
        if node.get("type") == "link out" and node.get("mode") == "link":
            for target_id in idx["link_out_to_in"].get(start_id, []):
                if target_id not in visited:
                    visited.add(target_id)
                    queue.append(target_id)
        elif node.get("type") == "link call":
            for target_id in idx["link_call_to_in"].get(start_id, []):
                if target_id not in visited:
                    visited.add(target_id)
                    queue.append(target_id)

    while queue:
        nid = queue.popleft()
        result.append(nid)
        for target_id, _port in idx["forward"].get(nid, []):
            if target_id not in visited:
                visited.add(target_id)
                queue.append(target_id)
        if follow_links:
            node = idx["by_id"].get(nid, {})
            ntype = node.get("type", "")
            if ntype == "link out" and node.get("mode") == "link":
                for target_id in idx["link_out_to_in"].get(nid, []):
                    if target_id not in visited:
                        visited.add(target_id)
                        queue.append(target_id)
            elif ntype == "link call":
                for target_id in idx["link_call_to_in"].get(nid, []):
                    if target_id not in visited:
                        visited.add(target_id)
                        queue.append(target_id)

    return result


def bfs_backward(start_id, idx, follow_links):
    visited = {start_id}
    queue = deque()
    result = []

    for source_id, _port in idx["backward"].get(start_id, []):
        if source_id not in visited:
            visited.add(source_id)
            queue.append(source_id)

    if follow_links:
        node = idx["by_id"].get(start_id, {})
        if node.get("type") == "link in":
            for source_id in idx["link_in_to_out"].get(start_id, []):
                if source_id not in visited:
                    visited.add(source_id)
                    queue.append(source_id)
            for source_id in idx["link_in_to_call"].get(start_id, []):
                if source_id not in visited:
                    visited.add(source_id)
                    queue.append(source_id)

    while queue:
        nid = queue.popleft()
        result.append(nid)
        for source_id, _port in idx["backward"].get(nid, []):
            if source_id not in visited:
                visited.add(source_id)
                queue.append(source_id)
        if follow_links:
            node = idx["by_id"].get(nid, {})
            if node.get("type") == "link in":
                for source_id in idx["link_in_to_out"].get(nid, []):
                    if source_id not in visited:
                        visited.add(source_id)
                        queue.append(source_id)
                for source_id in idx["link_in_to_call"].get(nid, []):
                    if source_id not in visited:
                        visited.add(source_id)
                        queue.append(source_id)

    return result


def has_incoming(nid, idx, follow_links):
    if idx["backward"].get(nid):
        return True
    if follow_links:
        node = idx["by_id"].get(nid, {})
        if node.get("type") == "link in":
            if idx["link_in_to_out"].get(nid) or idx["link_in_to_call"].get(nid):
                return True
    return False


def has_outgoing(nid, idx, follow_links):
    wires = idx["by_id"].get(nid, {}).get("wires", [])
    for targets in wires:
        if targets:
            return True
    if follow_links:
        node = idx["by_id"].get(nid, {})
        ntype = node.get("type", "")
        if ntype == "link out" and node.get("mode") == "link":
            if idx["link_out_to_in"].get(nid):
                return True
        elif ntype == "link call":
            if idx["link_call_to_in"].get(nid):
                return True
    return False


def get_scope_sources(scope_node_ids, idx, follow_links):
    """Nodes in the scope whose incoming connections are all from outside the scope.

    "Source" here means entry point: a node that either receives input from
    outside the scope or receives no input at all (event trigger). Metadata
    types (group, comment, tab, subflow defs) are excluded.
    """
    scope_set = set(scope_node_ids)
    sources = []
    for nid in scope_node_ids:
        node = idx["by_id"].get(nid, {})
        ntype = node.get("type", "")
        if ntype in ("group", "comment", "tab", "subflow"):
            continue
        has_internal = False
        for source_id, _port in idx["backward"].get(nid, []):
            if source_id in scope_set:
                has_internal = True
                break
        if not has_internal and follow_links and ntype == "link in":
            for source_id in idx["link_in_to_out"].get(nid, []):
                if source_id in scope_set:
                    has_internal = True
                    break
            if not has_internal:
                for source_id in idx["link_in_to_call"].get(nid, []):
                    if source_id in scope_set:
                        has_internal = True
                        break
        if not has_internal:
            sources.append(nid)
    return sources


def format_summary(node, idx):
    nid = node["id"]
    ntype = node.get("type", "")
    name = node.get("name", "")
    wire_count = sum(len(t) for t in node.get("wires", []))
    parts = [nid, ntype, f'"{name}"', f"wires:{wire_count}"]
    gid = node.get("g")
    if gid:
        group = idx["by_id"].get(gid, {})
        group_name = group.get("name", "")
        parts.append(f'group:"{group_name}"')
    return "  ".join(parts)


def output_nodes(nodes, idx, summary=False, full=False):
    if full:
        print(json.dumps(nodes, indent=2))
    elif summary:
        for node in nodes:
            print(format_summary(node, idx))
    else:
        for node in nodes:
            print(json.dumps(node, separators=(",", ":")))


def die(msg):
    print(f"Error: {msg}", file=sys.stderr)
    sys.exit(1)


def cmd_node(idx, args):
    if not args:
        die("node requires an <id> argument")
    nid = args[0]
    node = idx["by_id"].get(nid)
    if not node:
        die(f"node not found: {nid}")
    print(json.dumps(node, indent=2))


def cmd_function(idx, args):
    if not args:
        die("function requires an <id> argument")
    nid = args[0]
    node = idx["by_id"].get(nid)
    if not node:
        die(f"node not found: {nid}")
    if node.get("type") != "function":
        die(f"node {nid} is type '{node.get('type')}', not 'function'")
    func = node.get("func", "")
    if func:
        print(func)
    initialize = node.get("initialize", "")
    if initialize:
        print("\n// --- Setup (initialize) ---")
        print(initialize)
    finalize = node.get("finalize", "")
    if finalize:
        print("\n// --- Cleanup (finalize) ---")
        print(finalize)


def cmd_connected(idx, args):
    if not args:
        die("connected requires an <id> argument")
    nid = args[0]
    if nid not in idx["by_id"]:
        die(f"node not found: {nid}")

    flags = set(args[1:])
    summary = "--summary" in flags
    full = "--full" in flags
    follow_links = "--dont-follow-links" not in flags
    forward_only = "--forward" in flags
    backward_only = "--backward" in flags

    backward_ids = []
    forward_ids = []
    if not forward_only:
        backward_ids = bfs_backward(nid, idx, follow_links)
    if not backward_only:
        forward_ids = bfs_forward(nid, idx, follow_links)

    # backward reversed (root→start order), then start, then forward (start→leaf order)
    ordered_ids = list(reversed(backward_ids)) + [nid] + forward_ids
    nodes = [idx["by_id"][i] for i in ordered_ids if i in idx["by_id"]]
    output_nodes(nodes, idx, summary, full)


def cmd_head_nodes(idx, args):
    if not args:
        die("head-nodes requires an <id> argument")
    nid = args[0]
    if nid not in idx["by_id"]:
        die(f"node not found: {nid}")

    flags = set(args[1:])
    summary = "--summary" in flags
    full = "--full" in flags
    follow_links = "--dont-follow-links" not in flags

    backward_ids = bfs_backward(nid, idx, follow_links)
    # Include start node itself if it has no incoming
    candidates = backward_ids + [nid]
    heads = [i for i in candidates if not has_incoming(i, idx, follow_links)]
    nodes = [idx["by_id"][i] for i in heads if i in idx["by_id"]]
    output_nodes(nodes, idx, summary, full)


def cmd_tail_nodes(idx, args):
    if not args:
        die("tail-nodes requires an <id> argument")
    nid = args[0]
    if nid not in idx["by_id"]:
        die(f"node not found: {nid}")

    flags = set(args[1:])
    summary = "--summary" in flags
    full = "--full" in flags
    follow_links = "--dont-follow-links" not in flags

    forward_ids = bfs_forward(nid, idx, follow_links)
    candidates = forward_ids + [nid]
    tails = [i for i in candidates if not has_outgoing(i, idx, follow_links)]
    nodes = [idx["by_id"][i] for i in tails if i in idx["by_id"]]
    output_nodes(nodes, idx, summary, full)


def cmd_flow_nodes(idx, args):
    if not args:
        die("flow-nodes requires an <id> argument")
    flow_id = args[0]
    if flow_id not in idx["by_id"]:
        die(f"flow not found: {flow_id}")
    flags = set(args[1:])
    summary = "--summary" in flags
    full = "--full" in flags
    sources_only = "--sources" in flags
    follow_links = "--dont-follow-links" not in flags

    nodes = idx["by_z"].get(flow_id, [])
    if sources_only:
        all_ids = [n["id"] for n in nodes]
        source_ids = set(get_scope_sources(all_ids, idx, follow_links))
        nodes = [n for n in nodes if n["id"] in source_ids]
    nodes = sorted(nodes, key=lambda n: (n.get("type", ""), n.get("name", "")))
    output_nodes(nodes, idx, summary, full)


def cmd_group_nodes(idx, args):
    if not args:
        die("group-nodes requires an <id> argument")
    group_id = args[0]
    node = idx["by_id"].get(group_id)
    if not node or node.get("type") != "group":
        die(f"group not found: {group_id}")
    flags = set(args[1:])
    summary = "--summary" in flags
    full = "--full" in flags
    sources_only = "--sources" in flags
    follow_links = "--dont-follow-links" not in flags

    member_ids = collect_group_node_ids(group_id, idx)
    if sources_only:
        source_ids = set(get_scope_sources(member_ids, idx, follow_links))
        member_ids = [i for i in member_ids if i in source_ids]
    nodes = [idx["by_id"][i] for i in member_ids if i in idx["by_id"]]
    nodes = sorted(nodes, key=lambda n: (n.get("type", ""), n.get("name", "")))
    output_nodes(nodes, idx, summary, full)


def cmd_subflow_nodes(idx, args):
    if not args:
        die("subflow-nodes requires an <id> argument")
    sf_id = args[0]
    node = idx["by_id"].get(sf_id)
    if not node or node.get("type") != "subflow":
        die(f"subflow definition not found: {sf_id}")
    flags = set(args[1:])
    summary = "--summary" in flags
    full = "--full" in flags
    nodes = sorted(idx["by_z"].get(sf_id, []), key=lambda n: (n.get("type", ""), n.get("name", "")))
    output_nodes(nodes, idx, summary, full)


def cmd_subflow_instances(idx, args):
    if not args:
        die("subflow-instances requires an <id> argument")
    sf_id = args[0]
    node = idx["by_id"].get(sf_id)
    if not node or node.get("type") != "subflow":
        die(f"subflow definition not found: {sf_id}")
    flags = set(args[1:])
    summary = "--summary" in flags
    full = "--full" in flags
    instances = idx["subflow_instances"].get(sf_id, [])
    output_nodes(instances, idx, summary, full)


# ---------------------------------------------------------------------------
# Spatial query helpers
# ---------------------------------------------------------------------------

# Types that don't live on the canvas (no meaningful x, y position).
_NON_SPATIAL_TYPES = {"tab", "subflow"}


def _parse_coord(s):
    """Parse a coordinate value, supporting 'inf' and '-inf'."""
    if s in ("inf", "+inf"):
        return float("inf")
    if s == "-inf":
        return float("-inf")
    try:
        return float(s)
    except ValueError:
        die(f"invalid coordinate: {s}")


def _overlaps_rect(node, x1, y1, x2, y2):
    """Check if a node's center or a group's bbox overlaps the query rect."""
    ntype = node.get("type", "")
    if ntype in _NON_SPATIAL_TYPES:
        return False

    if ntype == "group":
        # Group: bounding-box overlap test (x, y is top-left, w/h stored).
        gx = node.get("x", 0)
        gy = node.get("y", 0)
        gw = node.get("w", 0)
        gh = node.get("h", 0)
        return gx < x2 and (gx + gw) > x1 and gy < y2 and (gy + gh) > y1

    # Regular node: center point within rect.
    nx = node.get("x")
    ny = node.get("y")
    if nx is None or ny is None:
        return False
    return x1 <= nx <= x2 and y1 <= ny <= y2


def _make_rect_sort_key(x1, y1, x2, y2):
    """Return a sort-key function for nodes matched by a rect query.

    Semi-infinite rects auto-sort by position along the infinite axis
    (closest to the finite edge first).  Finite rects sort by distance
    from the rect center.
    """
    x_inf = (x1 == float("-inf")) or (x2 == float("inf"))
    y_inf = (y1 == float("-inf")) or (y2 == float("inf"))

    if y_inf and not x_inf:
        return lambda n: n.get("y", 0)
    if x_inf and not y_inf:
        return lambda n: n.get("x", 0)

    # Both finite, or both infinite -- distance from best-available center.
    cx = (x1 + x2) / 2 if x1 != float("-inf") and x2 != float("inf") else 0
    cy = (y1 + y2) / 2 if y1 != float("-inf") and y2 != float("inf") else 0
    if x1 == float("-inf") and x2 != float("inf"):
        cx = x2
    elif x2 == float("inf") and x1 != float("-inf"):
        cx = x1
    if y1 == float("-inf") and y2 != float("inf"):
        cy = y2
    elif y2 == float("inf") and y1 != float("-inf"):
        cy = y1
    return lambda n: ((n.get("x", 0) - cx) ** 2 + (n.get("y", 0) - cy) ** 2) ** 0.5


def cmd_rect(idx, args):
    """Find nodes/groups within a rectangle on the canvas."""
    if len(args) < 4:
        die("rect requires 4 coordinates: <x1> <y1> <x2> <y2>\n"
            "Use 'inf' / '-inf' for semi-infinite edges.")

    x1 = _parse_coord(args[0])
    y1 = _parse_coord(args[1])
    x2 = _parse_coord(args[2])
    y2 = _parse_coord(args[3])

    # Normalize so x1 <= x2, y1 <= y2.
    if x1 > x2:
        x1, x2 = x2, x1
    if y1 > y2:
        y1, y2 = y2, y1

    flow_filter = None
    group_filter = None
    summary = False
    full = False
    i = 4
    while i < len(args):
        if args[i] == "--flow" and i + 1 < len(args):
            flow_filter = args[i + 1]
            i += 2
        elif args[i] == "--group" and i + 1 < len(args):
            group_filter = args[i + 1]
            i += 2
        elif args[i] == "--summary":
            summary = True
            i += 1
        elif args[i] == "--full":
            full = True
            i += 1
        else:
            die(f"unknown rect argument: {args[i]}")

    # Determine candidate set.
    if group_filter:
        node = idx["by_id"].get(group_filter)
        if not node or node.get("type") != "group":
            die(f"group not found: {group_filter}")
        member_ids = collect_group_node_ids(group_filter, idx)
        candidates = [idx["by_id"][mid] for mid in member_ids if mid in idx["by_id"]]
    elif flow_filter:
        candidates = idx["by_z"].get(flow_filter, [])
    else:
        candidates = list(idx["by_id"].values())

    results = [n for n in candidates if _overlaps_rect(n, x1, y1, x2, y2)]
    results.sort(key=_make_rect_sort_key(x1, y1, x2, y2))
    output_nodes(results, idx, summary, full)


def cmd_nearby(idx, args):
    """Find nodes/groups near a given node or group."""
    if not args:
        die("nearby requires an <id> argument")
    nid = args[0]
    node = idx["by_id"].get(nid)
    if not node:
        die(f"node not found: {nid}")

    margin = 100
    summary = False
    full = False
    i = 1
    while i < len(args):
        if args[i] == "--margin" and i + 1 < len(args):
            try:
                margin = float(args[i + 1])
            except ValueError:
                die(f"invalid margin: {args[i + 1]}")
            i += 2
        elif args[i] == "--summary":
            summary = True
            i += 1
        elif args[i] == "--full":
            full = True
            i += 1
        else:
            die(f"unknown nearby argument: {args[i]}")

    ntype = node.get("type", "")

    if ntype == "group":
        gx = node.get("x", 0)
        gy = node.get("y", 0)
        gw = node.get("w", 0)
        gh = node.get("h", 0)
        x1 = gx - margin
        y1 = gy - margin
        x2 = gx + gw + margin
        y2 = gy + gh + margin
        cx, cy = gx + gw / 2, gy + gh / 2
        # Exclude the group itself and all its members.
        exclude = set(collect_group_node_ids(nid, idx))
        exclude.add(nid)
    else:
        nx = node.get("x", 0)
        ny = node.get("y", 0)
        x1 = nx - margin
        y1 = ny - margin
        x2 = nx + margin
        y2 = ny + margin
        cx, cy = nx, ny
        exclude = {nid}

    # Scope to the same flow/subflow.
    z = node.get("z")
    candidates = idx["by_z"].get(z, []) if z else list(idx["by_id"].values())

    results = []
    for n in candidates:
        if n["id"] in exclude:
            continue
        if _overlaps_rect(n, x1, y1, x2, y2):
            results.append(n)

    # Sort by distance from reference center.
    results.sort(key=lambda n: (
        (n.get("x", 0) - cx) ** 2 + (n.get("y", 0) - cy) ** 2
    ) ** 0.5)
    output_nodes(results, idx, summary, full)


# Types that are legitimate entry points (no incoming wires expected).
# NOTE: This must stay in sync with NO_INPUT_TYPES in estimate-node-size.py.
_ENTRY_POINT_TYPES = {
    "inject", "link in", "server-events", "server-state-changed",
    "ha-time", "poll-state", "trigger-state", "cronplus",
    "complete", "catch", "status", "ha-webhook",
}
_ORPHAN_SKIP_TYPES = {"tab", "subflow", "group", "comment"}


def cmd_orphans(idx, args):
    """Find nodes with no incoming connections that aren't event triggers."""
    flags = set()
    flow_filter = None
    group_filter = None

    i = 0
    while i < len(args):
        if args[i] == "--flow" and i + 1 < len(args):
            flow_filter = args[i + 1]
            i += 2
        elif args[i] == "--group" and i + 1 < len(args):
            group_filter = args[i + 1]
            i += 2
        elif args[i] in ("--summary", "--full", "--dont-follow-links"):
            flags.add(args[i])
            i += 1
        else:
            die(f"unknown orphans argument: {args[i]}")
            i += 1

    follow_links = "--dont-follow-links" not in flags
    summary = "--summary" in flags
    full = "--full" in flags

    # Determine candidate set
    if group_filter:
        candidate_ids = set(collect_group_node_ids(group_filter, idx))
    elif flow_filter:
        candidate_ids = set(n["id"] for n in idx["by_z"].get(flow_filter, []))
    else:
        candidate_ids = set(idx["by_id"].keys())

    orphans = []
    for nid in candidate_ids:
        node = idx["by_id"].get(nid, {})
        ntype = node.get("type", "")

        # Skip metadata types
        if ntype in _ORPHAN_SKIP_TYPES:
            continue

        # Skip legitimate entry-point types
        if ntype in _ENTRY_POINT_TYPES:
            continue

        # Skip subflow instances whose definition has 0 input ports (event-driven subflows)
        if ntype.startswith("subflow:"):
            sf_id = ntype[len("subflow:"):]
            sf_def = idx["by_id"].get(sf_id, {})
            if sf_def.get("type") == "subflow" and len(sf_def.get("in", [])) == 0:
                continue

        # Skip subflow instance internal nodes that receive from the subflow's in ports
        z = node.get("z", "")
        z_node = idx["by_id"].get(z, {})
        if z_node.get("type") == "subflow":
            sf_in = z_node.get("in", [])
            is_subflow_input_target = False
            for in_port in sf_in:
                for wire_target in in_port.get("wires", []):
                    if wire_target.get("id") == nid:
                        is_subflow_input_target = True
                        break
                if is_subflow_input_target:
                    break
            if is_subflow_input_target:
                continue

        # Check for incoming wires
        has_inc = len(idx["backward"].get(nid, [])) > 0

        # Check for incoming link connections (if following links)
        if not has_inc and follow_links and ntype == "link in":
            has_inc = (len(idx["link_in_to_out"].get(nid, [])) > 0 or
                       len(idx["link_in_to_call"].get(nid, [])) > 0)

        if not has_inc:
            orphans.append(node)

    orphans.sort(key=lambda n: (n.get("z", ""), n.get("type", ""), n.get("name", "")))
    output_nodes(orphans, idx, summary, full)


def cmd_search(idx, args):
    type_filter = None
    name_filter = None
    flow_filter = None
    summary = False
    full = False
    i = 0
    while i < len(args):
        if args[i] == "--type" and i + 1 < len(args):
            type_filter = args[i + 1]
            i += 2
        elif args[i] == "--name" and i + 1 < len(args):
            name_filter = args[i + 1]
            i += 2
        elif args[i] == "--flow" and i + 1 < len(args):
            flow_filter = args[i + 1]
            i += 2
        elif args[i] == "--summary":
            summary = True
            i += 1
        elif args[i] == "--full":
            full = True
            i += 1
        else:
            die(f"unknown search argument: {args[i]}")

    if name_filter:
        try:
            name_re = re.compile(name_filter, re.IGNORECASE)
        except re.error as e:
            die(f"invalid regex for --name: {e}")

    results = []
    for node in idx["by_id"].values():
        if type_filter and node.get("type") != type_filter:
            continue
        if name_filter:
            node_name = node.get("name", "")
            if not name_re.search(node_name):
                continue
        if flow_filter and node.get("z") != flow_filter:
            continue
        results.append(node)

    results.sort(key=lambda n: (n.get("z", ""), n.get("type", ""), n.get("name", "")))
    output_nodes(results, idx, summary, full)


COMMANDS = {
    "node": cmd_node,
    "function": cmd_function,
    "connected": cmd_connected,
    "head-nodes": cmd_head_nodes,
    "tail-nodes": cmd_tail_nodes,
    "flow-nodes": cmd_flow_nodes,
    "group-nodes": cmd_group_nodes,
    "subflow-nodes": cmd_subflow_nodes,
    "subflow-instances": cmd_subflow_instances,
    "search": cmd_search,
    "rect": cmd_rect,
    "nearby": cmd_nearby,
    "orphans": cmd_orphans,
}

USAGE = """\
Usage: query-nodered-flows.sh <flows.json> <command> [args...]

Commands:
  node <id>                         Single node (pretty JSON)
  function <id>                     Print JavaScript source of a function node
  connected <id> [flags]            All nodes connected to <id> (BFS both directions)
  head-nodes <id> [flags]           Root nodes (no incoming) that can reach <id>
  tail-nodes <id> [flags]           Leaf nodes (no outgoing) reachable from <id>
  flow-nodes <id> [flags]           All nodes in a flow/tab
  group-nodes <id> [flags]          All nodes in a group (recursive)
  subflow-nodes <id>                All nodes in a subflow definition
  subflow-instances <id>            All instances of a subflow
  search [--type T] [--name P] [--flow ID]   Flexible search
  rect <x1> <y1> <x2> <y2> [flags] Nodes/groups within a rectangle
  nearby <id> [--margin PX]         Nodes/groups near a node or group
  orphans [flags]                   Find nodes with no incoming connections
                                    that aren't event triggers (likely leftovers
                                    from refactors). Excludes inject, link in,
                                    server-state-changed, trigger-state, etc.

Shared flags:
  --summary           Compact one-liner per node instead of JSONL
  --full              Pretty-printed JSON array of all matching nodes
  --dont-follow-links Don't cross link in/out/call boundaries
                      (applies to: connected, head-nodes, tail-nodes,
                       flow-nodes --sources, group-nodes --sources)

connected-specific flags:
  --forward           Only downstream
  --backward          Only upstream

flow-nodes / group-nodes flags:
  --sources           Only entry-point nodes (no incoming from within scope)

rect flags:
  Coordinates accept 'inf' / '-inf' for semi-infinite edges.
  Semi-infinite rects auto-sort results by position along the infinite axis.
  Nodes match by center point, groups match by bounding-box overlap.
  --flow ID           Only nodes on this flow
  --group ID          Only nodes in this group

nearby flags:
  For groups: expands the stored bounding box by margin, excludes own members.
  For nodes: creates a square of 2*margin centered on the node.
  Always scoped to the same flow.
  --margin PX         Expansion margin in pixels (default: 100)

orphans flags:
  --flow ID           Only check nodes on this flow
  --group ID          Only check nodes in this group (recursive)
  --dont-follow-links Don't consider link connections as incoming"""


def main():
    if len(sys.argv) < 3:
        print(USAGE, file=sys.stderr)
        sys.exit(1)

    flows_file = sys.argv[1]
    command = sys.argv[2]
    cmd_args = sys.argv[3:]

    if command not in COMMANDS:
        die(f"unknown command: {command}\n\n{USAGE}")

    with open(flows_file) as f:
        data = json.load(f)

    idx = build_index(data)
    COMMANDS[command](idx, cmd_args)


if __name__ == "__main__":
    main()

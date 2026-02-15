"""Print a summary of a Node-RED flows JSON file.

Designed to give Claude agents enough context to plan and implement flow
changes without reading the entire (large) flows JSON.

Usage: Called by summarize-nodered-flows.sh, not directly.

# NOTE: If you change this script's output sections, formatting, or
# behavior, update docs/exploring-nodered-json.md to match.
"""

import importlib.util
import json
import os
import re
import sys
from collections import Counter, defaultdict

# Import shared graph utilities from the query tool.
_spec = importlib.util.spec_from_file_location(
    "_query",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "query-nodered-flows.py"),
)
_query = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_query)
build_index = _query.build_index
get_scope_sources = _query.get_scope_sources
collect_group_node_ids = _query.collect_group_node_ids

# HA entity ID detection — matches domain.entity_name patterns.
_HA_DOMAINS = (
    "alarm_control_panel", "alert", "automation", "binary_sensor", "button",
    "calendar", "camera", "climate", "counter", "cover", "device_tracker",
    "fan", "group", "humidifier", "input_boolean", "input_button",
    "input_datetime", "input_number", "input_select", "input_text",
    "light", "lock", "media_player", "notify", "number", "person",
    "remote", "scene", "script", "select", "sensor", "siren", "sun",
    "switch", "text", "timer", "update", "vacuum", "water_heater",
    "weather", "zone",
)
_ENTITY_RE = re.compile(
    r"\b(?:" + "|".join(_HA_DOMAINS) + r")\.[a-z][a-z0-9_]+\b"
)


def _scan_entities(obj, out):
    """Recursively find HA entity IDs in any string values."""
    if isinstance(obj, str):
        out.update(_ENTITY_RE.findall(obj))
    elif isinstance(obj, dict):
        for v in obj.values():
            _scan_entities(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _scan_entities(v, out)


def extract_entities(nodes):
    """Return sorted unique HA entity IDs referenced across a list of nodes."""
    entities = set()
    for node in nodes:
        _scan_entities(node, entities)
    return sorted(entities)


def _format_entry_node(node):
    """Compact label for an entry-point node: type "name"."""
    ntype = node.get("type", "")
    name = node.get("name", "")
    if name:
        return f'{ntype} "{name}"'
    return ntype


def main():
    with open(sys.argv[1]) as f:
        data = json.load(f)

    idx = build_index(data)
    by_id = idx["by_id"]
    nodes_per_z = Counter(e.get("z") for e in data if "z" in e)

    tabs = sorted(
        [e for e in data if e.get("type") == "tab"],
        key=lambda e: e.get("label", ""),
    )
    subflows = sorted(
        [e for e in data if e.get("type") == "subflow"],
        key=lambda e: e.get("name", ""),
    )

    def container_label(z_id):
        c = by_id.get(z_id, {})
        return c.get("label", c.get("name", "(unknown)"))

    # Build set of grouped node IDs (for finding ungrouped entry points later).
    groups = [e for e in data if e.get("type") == "group"]
    grouped_ids = set()
    for g in groups:
        grouped_ids.update(collect_group_node_ids(g["id"], idx))

    # === Flows ===

    print(f"Flows ({len(tabs)}):")
    for t in tabs:
        label = t.get("label", "(unnamed)")
        nid = t["id"]
        count = nodes_per_z.get(nid, 0)
        disabled = " [disabled]" if t.get("disabled") else ""
        print(f"  {label} ({count} nodes){disabled}  id={nid}")

    # === Subflows ===

    print()
    print(f"Subflows ({len(subflows)}):")
    for s in subflows:
        name = s.get("name", "(unnamed)")
        nid = s["id"]
        count = nodes_per_z.get(nid, 0)
        ins = len(s.get("in", []))
        outs = len(s.get("out", []))
        print(f"  {name} ({count} nodes, {ins} in, {outs} out)  id={nid}")
        # For event-driven subflows (0 inputs), show their internal triggers.
        if ins == 0:
            sf_nodes = idx["by_z"].get(nid, [])
            sf_ids = [n["id"] for n in sf_nodes]
            source_ids = set(get_scope_sources(sf_ids, idx, follow_links=True))
            sources = [by_id[i] for i in source_ids if i in by_id]
            sources.sort(key=lambda n: (n.get("type", ""), n.get("name", "")))
            if sources:
                labels = [_format_entry_node(n) for n in sources]
                print(f"    triggers: {', '.join(labels)}")

    # === Groups with entry points ===

    groups_by_z = defaultdict(list)
    for g in groups:
        groups_by_z[g.get("z")].append(g)

    print()
    print(f"Groups ({len(groups)}):")
    for container in tabs + subflows:
        cid = container["id"]
        flow_groups = sorted(
            groups_by_z.get(cid, []),
            key=lambda g: g.get("name", ""),
        )
        if not flow_groups:
            continue
        clabel = container.get("label", container.get("name", "(unnamed)"))
        is_subflow = container.get("type") == "subflow"
        suffix = " [subflow]" if is_subflow else ""
        print(f"  {clabel}{suffix}:")
        for g in flow_groups:
            name = g.get("name", "(unnamed)")
            member_ids = collect_group_node_ids(g["id"], idx)
            node_count = len(member_ids)
            print(f"    {name} ({node_count} nodes)  id={g['id']}")
            source_ids = set(get_scope_sources(member_ids, idx, follow_links=True))
            sources = [by_id[i] for i in source_ids if i in by_id]
            # Exclude junction nodes from entry display — they're wiring helpers.
            sources = [n for n in sources if n.get("type") != "junction"]
            sources.sort(key=lambda n: (n.get("type", ""), n.get("name", "")))
            if sources:
                labels = [_format_entry_node(n) for n in sources]
                print(f"      entry: {', '.join(labels)}")

    # === Cross-flow links ===

    links_out = [e for e in data if e.get("type") == "link out"]
    links_call = [e for e in data if e.get("type") == "link call"]

    cross_flow_links = []
    for lo in links_out + links_call:
        lo_z = lo.get("z")
        for target_id in lo.get("links", []):
            target = by_id.get(target_id, {})
            target_z = target.get("z")
            if target_z and target_z != lo_z:
                cross_flow_links.append((
                    lo.get("name", lo.get("type")),
                    container_label(lo_z),
                    target.get("name", target.get("type")),
                    container_label(target_z),
                ))

    print()
    print(f"Cross-flow links ({len(cross_flow_links)}):")
    if cross_flow_links:
        for src_name, src_flow, dst_name, dst_flow in cross_flow_links:
            print(f"  {src_name} ({src_flow}) -> {dst_name} ({dst_flow})")
    else:
        print("  (none)")

    # === Subflow usage ===

    subflow_usage = defaultdict(list)
    for e in data:
        t = e.get("type", "")
        if t.startswith("subflow:"):
            sf_id = t[len("subflow:"):]
            z = e.get("z")
            subflow_usage[sf_id].append(z)

    print()
    print("Subflow usage:")
    for s in subflows:
        sf_id = s["id"]
        sf_name = s.get("name", "(unnamed)")
        usages = subflow_usage.get(sf_id, [])
        if not usages:
            print(f"  {sf_name}: (unused)")
            continue
        usage_counts = Counter(container_label(z) for z in usages)
        locations = ", ".join(
            f"{flow}({n})" if n > 1 else flow
            for flow, n in sorted(usage_counts.items())
        )
        print(f"  {sf_name}: {len(usages)} instances in {locations}")

    # === Ungrouped entry points per flow ===

    print()
    print("Ungrouped entry points:")
    has_any = False
    for t in tabs:
        flow_id = t["id"]
        flow_nodes = idx["by_z"].get(flow_id, [])
        flow_ids = [n["id"] for n in flow_nodes]
        source_ids = set(get_scope_sources(flow_ids, idx, follow_links=True))
        # Only ungrouped, non-metadata sources.
        ungrouped = [
            by_id[i] for i in source_ids
            if i in by_id
            and i not in grouped_ids
            and by_id[i].get("type") not in ("group", "comment", "junction")
        ]
        ungrouped.sort(key=lambda n: (n.get("type", ""), n.get("name", "")))
        if ungrouped:
            has_any = True
            label = t.get("label", "(unnamed)")
            print(f"  {label}:")
            for n in ungrouped:
                name = n.get("name") or f'({n.get("type")})'
                print(f"    {n.get('type')}  {name}  id={n['id']}")
    if not has_any:
        print("  (none)")

    # === Entity references per flow ===

    print()
    print("Entity references:")
    for t in tabs:
        flow_id = t["id"]
        flow_nodes = idx["by_z"].get(flow_id, [])
        entities = extract_entities(flow_nodes)
        if entities:
            label = t.get("label", "(unnamed)")
            print(f"  {label}:")
            # Wrap to ~100 chars per line for readability.
            line = "    "
            for i, eid in enumerate(entities):
                addition = eid if i == 0 else f", {eid}"
                if len(line) + len(addition) > 100:
                    print(line + ",")
                    line = f"    {eid}"
                else:
                    line += addition
            print(line)

    # === Disabled nodes ===

    disabled_nodes = [e for e in data if e.get("d") is True and e.get("type") not in ("tab",)]
    print()
    print(f"Disabled nodes ({len(disabled_nodes)}):")
    if disabled_nodes:
        disabled_by_z = defaultdict(list)
        for d in disabled_nodes:
            disabled_by_z[d.get("z")].append(d)
        for z_id in sorted(disabled_by_z, key=lambda z: container_label(z)):
            flow_label = container_label(z_id)
            nodes = disabled_by_z[z_id]
            print(f"  {flow_label}:")
            for n in sorted(nodes, key=lambda n: n.get("name", n.get("type", ""))):
                name = n.get("name") or f'({n.get("type")})'
                print(f"    {name}  id={n['id']}")
    else:
        print("  (none)")

    # === Function nodes ===

    fn_nodes = [e for e in data if e.get("type") == "function"]
    print()
    print(f"Function nodes ({len(fn_nodes)}):")
    fn_by_z = defaultdict(list)
    for fn in fn_nodes:
        fn_by_z[fn.get("z")].append(fn)
    for z_id in sorted(fn_by_z, key=lambda z: container_label(z)):
        flow_label = container_label(z_id)
        fns = sorted(fn_by_z[z_id], key=lambda f: f.get("name", ""))
        print(f"  {flow_label}:")
        for fn in fns:
            name = fn.get("name") or "(unnamed)"
            lines = len(fn.get("func", "").split("\n"))
            print(f"    {name} ({lines} lines)  id={fn['id']}")

    # === Comment nodes ===

    comments = [e for e in data if e.get("type") == "comment"]
    print()
    print(f"Comment nodes ({len(comments)}):")
    if comments:
        comments_by_z = defaultdict(list)
        for c in comments:
            comments_by_z[c.get("z")].append(c)
        for z_id in sorted(comments_by_z, key=lambda z: container_label(z)):
            flow_label = container_label(z_id)
            cnodes = sorted(comments_by_z[z_id], key=lambda c: c.get("name", ""))
            print(f"  {flow_label}:")
            for c in cnodes:
                name = c.get("name") or "(unnamed)"
                print(f"    {name}")
    else:
        print("  (none)")


if __name__ == "__main__":
    main()

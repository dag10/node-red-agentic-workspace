"""Print a summary of a Node-RED flows JSON file.

Designed to give Claude agents enough context to plan and implement flow
changes without reading the entire (large) flows JSON.

Usage: Called by summarize-nodered-flows.sh, not directly.
"""

import json
import sys
from collections import Counter, defaultdict


def main():
    with open(sys.argv[1]) as f:
        data = json.load(f)

    by_id = {e["id"]: e for e in data if "id" in e}
    nodes_per_z = Counter(e.get("z") for e in data if "z" in e)

    tabs = sorted(
        [e for e in data if e.get("type") == "tab"],
        key=lambda e: e.get("label", ""),
    )
    subflows = sorted(
        [e for e in data if e.get("type") == "subflow"],
        key=lambda e: e.get("name", ""),
    )
    tab_ids = {t["id"] for t in tabs}
    subflow_ids = {s["id"] for s in subflows}

    def container_label(z_id):
        c = by_id.get(z_id, {})
        return c.get("label", c.get("name", "(unknown)"))

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

    # === Groups per flow ===

    groups = [e for e in data if e.get("type") == "group"]
    groups_by_z = defaultdict(list)
    for g in groups:
        groups_by_z[g.get("z")].append(g)

    print()
    print(f"Groups ({len(groups)}):")
    for t in tabs:
        flow_groups = sorted(groups_by_z.get(t["id"], []), key=lambda g: g.get("name", ""))
        if not flow_groups:
            continue
        print(f"  {t.get('label', '(unnamed)')}:")
        for g in flow_groups:
            name = g.get("name", "(unnamed)")
            node_count = len(g.get("nodes", []))
            print(f"    {name} ({node_count} nodes)  id={g['id']}")
    for s in subflows:
        flow_groups = sorted(groups_by_z.get(s["id"], []), key=lambda g: g.get("name", ""))
        if not flow_groups:
            continue
        print(f"  {s.get('name', '(unnamed)')} [subflow]:")
        for g in flow_groups:
            name = g.get("name", "(unnamed)")
            node_count = len(g.get("nodes", []))
            print(f"    {name} ({node_count} nodes)  id={g['id']}")

    # === Cross-flow links ===

    links_out = [e for e in data if e.get("type") == "link out"]
    links_in = {e["id"]: e for e in data if e.get("type") == "link in"}
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

    # Subflow instance nodes have type "subflow:<subflow_id>"
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

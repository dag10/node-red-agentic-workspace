"""Print a diff-aware summary comparing two versions of a Node-RED flows JSON.

Includes all the information from the regular summary script (for the "after"
state), plus detailed change analysis: which flows/subflows/groups changed,
what specifically changed in each, and which documentation files likely need
updating.

Usage: Called by summarize-nodered-flows-diff.sh, not directly.
"""

import importlib.util
import json
import os
import re
import sys
from collections import Counter, defaultdict

# Import shared utilities from sibling scripts.
_dir = os.path.dirname(os.path.abspath(__file__))

_spec = importlib.util.spec_from_file_location(
    "_query", os.path.join(_dir, "query-nodered-flows.py"),
)
_query = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_query)
build_index = _query.build_index
get_scope_sources = _query.get_scope_sources
collect_group_node_ids = _query.collect_group_node_ids

_spec2 = importlib.util.spec_from_file_location(
    "_summary", os.path.join(_dir, "summarize-nodered-flows.py"),
)
_summary = importlib.util.module_from_spec(_spec2)
_spec2.loader.exec_module(_summary)
extract_entities = _summary.extract_entities

# Fields that only affect visual layout, not automation behavior.
COSMETIC_FIELDS = {"x", "y", "w", "h", "l", "inputLabels", "outputLabels",
                   "icon", "color"}

# HA entity ID pattern (reuse from summary script).
_HA_DOMAINS = _summary._HA_DOMAINS
_ENTITY_RE = _summary._ENTITY_RE


# ---------------------------------------------------------------------------
# Diff computation
# ---------------------------------------------------------------------------

def compute_diff(before_data, after_data):
    """Compare two flows arrays by node ID."""
    before_by_id = {n["id"]: n for n in before_data if "id" in n}
    after_by_id = {n["id"]: n for n in after_data if "id" in n}

    before_ids = set(before_by_id)
    after_ids = set(after_by_id)

    added = after_ids - before_ids
    removed = before_ids - after_ids
    common = before_ids & after_ids

    modified = set()
    cosmetic_only = set()
    for nid in common:
        if before_by_id[nid] != after_by_id[nid]:
            changed = diff_fields(before_by_id[nid], after_by_id[nid])
            if changed <= COSMETIC_FIELDS:
                cosmetic_only.add(nid)
            else:
                modified.add(nid)

    return {
        "added": added,
        "removed": removed,
        "modified": modified,
        "cosmetic_only": cosmetic_only,
        "unchanged": common - modified - cosmetic_only,
        "before_by_id": before_by_id,
        "after_by_id": after_by_id,
    }


def diff_fields(before, after):
    """Return set of field names that differ between two node dicts."""
    all_keys = set(before) | set(after)
    return {k for k in all_keys if before.get(k) != after.get(k)}


def semantic_field_changes(before, after):
    """Return only non-cosmetic changed field names."""
    return diff_fields(before, after) - COSMETIC_FIELDS


def _format_node(node):
    """Compact label: type "name" id=xxx."""
    ntype = node.get("type", "")
    name = node.get("name", "")
    nid = node.get("id", "")
    if name:
        return f'{ntype} "{name}"  id={nid}'
    return f"{ntype}  id={nid}"


def _format_entry_node(node):
    ntype = node.get("type", "")
    name = node.get("name", "")
    if name:
        return f'{ntype} "{name}"'
    return ntype


# ---------------------------------------------------------------------------
# Container helpers
# ---------------------------------------------------------------------------

def container_label(z_id, by_id):
    c = by_id.get(z_id, {})
    return c.get("label", c.get("name", "(unknown)"))


def classify_container(cid, diff):
    """Classify a flow/subflow/group: 'new', 'removed', 'modified', 'unchanged'."""
    if cid in diff["added"]:
        return "new"
    if cid in diff["removed"]:
        return "removed"
    if cid in diff["modified"]:
        return "modified"
    return "unchanged"


def flow_has_changes(flow_id, nodes_by_z, diff):
    """Check if any node on this flow was added/removed/modified."""
    for n in nodes_by_z.get(flow_id, []):
        nid = n["id"]
        if nid in diff["added"] or nid in diff["modified"]:
            return True
    # Check for removed nodes that were on this flow in the "before" state.
    for nid in diff["removed"]:
        before_node = diff["before_by_id"][nid]
        if before_node.get("z") == flow_id:
            return True
    return False


# ---------------------------------------------------------------------------
# Print helpers
# ---------------------------------------------------------------------------

def print_heading(title):
    print()
    print(f"{'=' * 60}")
    print(title)
    print(f"{'=' * 60}")


def print_subheading(title):
    print()
    print(title)
    print(f"{'-' * len(title)}")


# ---------------------------------------------------------------------------
# Output sections
# ---------------------------------------------------------------------------

def print_change_overview(before_data, after_data, diff):
    print_heading("CHANGE OVERVIEW")

    before_nodes = [n for n in before_data if "id" in n]
    after_nodes = [n for n in after_data if "id" in n]

    na = len(diff["added"])
    nr = len(diff["removed"])
    nm = len(diff["modified"])
    nc = len(diff["cosmetic_only"])
    nu = len(diff["unchanged"])

    if not before_nodes:
        print("  First import — all nodes are new.")
        print(f"  Total nodes in import: {len(after_nodes)}")
    else:
        print(f"  Before: {len(before_nodes)} nodes")
        print(f"  After:  {len(after_nodes)} nodes")
        print(f"  Added: {na}  Removed: {nr}  Modified: {nm}  "
              f"Cosmetic-only: {nc}  Unchanged: {nu}")

    # Summarize which types of containers changed.
    before_by_id = diff["before_by_id"]
    after_by_id = diff["after_by_id"]

    before_tabs = {n["id"] for n in before_data if n.get("type") == "tab"}
    after_tabs = {n["id"] for n in after_data if n.get("type") == "tab"}
    before_sfs = {n["id"] for n in before_data if n.get("type") == "subflow"}
    after_sfs = {n["id"] for n in after_data if n.get("type") == "subflow"}
    before_groups = {n["id"] for n in before_data if n.get("type") == "group"}
    after_groups = {n["id"] for n in after_data if n.get("type") == "group"}

    for label, before_set, after_set in [
        ("Flows", before_tabs, after_tabs),
        ("Subflows", before_sfs, after_sfs),
        ("Groups", before_groups, after_groups),
    ]:
        added = after_set - before_set
        removed = before_set - after_set
        parts = []
        if added:
            parts.append(f"{len(added)} added")
        if removed:
            parts.append(f"{len(removed)} removed")
        if parts:
            print(f"  {label}: {', '.join(parts)}")


def print_flows_summary(tabs, nodes_per_z, diff, after_by_z):
    """Flows section — same as normal summary but with change tags."""
    print_heading(f"FLOWS ({len(tabs)})")

    for t in tabs:
        label = t.get("label", "(unnamed)")
        nid = t["id"]
        count = nodes_per_z.get(nid, 0)
        disabled = " [disabled]" if t.get("disabled") else ""

        tag = ""
        status = classify_container(nid, diff)
        if status == "new":
            tag = " [NEW]"
        elif status == "removed":
            tag = " [REMOVED]"
        elif flow_has_changes(nid, after_by_z, diff):
            tag = " [MODIFIED]"

        print(f"  {label} ({count} nodes){disabled}{tag}  id={nid}")


def print_subflows_summary(subflows, nodes_per_z, idx, diff, after_by_z):
    print_heading(f"SUBFLOWS ({len(subflows)})")

    for s in subflows:
        name = s.get("name", "(unnamed)")
        nid = s["id"]
        count = nodes_per_z.get(nid, 0)
        ins = len(s.get("in", []))
        outs = len(s.get("out", []))

        tag = ""
        status = classify_container(nid, diff)
        if status == "new":
            tag = " [NEW]"
        elif status == "removed":
            tag = " [REMOVED]"
        elif flow_has_changes(nid, after_by_z, diff):
            tag = " [MODIFIED]"

        print(f"  {name} ({count} nodes, {ins} in, {outs} out){tag}  id={nid}")
        if ins == 0:
            sf_nodes = idx["by_z"].get(nid, [])
            sf_ids = [n["id"] for n in sf_nodes]
            source_ids = set(get_scope_sources(sf_ids, idx, follow_links=True))
            sources = [idx["by_id"][i] for i in source_ids if i in idx["by_id"]]
            sources.sort(key=lambda n: (n.get("type", ""), n.get("name", "")))
            if sources:
                labels = [_format_entry_node(n) for n in sources]
                print(f"    triggers: {', '.join(labels)}")


def print_groups_summary(data, tabs, subflows, idx, diff):
    groups = [e for e in data if e.get("type") == "group"]
    groups_by_z = defaultdict(list)
    for g in groups:
        groups_by_z[g.get("z")].append(g)

    print_heading(f"GROUPS ({len(groups)})")

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

            tag = ""
            g_status = classify_container(g["id"], diff)
            if g_status == "new":
                tag = " [NEW]"
            else:
                # Check if any member nodes changed.
                changed_in_group = sum(
                    1 for mid in member_ids
                    if mid in diff["added"] or mid in diff["modified"]
                )
                removed_from_group = sum(
                    1 for nid in diff["removed"]
                    if diff["before_by_id"][nid].get("g") == g["id"]
                )
                if changed_in_group or removed_from_group:
                    tag = " [MODIFIED]"

            print(f"    {name} ({node_count} nodes){tag}  id={g['id']}")

            source_ids = set(get_scope_sources(member_ids, idx, follow_links=True))
            sources = [idx["by_id"][i] for i in source_ids if i in idx["by_id"]]
            sources = [n for n in sources if n.get("type") != "junction"]
            sources.sort(key=lambda n: (n.get("type", ""), n.get("name", "")))
            if sources:
                labels = [_format_entry_node(n) for n in sources]
                print(f"      entry: {', '.join(labels)}")


def print_cross_flow_links(data, idx):
    """Same as normal summary — no diff annotations needed, just shows current state."""
    by_id = idx["by_id"]
    links_out = [e for e in data if e.get("type") == "link out"]
    links_call = [e for e in data if e.get("type") == "link call"]

    cross = []
    for lo in links_out + links_call:
        lo_z = lo.get("z")
        for target_id in lo.get("links", []):
            target = by_id.get(target_id, {})
            target_z = target.get("z")
            if target_z and target_z != lo_z:
                cross.append((
                    lo.get("name", lo.get("type")),
                    lo["id"],
                    container_label(lo_z, by_id),
                    target.get("name", target.get("type")),
                    target_id,
                    container_label(target_z, by_id),
                ))

    print_heading(f"CROSS-FLOW LINKS ({len(cross)})")
    if cross:
        for src_name, src_id, src_flow, dst_name, dst_id, dst_flow in cross:
            print(f"  {src_name} id={src_id} ({src_flow})"
                  f" -> {dst_name} id={dst_id} ({dst_flow})")
    else:
        print("  (none)")


def print_subflow_usage(data, subflows, idx):
    """Same as normal summary."""
    by_id = idx["by_id"]
    subflow_usage = defaultdict(list)
    for e in data:
        t = e.get("type", "")
        if t.startswith("subflow:"):
            sf_id = t[len("subflow:"):]
            subflow_usage[sf_id].append(e.get("z"))

    print_heading("SUBFLOW USAGE")
    for s in subflows:
        sf_id = s["id"]
        sf_name = s.get("name", "(unnamed)")
        usages = subflow_usage.get(sf_id, [])
        if not usages:
            print(f"  {sf_name}: (unused)")
            continue
        usage_counts = Counter(container_label(z, by_id) for z in usages)
        locations = ", ".join(
            f"{flow}({n})" if n > 1 else flow
            for flow, n in sorted(usage_counts.items())
        )
        print(f"  {sf_name}: {len(usages)} instances in {locations}")


def print_ungrouped_entry_points(tabs, idx, grouped_ids):
    """Same as normal summary."""
    by_id = idx["by_id"]
    print_heading("UNGROUPED ENTRY POINTS")
    has_any = False
    for t in tabs:
        flow_id = t["id"]
        flow_nodes = idx["by_z"].get(flow_id, [])
        flow_ids = [n["id"] for n in flow_nodes]
        source_ids = set(get_scope_sources(flow_ids, idx, follow_links=True))
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


def print_entity_references(tabs, idx):
    """Same as normal summary."""
    print_heading("ENTITY REFERENCES")
    for t in tabs:
        flow_id = t["id"]
        flow_nodes = idx["by_z"].get(flow_id, [])
        entities = extract_entities(flow_nodes)
        if entities:
            label = t.get("label", "(unnamed)")
            print(f"  {label}:")
            line = "    "
            for i, eid in enumerate(entities):
                addition = eid if i == 0 else f", {eid}"
                if len(line) + len(addition) > 100:
                    print(line + ",")
                    line = f"    {eid}"
                else:
                    line += addition
            print(line)


def print_disabled_nodes(data, idx):
    by_id = idx["by_id"]
    disabled = [e for e in data if e.get("d") is True and e.get("type") != "tab"]
    print_heading(f"DISABLED NODES ({len(disabled)})")
    if disabled:
        by_z = defaultdict(list)
        for d in disabled:
            by_z[d.get("z")].append(d)
        for z_id in sorted(by_z, key=lambda z: container_label(z, by_id)):
            print(f"  {container_label(z_id, by_id)}:")
            for n in sorted(by_z[z_id], key=lambda n: n.get("name", n.get("type", ""))):
                name = n.get("name") or f'({n.get("type")})'
                print(f"    {name}  id={n['id']}")
    else:
        print("  (none)")


def print_function_nodes(data, idx):
    by_id = idx["by_id"]
    fns = [e for e in data if e.get("type") == "function"]
    print_heading(f"FUNCTION NODES ({len(fns)})")
    fn_by_z = defaultdict(list)
    for fn in fns:
        fn_by_z[fn.get("z")].append(fn)
    for z_id in sorted(fn_by_z, key=lambda z: container_label(z, by_id)):
        print(f"  {container_label(z_id, by_id)}:")
        for fn in sorted(fn_by_z[z_id], key=lambda f: f.get("name", "")):
            name = fn.get("name") or "(unnamed)"
            lines = len(fn.get("func", "").split("\n"))
            print(f"    {name} ({lines} lines)  id={fn['id']}")


def print_comment_nodes(data, idx):
    by_id = idx["by_id"]
    comments = [e for e in data if e.get("type") == "comment"]
    print_heading(f"COMMENT NODES ({len(comments)})")
    if comments:
        by_z = defaultdict(list)
        for c in comments:
            by_z[c.get("z")].append(c)
        for z_id in sorted(by_z, key=lambda z: container_label(z, by_id)):
            print(f"  {container_label(z_id, by_id)}:")
            for c in sorted(by_z[z_id], key=lambda c: c.get("name", "")):
                name = c.get("name") or "(unnamed)"
                print(f"    {name}  id={c['id']}")
    else:
        print("  (none)")


# ---------------------------------------------------------------------------
# Diff-specific sections
# ---------------------------------------------------------------------------

def print_detailed_flow_changes(after_data, before_data, tabs, diff, after_idx):
    """Per-flow breakdown of exactly what changed."""
    by_id = after_idx["by_id"]
    after_by_z = after_idx["by_z"]

    # Also include removed flows.
    before_tabs = [n for n in before_data if n.get("type") == "tab"]
    removed_tab_ids = {t["id"] for t in before_tabs} - {t["id"] for t in tabs}

    print_heading("DETAILED CHANGES BY FLOW")

    any_changes = False
    for t in tabs:
        flow_id = t["id"]
        label = t.get("label", "(unnamed)")

        if flow_id in diff["added"]:
            any_changes = True
            print(f"\n  {label} [NEW FLOW]  id={flow_id}")
            flow_nodes = after_by_z.get(flow_id, [])
            print(f"    {len(flow_nodes)} nodes")
            continue

        if not flow_has_changes(flow_id, after_by_z, diff):
            continue

        any_changes = True
        print(f"\n  {label}  id={flow_id}")
        _print_container_changes(flow_id, diff, after_by_z, by_id)

    for tid in sorted(removed_tab_ids):
        any_changes = True
        before_tab = diff["before_by_id"][tid]
        label = before_tab.get("label", "(unnamed)")
        print(f"\n  {label} [REMOVED FLOW]  id={tid}")

    if not any_changes:
        print("  (no flow-level changes)")


def print_detailed_subflow_changes(after_data, before_data, subflows, diff, after_idx):
    by_id = after_idx["by_id"]
    after_by_z = after_idx["by_z"]

    before_sfs = [n for n in before_data if n.get("type") == "subflow"]
    removed_sf_ids = {s["id"] for s in before_sfs} - {s["id"] for s in subflows}

    print_heading("DETAILED CHANGES BY SUBFLOW")

    any_changes = False
    for s in subflows:
        sf_id = s["id"]
        name = s.get("name", "(unnamed)")

        if sf_id in diff["added"]:
            any_changes = True
            print(f"\n  {name} [NEW SUBFLOW]  id={sf_id}")
            sf_nodes = after_by_z.get(sf_id, [])
            print(f"    {len(sf_nodes)} nodes")
            continue

        if not flow_has_changes(sf_id, after_by_z, diff):
            continue

        any_changes = True
        print(f"\n  {name}  id={sf_id}")
        _print_container_changes(sf_id, diff, after_by_z, by_id)

    for sfid in sorted(removed_sf_ids):
        any_changes = True
        before_sf = diff["before_by_id"][sfid]
        name = before_sf.get("name", "(unnamed)")
        print(f"\n  {name} [REMOVED SUBFLOW]  id={sfid}")

    if not any_changes:
        print("  (no subflow-level changes)")


def _print_container_changes(container_id, diff, after_by_z, after_by_id):
    """Print added/removed/modified nodes within a flow or subflow."""
    after_nodes = after_by_z.get(container_id, [])
    after_node_ids = {n["id"] for n in after_nodes}

    added_here = [after_by_id[nid] for nid in after_node_ids if nid in diff["added"]]
    modified_here = [after_by_id[nid] for nid in after_node_ids if nid in diff["modified"]]
    removed_here = [
        diff["before_by_id"][nid] for nid in diff["removed"]
        if diff["before_by_id"][nid].get("z") == container_id
    ]

    if added_here:
        print(f"    Added ({len(added_here)}):")
        for n in sorted(added_here, key=lambda n: (n.get("type", ""), n.get("name", ""))):
            print(f"      {_format_node(n)}")

    if removed_here:
        print(f"    Removed ({len(removed_here)}):")
        for n in sorted(removed_here, key=lambda n: (n.get("type", ""), n.get("name", ""))):
            print(f"      {_format_node(n)}")

    if modified_here:
        print(f"    Modified ({len(modified_here)}):")
        for n in sorted(modified_here, key=lambda n: (n.get("type", ""), n.get("name", ""))):
            before = diff["before_by_id"][n["id"]]
            changed = sorted(semantic_field_changes(before, n))
            fields_str = ", ".join(changed)
            print(f"      {_format_node(n)}  changed: {fields_str}")


def print_entity_changes(before_data, after_data, diff):
    """Show new and removed entity references per flow."""
    print_heading("ENTITY REFERENCE CHANGES")

    # Gather per-flow entities for before and after.
    def entities_by_flow(data):
        by_z = defaultdict(list)
        for n in data:
            z = n.get("z")
            if z:
                by_z[z].append(n)
        result = {}
        tabs = {n["id"]: n for n in data if n.get("type") == "tab"}
        for flow_id, nodes in by_z.items():
            if flow_id in tabs:
                result[flow_id] = set(extract_entities(nodes))
        return result, tabs

    before_ents, before_tabs = entities_by_flow(before_data)
    after_ents, after_tabs = entities_by_flow(after_data)

    all_flow_ids = set(before_ents) | set(after_ents)
    any_changes = False

    for fid in sorted(all_flow_ids, key=lambda f: (
        after_tabs.get(f, before_tabs.get(f, {})).get("label", "")
    )):
        before = before_ents.get(fid, set())
        after = after_ents.get(fid, set())
        new_ents = sorted(after - before)
        removed_ents = sorted(before - after)
        if not new_ents and not removed_ents:
            continue
        any_changes = True
        tab = after_tabs.get(fid, before_tabs.get(fid, {}))
        label = tab.get("label", "(unnamed)")
        print(f"  {label}  id={fid}:")
        for e in new_ents:
            print(f"    + {e}")
        for e in removed_ents:
            print(f"    - {e}")

    if not any_changes:
        print("  (no entity reference changes)")


def print_function_changes(diff):
    """Show which function nodes had their code modified."""
    print_heading("FUNCTION CODE CHANGES")

    code_fields = {"func", "initialize", "finalize"}
    any_changes = False

    for nid in sorted(diff["modified"]):
        after = diff["after_by_id"][nid]
        if after.get("type") != "function":
            continue
        before = diff["before_by_id"][nid]
        changed = diff_fields(before, after) & code_fields
        if not changed:
            continue
        any_changes = True
        name = after.get("name") or "(unnamed)"
        parts = []
        if "func" in changed:
            parts.append("main body")
        if "initialize" in changed:
            parts.append("initialize")
        if "finalize" in changed:
            parts.append("finalize")
        print(f"  {name}  id={nid}  changed: {', '.join(parts)}")

    # Also list new function nodes.
    new_fns = [
        diff["after_by_id"][nid] for nid in diff["added"]
        if diff["after_by_id"][nid].get("type") == "function"
    ]
    if new_fns:
        any_changes = True
        for fn in sorted(new_fns, key=lambda n: n.get("name", "")):
            name = fn.get("name") or "(unnamed)"
            lines = len(fn.get("func", "").split("\n"))
            print(f"  {name}  id={fn['id']}  [NEW] ({lines} lines)")

    if not any_changes:
        print("  (no function code changes)")


def print_wiring_changes(diff):
    """Show connections that were added or removed."""
    print_heading("WIRING CHANGES")

    def get_connections(node_dict, node_ids):
        """Extract (source_id, target_id) pairs from wires."""
        conns = set()
        for nid in node_ids:
            node = node_dict.get(nid, {})
            for targets in node.get("wires", []):
                for tid in targets:
                    conns.add((nid, tid))
            # link connections
            ntype = node.get("type", "")
            if ntype in ("link out", "link call"):
                for tid in node.get("links", []):
                    conns.add((nid, tid))
        return conns

    all_before_ids = set(diff["before_by_id"])
    all_after_ids = set(diff["after_by_id"])

    before_conns = get_connections(diff["before_by_id"], all_before_ids)
    after_conns = get_connections(diff["after_by_id"], all_after_ids)

    new_conns = after_conns - before_conns
    removed_conns = before_conns - after_conns

    def format_conn(src_id, dst_id, node_dict):
        src = node_dict.get(src_id, {})
        dst = node_dict.get(dst_id, {})
        src_label = src.get("name") or src.get("type", src_id)
        dst_label = dst.get("name") or dst.get("type", dst_id)
        return f"{src_label} (id={src_id}) -> {dst_label} (id={dst_id})"

    if new_conns:
        print(f"  New connections ({len(new_conns)}):")
        for src, dst in sorted(new_conns):
            print(f"    + {format_conn(src, dst, diff['after_by_id'])}")

    if removed_conns:
        print(f"  Removed connections ({len(removed_conns)}):")
        for src, dst in sorted(removed_conns):
            print(f"    - {format_conn(src, dst, diff['before_by_id'])}")

    if not new_conns and not removed_conns:
        print("  (no wiring changes)")


def print_affected_docs(tabs, subflows, diff, after_by_z):
    """Summarize which documentation files likely need updating."""
    print_heading("AFFECTED DOCUMENTATION")

    needs_overview = False
    flow_docs = []
    subflow_docs = []

    before_tabs = {
        n["id"] for n in diff["before_by_id"].values()
        if n.get("type") == "tab"
    }
    after_tabs = {t["id"] for t in tabs}
    before_sfs = {
        n["id"] for n in diff["before_by_id"].values()
        if n.get("type") == "subflow"
    }
    after_sfs = {s["id"] for s in subflows}

    # Overview needs updating if any flow/subflow was added, removed, or renamed.
    if before_tabs != after_tabs or before_sfs != after_sfs:
        needs_overview = True
    else:
        for tid in after_tabs & before_tabs:
            before_label = diff["before_by_id"][tid].get("label")
            after_label = diff["after_by_id"][tid].get("label")
            if before_label != after_label:
                needs_overview = True
                break
        if not needs_overview:
            for sid in after_sfs & before_sfs:
                before_name = diff["before_by_id"][sid].get("name")
                after_name = diff["after_by_id"][sid].get("name")
                if before_name != after_name:
                    needs_overview = True
                    break

    for t in tabs:
        fid = t["id"]
        label = t.get("label", "(unnamed)")
        if fid in diff["added"]:
            flow_docs.append((fid, label, "new flow"))
            needs_overview = True
        elif flow_has_changes(fid, after_by_z, diff):
            flow_docs.append((fid, label, "nodes changed"))

    for tid in before_tabs - after_tabs:
        before_tab = diff["before_by_id"][tid]
        label = before_tab.get("label", "(unnamed)")
        flow_docs.append((tid, label, "flow removed"))
        needs_overview = True

    for s in subflows:
        sid = s["id"]
        name = s.get("name", "(unnamed)")
        if sid in diff["added"]:
            subflow_docs.append((sid, name, "new subflow"))
            needs_overview = True
        elif flow_has_changes(sid, after_by_z, diff):
            subflow_docs.append((sid, name, "nodes changed"))

    for sid in before_sfs - after_sfs:
        before_sf = diff["before_by_id"][sid]
        name = before_sf.get("name", "(unnamed)")
        subflow_docs.append((sid, name, "subflow removed"))
        needs_overview = True

    if needs_overview:
        print("  CLAUDE.md — flow/subflow list or names changed")

    for fid, label, reason in flow_docs:
        print(f"  docs/flows/{fid}.md — {label} ({reason})")

    for sid, name, reason in subflow_docs:
        print(f"  docs/subflows/{sid}.md — {name} ({reason})")

    if not needs_overview and not flow_docs and not subflow_docs:
        print("  (no documentation updates needed)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) != 3:
        print("Usage: summarize-nodered-flows-diff.py <before.json> <after.json>",
              file=sys.stderr)
        sys.exit(1)

    with open(sys.argv[1]) as f:
        before_data = json.load(f)
    with open(sys.argv[2]) as f:
        after_data = json.load(f)

    diff = compute_diff(before_data, after_data)
    after_idx = build_index(after_data)
    after_by_id = after_idx["by_id"]
    after_by_z = after_idx["by_z"]
    nodes_per_z = Counter(e.get("z") for e in after_data if "z" in e)

    tabs = sorted(
        [e for e in after_data if e.get("type") == "tab"],
        key=lambda e: e.get("label", ""),
    )
    subflows = sorted(
        [e for e in after_data if e.get("type") == "subflow"],
        key=lambda e: e.get("name", ""),
    )

    groups = [e for e in after_data if e.get("type") == "group"]
    grouped_ids = set()
    for g in groups:
        grouped_ids.update(collect_group_node_ids(g["id"], after_idx))

    # --- Change overview (diff-specific) ---
    print_change_overview(before_data, after_data, diff)

    # --- Full summary sections (same as normal summary, with change tags) ---
    print_flows_summary(tabs, nodes_per_z, diff, after_by_z)
    print_subflows_summary(subflows, nodes_per_z, after_idx, diff, after_by_z)
    print_groups_summary(after_data, tabs, subflows, after_idx, diff)
    print_cross_flow_links(after_data, after_idx)
    print_subflow_usage(after_data, subflows, after_idx)
    print_ungrouped_entry_points(tabs, after_idx, grouped_ids)
    print_entity_references(tabs, after_idx)
    print_disabled_nodes(after_data, after_idx)
    print_function_nodes(after_data, after_idx)
    print_comment_nodes(after_data, after_idx)

    # --- Diff-specific detail sections ---
    print_detailed_flow_changes(after_data, before_data, tabs, diff, after_idx)
    print_detailed_subflow_changes(after_data, before_data, subflows, diff, after_idx)
    print_entity_changes(before_data, after_data, diff)
    print_function_changes(diff)
    print_wiring_changes(diff)
    print_affected_docs(tabs, subflows, diff, after_by_z)


if __name__ == "__main__":
    main()

"""Modify a Node-RED flows JSON file.

Supports adding, updating, deleting, and wiring nodes -- so agents can
make flow changes without editing the JSON directly.

Usage: Called by modify-nodered-flows.sh, not directly.

# NOTE: If you change this script's commands, flags, output format, or
# behavior, update docs/modifying-nodered-json.md to match.
"""

import argparse
import copy
import importlib.util
import json
import os
import re
import sys

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
# Constants
# ---------------------------------------------------------------------------

# HA node types that need auto-populated `server` field.
HA_SERVER_NODE_TYPES = {
    "api-call-service", "server-state-changed", "trigger-state",
    "api-current-state", "poll-state", "api-get-history", "server-events",
    "ha-time", "ha-entity", "ha-button", "ha-sensor", "ha-webhook",
}

# Fields that cannot be changed via update-node.
IMMUTABLE_FIELDS = {"id", "type"}

# Node types with 0 default output ports.
ZERO_OUTPUT_TYPES = {"debug", "link out"}

# Default fields for known HA node type versions.
# NOTE: These defaults are injected by _cmd_add_node for recognized HA node types.
# The agent's --props are merged OVER these, so any explicit prop wins.
# If adding a new node type or version, derive defaults from an existing node
# of that type in the flows (query-nodered-flows.sh ... search --type <type>).
HA_NODE_DEFAULTS = {
    ("api-current-state", 3): {
        "version": 3,
        "blockInputOverrides": False,
        "entity_id": "",
        "entity_location": "data",
        "for": "0",
        "forType": "num",
        "forUnits": "minutes",
        "halt_if": "",
        "halt_if_compare": "is",
        "halt_if_type": "str",
        "outputProperties": [
            {"property": "payload", "propertyType": "msg", "value": "", "valueType": "entityState"},
            {"property": "data", "propertyType": "msg", "value": "", "valueType": "entity"},
        ],
        "override_data": "msg",
        "override_payload": "msg",
        "override_topic": False,
        "state_location": "payload",
        "state_type": "str",
    },
    ("api-call-service", 7): {
        "version": 7,
        "action": "",
        "areaId": [],
        "blockInputOverrides": False,
        "data": "",
        "dataType": "jsonata",
        "debugenabled": False,
        "deviceId": [],
        "domain": "",
        "entityId": [],
        "floorId": [],
        "labelId": [],
        "mergeContext": "",
        "mustacheAltTags": False,
        "outputProperties": [],
        "queue": "none",
        "service": "",
    },
    ("server-state-changed", 6): {
        "version": 6,
        "entities": {"entity": [], "regex": [], "substring": []},
        "exposeAsEntityConfig": "",
        "for": "0",
        "forType": "num",
        "forUnits": "minutes",
        "ifState": "",
        "ifStateOperator": "is",
        "ifStateType": "str",
        "ignoreCurrentStateUnavailable": False,
        "ignoreCurrentStateUnknown": False,
        "ignorePrevStateNull": False,
        "ignorePrevStateUnavailable": False,
        "ignorePrevStateUnknown": False,
        "outputInitially": False,
        "outputOnlyOnStateChange": False,
        "outputProperties": [
            {"property": "payload", "propertyType": "msg", "value": "", "valueType": "entityState"},
            {"property": "data", "propertyType": "msg", "value": "", "valueType": "eventData"},
            {"property": "topic", "propertyType": "msg", "value": "", "valueType": "triggerId"},
        ],
        "stateType": "str",
    },
    ("trigger-state", 5): {
        "version": 5,
        "constraints": [],
        "customOutputs": [],
        "debugEnabled": False,
        "enableInput": False,
        "entities": {"entity": [], "regex": [], "substring": []},
        "exposeAsEntityConfig": "",
        "inputs": 0,
        "outputInitially": False,
        "outputs": 2,
        "stateType": "str",
    },
    ("poll-state", 3): {
        "version": 3,
        "entityId": "",
        "exposeAsEntityConfig": "",
        "ifState": "",
        "ifStateOperator": "is",
        "ifStateType": "str",
        "outputInitially": False,
        "outputOnChanged": False,
        "outputProperties": [
            {"property": "payload", "propertyType": "msg", "value": "", "valueType": "entityState"},
            {"property": "data", "propertyType": "msg", "value": "", "valueType": "entity"},
            {"property": "topic", "propertyType": "msg", "value": "", "valueType": "triggerId"},
        ],
        "stateType": "str",
        "updateInterval": "5",
        "updateIntervalType": "num",
        "updateIntervalUnits": "minutes",
    },
}

# Index: node_type -> {version: defaults_dict, ...}
# Built once at import time for fast lookup.
_HA_DEFAULTS_BY_TYPE = {}
for (_ntype, _ver), _defaults in HA_NODE_DEFAULTS.items():
    _HA_DEFAULTS_BY_TYPE.setdefault(_ntype, {})[_ver] = _defaults


def _get_ha_defaults(node_type, props):
    """Get HA default fields for a node type, or empty dict if unknown.

    If props includes 'version', uses that version's defaults.
    Otherwise uses the highest known version for the type.
    """
    versions = _HA_DEFAULTS_BY_TYPE.get(node_type)
    if not versions:
        return {}
    requested_version = props.get("version")
    if requested_version is not None and requested_version in versions:
        return versions[requested_version]
    # Use highest known version
    return versions[max(versions)]


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def die(msg):
    print(f"Error: {msg}", file=sys.stderr)
    sys.exit(1)


def generate_id(existing_ids):
    """Generate a unique 16-char lowercase hex ID."""
    while True:
        new_id = os.urandom(8).hex()
        if new_id not in existing_ids:
            return new_id


def sort_keys_recursive(obj):
    """Recursively sort dict keys and return new structure.

    Matches normalize-json.sh: sorts dict keys alphabetically, recurses
    into list items and nested dicts. Does NOT sort list items themselves
    (only the top-level array is sorted by 'id' separately).
    """
    if isinstance(obj, dict):
        return {k: sort_keys_recursive(v) for k, v in sorted(obj.items())}
    if isinstance(obj, list):
        return [sort_keys_recursive(item) for item in obj]
    return obj


def coerce_positions(data):
    """Ensure position fields are integers, not floats.

    Node-RED positions should always be integers. This catches cases where
    Python math (e.g., w/2) produces floats that would be written as 200.0
    instead of 200 in the JSON output.
    """
    for node in data:
        if not isinstance(node, dict):
            continue
        # Groups have x, y, w, h; regular nodes have x, y
        fields = ("x", "y", "w", "h") if node.get("type") == "group" else ("x", "y")
        for field in fields:
            if field in node and isinstance(node[field], float):
                node[field] = int(round(node[field]))


def write_normalized(data, path):
    """Write flows JSON matching normalize-json.sh output exactly.

    Steps (must match normalize-json.sh):
    1. Coerce position fields (x, y, w, h) to integers.
    2. Recursively sort all dict keys alphabetically.
    3. Sort top-level array by 'id' field (if all elements are dicts with 'id').
    4. Write with json.dump(indent=2, ensure_ascii=False) + trailing newline.
    """
    coerce_positions(data)
    data = [sort_keys_recursive(node) for node in data]
    if all(isinstance(e, dict) and "id" in e for e in data):
        data.sort(key=lambda e: e["id"])
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def find_ha_server_id(data):
    """Find the single HA server config node ID, or None if ambiguous."""
    servers = [n for n in data if n.get("type") == "server"]
    if len(servers) == 1:
        return servers[0]["id"]
    return None


def resolve_refs(value, created_ids):
    """Replace $N references with created IDs in batch operations."""
    if isinstance(value, str):
        def replacer(m):
            n = int(m.group(1))
            if n >= len(created_ids):
                die(f"${n} references operation {n}, but only {len(created_ids)} "
                    f"add operations have executed so far")
            return created_ids[n]
        return re.sub(r'\$(\d+)', replacer, value)
    if isinstance(value, dict):
        return {k: resolve_refs(v, created_ids) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve_refs(item, created_ids) for item in value]
    return value


def _find_node(data, node_id):
    """Find a node by ID in the data array. Returns the node dict or None."""
    for node in data:
        if node.get("id") == node_id:
            return node
    return None


def _get_existing_ids(data):
    """Get set of all existing IDs in the data."""
    return {n["id"] for n in data if "id" in n}


def _validate_flow(data, flow_id):
    """Validate that flow_id exists and is a tab or subflow."""
    node = _find_node(data, flow_id)
    if not node:
        die(f"flow not found: {flow_id}")
    if node.get("type") not in ("tab", "subflow"):
        die(f"node {flow_id} is type '{node.get('type')}', not a tab or subflow")
    return node


def _validate_group(data, group_id, flow_id=None):
    """Validate that group_id exists and is a group (optionally on flow_id)."""
    node = _find_node(data, group_id)
    if not node:
        die(f"group not found: {group_id}")
    if node.get("type") != "group":
        die(f"node {group_id} is type '{node.get('type')}', not a group")
    if flow_id and node.get("z") != flow_id:
        die(f"group {group_id} is on flow {node.get('z')}, not {flow_id}")
    return node


# ---------------------------------------------------------------------------
# Core command logic
# ---------------------------------------------------------------------------

def _cmd_add_node(data, *, node_type, flow_id, name="", group_id=None,
                  props=None, dry_run=False):
    """Core logic for add-node. Returns (new_id, message)."""
    if props is None:
        props = {}

    # Merge HA defaults under agent props (agent wins).
    ha_defaults = _get_ha_defaults(node_type, props)
    if ha_defaults:
        merged_props = copy.deepcopy(ha_defaults)
        merged_props.update(props)
        props = merged_props

    _validate_flow(data, flow_id)

    if group_id:
        _validate_group(data, group_id, flow_id)

    # Determine output count.
    outputs = 1
    if node_type in ZERO_OUTPUT_TYPES:
        outputs = 0
    if "outputs" in props:
        outputs = int(props["outputs"])

    # Build wires array.
    wires = [[] for _ in range(outputs)]

    existing_ids = _get_existing_ids(data)
    new_id = generate_id(existing_ids)

    node = {
        "id": new_id,
        "type": node_type,
        "z": flow_id,
        "name": name,
        "x": 200,
        "y": 200,
        "wires": wires,
    }

    if group_id:
        node["g"] = group_id

    # Auto-set HA server config.
    if node_type in HA_SERVER_NODE_TYPES and "server" not in props:
        server_id = find_ha_server_id(data)
        if server_id:
            node["server"] = server_id

    # Merge props over base node (shallow).
    # If props contains "wires", it overrides the auto-generated wires.
    node.update(props)

    # Ensure wires matches outputs if outputs was in props but wires wasn't.
    if "outputs" in props and "wires" not in props:
        needed = int(props["outputs"])
        while len(node["wires"]) < needed:
            node["wires"].append([])

    group_part = f" group={group_id}" if group_id else ""
    name_part = f' "{name}"' if name else ' ""'
    defaults_part = f" (defaults: {node_type} v{ha_defaults['version']})" if ha_defaults else ""
    msg = f"added {new_id} {node_type}{name_part} on={flow_id}{group_part}{defaults_part}"

    if dry_run:
        return new_id, f"(dry-run) {msg}"

    data.append(node)

    # Add to group's nodes array.
    if group_id:
        group_node = _find_node(data, group_id)
        if "nodes" not in group_node:
            group_node["nodes"] = []
        group_node["nodes"].append(new_id)

    return new_id, msg


def _cmd_update_node(data, *, node_id, props=None, name=None, dry_run=False):
    """Core logic for update-node. Returns (None, message)."""
    if props is None:
        props = {}

    node = _find_node(data, node_id)
    if not node:
        die(f"node not found: {node_id}")

    # Check for immutable fields.
    for field in IMMUTABLE_FIELDS:
        if field in props:
            die(f"cannot change '{field}' via update-node (field is immutable)")

    if name is not None:
        props["name"] = name

    if not props:
        die("nothing to update (provide --props or --name)")

    # Warn about z changes.
    if "z" in props:
        print("Warning: changing z (flow assignment) -- ensure wiring is still valid",
              file=sys.stderr)

    changed_fields = []
    for key, value in props.items():
        if node.get(key) != value:
            changed_fields.append(key)

    node_name = props.get("name", node.get("name", ""))
    node_type = node.get("type", "")
    msg = f'updated {node_id} {node_type} "{node_name}" changed=[{", ".join(changed_fields)}]'

    if dry_run:
        return None, f"(dry-run) {msg}"

    node.update(props)
    return None, msg


def _cmd_delete_node(data, *, node_id, dry_run=False):
    """Core logic for delete-node. Returns (None, message)."""
    node = _find_node(data, node_id)
    if not node:
        die(f"node not found: {node_id}")

    node_type = node.get("type", "")
    node_name = node.get("name", "")

    # Refuse to delete tabs.
    if node_type == "tab":
        die("cannot delete a tab node -- too destructive for a single command")

    # Refuse to delete subflow definitions with existing instances.
    if node_type == "subflow":
        instances = [n for n in data if n.get("type") == f"subflow:{node_id}"]
        if instances:
            die(f"cannot delete subflow {node_id}: {len(instances)} instance(s) exist")

    # If it's a group, collect all members for recursive deletion.
    ids_to_delete = set()
    if node_type == "group":
        idx = build_index(data)
        member_ids = collect_group_node_ids(node_id, idx)
        ids_to_delete.update(member_ids)
    ids_to_delete.add(node_id)

    # Build output message parts.
    cleaned_wires = []
    cleaned_links = []
    cleaned_group = None

    # Clean up references across all nodes.
    for n in data:
        if n.get("id") in ids_to_delete:
            continue

        # Clean wires.
        wires = n.get("wires", [])
        wires_changed = False
        for port_targets in wires:
            for del_id in ids_to_delete:
                if del_id in port_targets:
                    port_targets.remove(del_id)
                    wires_changed = True
        if wires_changed:
            cleaned_wires.append(n["id"])

        # Clean links.
        links = n.get("links", [])
        links_changed = False
        for del_id in ids_to_delete:
            if del_id in links:
                links.remove(del_id)
                links_changed = True
        if links_changed:
            cleaned_links.append(n["id"])

        # Clean group membership (for nodes being deleted from their group).
        if n.get("type") == "group" and n.get("id") not in ids_to_delete:
            nodes_arr = n.get("nodes", [])
            for del_id in ids_to_delete:
                if del_id in nodes_arr:
                    nodes_arr.remove(del_id)

    # Also track the deleted node's own group.
    if node.get("g"):
        cleaned_group = node["g"]

    msg_lines = [f'deleted {node_id} {node_type} "{node_name}"']
    if cleaned_wires:
        msg_lines.append(f"  cleaned wires: [{', '.join(cleaned_wires)}]")
    if cleaned_links:
        msg_lines.append(f"  cleaned links: [{', '.join(cleaned_links)}]")
    if cleaned_group:
        msg_lines.append(f"  cleaned group: {cleaned_group}")
    if node_type == "group" and len(ids_to_delete) > 1:
        msg_lines.append(f"  deleted {len(ids_to_delete) - 1} member node(s)")

    msg = "\n".join(msg_lines)

    if dry_run:
        return None, f"(dry-run) {msg}"

    # Remove all collected nodes from data.
    data[:] = [n for n in data if n.get("id") not in ids_to_delete]

    return None, msg


def _cmd_wire(data, *, source_id, target_id, port=0, dry_run=False):
    """Core logic for wire. Returns (None, message)."""
    source = _find_node(data, source_id)
    if not source:
        die(f"source node not found: {source_id}")
    target = _find_node(data, target_id)
    if not target:
        die(f"target node not found: {target_id}")

    if source_id == target_id:
        print("Warning: self-wiring (source == target)", file=sys.stderr)

    if source.get("z") != target.get("z"):
        print(f"Warning: cross-flow wiring ({source.get('z')} -> {target.get('z')})",
              file=sys.stderr)

    # Ensure wires array exists and is large enough.
    if "wires" not in source:
        source["wires"] = []
    while len(source["wires"]) <= port:
        source["wires"].append([])

    if target_id in source["wires"][port]:
        return None, f"already wired {source_id}:{port} -> {target_id}"

    msg = f"wired {source_id}:{port} -> {target_id}"

    if dry_run:
        return None, f"(dry-run) {msg}"

    source["wires"][port].append(target_id)
    return None, msg


def _cmd_unwire(data, *, source_id, target_id, port=None, all_ports=False,
                dry_run=False):
    """Core logic for unwire. Returns (None, message)."""
    source = _find_node(data, source_id)
    if not source:
        die(f"source node not found: {source_id}")
    target = _find_node(data, target_id)
    if not target:
        die(f"target node not found: {target_id}")

    wires = source.get("wires", [])
    unwired_ports = []

    if all_ports:
        for p_idx, targets in enumerate(wires):
            if target_id in targets:
                unwired_ports.append(p_idx)
    else:
        p = port if port is not None else 0
        if p < len(wires) and target_id in wires[p]:
            unwired_ports.append(p)

    if not unwired_ports:
        return None, f"not wired {source_id} -> {target_id}"

    msg_lines = [f"unwired {source_id}:{p} -> {target_id}" for p in unwired_ports]
    msg = "\n".join(msg_lines)

    if dry_run:
        return None, f"(dry-run) {msg}"

    for p in unwired_ports:
        wires[p].remove(target_id)

    return None, msg


def _cmd_link(data, *, source_id, target_id, dry_run=False):
    """Core logic for link. Returns (None, message)."""
    source = _find_node(data, source_id)
    if not source:
        die(f"node not found: {source_id}")
    target = _find_node(data, target_id)
    if not target:
        die(f"node not found: {target_id}")

    source_type = source.get("type", "")
    target_type = target.get("type", "")

    # Validate source is link out (mode=link) or link call.
    if source_type == "link out":
        if source.get("mode") != "link":
            die(f"node {source_id} is a link out with mode '{source.get('mode')}' "
                f"(expected mode 'link'). A link out with mode 'return' has an "
                f"implicit return target and should not be manually linked.")
    elif source_type != "link call":
        die(f"node {source_id} is type '{source_type}', expected 'link out' (mode=link) "
            f"or 'link call'")

    if target_type != "link in":
        die(f"node {target_id} is type '{target_type}', expected 'link in'")

    # Ensure links arrays exist.
    if "links" not in source:
        source["links"] = []
    if "links" not in target:
        target["links"] = []

    already = target_id in source["links"] and source_id in target["links"]
    if already:
        return None, f"already linked {source_id} ({source_type}) -> {target_id} (link in)"

    msg = f"linked {source_id} ({source_type}) -> {target_id} (link in)"

    if dry_run:
        return None, f"(dry-run) {msg}"

    if target_id not in source["links"]:
        source["links"].append(target_id)
    if source_id not in target["links"]:
        target["links"].append(source_id)

    return None, msg


def _cmd_unlink(data, *, source_id, target_id, dry_run=False):
    """Core logic for unlink. Returns (None, message)."""
    source = _find_node(data, source_id)
    if not source:
        die(f"node not found: {source_id}")
    target = _find_node(data, target_id)
    if not target:
        die(f"node not found: {target_id}")

    source_links = source.get("links", [])
    target_links = target.get("links", [])

    if target_id not in source_links and source_id not in target_links:
        return None, f"not linked {source_id} -> {target_id}"

    msg = f"unlinked {source_id} -> {target_id}"

    if dry_run:
        return None, f"(dry-run) {msg}"

    if target_id in source_links:
        source_links.remove(target_id)
    if source_id in target_links:
        target_links.remove(source_id)

    return None, msg


def _cmd_add_group(data, *, flow_id, name, node_ids=None, dry_run=False):
    """Core logic for add-group. Returns (new_id, message)."""
    if node_ids is None:
        node_ids = []

    _validate_flow(data, flow_id)

    # Validate member nodes.
    for mid in node_ids:
        member = _find_node(data, mid)
        if not member:
            die(f"member node not found: {mid}")
        if member.get("z") != flow_id:
            die(f"member node {mid} is on flow {member.get('z')}, not {flow_id}")
        # Check if already in another group.
        existing_g = member.get("g")
        if existing_g and existing_g not in node_ids:
            die(f"member node {mid} is already in group {existing_g} "
                f"(which is not in this group's member list)")

    existing_ids = _get_existing_ids(data)
    new_id = generate_id(existing_ids)

    group = {
        "id": new_id,
        "type": "group",
        "z": flow_id,
        "name": name,
        "nodes": list(node_ids),
        "style": {"label": True},
        "x": 10,
        "y": 10,
        "w": 200,
        "h": 100,
    }

    msg = f'added group {new_id} "{name}" on={flow_id} members=[{len(node_ids)} nodes]'

    if dry_run:
        return new_id, f"(dry-run) {msg}"

    data.append(group)

    # Set g field on each member node.
    for mid in node_ids:
        member = _find_node(data, mid)
        member["g"] = new_id

    return new_id, msg


def _cmd_move_to_group(data, *, node_id, group_id, dry_run=False):
    """Core logic for move-to-group. Returns (None, message)."""
    node = _find_node(data, node_id)
    if not node:
        die(f"node not found: {node_id}")

    group = _validate_group(data, group_id)
    group_name = group.get("name", "")

    # Validate same flow.
    if node.get("z") != group.get("z"):
        die(f"node {node_id} is on flow {node.get('z')}, "
            f"group {group_id} is on flow {group.get('z')}")

    old_group_id = node.get("g")
    from_part = f"group {old_group_id}" if old_group_id else "ungrouped"

    msg = f'moved {node_id} to group {group_id} "{group_name}" (from {from_part})'

    if dry_run:
        return None, f"(dry-run) {msg}"

    # Remove from old group if present.
    if old_group_id:
        old_group = _find_node(data, old_group_id)
        if old_group and "nodes" in old_group:
            if node_id in old_group["nodes"]:
                old_group["nodes"].remove(node_id)

    # Add to new group.
    node["g"] = group_id
    if "nodes" not in group:
        group["nodes"] = []
    if node_id not in group["nodes"]:
        group["nodes"].append(node_id)

    return None, msg


def _cmd_remove_from_group(data, *, node_id, dry_run=False):
    """Core logic for remove-from-group. Returns (None, message)."""
    node = _find_node(data, node_id)
    if not node:
        die(f"node not found: {node_id}")

    group_id = node.get("g")
    if not group_id:
        return None, f"{node_id} is not in any group"

    group = _find_node(data, group_id)
    group_name = group.get("name", "") if group else ""

    msg = f'removed {node_id} from group {group_id} "{group_name}"'

    if dry_run:
        return None, f"(dry-run) {msg}"

    del node["g"]
    if group and "nodes" in group:
        if node_id in group["nodes"]:
            group["nodes"].remove(node_id)

    return None, msg


def _cmd_set_function(data, *, node_id, body=None, body_file=None,
                      setup=None, setup_file=None,
                      cleanup=None, cleanup_file=None, dry_run=False):
    """Core logic for set-function. Returns (None, message)."""
    node = _find_node(data, node_id)
    if not node:
        die(f"node not found: {node_id}")
    if node.get("type") != "function":
        die(f"node {node_id} is type '{node.get('type')}', not 'function'")

    node_name = node.get("name", "")
    changes = []

    # Resolve body.
    body_code = None
    if body_file is not None:
        if not os.path.isfile(body_file):
            die(f"file not found: {body_file}")
        with open(body_file) as f:
            body_code = f.read()
    elif body is not None:
        body_code = body

    # Resolve setup.
    setup_code = None
    if setup_file is not None:
        if not os.path.isfile(setup_file):
            die(f"file not found: {setup_file}")
        with open(setup_file) as f:
            setup_code = f.read()
    elif setup is not None:
        setup_code = setup

    # Resolve cleanup.
    cleanup_code = None
    if cleanup_file is not None:
        if not os.path.isfile(cleanup_file):
            die(f"file not found: {cleanup_file}")
        with open(cleanup_file) as f:
            cleanup_code = f.read()
    elif cleanup is not None:
        cleanup_code = cleanup

    if body_code is None and setup_code is None and cleanup_code is None:
        die("nothing to set (provide --body, --body-file, --setup, --setup-file, "
            "--cleanup, or --cleanup-file)")

    if body_code is not None:
        line_count = len(body_code.strip().split("\n")) if body_code.strip() else 0
        changes.append(f"body: {line_count} lines")
    if setup_code is not None:
        line_count = len(setup_code.strip().split("\n")) if setup_code.strip() else 0
        changes.append(f"setup: {line_count} lines")
    if cleanup_code is not None:
        line_count = len(cleanup_code.strip().split("\n")) if cleanup_code.strip() else 0
        changes.append(f"cleanup: {line_count} lines")

    msg = f'set-function {node_id} "{node_name}" [{", ".join(changes)}]'

    if dry_run:
        return None, f"(dry-run) {msg}"

    if body_code is not None:
        node["func"] = body_code
    if setup_code is not None:
        node["initialize"] = setup_code
    if cleanup_code is not None:
        node["finalize"] = cleanup_code

    return None, msg


# ---------------------------------------------------------------------------
# Argparse wrapper functions
# ---------------------------------------------------------------------------

def cmd_add_node(data, args):
    try:
        props = json.loads(args.props)
    except json.JSONDecodeError as e:
        die(f"invalid JSON for --props: {e}")
    if not isinstance(props, dict):
        die("--props must be a JSON object")
    new_id, msg = _cmd_add_node(
        data, node_type=args.type, flow_id=args.flow_id, name=args.name,
        group_id=args.group_id, props=props, dry_run=args.dry_run,
    )
    return msg


def cmd_update_node(data, args):
    try:
        props = json.loads(args.props)
    except json.JSONDecodeError as e:
        die(f"invalid JSON for --props: {e}")
    if not isinstance(props, dict):
        die("--props must be a JSON object")
    _, msg = _cmd_update_node(
        data, node_id=args.node_id, props=props, name=args.name,
        dry_run=args.dry_run,
    )
    return msg


def cmd_delete_node(data, args):
    _, msg = _cmd_delete_node(data, node_id=args.node_id, dry_run=args.dry_run)
    return msg


def cmd_wire(data, args):
    _, msg = _cmd_wire(
        data, source_id=args.source_id, target_id=args.target_id,
        port=args.port, dry_run=args.dry_run,
    )
    return msg


def cmd_unwire(data, args):
    _, msg = _cmd_unwire(
        data, source_id=args.source_id, target_id=args.target_id,
        port=args.port, all_ports=args.all_ports, dry_run=args.dry_run,
    )
    return msg


def cmd_link(data, args):
    _, msg = _cmd_link(
        data, source_id=args.source_id, target_id=args.target_id,
        dry_run=args.dry_run,
    )
    return msg


def cmd_unlink(data, args):
    _, msg = _cmd_unlink(
        data, source_id=args.source_id, target_id=args.target_id,
        dry_run=args.dry_run,
    )
    return msg


def cmd_add_group(data, args):
    node_ids = [nid.strip() for nid in args.nodes.split(",") if nid.strip()] \
        if args.nodes else []
    _, msg = _cmd_add_group(
        data, flow_id=args.flow_id, name=args.name, node_ids=node_ids,
        dry_run=args.dry_run,
    )
    return msg


def cmd_move_to_group(data, args):
    _, msg = _cmd_move_to_group(
        data, node_id=args.node_id, group_id=args.group_id,
        dry_run=args.dry_run,
    )
    return msg


def cmd_remove_from_group(data, args):
    _, msg = _cmd_remove_from_group(
        data, node_id=args.node_id, dry_run=args.dry_run,
    )
    return msg


def cmd_set_function(data, args):
    _, msg = _cmd_set_function(
        data, node_id=args.node_id,
        body=args.body, body_file=args.body_file,
        setup=args.setup, setup_file=args.setup_file,
        cleanup=args.cleanup, cleanup_file=args.cleanup_file,
        dry_run=args.dry_run,
    )
    return msg


def cmd_batch(data, args):
    """Execute multiple commands from stdin as a JSON array."""
    try:
        raw = sys.stdin.read()
        operations = json.loads(raw)
    except json.JSONDecodeError as e:
        die(f"invalid JSON on stdin: {e}")

    if not isinstance(operations, list):
        die("batch input must be a JSON array")

    dry_run = args.dry_run

    # Work on a deep copy so we can abort without side effects.
    data_copy = copy.deepcopy(data)

    created_ids = []
    messages = []

    # Map batch arg names to _cmd_* calls.
    for i, op in enumerate(operations):
        if not isinstance(op, dict):
            die(f"operation [{i}] is not a JSON object")
        command = op.get("command")
        if not command:
            die(f"operation [{i}] missing 'command' field")
        op_args = op.get("args", {})

        # Resolve $N references.
        op_args = resolve_refs(op_args, created_ids)

        try:
            new_id, msg = _dispatch_batch_op(data_copy, command, op_args, dry_run)
        except SystemExit:
            die(f"batch aborted at operation [{i}] ({command})")

        if new_id is not None:
            created_ids.append(new_id)

        messages.append(f"[{i}] {msg}")

    # All operations succeeded. Replace original data.
    if not dry_run:
        data.clear()
        data.extend(data_copy)

    # Print each operation's output.
    for m in messages:
        print(m)

    summary = f"batch: {len(operations)} operations applied"
    if dry_run:
        summary = f"(dry-run) {summary}"
    return summary


def _dispatch_batch_op(data, command, args, dry_run):
    """Dispatch a single batch operation. Returns (new_id_or_none, message)."""
    if command == "add-node":
        props = args.get("props", {})
        if isinstance(props, str):
            props = json.loads(props)
        return _cmd_add_node(
            data, node_type=args["type"], flow_id=args["on"],
            name=args.get("name", ""), group_id=args.get("group"),
            props=props, dry_run=dry_run,
        )
    elif command == "update-node":
        props = args.get("props", {})
        if isinstance(props, str):
            props = json.loads(props)
        return _cmd_update_node(
            data, node_id=args["node_id"], props=props,
            name=args.get("name"), dry_run=dry_run,
        )
    elif command == "delete-node":
        return _cmd_delete_node(data, node_id=args["node_id"], dry_run=dry_run)
    elif command == "wire":
        return _cmd_wire(
            data, source_id=args["source"], target_id=args["target"],
            port=args.get("port", 0), dry_run=dry_run,
        )
    elif command == "unwire":
        return _cmd_unwire(
            data, source_id=args["source"], target_id=args["target"],
            port=args.get("port"), all_ports=args.get("all_ports", False),
            dry_run=dry_run,
        )
    elif command == "link":
        return _cmd_link(
            data, source_id=args["source"], target_id=args["target"],
            dry_run=dry_run,
        )
    elif command == "unlink":
        return _cmd_unlink(
            data, source_id=args["source"], target_id=args["target"],
            dry_run=dry_run,
        )
    elif command == "add-group":
        node_ids_raw = args.get("nodes", [])
        if isinstance(node_ids_raw, str):
            node_ids = [nid.strip() for nid in node_ids_raw.split(",") if nid.strip()]
        else:
            node_ids = list(node_ids_raw)
        return _cmd_add_group(
            data, flow_id=args["on"], name=args["name"],
            node_ids=node_ids, dry_run=dry_run,
        )
    elif command == "move-to-group":
        return _cmd_move_to_group(
            data, node_id=args["node_id"], group_id=args["group_id"],
            dry_run=dry_run,
        )
    elif command == "remove-from-group":
        return _cmd_remove_from_group(
            data, node_id=args["node_id"], dry_run=dry_run,
        )
    elif command == "set-function":
        return _cmd_set_function(
            data, node_id=args["node_id"],
            body=args.get("body"), body_file=args.get("body_file"),
            setup=args.get("setup"), setup_file=args.get("setup_file"),
            cleanup=args.get("cleanup"), cleanup_file=args.get("cleanup_file"),
            dry_run=dry_run,
        )
    else:
        die(f"unknown batch command: {command}")


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def build_parser():
    parser = argparse.ArgumentParser(
        prog="modify-nodered-flows.sh",
        description="Modify a Node-RED flows JSON file.",
    )
    parser.add_argument("flows", help="Path to the flows JSON file")
    sub = parser.add_subparsers(dest="command", required=True)

    # add-node
    p = sub.add_parser("add-node", help="Add a new node")
    p.add_argument("type", help="Node type (e.g., function, inject, debug)")
    p.add_argument("--on", required=True, dest="flow_id",
                   help="ID of the tab or subflow to place the node on")
    p.add_argument("--name", default="", help="Human-readable name")
    p.add_argument("--group", dest="group_id", help="Group ID to add the node to")
    p.add_argument("--props", default="{}", help="JSON object of additional properties")
    p.add_argument("--dry-run", action="store_true")

    # update-node
    p = sub.add_parser("update-node", help="Update properties on an existing node")
    p.add_argument("node_id", help="ID of the node to modify")
    p.add_argument("--props", default="{}", help="JSON object of properties to set/update")
    p.add_argument("--name", help="Shorthand for setting the name property")
    p.add_argument("--dry-run", action="store_true")

    # delete-node
    p = sub.add_parser("delete-node", help="Delete a node and clean up references")
    p.add_argument("node_id", help="ID of the node to delete")
    p.add_argument("--dry-run", action="store_true")

    # wire
    p = sub.add_parser("wire", help="Connect output of one node to input of another")
    p.add_argument("source_id", help="Source node ID")
    p.add_argument("target_id", help="Target node ID")
    p.add_argument("--port", type=int, default=0, help="Output port index (default: 0)")
    p.add_argument("--dry-run", action="store_true")

    # unwire
    p = sub.add_parser("unwire", help="Remove a wire between two nodes")
    p.add_argument("source_id", help="Source node ID")
    p.add_argument("target_id", help="Target node ID")
    p.add_argument("--port", type=int, default=None, help="Specific output port")
    p.add_argument("--all-ports", action="store_true", help="Remove from all ports")
    p.add_argument("--dry-run", action="store_true")

    # link
    p = sub.add_parser("link", help="Create link connection between link nodes")
    p.add_argument("source_id", help="ID of link out (mode=link) or link call node")
    p.add_argument("target_id", help="ID of link in node")
    p.add_argument("--dry-run", action="store_true")

    # unlink
    p = sub.add_parser("unlink", help="Remove a link connection")
    p.add_argument("source_id", help="ID of link out (mode=link) or link call node")
    p.add_argument("target_id", help="ID of link in node")
    p.add_argument("--dry-run", action="store_true")

    # add-group
    p = sub.add_parser("add-group", help="Create a new group")
    p.add_argument("--on", required=True, dest="flow_id",
                   help="Tab/subflow to create the group on")
    p.add_argument("--name", required=True, help="Group name")
    p.add_argument("--nodes", default="", help="Comma-separated list of node IDs to include")
    p.add_argument("--dry-run", action="store_true")

    # move-to-group
    p = sub.add_parser("move-to-group", help="Move a node into a group")
    p.add_argument("node_id", help="Node to move")
    p.add_argument("group_id", help="Target group")
    p.add_argument("--dry-run", action="store_true")

    # remove-from-group
    p = sub.add_parser("remove-from-group", help="Remove a node from its group")
    p.add_argument("node_id", help="Node to remove from its group")
    p.add_argument("--dry-run", action="store_true")

    # set-function
    p = sub.add_parser("set-function", help="Set JavaScript code of a function node")
    p.add_argument("node_id", help="ID of the function node")
    p.add_argument("--body", help="Main function body code")
    p.add_argument("--body-file", help="File containing main function body")
    p.add_argument("--setup", help="Setup/initialize code")
    p.add_argument("--setup-file", help="File containing setup code")
    p.add_argument("--cleanup", help="Cleanup/finalize code")
    p.add_argument("--cleanup-file", help="File containing cleanup code")
    p.add_argument("--dry-run", action="store_true")

    # batch
    p = sub.add_parser("batch", help="Execute multiple commands from stdin as JSON")
    p.add_argument("--dry-run", action="store_true")

    return parser


# ---------------------------------------------------------------------------
# Command dispatch
# ---------------------------------------------------------------------------

COMMANDS = {
    "add-node": cmd_add_node,
    "update-node": cmd_update_node,
    "delete-node": cmd_delete_node,
    "wire": cmd_wire,
    "unwire": cmd_unwire,
    "link": cmd_link,
    "unlink": cmd_unlink,
    "add-group": cmd_add_group,
    "move-to-group": cmd_move_to_group,
    "remove-from-group": cmd_remove_from_group,
    "set-function": cmd_set_function,
    "batch": cmd_batch,
}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = build_parser()
    args = parser.parse_args()

    with open(args.flows) as f:
        data = json.load(f)

    msg = COMMANDS[args.command](data, args)
    if msg:
        print(msg)

    if not args.dry_run:
        write_normalized(data, args.flows)


if __name__ == "__main__":
    main()

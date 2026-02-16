# Implementation Plan: Node-RED Write Tools

## Overview

This plan details the implementation of the modify-nodered-flows tool suite as specified
in the [design plan](2026-02-16-nodered-write-tools.md). It covers the Python script
(12 subcommands), bash wrapper, agent documentation, and CLAUDE.md updates.

## Files to Create/Modify

| File | Action |
|------|--------|
| `helper-scripts/modify-nodered-flows.py` | Create |
| `helper-scripts/modify-nodered-flows.sh` | Create |
| `docs/modifying-nodered-json.md` | Create |
| `CLAUDE.md` | Modify |

## 1. `helper-scripts/modify-nodered-flows.py`

### Structure and Import Pattern

Follow the exact importlib pattern from `relayout-nodered-flows.py` (lines 19-27):

```python
"""Modify a Node-RED flows JSON file.

Supports adding, updating, deleting, and wiring nodes -- so agents can
make flow changes without editing the JSON directly.

Usage: Called by modify-nodered-flows.sh, not directly.

# NOTE: If you change this script's commands, flags, output format, or
# behavior, update docs/modifying-nodered-json.md to match.
"""

import importlib.util
import json
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
```

### Normalization: `write_normalized(data, path)`

Must produce byte-identical output to `normalize-json.sh`. Study the normalize script
carefully (lines 19-34 of `helper-scripts/normalize-json.sh`):

```python
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


def write_normalized(data, path):
    """Write flows JSON matching normalize-json.sh output exactly.

    Steps (must match normalize-json.sh):
    1. Recursively sort all dict keys alphabetically.
    2. Sort top-level array by 'id' field (if all elements are dicts with 'id').
    3. Write with json.dump(indent=2, ensure_ascii=False) + trailing newline.
    """
    data = [sort_keys_recursive(node) for node in data]
    # Top-level sort by id (matching normalize-json.sh line 30).
    if all(isinstance(e, dict) and "id" in e for e in data):
        data.sort(key=lambda e: e["id"])
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
```

Key details to get right:
- `ensure_ascii=False` -- the normalize script uses this (line 33 of normalize-json.sh).
- Trailing `\n` after json.dump (line 34 of normalize-json.sh).
- `indent=2` (line 33).
- `sorted(obj.items())` for dict keys -- Python's default `sort_keys=True` in json.dump
  would also work, but the normalize script does it at the data level, so we should too
  for identical behavior. Actually, applying `sort_keys_recursive` before calling
  `json.dump` means the data is already sorted, so json.dump with default `sort_keys=False`
  is fine. Do NOT also pass `sort_keys=True` to json.dump -- it would be redundant but harmless.
  However, to be safe and match exactly, just do the recursive sort and let json.dump write
  the pre-sorted data.

### ID Generation

```python
def generate_id(existing_ids):
    """Generate a unique 16-char lowercase hex ID."""
    while True:
        new_id = os.urandom(8).hex()
        if new_id not in existing_ids:
            return new_id
```

### Die / Error Utility

Follow the `die()` pattern from `query-nodered-flows.py` (line 267-269):

```python
def die(msg):
    print(f"Error: {msg}", file=sys.stderr)
    sys.exit(1)
```

### Constants

```python
# HA node types that need auto-populated `server` field.
HA_SERVER_NODE_TYPES = {
    "api-call-service", "server-state-changed", "trigger-state",
    "api-current-state", "poll-state", "api-get-history", "server-events",
    "ha-time", "ha-entity", "ha-button", "ha-sensor", "ha-webhook",
}

# Fields that cannot be changed via update-node.
IMMUTABLE_FIELDS = {"id", "type"}
```

### Arg Parsing Pattern

The query tool uses manual arg parsing (not argparse) in `main()` and passes `args` lists
to each `cmd_*` function. The relayout tool uses argparse. Since the modify tool has many
flags per command and needs robust parsing (especially for `--props` with JSON values
that could look like flags), use **argparse with subparsers**. This is more robust than
the manual approach for write operations where correctness matters.

```python
import argparse

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
```

### Command Implementations

Each `cmd_*` function receives `(data, args)` and returns a string message describing
what it did. The function modifies `data` in-place. On error, it calls `die()`.

For batch mode, each `cmd_*` function for batched commands receives `(data, op_args)` where
`op_args` is a dict from the JSON input, plus the `created_ids` list for `$N` resolution.

#### Helper: Find HA server config node

```python
def find_ha_server_id(data):
    """Find the single HA server config node ID, or None if ambiguous."""
    servers = [n for n in data if n.get("type") == "server"]
    if len(servers) == 1:
        return servers[0]["id"]
    return None
```

#### `cmd_add_node(data, args)` -- Implementation Details

1. Parse `--props` as JSON. Validate it's a dict.
2. Find the flow node (by `args.flow_id`). Validate it exists and is type `tab` or `subflow`.
3. If `--group`, find the group node. Validate it exists, is type `group`, and has `z == flow_id`.
4. Determine `outputs` from props (default 1 for most types, 0 for types like `link in`,
   `debug`, `link out`). Initialize `wires` as `[[] for _ in range(outputs)]`.
5. Build the node dict:
   ```python
   existing_ids = {n["id"] for n in data if "id" in n}
   new_id = generate_id(existing_ids)
   node = {
       "id": new_id,
       "type": args.type,
       "z": args.flow_id,
       "name": args.name,
       "x": 200,
       "y": 200,
       "wires": wires,
   }
   ```
6. If `--group`, set `node["g"] = args.group_id`.
7. If the type is in `HA_SERVER_NODE_TYPES` and `"server"` not in props, auto-set from
   `find_ha_server_id(data)`.
8. Merge props over node (shallow): `node.update(props)`.
   This lets agents override `wires`, `x`, `y`, etc. via props.
9. Append node to `data`.
10. If `--group`, add `new_id` to the group's `nodes` array.
11. Return the new ID and the output message string.

Output format: `added <id> <type> "<name>" on=<flow_id> [group=<group_id>]`

Special type handling:
- Types with 0 default outputs: `link in` (0 -- wait, `link in` actually has normal wires
  for downstream, so default is 1), `debug` (0 outputs). Actually let me re-examine:
  - `debug`: 0 outputs by default
  - `link out`: 0 outputs (uses `links`, not `wires`)
  - `link in`: 1 output (has normal `wires` for downstream)
  - `link call`: 1 output (returns come back on its output)
  - `junction`: 1 output
  - Most types: 1 output
  - `switch`: depends on rules (default 1, but agent should set `outputs` in props)
  - `function`: depends (default 1, agent sets `outputs` in props if >1)

For simplicity, default `outputs` to 1 unless the type is `debug` or `link out`
(where outputs is 0). Agents can override with `--props '{"outputs": N}'` and the
`wires` array will be sized accordingly.

Wait -- we need to be careful. The `outputs` field and the `wires` array size should match.
The approach:
1. Start with `outputs = 1` as default.
2. If type is in a known-zero-output set (`{"debug", "link out"}`), default to 0.
3. If props contains `"outputs"`, use that value.
4. Build `wires` from the `outputs` count: `[[] for _ in range(outputs)]`.
5. If props contains `"wires"`, that overrides the auto-generated wires.

#### `cmd_update_node(data, args)` -- Implementation Details

1. Parse `--props` as JSON. Validate it's a dict.
2. Find the node by `args.node_id`. Error if not found.
3. Check for immutable fields: if props contains `"id"` or `"type"`, error.
4. If `--name` is provided, add it to props: `props["name"] = args.name`.
5. Record which fields will change (for output message).
6. Shallow merge: `node.update(props)`.
7. Return output message.

Output format: `updated <id> <type> "<name>" changed=[field1, field2, ...]`

Note on `z` changes: The design plan says to warn but allow changes to `z`. Print a
warning to stderr: `"Warning: changing z (flow assignment) -- ensure wiring is still valid"`.

#### `cmd_delete_node(data, args)` -- Implementation Details

1. Find the node by `args.node_id`. Error if not found.
2. Refuse if type is `tab`: `die("cannot delete a tab node -- too destructive")`.
3. Refuse if type is `subflow` and instances exist (check `idx["subflow_instances"]`).
4. If type is `group`: collect all member node IDs recursively via `collect_group_node_ids`.
   Delete each member first (recursive call or iterative), then delete the group itself.
5. Remove from wires: scan all nodes, remove `node_id` from any `wires` inner arrays.
6. Remove from links: scan all nodes, remove `node_id` from any `links` arrays.
7. Remove from parent group: if node has `g` field, find that group and remove `node_id`
   from its `nodes` array.
8. Remove the node from `data`.

Output format:
```
deleted <id> <type> "<name>"
  cleaned wires: [<list of node IDs>]
  cleaned links: [<list of node IDs>]
  cleaned group: <group_id>
```

Implementation approach: Since we need to track what was cleaned, build up lists of
affected node IDs as we clean.

Note: When deleting recursively (group with members), we need to be careful about order.
Delete leaf members first, then nested groups, then the top group. Or simpler: collect
all IDs to delete first, then do a single pass to clean up all references, then remove
all collected nodes from `data`.

#### `cmd_wire(data, args)` -- Implementation Details

1. Find source and target nodes. Error if not found.
2. Get `port` from args (default 0).
3. Extend `source["wires"]` with empty arrays if `port >= len(source["wires"])`.
4. If `target_id` already in `source["wires"][port]`, print "already wired" and return.
5. Append `target_id` to `source["wires"][port]`.
6. If source and target have different `z` values, print warning to stderr.
7. If source == target, print warning to stderr (but still allow).

Output format: `wired <source_id>:<port> -> <target_id>`

#### `cmd_unwire(data, args)` -- Implementation Details

1. Find source and target nodes. Error if not found.
2. If `--all-ports`: iterate all ports, remove target_id from each.
3. Else: use `--port` (default 0 if not specified and `--all-ports` not set).
   Remove target_id from `source["wires"][port]` if present.
4. Track which ports were actually unwired.

Output format: `unwired <source_id>:<port> -> <target_id>` (one line per port if `--all-ports`)

#### `cmd_link(data, args)` -- Implementation Details

1. Find source and target nodes. Error if not found.
2. Validate source is `link out` (mode=link) or `link call`. Error otherwise.
3. Validate target is `link in`. Error otherwise.
4. Add target_id to source's `links` array if not already present.
5. Add source_id to target's `links` array if not already present.
6. Both idempotent -- check before adding.

Output format: `linked <source_id> (<type>) -> <target_id> (link in)`

#### `cmd_unlink(data, args)` -- Implementation Details

1. Find source and target. Error if not found.
2. Remove target_id from source's `links`.
3. Remove source_id from target's `links`.

Output format: `unlinked <source_id> -> <target_id>`

#### `cmd_add_group(data, args)` -- Implementation Details

1. Validate flow_id exists and is tab/subflow.
2. Parse `--nodes` (comma-separated) into list. Filter empty strings.
3. For each member node ID:
   - Validate it exists.
   - Validate `z` matches flow_id.
   - If it has a `g` field pointing to another group, and that group is NOT also
     in the member list, error (can't steal from another group).
4. Generate new group ID.
5. Create group node:
   ```python
   group = {
       "id": new_id,
       "type": "group",
       "z": args.flow_id,
       "name": args.name,
       "nodes": member_ids,
       "style": {"label": True},
       "x": 10,
       "y": 10,
       "w": 200,
       "h": 100,
   }
   ```
6. Set `g` field on each member node to new group ID.
7. Append group to `data`.

Output format: `added group <id> "<name>" on=<flow_id> members=[<count> nodes]`

#### `cmd_move_to_group(data, args)` -- Implementation Details

1. Find node and group. Error if not found.
2. Validate group is type `group`.
3. Validate node and group are on same flow (same `z`).
4. If node has existing `g`, remove node from old group's `nodes` array.
5. Set node's `g` to new group ID.
6. Add node's ID to new group's `nodes` array.

Output format: `moved <node_id> to group <group_id> "<group_name>" (from group <old>|ungrouped)`

#### `cmd_remove_from_group(data, args)` -- Implementation Details

1. Find node. Error if not found.
2. If node has no `g`, print "not in a group" and return (no-op).
3. Find the group, remove node_id from its `nodes` array.
4. Delete the `g` key from node.

Output format: `removed <node_id> from group <group_id> "<group_name>"`

#### `cmd_set_function(data, args)` -- Implementation Details

1. Find node. Error if not found.
2. Validate type is `function`.
3. For each of body/setup/cleanup:
   - If `--body-file` given, read file contents (error if not found).
   - If `--body` given, use directly.
   - If neither, leave existing value unchanged.
4. Set `func`, `initialize`, `finalize` fields as appropriate.
5. Count lines for output.

Output format: `set-function <id> "<name>" [body: <n> lines] [setup: <n> lines] [cleanup: <n> lines]`

Only show the sections that were actually changed.

#### `cmd_batch(data, args)` -- Implementation Details

This is the most complex command. Key design:

1. Read JSON from stdin. Parse as array. Error if not array.
2. Work on a deep copy of `data` so we can abort without side effects.
3. Maintain `created_ids = []` -- list of IDs generated by `add-node` and `add-group` ops.
4. For each operation in the array:
   a. Resolve `$N` references in all string values in `args` dict.
   b. Map `"command"` to the appropriate handler.
   c. Execute it on the copy.
   d. If add-node or add-group, append the new ID to `created_ids`.
   e. Print `[N] <output message>`.
5. If all operations succeed, replace original `data` contents with the copy's contents.
6. Print `batch: N operations applied`.

`$N` resolution: Walk the `args` dict recursively. For any string value, replace `$0`, `$1`,
etc. with `created_ids[N]`. Error if N >= len(created_ids).

```python
def resolve_refs(value, created_ids):
    """Replace $N references with created IDs."""
    if isinstance(value, str):
        import re
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
```

Batch arg mapping -- the JSON `"args"` dict maps to the argparse namespace. We need a
mapping from batch arg names to the handler's expected interface. The simplest approach:
have each `cmd_*` function accept either an argparse.Namespace or have internal helper
functions that accept keyword args.

**Recommended approach**: Define internal `_cmd_*` functions that accept explicit keyword
arguments (the actual logic), and have the argparse-facing `cmd_*` functions just unpack
the namespace into calls to `_cmd_*`. The batch command calls `_cmd_*` directly with the
dict from JSON. This avoids duplicating logic.

```python
def _cmd_add_node(data, *, type, flow_id, name="", group_id=None,
                  props=None, dry_run=False):
    """Core logic for add-node. Returns (new_id, message)."""
    ...

def cmd_add_node(data, args):
    """Argparse wrapper."""
    props = json.loads(args.props)
    new_id, msg = _cmd_add_node(
        data, type=args.type, flow_id=args.flow_id, name=args.name,
        group_id=args.group_id, props=props, dry_run=args.dry_run,
    )
    return msg
```

For batch, the JSON args dict uses these key names (matching the design plan):
- add-node: `type`, `on` (maps to flow_id), `name`, `group`, `props`
- update-node: `node_id`, `props`, `name`
- delete-node: `node_id`
- wire: `source`, `target`, `port`
- unwire: `source`, `target`, `port`, `all_ports`
- link: `source`, `target`
- unlink: `source`, `target`
- add-group: `on`, `name`, `nodes` (comma-separated string or list)
- move-to-group: `node_id`, `group_id`
- remove-from-group: `node_id`
- set-function: `node_id`, `body`, `body_file`, `setup`, `setup_file`, `cleanup`, `cleanup_file`

The batch dispatcher translates these to `_cmd_*` kwargs:

```python
BATCH_DISPATCH = {
    "add-node": lambda data, a: _cmd_add_node(
        data, type=a["type"], flow_id=a["on"], name=a.get("name", ""),
        group_id=a.get("group"), props=a.get("props"), dry_run=False),
    "wire": lambda data, a: _cmd_wire(
        data, source_id=a["source"], target_id=a["target"],
        port=a.get("port", 0), dry_run=False),
    # ... etc
}
```

Important: batch `_cmd_add_node` and `_cmd_add_group` return `(new_id, message)` tuples.
Other commands return `(None, message)`. The batch loop checks for non-None IDs to append
to `created_ids`.

Deep copy approach: Use `import copy; copy.deepcopy(data)`. For a 1000+ node file this
is fast enough (milliseconds). The batch operates on the deep copy, and on success, we
replace the original list contents:

```python
data_copy = copy.deepcopy(data)
# ... run all ops on data_copy ...
# On success:
data.clear()
data.extend(data_copy)
```

### Main Function

```python
def main():
    parser = build_parser()
    args = parser.parse_args()

    with open(args.flows) as f:
        data = json.load(f)

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

    msg = COMMANDS[args.command](data, args)
    print(msg)

    if not args.dry_run:
        write_normalized(data, args.flows)


if __name__ == "__main__":
    main()
```

Wait -- the batch command has its own write logic (it should not write until all ops succeed).
But the main function calls `write_normalized` after the command. This is fine because:
- For non-batch commands, `cmd_*` modifies `data` in-place, then main writes.
- For batch, `cmd_batch` modifies `data` in-place only on full success (via the
  deep-copy-then-swap pattern), then main writes.

So the main function always writes. The `--dry-run` flag is checked in main to skip writing.
But batch also needs to suppress individual operation output in dry-run mode... Actually,
for batch dry-run, we still execute all ops (to validate them) but don't write. The batch
command itself prints `[N] ...` lines. In dry-run mode, it should add "(dry-run)" to output.

Revised main:

```python
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
```

For batch, `cmd_batch` prints its own output (the `[N]` lines) and returns the summary
line. For non-batch commands, the command returns a single message line.

### Full Implementation Order (within the .py file)

1. Module docstring and imports
2. Importlib section (query tool imports)
3. Constants (`HA_SERVER_NODE_TYPES`, `IMMUTABLE_FIELDS`, zero-output types)
4. Utility functions: `die`, `generate_id`, `sort_keys_recursive`, `write_normalized`,
   `find_ha_server_id`, `resolve_refs`
5. Core logic functions: `_cmd_add_node`, `_cmd_update_node`, `_cmd_delete_node`,
   `_cmd_wire`, `_cmd_unwire`, `_cmd_link`, `_cmd_unlink`, `_cmd_add_group`,
   `_cmd_move_to_group`, `_cmd_remove_from_group`, `_cmd_set_function`
6. Argparse wrapper functions: `cmd_add_node`, etc. (these parse args and call `_cmd_*`)
7. `cmd_batch` (uses `_cmd_*` directly)
8. `build_parser`
9. `COMMANDS` dict
10. `main`

### Edge Cases to Handle

- **`--props` with `wires` override**: If agent passes `wires` in props, it replaces the
  auto-generated wires array entirely.
- **`--props` with `outputs` override**: If agent passes `outputs`, regenerate wires to
  match (unless wires is also in props).
- **Empty `links` and `nodes` arrays**: Some nodes have empty arrays. Preserve them.
  When adding to a group that has `"nodes": []`, just append.
- **Missing `wires` on source node**: Some config nodes have no `wires` field. When
  `cmd_wire` needs to add a wire, create the `wires` field if missing.
- **Missing `links` on link nodes**: Create if missing.
- **Node deletion order in group recursive delete**: Collect all IDs first, then clean
  refs in one pass, then filter `data` to remove all collected IDs. This avoids issues
  with nested groups pointing to already-deleted members.

## 2. `helper-scripts/modify-nodered-flows.sh`

Follows the exact pattern of `query-nodered-flows.sh` (18 lines). The only difference
is the script name and a slightly different usage message since `batch` only requires
the flows file (the command comes from stdin).

```bash
#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: modify-nodered-flows.sh <flows.json> <command> [args...]" >&2
  echo "Run with --help for full command list." >&2
  exit 1
fi

FLOWS_FILE="$1"

if [[ ! -f "$FLOWS_FILE" ]]; then
  echo "Error: file not found: $FLOWS_FILE" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/modify-nodered-flows.py" "$@"
```

This is nearly identical to `query-nodered-flows.sh`. Make it executable: `chmod +x`.

## 3. `docs/modifying-nodered-json.md`

This is the agent-facing documentation. It should mirror `docs/exploring-nodered-json.md`
in style -- practical, workflow-oriented, with lots of examples.

### Document Structure

```markdown
# Modifying Node-RED Flows JSON

This guide teaches agents how to modify Node-RED flows using the
`helper-scripts/modify-nodered-flows.sh` tool. [Intro paragraph explaining
that this is the write companion to the read tools.]

## Before You Start

[Brief reminders:]
- Read `docs/exploring-nodered-json.md` first if you haven't -- understand the
  read tools before using write tools.
- Always query existing similar nodes as templates before creating new ones.
- The modify tool handles normalization automatically (sorted keys, sorted array).
- Positions don't matter -- the relayout tool handles positioning before upload.

## Commands Reference

### add-node

[Full syntax, explanation, examples]

### update-node

[Full syntax, explanation, examples]

### delete-node

[Full syntax, explanation, examples -- including recursive group deletion]

### wire

[Full syntax, explanation, examples]

### unwire

[Full syntax, explanation, examples]

### link

[Full syntax, explanation, examples]

### unlink

[Full syntax, explanation, examples]

### add-group

[Full syntax, explanation, examples]

### move-to-group

[Full syntax, explanation, examples]

### remove-from-group

[Full syntax, explanation, examples]

### set-function

[Full syntax, explanation, examples -- including --body-file pattern]

### batch

[Full syntax, $N reference system, examples]

## Workflows

### "Add a simple automation (trigger -> action)"

[Step by step with batch mode example]

### "Add a node to an existing chain"

[Show: query existing chain, add node, wire into the chain]

### "Replace a node's logic"

[Show: update-node or set-function for function nodes]

### "Remove a node from a chain"

[Show: query connected to understand wiring, unwire, delete-node]

### "Move automation logic to a new group"

[Show: add-group, move-to-group]

### "Build a complex automation from scratch"

[Full batch example with multiple nodes, wiring, and group]

### "End-to-end workflow: modify, verify, deploy"

[Full workflow: read -> query -> modify -> diff -> upload]

## Tips

- Always use batch mode for multi-step operations (atomic, faster).
- Query existing similar nodes as templates for --props.
- The --dry-run flag is your friend -- verify before committing changes.
- Positions are irrelevant -- relayout handles them.
- After modifying, run the diff summary to verify and find docs to update.
- HA server node types get auto-configured -- you don't need to specify `server`.
```

### Key Content Details for the Doc

For each command, include:
1. Full syntax line
2. What it does (1-2 sentences)
3. Important flags explained
4. At least one concrete example (using realistic-looking IDs)
5. Output format shown

For the batch section, be especially thorough:
- Explain the JSON format
- Explain `$N` references with a clear example
- Show that `$0` refers to the first add-node/add-group's created ID
- Show error behavior (entire batch rolls back)

For workflows, use the same style as `exploring-nodered-json.md` -- numbered steps
with shell commands and brief explanations. The "Add a simple automation" workflow
should mirror the example from the design plan but be more annotated.

## 4. CLAUDE.md Updates

### Helper Scripts Section

Add this entry after the existing `relayout-nodered-flows.sh` entry (maintaining
alphabetical-ish order isn't required -- group it near the query tool for logical flow):

```markdown
- `helper-scripts/modify-nodered-flows.sh <flows.json> <command> [args...]` - Modifies a flows JSON file: add/update/delete nodes, wire/unwire connections, link/unlink link nodes, manage groups, set function code, and batch multiple operations atomically. Commands: `add-node`, `update-node`, `delete-node`, `wire`, `unwire`, `link`, `unlink`, `add-group`, `move-to-group`, `remove-from-group`, `set-function`, `batch`. Output is auto-normalized (sorted keys, sorted by id). Use `--dry-run` on any command to preview changes.
```

### Deep-dive Documentation Section

Add a new bullet:

```markdown
- `docs/modifying-nodered-json.md` -- How to use `modify-nodered-flows.sh` to make
  changes to Node-RED flows. Covers all commands, batch operations, and end-to-end
  modification workflows. **Load when:** making changes to `mynodered/nodered.json`,
  adding new automations, or modifying existing ones.
```

### Working with Automations Section

Add a step 2.5 (or update step 2) mentioning that agents should also load the modify
doc when making changes:

Current step 2 says to load `docs/exploring-nodered-json.md`. Add after it:
```
2b. If you'll be modifying flows, also load `docs/modifying-nodered-json.md`.
```

Or restructure the numbered list to include it. The simplest edit: add to step 2:

```
2. Load `docs/exploring-nodered-json.md` for guidance on using the flow analysis tools.
   If you'll be modifying flows, also load `docs/modifying-nodered-json.md` for the
   write tool reference.
```

## Implementation Order

1. **`modify-nodered-flows.py`** -- The bulk of the work. Build and test incrementally:
   a. Skeleton: imports, parser, main, write_normalized, die, generate_id
   b. `add-node` + `wire` (the most common pair)
   c. `delete-node` + `unwire` (cleanup commands)
   d. `update-node`
   e. `link` + `unlink`
   f. `add-group` + `move-to-group` + `remove-from-group`
   g. `set-function`
   h. `batch`
2. **`modify-nodered-flows.sh`** -- Trivial, write alongside step 1a.
3. **`docs/modifying-nodered-json.md`** -- Write after the tool works.
4. **`CLAUDE.md` updates** -- Last, once the doc exists to reference.

## Testing Strategy

### Verification Commands

After implementing, test with the real `mynodered/nodered.json` file (on a git branch
or using `--dry-run`).

1. **Normalization equivalence test**:
   ```bash
   # Copy the file, run normalize, then run modify dry-run, compare
   cp mynodered/nodered.json /tmp/test-flows.json
   bash helper-scripts/normalize-json.sh /tmp/test-flows.json /tmp/norm1.json
   # Add a node then immediately delete it -- file should be identical to normalized
   bash helper-scripts/modify-nodered-flows.sh /tmp/test-flows.json \
     add-node inject --on <any_flow_id> --name "test"
   # Capture the new ID from output
   bash helper-scripts/modify-nodered-flows.sh /tmp/test-flows.json \
     delete-node <new_id>
   diff /tmp/norm1.json /tmp/test-flows.json
   # Should be identical (proving normalization matches)
   ```

2. **Add node and verify with query tool**:
   ```bash
   bash helper-scripts/modify-nodered-flows.sh /tmp/test-flows.json \
     add-node function --on <flow_id> --name "Test func" --props '{"outputs": 2}'
   # Note the ID
   bash helper-scripts/query-nodered-flows.sh /tmp/test-flows.json node <new_id>
   # Verify: type=function, name="Test func", wires=[[], []], z=<flow_id>
   ```

3. **Wire and verify**:
   ```bash
   bash helper-scripts/modify-nodered-flows.sh /tmp/test-flows.json \
     wire <new_id> <existing_id>
   bash helper-scripts/query-nodered-flows.sh /tmp/test-flows.json \
     connected <new_id> --forward --summary
   # Should show existing_id downstream
   ```

4. **Batch test with $N refs**:
   ```bash
   bash helper-scripts/modify-nodered-flows.sh /tmp/test-flows.json batch <<'EOF'
   [
     {"command": "add-node", "args": {"type": "inject", "on": "<flow_id>", "name": "Batch trigger"}},
     {"command": "add-node", "args": {"type": "debug", "on": "<flow_id>", "name": "Batch debug"}},
     {"command": "wire", "args": {"source": "$0", "target": "$1"}}
   ]
   EOF
   # Should show 3 operations, verify with query
   ```

5. **Dry-run verification** (no file changes):
   ```bash
   md5 /tmp/test-flows.json > /tmp/before.md5
   bash helper-scripts/modify-nodered-flows.sh /tmp/test-flows.json \
     add-node inject --on <flow_id> --dry-run
   md5 /tmp/test-flows.json > /tmp/after.md5
   diff /tmp/before.md5 /tmp/after.md5
   # Should match
   ```

6. **Integration with diff summary**:
   ```bash
   # Make changes on a git-tracked copy, then run diff summary
   bash helper-scripts/summarize-nodered-flows-diff.sh --git /tmp/test-flows.json
   ```

7. **Integration with relayout**:
   ```bash
   # After adding nodes to a group, run relayout
   bash helper-scripts/relayout-nodered-flows.sh /tmp/test-flows.json --verbose
   ```

## Risks and Considerations

### Normalization byte-for-byte match
The most critical risk. If `write_normalized` produces different output than
`normalize-json.sh` for the same logical content, every modify operation will create
a massive git diff. Test with the equivalence test above.

### Batch atomicity
The deep-copy approach is simple and correct. The risk is that `copy.deepcopy` on a large
list of dicts could be slow -- but for ~1000 nodes of modest size, it should be well under
a second.

### argparse vs manual parsing
The query tool uses manual parsing, but argparse is better for the modify tool because:
- Write operations need robust validation (e.g., `--props` JSON could contain `--` strings)
- Subcommands with different required args map cleanly to argparse subparsers
- Error messages are automatic and helpful

The downside is that argparse consumes `sys.argv`, so the `--help` flag shows Python's
auto-generated help. This is fine -- it's supplementary to the doc.

### Link node mode validation
The `link` command must validate that `link out` nodes have `mode == "link"` (not `"return"`).
A `link out` with mode `"return"` should not be manually linked -- its return target is
implicit. The error message should explain this.

### Group nesting
When adding a node to a group, we only set the node's `g` field and add to the immediate
group's `nodes` array. We do NOT add to ancestor groups. This matches Node-RED's data model.

### Props merging is shallow
The design plan specifies shallow merge. This means if a node has
`{"entities": {"entity": ["a"], "regex": []}}` and you pass
`--props '{"entities": {"entity": ["b"]}}'`, the entire `entities` object is replaced
(losing `"regex"`). The doc should warn about this and advise using the full nested object
in props.

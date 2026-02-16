# Plan: Node-RED Write Tools

## Problem Statement

Agents have excellent read-only tools for navigating `mynodered/nodered.json` (a flat JSON array of 1000+ objects), but no tools for _writing_ changes. Currently, to modify a flow, an agent would have to read, understand, and directly edit the JSON file -- which is impractical at this scale and error-prone given the interconnected ID references, wire arrays, group membership, and position metadata.

We need a set of write tools that let agents safely add, modify, wire, and delete nodes without understanding the low-level JSON structure.

## Current State Analysis

### The JSON format

`nodered.json` is a flat JSON array. Every object has an `id` and `type`. Key relationships:

- **`z` field**: Points a node to its parent flow tab or subflow definition.
- **`g` field**: Points a node to its parent group.
- **`wires` field**: `[[id, id], [id]]` -- array of arrays, one per output port, listing downstream node IDs.
- **`links` field**: Used by `link in`, `link out` (mode=link), `link call` to reference partner link nodes.
- **Group `nodes` array**: Lists member node IDs (must stay in sync with members' `g` fields).
- **IDs**: 15-16 character lowercase hex strings (e.g., `90fdf70dd7cf3bc1`). One legacy config node uses a dot format (`44af031a.8180bc`).

### Existing read tools

- `query-nodered-flows.py` (via `.sh` wrapper): `node`, `function`, `connected`, `head-nodes`, `tail-nodes`, `flow-nodes`, `group-nodes`, `subflow-nodes`, `subflow-instances`, `search`
- `summarize-nodered-flows.py` (via `.sh` wrapper): Full overview of flows, groups, entities, etc.
- `summarize-nodered-flows-diff.py` (via `.sh` wrapper): Diff-aware summary with change tracking.

### Existing write-adjacent tools

- `normalize-json.sh`: Sorts keys and arrays by ID for stable diffs. The write tool should produce normalized output.
- `relayout-nodered-flows.sh`: Auto-relayouts groups with structural changes. Runs before upload. The write tool does NOT need to worry about layout -- relayout handles it.
- `upload-flows.sh`: Pipeline is relayout -> check divergence -> confirm -> upload.

### Patterns in the codebase

- Shell wrapper (`.sh`) calls Python script (`.py`). The shell script handles arg parsing, file existence checks, and git operations (extracting HEAD versions). The Python does the real work.
- Python scripts import from `query-nodered-flows.py` using `importlib.util` for shared utilities like `build_index` and `collect_group_node_ids`.
- Output normalization (sorted keys, sorted arrays by id) is done by `normalize-json.sh` and should be done by the write tool when saving.

## Design Decisions

### One script with subcommands (like query)

The write tool follows the same pattern as the read tool: a single `modify-nodered-flows.sh` / `modify-nodered-flows.py` with subcommands. This keeps the interface consistent and familiar to agents.

### Python implementation

Python, matching the existing tools. Imports shared utilities from `query-nodered-flows.py`.

### Modify in-place by default

The tool modifies `nodered.json` in-place (like `relayout-nodered-flows.py` does). This matches the workflow: agents make a series of changes to the working file, then run the diff summary to review, then upload.

A `--dry-run` flag on all commands shows what would change without writing.

### Normalized output

After every modification, the file is written with sorted keys and the top-level array sorted by `id` (matching `normalize-json.sh` behavior). This ensures stable diffs.

### ID generation

New nodes get randomly generated 16-character lowercase hex IDs (`os.urandom(8).hex()`). The tool verifies uniqueness against all existing IDs before assigning.

### Position handling

The write tool assigns default positions (`x: 200, y: 200`) for new nodes. The relayout tool handles proper positioning before upload. Agents should not need to think about positions.

### Validation

Every command validates referential integrity before writing:
- All `z` values point to existing tab/subflow IDs
- All `g` values point to existing group IDs
- All wire targets exist
- All link partners exist
- Group `nodes` arrays are consistent with members' `g` fields

Validation errors are printed to stderr and abort the operation (exit 1).

### Composability

Commands output information that agents need for subsequent commands:
- `add-node` prints the new node's ID
- `add-group` prints the new group's ID
- `wire` confirms what was connected
- All commands print a concise summary to stdout describing what changed

### Batching via stdin

For complex multi-step operations (e.g., "add 3 nodes and wire them together"), the tool supports a `batch` command that reads a sequence of operations from stdin as JSON. This avoids the overhead of loading/parsing/writing the 1000+ node file for every single operation.

## Proposed Solution: `modify-nodered-flows.sh` / `modify-nodered-flows.py`

### Architecture

```
helper-scripts/modify-nodered-flows.sh   <-- bash wrapper (file checks, delegates to Python)
helper-scripts/modify-nodered-flows.py   <-- all logic
```

The Python script imports `build_index` and `collect_group_node_ids` from `query-nodered-flows.py` (same pattern as the other scripts).

### Commands

#### 1. `add-node <flows.json> <type> [--on <flow_id>] [--name <name>] [--group <group_id>] [--props <json>] [--dry-run]`

Add a new node to a flow.

**Arguments:**
- `<type>`: Node type string (e.g., `function`, `api-call-service`, `switch`, `change`, `inject`, `debug`, `junction`, `link in`, `link out`, `link call`, `delay`).
- `--on <flow_id>`: (Required) ID of the tab or subflow to place the node on. Sets the `z` field.
- `--name <name>`: (Optional) Human-readable name for the node.
- `--group <group_id>`: (Optional) Group to add the node to. Sets `g` and adds the ID to the group's `nodes` array.
- `--props <json>`: (Optional) JSON object of additional properties to set on the node. This is how agents set type-specific fields like `func` (for function nodes), `entityId` (for api-call-service), `rules` (for switch nodes), etc.
- `--dry-run`: Print what would be added without modifying the file.

**Behavior:**
- Generates a unique 16-char hex ID.
- Sets core fields: `id`, `type`, `z`, `name` (if provided), `g` (if provided), `wires` (empty, based on type defaults), `x`, `y` (defaults).
- Merges `--props` over the base fields (so agents can override anything).
- For nodes requiring a `server` field (HA node types like `api-call-service`, `server-state-changed`, `trigger-state`, `api-current-state`, `poll-state`, `api-get-history`, `server-events`), auto-sets `server` to the existing HA server config node ID if exactly one exists and `--props` doesn't specify one.
- Validates: flow_id exists and is a tab/subflow, group_id exists and is a group on the same flow.
- If `--group` is specified, adds the new node's ID to the group's `nodes` array.
- Writes normalized JSON.

**Output (stdout):**
```
added <id> <type> "<name>" on=<flow_id> group=<group_id>
```

**Error cases:**
- Flow ID doesn't exist or isn't a tab/subflow.
- Group ID doesn't exist, isn't a group, or is on a different flow.
- `--props` is not valid JSON.

#### 2. `update-node <flows.json> <node_id> [--props <json>] [--name <name>] [--dry-run]`

Update properties on an existing node.

**Arguments:**
- `<node_id>`: ID of the node to modify.
- `--props <json>`: JSON object of properties to set/update. Merges with existing properties (top-level only; nested objects are replaced wholesale).
- `--name <name>`: Shorthand for `--props '{"name": "..."}'`.
- `--dry-run`: Print what would change without modifying the file.

**Behavior:**
- Finds the node by ID.
- Merges `--props` into the existing node dict (shallow merge at top level).
- Does NOT allow changing `id`, `type`, or `z` via this command (these are structural -- use `move-node` for `z` changes, and `id`/`type` are immutable).
- Writes normalized JSON.

**Output (stdout):**
```
updated <id> <type> "<name>" changed=[field1, field2, ...]
```

**Error cases:**
- Node ID doesn't exist.
- Attempting to change `id` or `type`.
- `--props` is not valid JSON.

#### 3. `delete-node <flows.json> <node_id> [--dry-run]`

Delete a node and clean up all references to it.

**Arguments:**
- `<node_id>`: ID of the node to delete.
- `--dry-run`: Print what would be deleted/cleaned without modifying.

**Behavior:**
- Removes the node from the top-level array.
- Removes the node's ID from all `wires` arrays of other nodes (any output port referencing this ID).
- Removes the node's ID from all `links` arrays of link partner nodes.
- Removes the node's ID from its parent group's `nodes` array (if it has a `g` field).
- If the node IS a group: recursively deletes all member nodes first (including nested groups), then deletes the group itself.
- If the node is a tab: refuses (deleting a tab is too destructive for a single command -- use `delete-flow` if we ever need that).
- If the node is a subflow definition: refuses if any instances exist.

**Output (stdout):**
```
deleted <id> <type> "<name>"
  cleaned wires: [<list of node IDs that had wires to this node>]
  cleaned links: [<list of node IDs that had links to this node>]
  cleaned group: <group_id>
```

**Error cases:**
- Node ID doesn't exist.
- Node is a tab (not allowed).
- Node is a subflow with existing instances.

#### 4. `wire <flows.json> <source_id> <target_id> [--port <n>] [--dry-run]`

Connect the output of one node to the input of another.

**Arguments:**
- `<source_id>`: Node whose output port to connect from.
- `<target_id>`: Node whose input to connect to.
- `--port <n>`: (Optional, default 0) Which output port of the source to use. Zero-indexed.
- `--dry-run`: Print what would change without modifying.

**Behavior:**
- Adds `target_id` to `source.wires[port]`. Extends the `wires` array with empty arrays if the port index is beyond current length.
- No-op if the wire already exists (idempotent).
- Validates both nodes exist and are on the same flow (or warns if cross-flow wiring, which is unusual but not forbidden for certain node types).

**Output (stdout):**
```
wired <source_id>:<port> -> <target_id>
```
Or if already wired:
```
already wired <source_id>:<port> -> <target_id>
```

**Error cases:**
- Source or target node doesn't exist.
- Self-wiring (source == target) -- warn but allow.

#### 5. `unwire <flows.json> <source_id> <target_id> [--port <n>] [--all-ports] [--dry-run]`

Remove a wire between two nodes.

**Arguments:**
- `<source_id>`: Source node.
- `<target_id>`: Target node.
- `--port <n>`: (Optional) Specific output port. If omitted and `--all-ports` is not set, defaults to port 0.
- `--all-ports`: Remove the target from ALL output ports of the source.
- `--dry-run`: Print what would change without modifying.

**Behavior:**
- Removes `target_id` from `source.wires[port]` (or all ports with `--all-ports`).
- No-op if the wire doesn't exist.

**Output (stdout):**
```
unwired <source_id>:<port> -> <target_id>
```

**Error cases:**
- Source or target node doesn't exist.

#### 6. `link <flows.json> <link_out_or_call_id> <link_in_id> [--dry-run]`

Create a link connection between a `link out` (mode=link) or `link call` node and a `link in` node.

**Arguments:**
- `<link_out_or_call_id>`: ID of a `link out` (mode=link) or `link call` node.
- `<link_in_id>`: ID of a `link in` node.
- `--dry-run`: Print what would change without modifying.

**Behavior:**
- Adds `link_in_id` to the `links` array of the link-out/call node.
- Adds `link_out_or_call_id` to the `links` array of the link-in node.
- Both additions are idempotent.
- Validates that the source is actually a `link out` (mode=link) or `link call`, and the target is actually a `link in`.

**Output (stdout):**
```
linked <source_id> (<type>) -> <target_id> (link in)
```

**Error cases:**
- Node IDs don't exist.
- Source is not a `link out` (mode=link) or `link call`.
- Target is not a `link in`.

#### 7. `unlink <flows.json> <link_out_or_call_id> <link_in_id> [--dry-run]`

Remove a link connection.

**Behavior:**
- Removes each ID from the other's `links` array.
- No-op if not linked.

#### 8. `add-group <flows.json> --on <flow_id> --name <name> [--nodes <id1,id2,...>] [--dry-run]`

Create a new group.

**Arguments:**
- `--on <flow_id>`: (Required) Tab/subflow to create the group on.
- `--name <name>`: (Required) Group name (these serve as documentation in Node-RED).
- `--nodes <id1,id2,...>`: (Optional) Comma-separated list of existing node IDs to include in the group. These nodes must be on the same flow, and must not already be in another group (unless you're nesting -- see below).
- `--dry-run`: Print what would change without modifying.

**Behavior:**
- Creates a new group node with `type: "group"`, `z`, `name`, `nodes`, `style: {"label": true}`, and default position/dimensions.
- Sets `g` field on each member node to the new group's ID.
- If a member node already has a `g` pointing to a different group, and that group is NOT being included in this new group, it's an error (can't steal nodes from another group). If the existing group IS listed as a member, that's valid nesting.
- Validates all member nodes exist and are on the same flow.

**Output (stdout):**
```
added group <id> "<name>" on=<flow_id> members=[<count> nodes]
```

**Error cases:**
- Flow doesn't exist.
- Member node IDs don't exist or are on a different flow.
- Member nodes are already in a non-nested group.

#### 9. `move-to-group <flows.json> <node_id> <group_id> [--dry-run]`

Move a node into a group (or between groups).

**Arguments:**
- `<node_id>`: Node to move.
- `<group_id>`: Target group.
- `--dry-run`: Print what would change without modifying.

**Behavior:**
- If the node is already in a group, removes it from that group's `nodes` array.
- Adds the node's ID to the target group's `nodes` array.
- Sets the node's `g` field to the target group ID.
- Validates the node and group are on the same flow.

**Output (stdout):**
```
moved <node_id> to group <group_id> "<group_name>" (from group <old_group_id>|ungrouped)
```

#### 10. `remove-from-group <flows.json> <node_id> [--dry-run]`

Remove a node from its group without deleting it.

**Behavior:**
- Removes the node's ID from its parent group's `nodes` array.
- Removes the `g` field from the node.
- No-op if node is not in any group.

**Output (stdout):**
```
removed <node_id> from group <group_id> "<group_name>"
```

#### 11. `set-function <flows.json> <node_id> [--body <code>] [--body-file <path>] [--setup <code>] [--setup-file <path>] [--cleanup <code>] [--cleanup-file <path>] [--dry-run]`

Set the JavaScript code of a function node. This is separate from `update-node --props` because function code is typically multi-line and awkward to pass as JSON.

**Arguments:**
- `<node_id>`: Must be a `function` node.
- `--body <code>` or `--body-file <path>`: Main function body (sets `func` field).
- `--setup <code>` or `--setup-file <path>`: Setup/initialize code (sets `initialize` field).
- `--cleanup <code>` or `--cleanup-file <path>`: Cleanup/finalize code (sets `finalize` field).
- Only the fields specified are changed; others are left as-is.

**Output (stdout):**
```
set-function <id> "<name>" [body: <n> lines] [setup: <n> lines] [cleanup: <n> lines]
```

**Error cases:**
- Node doesn't exist or isn't a `function` type.
- File path doesn't exist.

#### 12. `batch <flows.json> [--dry-run]`

Execute multiple commands from stdin as a JSON array of operations.

**Stdin format:**
```json
[
  {"command": "add-node", "args": {"type": "function", "on": "abc123", "name": "My Func", "props": {"outputs": 2}}},
  {"command": "wire", "args": {"source": "$0", "target": "existing_node_id", "port": 0}},
  {"command": "wire", "args": {"source": "$0", "target": "other_node_id", "port": 1}}
]
```

**Special references:**
- `$0`, `$1`, `$2`, etc. reference the node ID created by the 0th, 1st, 2nd `add-node` or `add-group` command in the batch. This enables "add a node, then wire it" without knowing the ID in advance.

**Behavior:**
- Loads the file once.
- Executes all operations sequentially, building up state.
- Runs validation after all operations.
- Writes the file once at the end.
- If any operation fails, aborts the entire batch and does not write (atomic).
- Prints each operation's output line as it executes.

**Output (stdout):**
```
[0] added abc123def456 function "My Func" on=abc123
[1] wired abc123def456:0 -> existing_node_id
[2] wired abc123def456:1 -> other_node_id
batch: 3 operations applied
```

**Error cases:**
- Invalid JSON on stdin.
- Any operation fails (entire batch is rolled back).
- `$N` reference is out of range or doesn't correspond to an add command.

### Commands NOT included (and why)

- **`add-flow` / `delete-flow`**: Creating/deleting entire flow tabs is rare and high-risk. Agents can do this via `add-node` with type `tab` if truly needed, but it's not worth a dedicated command.
- **`add-subflow` / `delete-subflow`**: Subflow definitions are complex (in/out ports, env vars, internal nodes). Creating one from scratch via CLI is impractical. Agents should create them in the Node-RED editor.
- **`move-node` (between flows)**: Changing a node's `z` to a different flow is risky (all wires to/from same-flow nodes become cross-flow). Not a common operation.
- **`copy-node` / `duplicate`**: Tempting but complex (need to deep-clone, assign new IDs, update internal references). Agents can achieve this with `add-node` + `update-node` for the properties.

## Implementation Steps

### Step 1: Create `helper-scripts/modify-nodered-flows.py`

The main Python script. Structure:

```python
"""Modify a Node-RED flows JSON file.

Supports adding, updating, deleting, and wiring nodes -- so agents can
make flow changes without editing the JSON directly.

Usage: Called by modify-nodered-flows.sh, not directly.

# NOTE: If you change this script's commands, flags, output format, or
# behavior, update docs/exploring-nodered-json.md to match.
"""

import json
import os
import sys
from collections import defaultdict

# Import shared utilities from query tool
_dir = os.path.dirname(os.path.abspath(__file__))
# ... importlib pattern from other scripts ...
build_index = _query.build_index
collect_group_node_ids = _query.collect_group_node_ids

def generate_id(existing_ids):
    """Generate a unique 16-char hex ID."""
    ...

def write_normalized(data, path):
    """Write flows JSON with sorted keys and sorted top-level array by id."""
    ...

# HA node types that need a `server` field auto-populated
HA_SERVER_NODE_TYPES = {
    'api-call-service', 'server-state-changed', 'trigger-state',
    'api-current-state', 'poll-state', 'api-get-history', 'server-events',
    'ha-time', 'ha-entity', 'ha-button', 'ha-sensor', 'ha-webhook',
}

# One cmd_* function per subcommand
def cmd_add_node(data, idx, args): ...
def cmd_update_node(data, idx, args): ...
def cmd_delete_node(data, idx, args): ...
def cmd_wire(data, idx, args): ...
def cmd_unwire(data, idx, args): ...
def cmd_link(data, idx, args): ...
def cmd_unlink(data, idx, args): ...
def cmd_add_group(data, idx, args): ...
def cmd_move_to_group(data, idx, args): ...
def cmd_remove_from_group(data, idx, args): ...
def cmd_set_function(data, idx, args): ...
def cmd_batch(data, idx, args): ...
```

Key implementation details:

- **`write_normalized()`**: Replicates `normalize-json.sh` logic in Python: recursively sort dict keys, sort top-level array by `id`, write with `indent=2` and trailing newline.
- **`generate_id()`**: `os.urandom(8).hex()`, retry if collision (astronomically unlikely but cheap to check).
- **Auto-server**: When adding HA node types, scan existing nodes for a single `type: "server"` node and auto-populate the `server` field.
- **Batch `$N` references**: Maintain a list of IDs created by add commands during the batch. Before executing each operation, string-replace `$N` patterns in all string values.
- **Immutable fields in update-node**: Hard-reject changes to `id` and `type`. Warn (but allow) changes to `z` with a message suggesting `move-node` considerations.

### Step 2: Create `helper-scripts/modify-nodered-flows.sh`

Minimal bash wrapper following the `query-nodered-flows.sh` pattern:

```bash
#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: modify-nodered-flows.sh <flows.json> <command> [args...]" >&2
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

### Step 3: Update `docs/exploring-nodered-json.md`

Add a new major section "Tool 3: modify-nodered-flows.sh" covering:
- Overview of the write tool
- All commands with examples
- The batch command with $N reference syntax
- Typical agent workflow (read -> query -> modify -> diff -> relayout -> upload)
- Rename the doc to something more general (or keep the name and note it covers both reading and writing)

### Step 4: Update `CLAUDE.md`

Add `modify-nodered-flows.sh` to the Helper Scripts section with a description matching the style of the existing entries.

## Agent Workflow (End-to-End)

Here's how an agent would use the read + write tools together for a typical task like "add a notification when the front door is left open for 5 minutes":

```bash
# 1. Understand current state
bash helper-scripts/summarize-nodered-flows.sh mynodered/nodered.json
# -> Find the relevant flow (e.g., "Security" flow, id=abc123)

# 2. Query existing nodes to understand the pattern
bash helper-scripts/query-nodered-flows.sh mynodered/nodered.json \
  search --name "door" --summary
# -> Find existing door-related automations to match patterns

# 3. Look at an existing similar automation for reference
bash helper-scripts/query-nodered-flows.sh mynodered/nodered.json \
  group-nodes <some_group_id> --full
# -> See full node configs to use as templates

# 4. Create nodes using batch mode for atomicity
bash helper-scripts/modify-nodered-flows.sh mynodered/nodered.json batch <<'EOF'
[
  {"command": "add-group", "args": {"on": "abc123", "name": "Notify when front door open 5min"}},
  {"command": "add-node", "args": {"type": "server-state-changed", "on": "abc123", "group": "$0",
    "name": "Front door opens",
    "props": {"entities": {"entity": ["binary_sensor.front_door"], "regex": [], "substring": []},
              "ifState": "on", "ifStateOperator": "is", "ifStateType": "str",
              "outputInitially": false, "stateType": "str"}}},
  {"command": "add-node", "args": {"type": "delay", "on": "abc123", "group": "$0",
    "name": "Wait 5 min",
    "props": {"timeout": "5", "timeoutUnits": "minutes", "pauseType": "delay"}}},
  {"command": "add-node", "args": {"type": "api-call-service", "on": "abc123", "group": "$0",
    "name": "Notify phone",
    "props": {"domain": "notify", "service": "mobile_app_drew",
              "data": "{\"message\": \"Front door has been open for 5 minutes\"}",
              "dataType": "json"}}},
  {"command": "wire", "args": {"source": "$1", "target": "$2"}},
  {"command": "wire", "args": {"source": "$2", "target": "$3"}}
]
EOF
# Output:
# [0] added group a1b2c3d4e5f67890 "Notify when front door open 5min" on=abc123 members=[0 nodes]
# [1] added f1e2d3c4b5a69870 server-state-changed "Front door opens" on=abc123 group=a1b2c3d4e5f67890
# [2] added 1234567890abcdef delay "Wait 5 min" on=abc123 group=a1b2c3d4e5f67890
# [3] added fedcba0987654321 api-call-service "Notify phone" on=abc123 group=a1b2c3d4e5f67890
# [4] wired f1e2d3c4b5a69870:0 -> 1234567890abcdef
# [5] wired 1234567890abcdef:0 -> fedcba0987654321
# batch: 6 operations applied

# 5. Verify the changes
bash helper-scripts/summarize-nodered-flows-diff.sh --git mynodered/nodered.json
# -> Review what changed, check affected documentation

# 6. Upload (relayout runs automatically)
bash upload-flows.sh
```

## Testing Strategy

### Unit-level verification

1. **Add a single node**, then query it back with the read tool:
   ```bash
   bash helper-scripts/modify-nodered-flows.sh mynodered/nodered.json \
     add-node inject --on <flow_id> --name "Test node"
   # Get the ID from output, then:
   bash helper-scripts/query-nodered-flows.sh mynodered/nodered.json node <new_id>
   ```

2. **Wire two nodes**, then verify with `connected`:
   ```bash
   bash helper-scripts/modify-nodered-flows.sh mynodered/nodered.json \
     wire <id1> <id2>
   bash helper-scripts/query-nodered-flows.sh mynodered/nodered.json \
     connected <id1> --forward --summary
   ```

3. **Delete a node**, then verify cleanup:
   ```bash
   bash helper-scripts/modify-nodered-flows.sh mynodered/nodered.json \
     delete-node <id>
   # Verify: node gone, wires cleaned, group updated
   bash helper-scripts/query-nodered-flows.sh mynodered/nodered.json node <id>
   # Should error: "node not found"
   ```

4. **Batch operations**, then verify end state.

5. **Dry-run** every command and verify no file changes:
   ```bash
   md5 mynodered/nodered.json
   bash helper-scripts/modify-nodered-flows.sh mynodered/nodered.json \
     add-node inject --on <flow_id> --dry-run
   md5 mynodered/nodered.json  # should match
   ```

### Integration verification

6. **Run the diff summary** after modifications:
   ```bash
   bash helper-scripts/summarize-nodered-flows-diff.sh --git mynodered/nodered.json
   ```
   Verify: new nodes show as [NEW], wiring changes appear, affected docs listed.

7. **Run relayout** on the modified file:
   ```bash
   bash helper-scripts/relayout-nodered-flows.sh mynodered/nodered.json --verbose
   ```
   Verify: groups with new nodes get relaid out.

8. **Round-trip test**: Make changes, upload to Node-RED, download, normalize both, and diff. Should be identical (proving the tool produces valid Node-RED JSON).

### Edge case tests

9. Delete a node that is wired to/from multiple nodes -- verify all references cleaned.
10. Delete a group -- verify all member nodes deleted and their references cleaned.
11. Wire to a port > current wires length -- verify array extended with empty arrays.
12. Batch with `$N` references -- verify correct ID substitution.
13. Batch where one operation fails -- verify no file changes (atomicity).
14. Add node to group that's nested inside another group -- verify only inner group's `nodes` updated.

## Risks and Considerations

### Output normalization must match normalize-json.sh exactly

If the write tool's normalization differs from `normalize-json.sh` even slightly (e.g., trailing whitespace, key ordering edge case), every write operation will produce a large diff. The Python implementation must produce byte-identical output to `normalize-json.sh` for the same input.

**Mitigation:** Test by running both on the same file and diffing the output.

### HA node type defaults are complex

Different HA node types have many fields with specific default values (e.g., `server-state-changed` has `ifState`, `ifStateOperator`, `forType`, etc.). The tool doesn't try to provide smart defaults for every field -- agents specify what they need via `--props`, and missing fields get whatever Node-RED does when it encounters them.

**Mitigation:** Agents should use the read tools to inspect existing similar nodes and use those as templates for `--props`.

### Wires arrays structure is subtle

`wires` is an array of arrays. Port 0's targets are in `wires[0]`, port 1's in `wires[1]`, etc. If a node has 2 output ports, `wires` should have 2 inner arrays. The write tool must maintain this structure correctly when adding/removing wires.

**Mitigation:** The `wire` command explicitly handles extending the array. The `add-node` command initializes `wires` with the correct number of empty arrays based on the `outputs` field in `--props` (defaulting to `[[]]` for 1 output).

### Batch error handling complexity

If operation 5 in a 10-operation batch fails, the tool must roll back operations 1-4. Rather than implementing undo logic, the tool simply operates on an in-memory copy and only writes to disk on full success.

### The server config node ID

There's exactly one `type: "server"` node with ID `44af031a.8180bc`. The auto-server feature should find this dynamically, not hard-code it. Some users might have multiple server configs.

### Group nesting validation

Groups can contain other groups. When adding a node to a group, the tool only modifies the immediate parent group's `nodes` array (not ancestor groups). This matches Node-RED's behavior: a node's `g` points to its direct parent group, and that group's `nodes` includes both regular nodes and nested group IDs.

# Modifying Node-RED Flows JSON

This guide teaches agents how to modify Node-RED flows using the
`helper-scripts/modify-nodered-flows.sh` tool. This is the write companion
to the read tools documented in `docs/exploring-nodered-json.md` -- read
that first if you haven't already, since understanding the read tools and
the JSON structure is essential before making changes.

## Before You Start

- **Verify the local copy is in sync with production** before making any changes:
  ```
  bash helper-scripts/check-nodered-flows-unchanged.sh mynodered/nodered-last-downloaded.json
  ```
  If this fails, stop and tell the user to run `bash download-flows.sh` first.
  This check only needs to happen once per user prompt, not per subagent.
- **Read `docs/exploring-nodered-json.md` first** if you haven't. Understand
  the read tools before using write tools.
- **Always query existing similar nodes as templates** before creating new ones.
  Use `query-nodered-flows.sh ... search --type <type> --summary` to find
  examples, then `node <id>` to see their full configuration. Copy the relevant
  fields into `--props`.
- **The modify tool handles normalization automatically.** Output is sorted by
  keys and by ID, matching `normalize-json.sh` exactly.
- **HA server config is auto-populated.** When adding HA node types
  (`api-call-service`, `server-state-changed`, `trigger-state`, etc.), the
  `server` field is auto-set if there's exactly one server config node.
- **Use `--dry-run` to preview** any command without modifying the file.

## Commands Reference

All commands follow this pattern:

```
helper-scripts/modify-nodered-flows.sh <flows.json> <command> [args...]
```

The `<flows.json>` argument is typically `mynodered/nodered.json`.

### add-node

Add a new node to a flow.

```
modify-nodered-flows.sh <flows.json> add-node <type> --on <flow_id> [--name <name>] [--group <group_id>] [--props <json>] [--dry-run]
```

**Arguments:**
- `<type>`: Node type string (e.g., `function`, `api-call-service`, `switch`,
  `change`, `inject`, `debug`, `junction`, `link in`, `link out`, `link call`,
  `delay`).
- `--on <flow_id>`: (Required) ID of the tab or subflow to place the node on.
- `--name <name>`: Human-readable name for the node.
- `--group <group_id>`: Group to add the node to.
- `--props <json>`: JSON object of additional properties. This is how you set
  type-specific fields like `func`, `entityId`, `rules`, `outputs`, etc.
- `--dry-run`: Print what would be added without modifying the file.

**Behavior:**
- Generates a unique 16-char hex ID.
- Sets core fields: `id`, `type`, `z`, `name`, `wires`, `x`, `y`.
- Defaults to 1 output port (empty `wires: [[]]`). Types `debug` and `link out`
  default to 0 output ports. Override with `--props '{"outputs": N}'`.
- Props are merged over the base fields (so you can override anything).

**Output:**
```
added <id> <type> "<name>" on=<flow_id> [group=<group_id>]
```

**Example:**
```bash
# Add a function node with 2 outputs to a flow, inside a group
bash helper-scripts/modify-nodered-flows.sh mynodered/nodered.json \
  add-node function --on d5bd27f8e3f4b6b4 --name "Route by state" \
  --group 855835066a0958b1 --props '{"outputs": 2}'
# Output: added a1b2c3d4e5f67890 function "Route by state" on=d5bd27f8e3f4b6b4 group=855835066a0958b1
```

### update-node

Update properties on an existing node.

```
modify-nodered-flows.sh <flows.json> update-node <node_id> [--props <json>] [--name <name>] [--dry-run]
```

**Arguments:**
- `<node_id>`: ID of the node to modify.
- `--props <json>`: JSON object of properties to set/update. Shallow merge at
  top level -- nested objects are replaced wholesale.
- `--name <name>`: Shorthand for setting the name property.

**Behavior:**
- Cannot change `id` or `type` (immutable fields -- will error).
- Changing `z` (flow assignment) prints a warning but is allowed.
- Shallow merge: if a node has `{"entities": {"entity": ["a"], "regex": []}}` and
  you pass `--props '{"entities": {"entity": ["b"]}}'`, the entire `entities`
  object is replaced (losing `"regex"`). Always pass the full nested object.

**Output:**
```
updated <id> <type> "<name>" changed=[field1, field2, ...]
```

**Example:**
```bash
# Change a node's entity reference
bash helper-scripts/modify-nodered-flows.sh mynodered/nodered.json \
  update-node abc123def456 --props '{"entityId": ["light.bedroom"]}'
```

### delete-node

Delete a node and clean up all references to it.

```
modify-nodered-flows.sh <flows.json> delete-node <node_id> [--dry-run]
```

**Behavior:**
- Removes the node from the file.
- Cleans up: removes from all `wires` arrays, all `links` arrays, and its
  parent group's `nodes` array.
- **Deleting a group** recursively deletes all member nodes (including nested
  groups) and cleans up all their references.
- **Refuses to delete tabs** (too destructive).
- **Refuses to delete subflow definitions** that have existing instances.

**Output:**
```
deleted <id> <type> "<name>"
  cleaned wires: [<list of node IDs>]
  cleaned links: [<list of node IDs>]
  cleaned group: <group_id>
  deleted N member node(s)
```

**Example:**
```bash
# Delete a node (auto-cleans wires and group membership)
bash helper-scripts/modify-nodered-flows.sh mynodered/nodered.json \
  delete-node abc123def456
```

### wire

Connect the output of one node to the input of another.

```
modify-nodered-flows.sh <flows.json> wire <source_id> <target_id> [--port <n>] [--dry-run]
```

**Arguments:**
- `<source_id>`: Node whose output port to connect from.
- `<target_id>`: Node whose input to connect to.
- `--port <n>`: Which output port of the source to use (default: 0).

**Behavior:**
- Adds `target_id` to `source.wires[port]`.
- Extends the wires array with empty arrays if port is beyond current length.
- Idempotent -- no-op if the wire already exists.
- Warns on cross-flow wiring and self-wiring.

**Output:**
```
wired <source_id>:<port> -> <target_id>
```

**Example:**
```bash
# Wire node A's output 0 to node B
bash helper-scripts/modify-nodered-flows.sh mynodered/nodered.json \
  wire a1b2c3d4e5f67890 f1e2d3c4b5a69870

# Wire node A's second output (port 1) to node C
bash helper-scripts/modify-nodered-flows.sh mynodered/nodered.json \
  wire a1b2c3d4e5f67890 1234567890abcdef --port 1
```

### unwire

Remove a wire between two nodes.

```
modify-nodered-flows.sh <flows.json> unwire <source_id> <target_id> [--port <n>] [--all-ports] [--dry-run]
```

**Arguments:**
- `--port <n>`: Specific output port (default: 0 if `--all-ports` not set).
- `--all-ports`: Remove the target from ALL output ports of the source.

**Output:**
```
unwired <source_id>:<port> -> <target_id>
```

### link

Create a link connection between a `link out` (mode=link) or `link call` node
and a `link in` node.

```
modify-nodered-flows.sh <flows.json> link <source_id> <target_id> [--dry-run]
```

**Behavior:**
- Adds each ID to the other's `links` array (bidirectional).
- Idempotent.
- Validates source is `link out` (mode=link) or `link call`, target is `link in`.
- Errors if source is `link out` with mode `return` (these have implicit targets).

**Output:**
```
linked <source_id> (link out) -> <target_id> (link in)
```

### unlink

Remove a link connection.

```
modify-nodered-flows.sh <flows.json> unlink <source_id> <target_id> [--dry-run]
```

**Behavior:**
- Removes each ID from the other's `links` array.
- No-op if not linked.

**Output:**
```
unlinked <source_id> -> <target_id>
```

### add-group

Create a new group on a flow.

```
modify-nodered-flows.sh <flows.json> add-group --on <flow_id> --name <name> [--nodes <id1,id2,...>] [--dry-run]
```

**Arguments:**
- `--on <flow_id>`: (Required) Tab/subflow to create the group on.
- `--name <name>`: (Required) Group name.
- `--nodes <id1,id2,...>`: Comma-separated list of existing node IDs to include.
  Nodes must be on the same flow and must not already be in another group
  (unless that group is also being included as a member -- valid nesting).

**Output:**
```
added group <id> "<name>" on=<flow_id> members=[<count> nodes]
```

**Example:**
```bash
# Create a group containing three existing nodes
bash helper-scripts/modify-nodered-flows.sh mynodered/nodered.json \
  add-group --on d5bd27f8e3f4b6b4 --name "Front door notification" \
  --nodes abc123,def456,789abc
```

### move-to-group

Move a node into a group (or between groups).

```
modify-nodered-flows.sh <flows.json> move-to-group <node_id> <group_id> [--dry-run]
```

**Behavior:**
- If the node is already in a group, removes it from that group first.
- Validates the node and group are on the same flow.

**Output:**
```
moved <node_id> to group <group_id> "<group_name>" (from group <old_group_id>|ungrouped)
```

### remove-from-group

Remove a node from its group without deleting it.

```
modify-nodered-flows.sh <flows.json> remove-from-group <node_id> [--dry-run]
```

**Output:**
```
removed <node_id> from group <group_id> "<group_name>"
```

### set-function

Set the JavaScript code of a function node. Separate from `update-node`
because function code is multi-line and awkward to pass as JSON.

```
modify-nodered-flows.sh <flows.json> set-function <node_id> [--body <code>] [--body-file <path>] [--setup <code>] [--setup-file <path>] [--cleanup <code>] [--cleanup-file <path>] [--dry-run]
```

**Arguments:**
- `--body <code>` or `--body-file <path>`: Main function body (`func` field).
- `--setup <code>` or `--setup-file <path>`: Setup code (`initialize` field).
- `--cleanup <code>` or `--cleanup-file <path>`: Cleanup code (`finalize` field).
- Only the fields specified are changed; others are left as-is.

**Output:**
```
set-function <id> "<name>" [body: <n> lines, setup: <n> lines, cleanup: <n> lines]
```

**Example:**
```bash
# Set function body from a file
bash helper-scripts/modify-nodered-flows.sh mynodered/nodered.json \
  set-function abc123def456 --body-file /tmp/my-function.js

# Set function body inline
bash helper-scripts/modify-nodered-flows.sh mynodered/nodered.json \
  set-function abc123def456 --body 'const state = msg.payload;
if (state === "on") {
    msg.payload = "Active";
    return [msg, null];
}
return [null, msg];'
```

### batch

Execute multiple commands from stdin as a JSON array. This is the preferred
way to do multi-step operations -- it loads and writes the file only once and
is atomic (if any operation fails, nothing is written).

```
modify-nodered-flows.sh <flows.json> batch [--dry-run] <<'EOF'
[ ...operations... ]
EOF
```

**Stdin format:**
```json
[
  {"command": "<command-name>", "args": { ... }},
  {"command": "<command-name>", "args": { ... }}
]
```

**Batch arg names** for each command:

| Command | Required args | Optional args |
|---------|--------------|---------------|
| `add-node` | `type`, `on` | `name`, `group`, `props` |
| `update-node` | `node_id` | `props`, `name` |
| `delete-node` | `node_id` | |
| `wire` | `source`, `target` | `port` |
| `unwire` | `source`, `target` | `port`, `all_ports` |
| `link` | `source`, `target` | |
| `unlink` | `source`, `target` | |
| `add-group` | `on`, `name` | `nodes` (comma-sep string or array) |
| `move-to-group` | `node_id`, `group_id` | |
| `remove-from-group` | `node_id` | |
| `set-function` | `node_id` | `body`, `body_file`, `setup`, `setup_file`, `cleanup`, `cleanup_file` |

**The `$N` reference system:**

When you add nodes or groups in a batch, you don't know the generated IDs
in advance. Use `$0`, `$1`, `$2`, etc. to reference the ID created by the
Nth `add-node` or `add-group` command in the batch.

`$N` references are resolved in all string values in an operation's `args`.
The counter is based on *add operations only* (add-node and add-group), not
the total operation index. So if operation 0 is `add-group`, operation 1 is
`add-node`, and operation 2 is `wire`, then `$0` is the group's ID and `$1`
is the node's ID.

**Atomicity:** If any operation fails, the entire batch is aborted and the
file is not modified.

**Output:**
```
[0] <operation 0 output>
[1] <operation 1 output>
...
batch: N operations applied
```

**Example:**
```bash
bash helper-scripts/modify-nodered-flows.sh mynodered/nodered.json batch <<'EOF'
[
  {"command": "add-group", "args": {"on": "d5bd27f8e3f4b6b4", "name": "Notify when door open 5min"}},
  {"command": "add-node", "args": {"type": "server-state-changed", "on": "d5bd27f8e3f4b6b4", "group": "$0",
    "name": "Front door opens",
    "props": {"entities": {"entity": ["binary_sensor.front_door"]},
              "ifState": "on", "ifStateOperator": "is"}}},
  {"command": "add-node", "args": {"type": "delay", "on": "d5bd27f8e3f4b6b4", "group": "$0",
    "name": "Wait 5 min",
    "props": {"timeout": "5", "timeoutUnits": "minutes"}}},
  {"command": "add-node", "args": {"type": "api-call-service", "on": "d5bd27f8e3f4b6b4", "group": "$0",
    "name": "Notify phone",
    "props": {"domain": "notify", "service": "mobile_app_drew",
              "data": "{\"message\": \"Front door open 5 min\"}", "dataType": "json"}}},
  {"command": "wire", "args": {"source": "$1", "target": "$2"}},
  {"command": "wire", "args": {"source": "$2", "target": "$3"}}
]
EOF
# Output:
# [0] added group a1b2c3d4e5f67890 "Notify when door open 5min" on=d5bd27f8e3f4b6b4 members=[0 nodes]
# [1] added f1e2d3c4b5a69870 server-state-changed "Front door opens" on=d5bd27f8e3f4b6b4 group=a1b2c3d4e5f67890
# [2] added 1234567890abcdef delay "Wait 5 min" on=d5bd27f8e3f4b6b4 group=a1b2c3d4e5f67890
# [3] added fedcba0987654321 api-call-service "Notify phone" on=d5bd27f8e3f4b6b4 group=a1b2c3d4e5f67890
# [4] wired f1e2d3c4b5a69870:0 -> 1234567890abcdef
# [5] wired 1234567890abcdef:0 -> fedcba0987654321
# batch: 6 operations applied
```

## Workflows

### Add a simple automation (trigger -> action)

This is the most common pattern: create a group, add a few nodes, wire them.

1. **Find the target flow** using the summary or search:
   ```bash
   bash helper-scripts/summarize-nodered-flows.sh mynodered/nodered.json
   ```

2. **Find a similar existing automation** for reference:
   ```bash
   bash helper-scripts/query-nodered-flows.sh mynodered/nodered.json \
     search --type server-state-changed --summary
   # Pick one that's similar, inspect its full config:
   bash helper-scripts/query-nodered-flows.sh mynodered/nodered.json \
     node <similar_node_id>
   ```

3. **Create all nodes in one batch**:
   ```bash
   bash helper-scripts/modify-nodered-flows.sh mynodered/nodered.json batch <<'EOF'
   [
     {"command": "add-group", "args": {"on": "<flow_id>", "name": "My new automation"}},
     {"command": "add-node", "args": {"type": "server-state-changed", "on": "<flow_id>",
       "group": "$0", "name": "Trigger", "props": {... from template ...}}},
     {"command": "add-node", "args": {"type": "api-call-service", "on": "<flow_id>",
       "group": "$0", "name": "Action", "props": {... from template ...}}},
     {"command": "wire", "args": {"source": "$1", "target": "$2"}}
   ]
   EOF
   ```

4. **Verify** with the diff summary:
   ```bash
   bash helper-scripts/summarize-nodered-flows-diff.sh --git mynodered/nodered.json
   ```

### Add a node to an existing chain

Insert a delay node between two existing wired nodes.

1. **Query the existing chain** to understand the wiring:
   ```bash
   bash helper-scripts/query-nodered-flows.sh mynodered/nodered.json \
     connected <node_in_chain> --forward --summary
   ```

2. **Add the new node, unwire the old connection, wire the new ones**:
   ```bash
   bash helper-scripts/modify-nodered-flows.sh mynodered/nodered.json batch <<'EOF'
   [
     {"command": "add-node", "args": {"type": "delay", "on": "<flow_id>",
       "group": "<group_id>", "name": "Wait 5 min",
       "props": {"timeout": "5", "timeoutUnits": "minutes"}}},
     {"command": "unwire", "args": {"source": "<upstream_id>", "target": "<downstream_id>"}},
     {"command": "wire", "args": {"source": "<upstream_id>", "target": "$0"}},
     {"command": "wire", "args": {"source": "$0", "target": "<downstream_id>"}}
   ]
   EOF
   ```

### Replace a node's logic

For function nodes, use `set-function`. For other nodes, use `update-node`.

```bash
# Update a function node's JavaScript
bash helper-scripts/modify-nodered-flows.sh mynodered/nodered.json \
  set-function abc123def456 --body 'const state = msg.payload;
if (state === "on") {
    return [msg, null];
}
return [null, msg];'

# Update a switch node's rules
bash helper-scripts/modify-nodered-flows.sh mynodered/nodered.json \
  update-node abc123def456 --props '{"rules": [{"t": "eq", "v": "on", "vt": "str"}], "outputs": 1}'
```

### Remove a node from a chain

When removing a node from the middle of a chain, reconnect the upstream and
downstream nodes so the chain isn't broken.

1. **Find the node's connections**:
   ```bash
   bash helper-scripts/query-nodered-flows.sh mynodered/nodered.json \
     connected <target_node> --summary
   ```

2. **Rewire and delete**:
   ```bash
   bash helper-scripts/modify-nodered-flows.sh mynodered/nodered.json batch <<'EOF'
   [
     {"command": "wire", "args": {"source": "<upstream_id>", "target": "<downstream_id>"}},
     {"command": "delete-node", "args": {"node_id": "<target_node>"}}
   ]
   EOF
   ```
   Note: `delete-node` automatically cleans up wires to/from the deleted node,
   so you only need to add the new bypass wire.

### Build a complex automation from scratch

For automations with branching logic (e.g., a switch node with multiple
outputs going to different actions):

```bash
bash helper-scripts/modify-nodered-flows.sh mynodered/nodered.json batch <<'EOF'
[
  {"command": "add-group", "args": {"on": "<flow_id>", "name": "Climate control"}},
  {"command": "add-node", "args": {"type": "server-state-changed", "on": "<flow_id>",
    "group": "$0", "name": "Temp sensor changes",
    "props": {"entities": {"entity": ["sensor.living_room_temp"]}}}},
  {"command": "add-node", "args": {"type": "switch", "on": "<flow_id>",
    "group": "$0", "name": "Check temperature",
    "props": {"property": "payload", "propertyType": "msg", "outputs": 2,
              "rules": [
                {"t": "lt", "v": "18", "vt": "num"},
                {"t": "gt", "v": "25", "vt": "num"}
              ]}}},
  {"command": "add-node", "args": {"type": "api-call-service", "on": "<flow_id>",
    "group": "$0", "name": "Turn on heater",
    "props": {"domain": "climate", "service": "set_hvac_mode",
              "entityId": ["climate.living_room"], "data": "{\"hvac_mode\": \"heat\"}"}}},
  {"command": "add-node", "args": {"type": "api-call-service", "on": "<flow_id>",
    "group": "$0", "name": "Turn on AC",
    "props": {"domain": "climate", "service": "set_hvac_mode",
              "entityId": ["climate.living_room"], "data": "{\"hvac_mode\": \"cool\"}"}}},
  {"command": "wire", "args": {"source": "$1", "target": "$2"}},
  {"command": "wire", "args": {"source": "$2", "target": "$3", "port": 0}},
  {"command": "wire", "args": {"source": "$2", "target": "$4", "port": 1}}
]
EOF
```

### End-to-end workflow: modify, verify, deploy

The full workflow from making changes to getting them live:

```bash
# 1. Understand current state
bash helper-scripts/summarize-nodered-flows.sh mynodered/nodered.json

# 2. Query existing automations for context and templates
bash helper-scripts/query-nodered-flows.sh mynodered/nodered.json \
  search --name "door" --summary
bash helper-scripts/query-nodered-flows.sh mynodered/nodered.json \
  node <template_node_id>

# 3. Make changes (batch or individual commands)
bash helper-scripts/modify-nodered-flows.sh mynodered/nodered.json batch <<'EOF'
[ ... ]
EOF

# 4. Verify the changes with diff summary
bash helper-scripts/summarize-nodered-flows-diff.sh --git mynodered/nodered.json

# 5. Relayout new/modified groups
# Follow the /relayout-nodered-flows skill to position new nodes and size groups

# 6. Update documentation (check AFFECTED DOCUMENTATION in diff output)
# Update docs/flows/*.md, docs/subflows/*.md, mynodered/CLAUDE.md as needed

# 7. Commit, then upload
bash upload-flows.sh
```

## Tips

- **Always use batch mode for multi-step operations.** It's atomic (all or
  nothing), faster (one file read/write), and lets you use `$N` references.
- **Query existing similar nodes as templates for `--props`.** This is the
  best way to get the right fields and values for type-specific properties.
- **The `--dry-run` flag is your friend.** Use it to verify commands before
  committing to changes.
- **After modifying, always run the diff summary.** It shows exactly what
  changed and lists which documentation files need updating.
- **HA server node types get auto-configured.** You don't need to specify the
  `server` field for `api-call-service`, `server-state-changed`, etc.
- **Props merging is shallow.** For nested objects, always pass the complete
  object in `--props`. Don't expect deep merging.
- **Delete cleans up automatically.** When you delete a node, its wires, links,
  and group membership are all cleaned up. You don't need to unwire first.
- **Groups can be deleted recursively.** Deleting a group deletes all its
  member nodes too. Use with care.
- **Wire and link are idempotent.** Running the same wire/link command twice
  is safe -- it just reports "already wired/linked".

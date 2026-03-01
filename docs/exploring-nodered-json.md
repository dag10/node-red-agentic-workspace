# Exploring Node-RED Flows JSON

This guide teaches you to navigate and understand large Node-RED flows exports
using the `helper-scripts/summarize-nodered-flows.sh` and `helper-scripts/query-nodered-flows.sh` scripts.
The flows file (`mynodered/nodered.json`) is a flat JSON array of 1000+ nodes
that's impractical to read directly. These tools let you drill into exactly
the parts you need.

## How Node-RED flows JSON is structured

The entire export is a **flat array of objects**. Every object has an `id` and a
`type`. There is no nesting — parent-child relationships are encoded by ID
references:

- **Tabs** (type `tab`): Top-level flow containers. Each has a `label`.
- **Subflows** (type `subflow`): Reusable flow definitions. Each has a `name`,
  plus `in`/`out` arrays defining its ports.
- **Nodes**: Everything else. A node's `z` field points to the tab or subflow it
  lives on. Its `wires` field is an array of arrays — one inner array per output
  port, each containing IDs of downstream nodes.
- **Groups** (type `group`): Visual containers. A group's `nodes` array lists
  member IDs. Groups can nest (a group can contain another group). A node's `g`
  field points to its immediate parent group.
- **Junctions** (type `junction`): Wiring helpers with no logic. Treat them as
  invisible wire merges/splits.
- **Link nodes**: Three types that create "virtual wires" between distant nodes:
  - `link out` (mode `link`): Its `links` array points to `link in` node IDs.
    `wires` is always empty.
  - `link in`: Its `links` array points back to the `link out` nodes that feed
    it. It has normal `wires` for its downstream connections.
  - `link call`: Like `link out` but acts as a function call — sends a message
    to a `link in`, waits for a `link out` (mode `return`) to send it back.
    Its `links` array points to `link in` nodes.
  - `link out` (mode `return`): Returns a message to whichever `link call`
    invoked the chain. `links` is empty (the return target is implicit).
- **Subflow instances**: Nodes with type `subflow:<def_id>`. They're black boxes
  — their `wires` connect to other nodes on the same flow, but you can't see
  inside from the parent flow's perspective.

### Key fields on most nodes

| Field    | Meaning                                              |
|----------|------------------------------------------------------|
| `id`     | Unique hex identifier                                |
| `type`   | Node type (e.g., `function`, `api-call-service`)     |
| `name`   | Human-readable label (often empty)                   |
| `z`      | ID of containing tab or subflow                      |
| `g`      | ID of containing group (if any)                      |
| `wires`  | `[[id, id], [id]]` — per-output-port downstream IDs  |
| `d`      | `true` if disabled                                   |
| `links`  | Used by link nodes — IDs of connected link partners  |

### Where Home Assistant entity IDs live

Different HA node types store entity IDs in different fields:

| Node type              | Field                  | Type             |
|------------------------|------------------------|------------------|
| `api-call-service`     | `entityId`             | Array of strings |
| `trigger-state`        | `entities.entity`      | Array of strings |
| `server-state-changed` | `entities.entity`      | Array of strings |
| `api-current-state`    | `entity_id`            | String           |
| `poll-state`           | `entityId`             | String           |

The summarize script scans all string values recursively to find entity IDs,
so it catches them regardless of which field they're in.

## Tool 1: summarize-nodered-flows.sh

```
helper-scripts/summarize-nodered-flows.sh mynodered/nodered.json
```

This is your **starting point**. Run it first whenever you need to work with
flows. It prints a structured overview with these sections:

### Summary sections

**Flows** — All tabs with node counts and IDs. Use the IDs to drill in with
`flow-nodes` or `--flow` filters.

**Subflows** — All subflow definitions with node counts, input/output port
counts, and IDs. Event-driven subflows (0 inputs) show their internal
`triggers:` line — the node types that kick them off.

**Groups** — Every group organized by parent flow. Each group shows:
- Node count and group ID
- `entry:` line listing entry-point nodes (nodes with no incoming connections
  from within the group). These tell you what triggers or feeds the group.

This is the most important section for understanding what each automation does.
The group names are usually descriptive ("When bedtime begins", "Daily reset
and confirmation") and the entry nodes tell you what events drive them.

**Cross-flow links** — Link connections that span across different flows/
subflows. Useful for understanding inter-flow dependencies.

**Subflow usage** — Where each subflow is instantiated and how many times.

**Ungrouped entry points** — Source nodes on each flow that aren't inside any
group. These are "loose" automations or test nodes that haven't been organized
into a named group.

**Entity references** — All HA entity IDs found in each flow's nodes. This is
the fastest way to answer "which flow handles entity X?" — search this section
for the entity ID.

**Disabled nodes** — Nodes with `d: true`. Useful context so you don't
accidentally build on disabled logic.

**Function nodes** — All function nodes with line counts. Tells you where custom
JavaScript logic lives, so you know what to read with the `function` query
command.

**Comment nodes** — Human-authored documentation within the flows.

## Tool 2: query-nodered-flows.sh

```
helper-scripts/query-nodered-flows.sh mynodered/nodered.json <command> [args...]
```

This is your **drill-down tool**. Once the summary tells you which flow, group,
or node to investigate, use these commands to get the details.

### Output formats

- **`node`**: Pretty-printed JSON (always human-readable).
- **All other multi-node commands**: JSONL by default (one compact JSON object
  per line). Pipe to `jq` for formatting or field extraction.
- **`--summary` flag**: One-liner per node:
  `<id>  <type>  "<name>"  wires:<n>  [group:"<group>"]`
- **`--full` flag**: Pretty-printed JSON array containing all matching nodes
  with full detail. Use this to load an entire flow or subflow into context
  when you need to understand all node configurations at once.

Use `--summary` when you want a quick overview. Use `--full` when you want all
node data in a readable format (e.g., loading a whole flow into context). Use
default JSONL when piping into other tools.

### Commands reference

#### node \<id\>

Print a single node as pretty JSON. Use this to inspect the full configuration
of any node — its fields, entity references, rules, templates, etc.

```
query-nodered-flows.sh flows.json node abc123def456
```

#### function \<id\>

Print the JavaScript source code of a function node. Shows the main function
body, plus `// --- Setup (initialize) ---` and `// --- Cleanup (finalize) ---`
sections if they exist.

```
query-nodered-flows.sh flows.json function abc123def456
```

This is the only way to read function node JavaScript without wading through
the raw JSON. Use it after the summary's "Function nodes" section tells you
which function nodes exist.

#### connected \<id\> [flags]

BFS traversal in both directions from a node. Returns the full connected
subgraph in flow order: upstream nodes (root-first), the start node, then
downstream nodes (BFS order).

```
query-nodered-flows.sh flows.json connected abc123 --summary
query-nodered-flows.sh flows.json connected abc123 --forward --summary
query-nodered-flows.sh flows.json connected abc123 --backward --summary
```

By default, the traversal follows link connections (link out -> link in,
link call -> link in). Use `--dont-follow-links` to stay within wire-only
connections.

Flags:
- `--forward`: Only downstream nodes from the start.
- `--backward`: Only upstream nodes reaching the start.
- `--dont-follow-links`: Don't cross link node boundaries.
- `--summary`: Compact one-liners.

#### head-nodes \<id\> [flags]

Find the root trigger nodes that can reach a given node. BFS backward, then
filter to only nodes with no incoming connections. These are the event sources
(inject, cronplus, trigger-state, server-events, etc.) that ultimately drive
the node you're asking about.

```
query-nodered-flows.sh flows.json head-nodes abc123 --summary
```

#### tail-nodes \<id\> [flags]

Find the terminal nodes reachable from a given node. BFS forward, then filter
to only nodes with no outgoing connections. These are the endpoints — typically
`api-call-service`, `debug`, or `link out` (mode return) nodes.

```
query-nodered-flows.sh flows.json tail-nodes abc123 --summary
```

#### flow-nodes \<id\> [flags]

All nodes on a flow/tab. The ID is the tab's ID from the summary.

```
query-nodered-flows.sh flows.json flow-nodes d5bd27f8e3f4b6b4 --summary
query-nodered-flows.sh flows.json flow-nodes d5bd27f8e3f4b6b4 --sources --summary
query-nodered-flows.sh flows.json flow-nodes d5bd27f8e3f4b6b4 --full
```

Flags:
- `--sources`: Only entry-point nodes — nodes with no incoming connections from
  other nodes within the same flow. These are the flow's triggers and external
  inputs.
- `--full`: All nodes as a pretty-printed JSON array.
- `--summary`: Compact one-liners.

#### group-nodes \<id\> [flags]

All nodes in a group (recursively includes nested groups). The ID is the
group's ID from the summary.

```
query-nodered-flows.sh flows.json group-nodes 855835066a0958b1 --summary
query-nodered-flows.sh flows.json group-nodes 855835066a0958b1 --sources --summary
```

Flags:
- `--sources`: Only entry-point nodes — nodes with no incoming connections from
  other nodes within the same group. Shows both event triggers and nodes fed
  from outside the group.
- `--summary`: Compact one-liners.

#### subflow-nodes \<id\> [flags]

All internal nodes of a subflow definition. The ID is the subflow's definition
ID (not an instance ID).

```
query-nodered-flows.sh flows.json subflow-nodes 886281ab0c2f1008 --summary
query-nodered-flows.sh flows.json subflow-nodes 886281ab0c2f1008 --full
```

#### subflow-instances \<id\>

All instances of a subflow across all flows. Shows where it's used.

```
query-nodered-flows.sh flows.json subflow-instances ff9ede4b51732f90 --summary
```

#### search [--type T] [--name P] [--flow ID]

Find nodes matching filters. All filters are AND-ed.

```
query-nodered-flows.sh flows.json search --type function --summary
query-nodered-flows.sh flows.json search --name "bedroom" --summary
query-nodered-flows.sh flows.json search --type api-call-service --flow d5bd27f8e3f4b6b4 --summary
```

- `--type T`: Exact match on node type.
- `--name P`: Regex match (case-insensitive) on node name.
- `--flow ID`: Only nodes on a specific flow/subflow (by z value).

#### rect \<x1\> \<y1\> \<x2\> \<y2\> [flags]

Find all nodes and groups within a rectangle on the canvas. Nodes match when
their center point (x, y) falls within the rect. Groups match when their
bounding box overlaps the rect.

Coordinates accept `inf` and `-inf` for semi-infinite edges. This enables
directional queries like "everything below y=500" or "everything to the right
of x=300". Semi-infinite rects auto-sort results by position along the
infinite axis (closest to the finite edge first). Finite rects sort by
distance from the rect center.

```
# Everything below y=500 on a specific flow (sorted by y, closest first)
query-nodered-flows.sh flows.json rect -inf 500 inf inf --flow <flow_id> --summary

# Nodes in a specific region
query-nodered-flows.sh flows.json rect 100 200 600 400 --flow <flow_id> --summary

# Everything to the right of x=800 (sorted by x, closest first)
query-nodered-flows.sh flows.json rect 800 -inf inf inf --flow <flow_id> --summary

# Within a specific group only
query-nodered-flows.sh flows.json rect 0 0 inf inf --group <group_id> --summary
```

Flags:
- `--flow ID`: Limit to nodes on this flow/tab.
- `--group ID`: Limit to nodes in this group (recursive).
- `--summary`, `--full`: Output format.

#### nearby \<id\> [--margin PX]

Find nodes and groups near a given node or group. For groups, expands the
stored bounding box (x, y, w, h) by the margin on all sides and finds
everything outside the group that overlaps the expanded area. For nodes,
creates a square of 2 * margin centered on the node's position. Always
scoped to the same flow/subflow as the reference.

For group queries, the group itself and all its member nodes are excluded
from results — you get only things *outside* the group that are nearby.

```
# Groups and nodes within 50px of a group's boundary
query-nodered-flows.sh flows.json nearby <group_id> --margin 50 --summary

# Nodes within 80px of a specific node
query-nodered-flows.sh flows.json nearby <node_id> --margin 80 --summary
```

Results are sorted by distance from the reference center (closest first).

- `--margin PX`: Expansion margin in pixels (default: 100).
- `--summary`, `--full`: Output format.

### The --sources flag

`--sources` on `flow-nodes` and `group-nodes` identifies **scope-local entry
points**: nodes whose incoming connections are all from outside the scope.

This is different from the global head-nodes command. A node that receives input
from outside its group is a group source (it's an entry point *to that group*)
even though it has incoming wires globally. This makes `--sources` the right
tool for understanding "what feeds this group?" rather than "what are the global
root triggers?"

### The --dont-follow-links flag

By default, graph traversal commands (`connected`, `head-nodes`, `tail-nodes`)
and the `--sources` flag cross link node boundaries — a `link out` (mode link)
is treated as connecting to its `link in` targets, and vice versa.

Use `--dont-follow-links` when you want to stay within wire-only topology. This
is useful when:
- You want to see only the directly-wired chain, ignoring virtual links.
- You're debugging a specific segment and don't want to pull in the entire
  linked graph.
- The link connections lead to large subgraphs you don't need.

## Workflows

### "Which flow handles entity X?"

1. Run the summary and search the **Entity references** section for the entity
   ID. Note which flow(s) list it.
2. If multiple flows reference it, use `search` to find the specific nodes:
   ```
   query-nodered-flows.sh flows.json search --name "entity_name" --summary
   ```
3. For HA node types, use `node` to inspect the full config and confirm it's
   the right one.

### "What triggers this automation?"

1. Find the group in the summary's **Groups** section. The `entry:` line gives
   you the trigger types at a glance.
2. For more detail, use `group-nodes --sources`:
   ```
   query-nodered-flows.sh flows.json group-nodes <group_id> --sources --summary
   ```
3. To see the full trigger node config (e.g., which entity a `trigger-state`
   watches):
   ```
   query-nodered-flows.sh flows.json node <trigger_node_id>
   ```

### "What does this automation do end-to-end?"

1. Pick any node in the automation (e.g., a source node from the group).
2. Trace the full connected graph:
   ```
   query-nodered-flows.sh flows.json connected <node_id> --summary
   ```
3. To see just the endpoints (what actions it takes):
   ```
   query-nodered-flows.sh flows.json tail-nodes <node_id> --summary
   ```
4. Inspect specific nodes for detail:
   ```
   query-nodered-flows.sh flows.json node <api_call_service_id>
   query-nodered-flows.sh flows.json function <function_node_id>
   ```

### "I need to understand this group in depth"

1. List all nodes in the group:
   ```
   query-nodered-flows.sh flows.json group-nodes <group_id> --summary
   ```
2. Identify entry points:
   ```
   query-nodered-flows.sh flows.json group-nodes <group_id> --sources --summary
   ```
3. Trace from each entry point to see what it does:
   ```
   query-nodered-flows.sh flows.json connected <source_id> --forward --summary
   ```
4. Read function node logic:
   ```
   query-nodered-flows.sh flows.json function <fn_id>
   ```
5. Inspect specific nodes that matter (switches, change nodes, api calls):
   ```
   query-nodered-flows.sh flows.json node <id>
   ```

### "Where is this subflow used and what does it do?"

1. The summary's **Subflow usage** section shows instance counts and locations.
2. List all instances to see their wiring context:
   ```
   query-nodered-flows.sh flows.json subflow-instances <sf_def_id> --summary
   ```
3. Look inside the subflow:
   ```
   query-nodered-flows.sh flows.json subflow-nodes <sf_def_id> --summary
   ```
4. Pick a specific instance and trace its connections on the parent flow:
   ```
   query-nodered-flows.sh flows.json connected <instance_id> --summary
   ```

### "I need to understand cross-flow dependencies"

1. Check the summary's **Cross-flow links** section for connections between
   flows.
2. For a specific link node, use `connected` to trace the full chain across
   flows:
   ```
   query-nodered-flows.sh flows.json connected <link_in_id> --summary
   ```
3. Use `--dont-follow-links` if you only want the local side:
   ```
   query-nodered-flows.sh flows.json connected <link_in_id> --dont-follow-links --summary
   ```

### "Are any nodes overlapping on this flow?"

Use the `overlaps` command from `estimate-node-size.sh` to detect node pairs whose
rendered bounding boxes overlap or are too close. This uses actual node dimensions
(not just center points) for accurate collision detection.

```
# Find all overlapping nodes on a flow
estimate-node-size.sh flows.json overlaps --flow <flow_id>

# Find nodes within a group that violate minimum spacing (30px)
estimate-node-size.sh flows.json overlaps --gap 30 --group <group_id>

# JSON output for programmatic use
estimate-node-size.sh flows.json overlaps --flow <flow_id> --json
```

Output shows each overlapping pair with their sizes, positions, and the actual
edge-to-edge gap in both dimensions. Negative gap = overlap, positive = separation:
```
<id1> <type1> "<name1>" WxH @x,y  ↔  <id2> <type2> "<name2>" WxH @x,y  h_gap:-100 v_gap:-30
```

Use `--gap 30` (the `MIN_VERTICAL_NODE_GAP`) to find all spacing violations, not
just actual overlaps.

### "Will my new node positions collide with existing nodes?"

Use the spatial queries during relayout to detect collisions before they happen:

1. **Before placing a node**, check what's already in the target area:
   ```
   query-nodered-flows.sh flows.json rect <x-80> <y-40> <x+80> <y+40> --flow <flow_id> --summary
   ```
   Expand the rect by half the node's estimated dimensions plus the minimum gap.

2. **After resizing a group**, check for groups below it that need shifting:
   ```
   query-nodered-flows.sh flows.json rect -inf <group_bottom> inf inf --flow <flow_id> --summary
   ```
   This returns everything below the group, sorted closest-first.

3. **Check a group's surroundings** for overlap after repositioning:
   ```
   query-nodered-flows.sh flows.json nearby <group_id> --margin 20 --summary
   ```
   Anything returned overlaps or is within 20px of the group (the minimum gap).

### "I need to plan a modification to an existing automation"

1. **Start with the summary.** Find the relevant flow and group. Read the entry
   nodes and entity references to confirm you're in the right place.
2. **Map the existing logic.** Use `group-nodes --summary` for the full node
   list, then `connected --forward --summary` from each entry point.
3. **Read the details.** Use `node` on switch/change/api-call-service nodes to
   understand branching logic, data transformations, and service calls. Use
   `function` to read JavaScript.
4. **Check for side effects.** Use `tail-nodes` to see all endpoints. Use
   `connected --forward` from the node you plan to modify to understand
   downstream impact.
5. **Check cross-flow links.** If the group contains link-out or link-call
   nodes, trace where they go with `connected`.

## Tips

- **Always start with the summary.** It's fast and gives you IDs and context
  for everything else.
- **Use `--summary` liberally.** It's much more readable than JSONL for
  orientation. Switch to JSONL or `node` only when you need full detail.
- **Group names are documentation.** They're usually descriptive phrases like
  "When coming home past bedtime, start bedtime alarm within 10 mins". Read them
  as intent descriptions.
- **The `entry:` lines are the table of contents.** They tell you at a glance
  what triggers each group — `cronplus` = scheduled, `server-state-changed` =
  reacts to entity changes, `inject` = manual test button, `link in` = called
  from elsewhere, `subflow:*` = event from a subflow.
- **`inject` nodes are usually test triggers.** In production automations, the
  real triggers are `cronplus`, `server-state-changed`, `trigger-state`,
  `ha-time`, `server-events`, or `poll-state`.
- **Subflow instances are black boxes.** `connected` follows their external
  wires but doesn't enter the subflow's internal nodes. Use `subflow-nodes` to
  look inside.
- **Entity references may include false positives.** The scanner matches any
  `domain.name` pattern in string values. Service action names like
  `input_boolean.turn_on` will show up alongside actual entity IDs like
  `input_boolean.vacation_mode`. You can usually distinguish them by context.

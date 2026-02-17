---
name: relayout-nodered-flows
description: Position nodes and size groups in nodered.json after modifications. Reads the diff to understand what changed, then applies the project's layout conventions to new/modified nodes and groups.
---

# Relayout Node-RED Flows

After modifying `nodered.json` (adding nodes, creating groups, rewiring flows), newly
created nodes have default placeholder positions (x=200, y=200) and new groups have
placeholder dimensions (x=10, y=10, w=200, h=100). This skill repositions them to
match the project's hand-crafted layout conventions.

## Philosophy

Be conservative. Only reposition what needs repositioning:

- **ALWAYS** position newly created nodes properly.
- **ALWAYS** size and position newly created groups properly.
- **Only** move existing nodes when necessary -- to resolve overlaps or maintain spacing
  after a group above them grew.
- When existing nodes must move, prefer translating entire groups by a uniform offset
  (preserving their internal layout) rather than re-laying-out their internals.
- **Never** touch nodes or groups that were not affected by the current changes.

## Step 1: Understand the Changes

Run the diff tool to see what changed:

```bash
bash helper-scripts/summarize-nodered-flows-diff.sh \
  mynodered/nodered-last-downloaded.json mynodered/nodered.json
```

Categorize changes into these scenarios (a single modification may involve multiple):

| Scenario | What to do |
|----------|-----------|
| **New group with new nodes** | Full layout of the group (most common). See "Layout a New Group." |
| **New nodes added to existing group** | Position new nodes relative to existing ones. See "Add Nodes to an Existing Group." |
| **Nodes rewired in existing group** | Usually leave alone; reposition only if topology changed drastically. See "Handle Rewired Nodes." |
| **Existing group needs to shift** | A group above grew or a new group was inserted above. See "Resolve Group Overlaps." |

## Step 2: Read the Affected Groups

For each group you need to lay out (or adjust), read its current state:

```bash
# All nodes in a group with positions
bash helper-scripts/query-nodered-flows.sh mynodered/nodered.json \
  group-nodes <group_id> --summary

# Source (entry) nodes only
bash helper-scripts/query-nodered-flows.sh mynodered/nodered.json \
  group-nodes <group_id> --sources --summary

# Full details of a specific node
bash helper-scripts/query-nodered-flows.sh mynodered/nodered.json \
  node <node_id>

# Forward chain from a node
bash helper-scripts/query-nodered-flows.sh mynodered/nodered.json \
  connected <node_id> --forward --summary
```

## Numeric Constants

These constants are derived from detailed analysis of four hand-crafted flows. Use them
for all positioning calculations.

### Inter-group spacing

| Constant | Value | Meaning |
|----------|-------|---------|
| `GROUP_VERTICAL_GAP` | 18 px | Vertical gap between stacked groups |
| `GROUP_HORIZONTAL_GAP` | 28 px | Horizontal gap between side-by-side groups |
| `GROUP_LEFT_MARGIN` | 34 px | X coordinate of a group's left edge |

### Group padding (group edge to outermost node center)

| Constant | Value | Meaning |
|----------|-------|---------|
| `GROUP_PADDING_TOP` | 40 px | Group top edge to topmost node center |
| `GROUP_PADDING_BOTTOM` | 40 px | Bottommost node center to group bottom edge |
| `GROUP_PADDING_LEFT` | 120 px | Group left edge to leftmost node center |
| `GROUP_PADDING_RIGHT` | 90 px | Rightmost node center to group right edge |

### Horizontal spacing (center-to-center between consecutive nodes)

| Constant | Value | When to use |
|----------|-------|-------------|
| `HORIZONTAL_SPACING_DEFAULT` | 200 px | Standard nodes (function, change, switch, api-call-service) |
| `HORIZONTAL_SPACING_TIGHT` | 120 px | Compact nodes (junction, link in, link out, link call) |
| `HORIZONTAL_SPACING_WIDE` | 260 px | Wide nodes (server-state-changed, named inject, trigger-state) |

Choose spacing based on the **source** node of each hop -- use the wider spacing when
the node being spaced away from is wide.

### Vertical spacing

| Constant | Value | When to use |
|----------|-------|-------------|
| `BRANCH_VERTICAL_SPACING` | 60 px | Between branch outputs from a multi-output node |
| `ENTRY_NODE_STACKING` | 40 px | Between stacked entry nodes of the same type |
| `SOURCE_NODE_SPACING` | 80 px | Between entry nodes of different types |
| `PARALLEL_CHAIN_SPACING` | 60 px | Between replicated identical chains |
| `TEST_INJECT_OFFSET_Y` | 60 px | Below the main flow line for test inject nodes |

## Node Width Estimation

Horizontal spacing depends on node width. Since we cannot query rendered widths,
use these estimates:

| Node type | Estimated width (px) |
|-----------|---------------------|
| junction | 10 |
| link in, link out, link call | 30 |
| inject (no name) | 90 |
| inject (with name) | 140-180 |
| function, change, delay, switch | 120-160 (varies by name length) |
| api-call-service | 140-180 |
| server-state-changed, trigger-state | 180-220 |
| api-current-state | 160-200 |
| subflow instance | 140-200 (varies by subflow name) |
| debug | 100-140 |

**Rule of thumb:** `max(100, 30 + len(name) * 7)` pixels, capped at 220.
For junctions, always 10 px. For link nodes, always 30 px.

## Algorithm: Layout a New Group

This is the most common scenario -- a new group was created with new nodes inside it.

### 1. Identify source nodes

Source nodes have no incoming wires from other nodes within the same group. Query them:

```bash
bash helper-scripts/query-nodered-flows.sh mynodered/nodered.json \
  group-nodes <group_id> --sources --summary
```

### 2. Build the topology

From each source, trace forward through wires to build a mental model of the chain(s).
Use `connected --forward --summary` from each source. Assign each node a **column**
(depth from source):

- Column 0: Source/entry nodes
- Column 1: First downstream nodes
- Column N: Nodes at depth N from any source

If a node is reachable from multiple sources at different depths, use the **longest
path** (maximum depth) -- this keeps it to the right of all its predecessors.

### 3. Position columns left to right

Start column 0 at:
```
x = GROUP_LEFT_MARGIN + GROUP_PADDING_LEFT  (= 34 + 120 = 154)
```

For each subsequent column, add the horizontal spacing based on the node connecting
into it:
- From a junction or link node: add `HORIZONTAL_SPACING_TIGHT` (120)
- From a wide trigger/event node: add `HORIZONTAL_SPACING_WIDE` (260)
- Otherwise: add `HORIZONTAL_SPACING_DEFAULT` (200)

### 4. Position nodes vertically within columns

**Single node in a column** -- place at the y of its upstream parent's output:
- If the parent has one output going to this node, use the parent's y.
- If the parent has multiple outputs, see fan-out rules below.

**Multiple source nodes (column 0):**
- Same type (e.g., multiple injects): stack at `ENTRY_NODE_STACKING` (40 px) intervals.
- Different types: stack at `SOURCE_NODE_SPACING` (80 px) intervals.
- Test inject nodes: place below the production triggers at `TEST_INJECT_OFFSET_Y`
  (60 px) below the nearest production source.
- The topmost source node's y becomes the group's "main flow line."

**Fan-out (multi-output node):**
When a node has N outputs going to N different downstream nodes, center the source
node vertically among its targets:
- 2 outputs: targets at `parent_y - 30` and `parent_y + 30` (60 px apart, centered)
- 3 outputs: targets at `parent_y - 60`, `parent_y`, `parent_y + 60`
- N outputs: spread at `BRANCH_VERTICAL_SPACING` (60 px) intervals, centered on `parent_y`
- General formula: target_i_y = `parent_y + (i - (N-1)/2) * 60`

**Parallel replicated chains** (same logic repeated per device):
Stack at `PARALLEL_CHAIN_SPACING` (60 px) between chains.

### 5. Determine the group's base y

- **First group on the flow:** topmost node y = `GROUP_LEFT_MARGIN + GROUP_PADDING_TOP`
  (= 34 + 40 = 74). So the group's top = 34.
- **Group below another group:** topmost node y = `previous_group_bottom + GROUP_VERTICAL_GAP + GROUP_PADDING_TOP`. So the group's top = `previous_group_bottom + GROUP_VERTICAL_GAP`.

### 6. Calculate group bounding box

```
group.x = leftmost_node_x - GROUP_PADDING_LEFT
group.y = topmost_node_y - GROUP_PADDING_TOP
group.w = (rightmost_node_x + GROUP_PADDING_RIGHT) - group.x
group.h = (bottommost_node_y + GROUP_PADDING_BOTTOM) - group.y
```

Typically `group.x` will be `GROUP_LEFT_MARGIN` (34) since `leftmost_node_x` =
`GROUP_LEFT_MARGIN + GROUP_PADDING_LEFT` (154).

### 7. Apply positions with batch update-node

```bash
bash helper-scripts/modify-nodered-flows.sh mynodered/nodered.json batch <<'EOF'
[
  {"command": "update-node", "args": {"node_id": "<node_id>", "props": {"x": 154, "y": 74}}},
  {"command": "update-node", "args": {"node_id": "<node_id>", "props": {"x": 354, "y": 74}}},
  ...
  {"command": "update-node", "args": {"node_id": "<group_id>", "props": {"x": 34, "y": 34, "w": 500, "h": 120}}}
]
EOF
```

## Algorithm: Add Nodes to an Existing Group

When new nodes are added to a group that already has well-positioned nodes:

1. **Read the existing group layout** -- query all nodes with positions.
2. **Identify new nodes** -- they will be at the default position (x=200, y=200).
3. **Determine where new nodes fit** in the chain:
   - **Inserted mid-chain** (between two existing nodes): place at the midpoint x, same
     y as the chain. If there is not enough horizontal space, shift all downstream nodes
     right by `HORIZONTAL_SPACING_DEFAULT`.
   - **New branch from an existing node**: place at the next column's x, with y offset by
     `BRANCH_VERTICAL_SPACING` from the nearest sibling branch.
   - **New source/entry node**: stack below existing sources at `ENTRY_NODE_STACKING` spacing.
   - **New tail node**: place to the right of the current rightmost node in the chain, same y.
4. **Resize the group** if the new nodes extend beyond the current bounding box. Expand
   w and/or h while maintaining padding constants.
5. **Check for downstream group overlaps** after resizing -- see "Resolve Group Overlaps."

## Algorithm: Resolve Group Overlaps

After any layout change (new group, resized group), check that groups do not overlap:

### Vertically stacked groups

1. List all groups on the affected flow with their bounding boxes.
2. Sort by y (top to bottom).
3. For each consecutive pair, check:
   `group_above.y + group_above.h + GROUP_VERTICAL_GAP > group_below.y`
4. If overlap exists: compute the delta needed, then shift the lower group (and ALL
   subsequent groups below it) down by that delta.
5. **When shifting a group, translate ALL its member nodes by the same y delta.**
   Do not re-layout the group's internals -- just move everything uniformly.

### Side-by-side groups

Groups placed horizontally adjacent (same y range, different x) should have at least
`GROUP_HORIZONTAL_GAP` (28 px) between them. If a group's width grew:
- Check if the right neighbor now overlaps.
- If so, shift the right group (and its nodes) rightward by the needed amount.

## Algorithm: Handle Rewired Nodes

When existing nodes have been rewired but not repositioned:

1. **Minor rewiring** (e.g., adding one more output to a switch): the existing layout is
   probably fine. Just check that any new output targets have reasonable positions.
2. **Major rewiring** (e.g., a node moved from one branch to another): reposition only
   the specific nodes that moved, not the entire group.
3. **When in doubt, leave existing positions alone.** The user may prefer to manually
   adjust after deploying.

## Special Patterns

Recognize these common layout patterns and apply the appropriate rules:

### Guard chain (linear pipeline of checks)
All nodes at the **same y**, spaced horizontally. Common for sequences of
`api-current-state` checks. The group will be short (h ~ 80-82 px) with nodes
vertically centered.

### Fan-out (one node to many actions)
Center the source node vertically among its outputs. Space outputs at
`BRANCH_VERTICAL_SPACING` (60 px). The fan creates a triangular shape pointing right.

### Fan-in (many sources to one junction/node)
Stack source nodes vertically, merging into a junction or the next processing node.
Use `ENTRY_NODE_STACKING` (40 px) for same-type sources, `SOURCE_NODE_SPACING` (80 px)
for different types.

### Switch with symmetric branches
Place the switch node at the **vertical center** of its output range. For 2 outputs:
branches at switch_y - 30 and switch_y + 30.

### Parallel replicated chains (per-device logic)
Identical chains repeated for each device, stacked at `PARALLEL_CHAIN_SPACING` (60 px).
Each chain is a horizontal line at a different y. All chains share the same column x values.

### Subroutine groups (called via link nodes)
Place **side-by-side** with the calling group using `GROUP_HORIZONTAL_GAP` (28 px),
aligned at the same y as the calling group's top edge. The subroutine group's `link in`
node should be at its left edge, visually adjacent to the calling group's `link call`
or `link out` node.

### Test inject nodes
Position below the main flow line by `TEST_INJECT_OFFSET_Y` (60 px). They connect
to the point in the chain they are meant to test -- a "test notify" inject connects
to the notification function, not to the beginning of the chain.

## Step 3: Apply Positions

After calculating all positions, apply them in a single batch operation (see examples
in the algorithms above). Use `update-node` for both regular nodes (setting `x`, `y`)
and groups (setting `x`, `y`, `w`, `h`).

## Step 4: Verify

After applying positions, verify the layout is correct:

1. **Read back affected groups** with `group-nodes <id> --summary` to confirm positions
   look reasonable.
2. **Check for collisions**: no two nodes in the same group should share the exact
   same (x, y).
3. **Check group containment**: every node's (x, y) should fall within its group's
   bounding box with appropriate padding.
4. **Check inter-group spacing**: consecutive groups on the same flow should have at
   least `GROUP_VERTICAL_GAP` (18 px) between them.
5. If anything looks wrong, adjust and re-apply.

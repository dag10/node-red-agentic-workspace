---
name: relayout-nodered-flows
description: Position nodes and size groups in nodered.json after modifications. Reads the diff to understand what changed, then applies the project's layout conventions to new/modified nodes and groups.
---

# Relayout Node-RED Flows

After modifying `nodered.json` (adding nodes, creating groups, rewiring flows), newly
created nodes have default placeholder positions (x=200, y=200) and new groups have
placeholder dimensions (x=10, y=10, w=200, h=100). This skill repositions them to
match the project's hand-crafted layout conventions.

> **DRY-RUN FIRST**: Before applying any position changes, always do a dry-run of
> the batch update to preview what will change. Add `--dry-run` to the
> `modify-nodered-flows.sh batch` command. Review the output, then run again without
> `--dry-run` to apply. This catches miscalculations before they corrupt the file.

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

Run the diff tool to see what changed. The baseline for comparison is always
`nodered-last-downloaded.json` (the last deployed state), not the last git commit:

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

## Step 2: Read the Affected Groups and Measure Node Sizes

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

### Get node sizes for layout

Use `estimate-node-size.sh` to get accurate pixel dimensions for all nodes you need
to position. **Use batch mode** when sizing multiple nodes (which is almost always):

```bash
# Batch mode: get sizes for all nodes in one call (preferred)
echo '["node_id_1", "node_id_2", "node_id_3"]' | \
  bash helper-scripts/estimate-node-size.sh mynodered/nodered.json batch
# Output: {"node_id_1": {"w": 160, "h": 30}, "node_id_2": {"w": 120, "h": 30, "has_button": "left"}, ...}

# Single node (for quick checks)
bash helper-scripts/estimate-node-size.sh mynodered/nodered.json node <node_id>
# Output: 160 30

# Full group layout info (member sizes + group bbox)
bash helper-scripts/estimate-node-size.sh mynodered/nodered.json group-layout <group_id>
# Output: JSON with {"group": {"id": ..., "w": ..., "h": ...}, "nodes": {"id": {"w": ..., "h": ...}, ...}}
```

The batch output includes `has_button` for inject nodes (`"left"`) and debug nodes
(`"right"`). Button nodes have a 20px clickable area that extends beyond the node body;
account for this when checking edge clearance but not when calculating center-to-center
spacing.

**Always gather sizes before calculating positions.** The horizontal spacing algorithm
below depends on knowing the actual width of each node.

## Numeric Constants

These constants are derived from detailed analysis of four hand-crafted flows. Use them
for all positioning calculations. All constants are designed so that positions computed
from them will naturally land on the 20px grid when starting positions are on-grid.

### Inter-group spacing

| Constant | Value | Meaning |
|----------|-------|---------|
| `GROUP_VERTICAL_GAP` | 20 px | Vertical gap between stacked groups |
| `GROUP_HORIZONTAL_GAP` | 20 px | Horizontal gap between side-by-side groups |
| `GROUP_LEFT_MARGIN` | 40 px | X coordinate of a group's left edge |

### Group padding (group edge to outermost node center)

| Constant | Value | Meaning |
|----------|-------|---------|
| `GROUP_PADDING_TOP` | 40 px | Group top edge to topmost node center |
| `GROUP_PADDING_BOTTOM` | 40 px | Bottommost node center to group bottom edge |
| `GROUP_PADDING_LEFT` | 120 px | Group left edge to leftmost node center |
| `GROUP_PADDING_RIGHT` | 80 px | Rightmost node center to group right edge |

### Horizontal spacing (edge-to-edge gap between consecutive nodes)

| Constant | Value | Meaning |
|----------|-------|---------|
| `HORIZONTAL_GAP` | 60 px | Visible gap between the right edge of one node and the left edge of the next |

This is the consistent visible space between node edges. The actual center-to-center
distance varies based on node widths -- wide nodes are spaced further apart and narrow
nodes closer together, but the gap between their edges stays uniform.

### Vertical spacing

| Constant | Value | When to use |
|----------|-------|-------------|
| `MIN_VERTICAL_NODE_GAP` | 30 px | Minimum edge-to-edge gap between any two vertically adjacent nodes. Verify after layout. |
| `BRANCH_VERTICAL_SPACING` | 60 px | Between branch outputs from a multi-output node |
| `ENTRY_NODE_STACKING` | 60 px | Between stacked entry nodes of the same type |
| `SOURCE_NODE_SPACING` | 80 px | Between entry nodes of different types |
| `PARALLEL_CHAIN_SPACING` | 60 px | Between replicated identical chains |
| `TEST_INJECT_OFFSET_Y` | 60 px | Below the main flow line for test inject nodes |

### Grid alignment

Node-RED's editor snaps to a 20px grid. All positions written to `nodered.json` must
conform to this grid:

- **All `x`, `y` values** (node positions) must be multiples of 20.
- **All `x`, `y`, `w`, `h` values** (group bounding boxes) must be multiples of 20.
- **All position values must be integers** -- never floats (no `200.0`, only `200`).

When computing positions, apply grid snapping as the final step:
```
snap(v) = int(round(v / 20) * 20)
```

For example, if a formula yields x=154, snap to x=160. If it yields y=1398, snap to y=1400.

The constants in this document are designed so that positions computed from them will
naturally land on the 20px grid when the starting positions are on-grid. If a calculation
produces an off-grid result (due to rounding or unusual node dimensions), always snap
to the nearest grid point. After snapping, verify that the edge-to-edge gap between
every pair of vertically adjacent nodes is at least `MIN_VERTICAL_NODE_GAP` (30px).
If snapping compressed a gap below the minimum, shift the lower node down to the next
grid point.

## Algorithm: Layout a New Group

This is the most common scenario -- a new group was created with new nodes inside it.

### 1. Identify source nodes

Source nodes have no incoming wires from other nodes within the same group. Query them:

```bash
bash helper-scripts/query-nodered-flows.sh mynodered/nodered.json \
  group-nodes <group_id> --sources --summary
```

### 2. Gather all node sizes

Collect the IDs of every node in the group and get their sizes in one batch call:

```bash
echo '["id_a", "id_b", "id_c", ...]' | \
  bash helper-scripts/estimate-node-size.sh mynodered/nodered.json batch
```

Store the resulting widths -- you will need them for horizontal positioning.

### 3. Build the topology

From each source, trace forward through wires to build a mental model of the chain(s).
Use `connected --forward --summary` from each source. Assign each node a **column**
(depth from source):

- Column 0: Source/entry nodes
- Column 1: First downstream nodes
- Column N: Nodes at depth N from any source

If a node is reachable from multiple sources at different depths, use the **longest
path** (maximum depth) -- this keeps it to the right of all its predecessors.

### 4. Position columns left to right (edge-to-edge spacing)

Start column 0 at:
```
x_col0 = GROUP_LEFT_MARGIN + GROUP_PADDING_LEFT  (= 40 + 120 = 160)
```

For each subsequent column, calculate the x position using **actual node widths** to
prevent overlaps. The goal is a consistent `HORIZONTAL_GAP` (60 px) of visible space
between the right edge of a node and the left edge of the next node.

**For each hop from column N to column N+1:**

1. Find the widest node in column N (call it `w_prev`) and the widest node in
   column N+1 (call it `w_next`). Use actual widths from `estimate-node-size.sh`.
2. Calculate the center-to-center distance:
   ```
   center_to_center = w_prev/2 + HORIZONTAL_GAP + w_next/2
   ```
3. Place column N+1 at:
   ```
   x_col(N+1) = x_col(N) + center_to_center
   ```

**Example:** A 160px-wide function node connects to a 120px-wide call-service node.
The target's center x = function_x + 160/2 + 60 + 120/2 = function_x + 80 + 60 + 60
= function_x + 200.

When a column has multiple nodes (fan-out branches at different y values), use the
widest node in that column for spacing since all nodes in a column share the same x.

### 5. Position nodes vertically within columns

**Single node in a column** -- place at the y of its upstream parent's output:
- If the parent has one output going to this node, use the parent's y.
- If the parent has multiple outputs, see fan-out rules below.

**Multiple source nodes (column 0):**
- Same type (e.g., multiple injects): stack at `ENTRY_NODE_STACKING` (60 px) intervals.
- Different types: stack at `SOURCE_NODE_SPACING` (80 px) intervals.
- Test inject nodes: place below the production triggers at `TEST_INJECT_OFFSET_Y`
  (60 px) below the nearest production source.
- The topmost source node's y becomes the group's "main flow line."

**Fan-out (multi-output node):**
When a node has N outputs going to N different downstream nodes, center the source
node vertically among its targets:
- General formula: target_i_y = `parent_y + (i - (N-1)/2) * BRANCH_VERTICAL_SPACING`
- Snap each target to the 20px grid: `target_i_y = snap(target_i_y)`
- 2 outputs: raw targets at `parent_y - 30` and `parent_y + 30`. After snapping:
  e.g., parent_y=300 -> targets 280 and 320 (both on-grid, 40px gap = 10px edge gap,
  too small). Instead shift to 260 and 320 (60px gap, 30px edge gap, meets minimum).
  The simplest approach: place first target at `snap(parent_y - 30)` and second at
  `first_target + 60` -- this guarantees the 60px spacing and grid alignment.
- 3 outputs: targets at `parent_y - 60`, `parent_y`, `parent_y + 60` (already on-grid
  when parent_y is on-grid)
- N outputs: spread at `BRANCH_VERTICAL_SPACING` (60 px) intervals, centered on `parent_y`,
  snap each to grid, then verify every consecutive pair has at least `MIN_VERTICAL_NODE_GAP`
  (30px) edge-to-edge gap

**Parallel replicated chains** (same logic repeated per device):
Stack at `PARALLEL_CHAIN_SPACING` (60 px) between chains.

### 6. Determine the group's base y and placement in the vertical stack

- **First group on the flow (or no groups above):** topmost node y =
  `GROUP_LEFT_MARGIN + GROUP_PADDING_TOP` (= 40 + 40 = 80). So the group's top = 40.

- **New group inserted into an existing vertical stack:** Find the correct position
  in the stack based on logical ordering:
  - If the new group is related to (wired from) an existing group, place it
    immediately below that group.
  - If the new group is independent, place it at the bottom of the stack (below
    all existing groups).
  - Topmost node y = `group_above_bottom + GROUP_VERTICAL_GAP + GROUP_PADDING_TOP`.
  - After inserting, check for overlaps with groups that were already below the
    insertion point -- see "Resolve Group Overlaps."

- **Group below another group (general rule):** topmost node y =
  `previous_group_bottom + GROUP_VERTICAL_GAP + GROUP_PADDING_TOP`.
  The group's top = `previous_group_bottom + GROUP_VERTICAL_GAP`.

### 7. Calculate group bounding box

```
group.x = leftmost_node_x - GROUP_PADDING_LEFT
group.y = topmost_node_y - GROUP_PADDING_TOP
group.w = (rightmost_node_x + GROUP_PADDING_RIGHT) - group.x
group.h = (bottommost_node_y + GROUP_PADDING_BOTTOM) - group.y
```

Typically `group.x` will be `GROUP_LEFT_MARGIN` (40) since `leftmost_node_x` =
`GROUP_LEFT_MARGIN + GROUP_PADDING_LEFT` (160). All group bounding box values
(x, y, w, h) must be multiples of 20 and integers.

### 8. Apply positions with batch update-node

**First, dry-run to verify:**

```bash
bash helper-scripts/modify-nodered-flows.sh mynodered/nodered.json batch --dry-run <<'EOF'
[
  {"command": "update-node", "args": {"node_id": "<node_id>", "props": {"x": 160, "y": 80}}},
  {"command": "update-node", "args": {"node_id": "<node_id>", "props": {"x": 360, "y": 80}}},
  ...
  {"command": "update-node", "args": {"node_id": "<group_id>", "props": {"x": 40, "y": 40, "w": 500, "h": 120}}}
]
EOF
```

Review the dry-run output, then apply for real (same command without `--dry-run`).

## Algorithm: Add Nodes to an Existing Group

When new nodes are added to a group that already has well-positioned nodes:

1. **Read the existing group layout** -- query all nodes with positions.
2. **Get sizes for all relevant nodes** -- use batch mode on at least the new nodes and
   their immediate neighbors, so you know the widths for spacing.
3. **Identify new nodes** -- they will be at the default position (x=200, y=200).
4. **Determine where new nodes fit** in the chain:
   - **New independent chain** (most common -- e.g., a new trigger->process->action
     pipeline added alongside existing chains): All nodes in the new chain go below
     existing nodes.
     - First new chain's y: `new_y = max_existing_y + SOURCE_NODE_SPACING` (where
       `max_existing_y` is the maximum y of any existing node in the group, and
       `SOURCE_NODE_SPACING` = 80 px).
     - Additional parallel chains: stack at `PARALLEL_CHAIN_SPACING` (60 px) intervals
       below the first new chain.
     - All nodes in a single horizontal chain share the same y.
     - Use the same column x values as the existing nodes where columns align, or
       compute new column x values using the edge-to-edge spacing formula.
   - **Inserted mid-chain** (between two existing nodes): place at the midpoint x, same
     y as the chain. If there is not enough horizontal space (check using actual widths:
     `gap = next_node_x - prev_node_x - prev_width/2 - next_width/2`; if gap < new_width + 2 * HORIZONTAL_GAP,
     there is not enough room), shift all nodes that are wired downstream of the insertion
     point right by the needed amount.
   - **New branch from an existing node**: place at the next column's x, with y offset by
     `BRANCH_VERTICAL_SPACING` from the nearest sibling branch.
   - **New source/entry node** (additional trigger feeding into an existing chain):
     stack below existing sources at `SOURCE_NODE_SPACING` (80 px) if the new source
     is a different type, or `ENTRY_NODE_STACKING` (60 px) if it is the same type as
     the existing sources.
   - **New tail node**: place to the right of the current rightmost node in the chain,
     using edge-to-edge spacing: `x = rightmost_x + rightmost_width/2 + HORIZONTAL_GAP + new_width/2`.
     Snap the result to the 20px grid.
5. **Compute absolute y coordinates.** For each new node, the y coordinate must be
   an absolute canvas position, not a relative offset. Verify that every new node's
   y value is within the expected range for its group (it should be between
   `group.y + GROUP_PADDING_TOP` and `group.y + group.h - GROUP_PADDING_BOTTOM` after
   the group is resized). If any new node still has y=200 (the add-node default),
   that is a bug -- it means the y calculation was skipped.
6. **Resize the group** if the new nodes extend beyond the current bounding box. Expand
   w and/or h while maintaining padding constants.
7. **Check for overlaps with groups below** after resizing -- see "Resolve Group Overlaps."

**"Downstream of the insertion point"** means: starting from the insertion point, follow
wires forward (output-to-input) recursively to collect all transitively connected nodes.
Only those nodes get shifted -- nodes on unrelated branches at higher x values stay put.

### Worked Example: Adding a 4-node chain to an existing group

Starting state: A group with existing nodes, max y = 420, group at (40, 20, 1000, 440).

New chain: server-state-changed -> RBE -> function -> subflow instance

**1. Compute y for the new chain:**
```
new_y = max_existing_y + SOURCE_NODE_SPACING = 420 + 80 = 500
```
All 4 new nodes get y = 500 (they form a single horizontal chain).

**2. Compute x per column** (using widths from estimate-node-size.sh):
```
Col 0: x = GROUP_LEFT_MARGIN + GROUP_PADDING_LEFT = 40 + 120 = 160
Col 1: x = 160 + server_w/2 + 60 + rbe_w/2
Col 2: x = col1_x + rbe_w/2 + 60 + func_w/2
Col 3: x = col2_x + func_w/2 + 60 + subflow_w/2
```

**3. Resize the group:**
```
new_group_h = (500 + GROUP_PADDING_BOTTOM) - 20 = 520
```
Group becomes (40, 20, 1000, 520).

**4. Build batch (Phase 1 -- positions + group resize):**
```json
[
  {"command": "update-node", "args": {"node_id": "NEW_1", "props": {"x": 160, "y": 500}}},
  {"command": "update-node", "args": {"node_id": "NEW_2", "props": {"x": 380, "y": 500}}},
  {"command": "update-node", "args": {"node_id": "NEW_3", "props": {"x": 560, "y": 500}}},
  {"command": "update-node", "args": {"node_id": "NEW_4", "props": {"x": 760, "y": 500}}},
  {"command": "update-node", "args": {"node_id": "GROUP_ID", "props": {"x": 40, "y": 20, "w": 1000, "h": 520}}}
]
```

**5. Resolve overlaps (Phase 2 -- if needed):**

If the group below was at y=480 (old gap was 20px, now overlapping because the
group grew from h=440 to h=520):
```
delta = (20 + 520 + 20) - 480 = 80
```
Build a second batch shifting that group and ALL its member nodes down by 80px.
Shift every group below it by the same delta too.

## Algorithm: Resolve Group Overlaps

After any layout change (new group, resized group), check that groups do not overlap:

### Vertically stacked groups

1. List all groups on the affected flow with their bounding boxes.
2. Sort by y (top to bottom).
3. For each consecutive pair, check:
   `group_above.y + group_above.h + GROUP_VERTICAL_GAP > group_below.y`
4. If overlap exists, compute the shift delta:
   ```
   delta = (group_above.y + group_above.h + GROUP_VERTICAL_GAP) - group_below.y
   ```
   Then shift the overlapping group **and every group below it on the same flow** down
   by `delta`. "Below it" means all groups with `y >= group_below.y` on the same flow tab.
5. **When shifting a group, translate ALL its member nodes by the same y delta.**
   This includes newly added nodes that were just positioned in the previous step.
   Do not re-layout the group's internals -- just move everything uniformly.
   Update the group's own `y` by the same delta (its `w` and `h` stay unchanged).

### Side-by-side groups

Groups placed horizontally adjacent (same y range, different x) should have at least
`GROUP_HORIZONTAL_GAP` (20 px) between them. Side-by-side overlaps can arise in two ways:

- **A group's width grew** (e.g., nodes were added, making it wider). Its right edge
  may now intrude into a neighboring group's x range.
- **A group was shifted or inserted** adjacent to an existing group at the same y range.

To detect horizontal overlaps: for every pair of groups on the same flow, check whether
their bounding boxes overlap in **both** x and y. Two groups overlap if and only if
`x1 < x2 + w2` and `x2 < x1 + w1` and `y1 < y2 + h2` and `y2 < y1 + h1`. This catches
side-by-side overlaps that a simple top-to-bottom vertical scan would miss.

If an overlap exists:
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
Use `ENTRY_NODE_STACKING` (60 px) for same-type sources, `SOURCE_NODE_SPACING` (80 px)
for different types.

### Switch with symmetric branches
Place the switch node at the **vertical center** of its output range. For 2 outputs:
compute raw targets at switch_y - 30 and switch_y + 30, then snap both to the 20px grid.
Use the approach from the fan-out section to ensure 60px spacing and grid alignment.

### Parallel replicated chains (per-device logic)
Identical chains repeated for each device, stacked at `PARALLEL_CHAIN_SPACING` (60 px).
Each chain is a horizontal line at a different y. All chains share the same column x values.

### Subroutine groups (called via link nodes)
Place **side-by-side** with the calling group using `GROUP_HORIZONTAL_GAP` (20 px),
aligned at the same y as the calling group's top edge. The subroutine group's `link in`
node should be at its left edge, visually adjacent to the calling group's `link call`
or `link out` node.

### Test inject nodes
Position below the main flow line by `TEST_INJECT_OFFSET_Y` (60 px). They connect
to the point in the chain they are meant to test -- a "test notify" inject connects
to the notification function, not to the beginning of the chain.

## Step 3: Apply Positions

**Sanity check before applying:** Scan your batch for:
- Any node that still has y=200 or x=200 (add-node defaults -- position was never calculated)
- Any position value that is not a multiple of 20 (off-grid)
- Any position value that is a float instead of an integer (e.g., 154.0 instead of 160)

Every new node must have explicit x and y values computed from the layout algorithm,
snapped to the 20px grid, and expressed as integers.

After calculating all positions, apply them in a single batch operation (see examples
in the algorithms above). Use `update-node` for both regular nodes (setting `x`, `y`)
and groups (setting `x`, `y`, `w`, `h`).

**Always dry-run first** (`--dry-run` flag), review the changes, then apply for real.

## Step 4: Verify

After applying positions, verify the layout is correct:

1. **Read back affected groups** with `group-nodes <id> --summary` to confirm positions
   look reasonable.
2. **Check for collisions**: no two nodes in the same group should share the exact
   same (x, y).
3. **Check group containment**: every node's (x, y) should fall within its group's
   bounding box with appropriate padding.
4. **Check inter-group spacing**: consecutive groups on the same flow should have at
   least `GROUP_VERTICAL_GAP` (20 px) between them.
5. **Check grid alignment**: every x, y, w, h value in the batch must be a multiple of 20
   and an integer. No floats, no off-grid values.
6. **Check minimum vertical gaps**: every pair of vertically adjacent nodes must have at
   least `MIN_VERTICAL_NODE_GAP` (30px) edge-to-edge gap. Edge gap = `abs(y2 - y1) - (h1/2 + h2/2)`.
7. If anything looks wrong, adjust and re-apply.

## Quick Reference Checklist

Use this as a shorthand when performing a relayout:

1.  Run diff: `summarize-nodered-flows-diff.sh nodered-last-downloaded.json nodered.json`
2.  Query affected groups: `group-nodes <id> --summary` and `--sources --summary`
3.  Batch-measure all nodes: `echo '[...]' | estimate-node-size.sh ... batch`
4.  Build topology (columns by depth from sources)
5.  Compute x per column: `x_next = x_prev + w_prev/2 + 60 + w_next/2`
6.  Compute y per node (stacking, fan-out, parallel chains, new independent chains)
7.  Snap all positions to 20px grid: `snap(v) = int(round(v / 20) * 20)`
8.  Set group base y (first group at 40, others at `prev_bottom + 20`)
9.  Compute group bbox from node extents + padding
10. Sanity check: no node has y=200 or x=200 (defaults); all positions are multiples of 20; all are integers
11. **Phase 1:** Dry-run batch update (node positions + group sizes), review output
12. Apply Phase 1 batch (remove `--dry-run`)
13. Verify: read back positions, check containment, spacing, grid alignment, and min vertical gaps
14. **Phase 2:** Resolve overlaps -- if any group grew or was inserted, compute shift
    deltas for groups below. Build a SECOND batch of update-node commands to shift
    affected groups and ALL their member nodes (including newly positioned ones).
    Dry-run, review, then apply.
15. Final verify: read back positions, check inter-group spacing (20px gaps)
16. **Check for inter-group overlaps beyond immediate neighbors.** When a group grew
    or shifted, check ALL groups on the same flow for bounding-box overlaps -- not just
    vertically adjacent ones. A group that grew wider may now overlap a side-by-side
    group that wasn't part of the current modification. Use the 2D overlap test:
    `x1 < x2+w2 && x2 < x1+w1 && y1 < y2+h2 && y2 < y1+h1`.

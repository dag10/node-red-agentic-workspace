# Plan: Update Layout Guidance for Vertical Spacing and Grid Alignment

## Problem Statement

Two layout rules need to be enforced across all layout guidance:

1. **Minimum vertical separation between nodes**: The current `ENTRY_NODE_STACKING` constant
   (40px center-to-center) produces only a 10px edge-to-edge gap for standard 30px-tall nodes.
   This clips status text. The minimum acceptable edge-to-edge gap is 30px (60px center-to-center
   for 30px-tall nodes), as demonstrated by the good pair at y=240/y=300.

2. **Grid alignment**: Node-RED snaps to a 20px grid, but the relayout guidance has no mention
   of grid alignment. Positions should always be multiples of 20 and always integers (never
   floats like `200.0`). Many existing nodes already have non-grid positions (e.g., y=899,
   x=1154), and some positions are written as floats (e.g., `4484.5`).

## Current State Analysis

### Vertical spacing measurements

**Good pair** (nodes `e8580effc15fae65` and `d42b708651cac365` in group `3dd00e57cdd419d4`):
- Both: `api-call-service`, 100w x 30h
- Positions: y=240, y=300
- Center-to-center: 60px
- Edge-to-edge gap: 60 - 30 = **30px** (acceptable)

**Too-close pair** (nodes `da365617ca4568c4` and `f0a29bcff40c5ca9` in group `6875e536db1a7077`):
- Both: `api-call-service`, 100w x 30h
- Positions: y=1398, y=1438
- Center-to-center: 40px
- Edge-to-edge gap: 40 - 30 = **10px** (clips status text)

**Conclusion**: Minimum edge-to-edge vertical gap = 30px. For standard 30h nodes, minimum
center-to-center = 60px.

### Current constants and their effective edge gaps (for 30h nodes)

| Constant | Value (c-to-c) | Edge gap | Status |
|----------|----------------|----------|--------|
| `BRANCH_VERTICAL_SPACING` | 60 | 30 | OK (meets minimum) |
| `ENTRY_NODE_STACKING` | 40 | 10 | **VIOLATES** -- must increase to 60 |
| `PARALLEL_CHAIN_SPACING` | 60 | 30 | OK (meets minimum) |
| `SOURCE_NODE_SPACING` | 80 | 50 | OK (exceeds minimum) |
| `TEST_INJECT_OFFSET_Y` | 60 | 30 | OK (meets minimum) |

Only `ENTRY_NODE_STACKING` violates the minimum. It must increase from 40 to 60.

### Grid alignment analysis

**Reference grid-aligned group** (`3c5a78c3963230f2`):
- Group: x=54, y=999, w=712, h=222
- Nodes: x values 230, 290, 540, 640; y values 1040, 1120, 1140, 1180
- All y values are multiples of 20
- Some x values (230, 290) are multiples of 10 but not 20

**Reference NOT grid-aligned nodes**:
- `253d46e1a3d43188`: x=790 (790%20=10), y=640 (ok)
- `4580f1613e8529e8`: x=1290 (1290%20=10), y=899 (899%20=19)
- `6bbdfe6c1af815b0` (group): x=1154 (1154%20=14), y=798 (798%20=18)

The worst offenders are odd values like 899, 1154, 798 that aren't on any clean grid.
The user wants ALL new positions to be multiples of 20 going forward.

### Float/decimal positions in existing JSON

The flows JSON contains many non-integer positions:
- `y: 4484.5`, `y: 1701.5`, `y: 6096.5`, etc.
- `h: 344.5`, `h: 564.5`, `w: 1092.9999809265137`, etc.

Python's `json.dumps` writes `200.0` for float values, but `200` for integers.
The `modify-nodered-flows.py` `write_normalized` function does not coerce floats
to ints. If an agent computes `w_prev/2` (which produces a float in Python) and
passes it as a position, it would be written as a float.

### Current guidance inventory

Files containing layout constants, spacing rules, or positioning guidance:

| File | What it contains |
|------|-----------------|
| `.claude/skills/relayout-nodered-flows/SKILL.md` | Primary layout algorithm, all constants, positioning formulas |
| `docs/plans/2026-02-16-flow-layout-analysis.md` | Original analysis that derived the constants (historical reference) |
| `docs/plans/2026-02-16-relayout-skill.md` | Plan for creating the relayout skill (historical reference) |
| `docs/plans/2026-02-17-fix-relayout-skill.md` | Plan for fixing y-position bugs (historical reference) |
| `helper-scripts/estimate-node-size.py` | Node/group size estimation (no position logic, but used by relayout) |
| `helper-scripts/modify-nodered-flows.py` | Write tool; default add-node position (200,200); `write_normalized` |
| `docs/modifying-nodered-json.md` | References relayout skill for positioning |
| `CLAUDE.md` | References relayout skill for positioning |

The plan files are historical records and should NOT be modified. The active guidance lives
in SKILL.md, and the tools live in the Python scripts.

## Proposed Solution

### Rule 1: Minimum vertical separation

1. Introduce a new constant `MIN_VERTICAL_NODE_GAP` = 30px (edge-to-edge) in SKILL.md.
2. Increase `ENTRY_NODE_STACKING` from 40 to 60 (center-to-center), which produces 30px
   edge gap for 30h nodes, meeting the minimum.
3. Add a general rule: after computing any vertical position, verify that the edge-to-edge
   gap to the nearest neighbor is at least `MIN_VERTICAL_NODE_GAP`. The formula is:
   `gap = abs(y2 - y1) - (h1/2 + h2/2)`. If gap < 30, increase the spacing.
4. Update the fan-out formula for 2 outputs to use parent_y +/- 30 (unchanged) since
   60px c-to-c already meets the minimum for 30h nodes.

### Rule 2: Grid alignment

1. Add a new "Grid Alignment" section to SKILL.md establishing the 20px grid rule.
2. All computed positions (x, y for nodes; x, y, w, h for groups) must be rounded to the
   nearest multiple of 20 before being written.
3. All positions must be integers -- no `.0` decimal components. Agents should use `int()`
   or integer arithmetic when computing positions.
4. Add a `snap_to_grid` helper concept in the guidance: `snap(v) = round(v / 20) * 20`.
5. Update the `modify-nodered-flows.py` `write_normalized` function to coerce position
   fields (x, y, w, h) to integers, preventing accidental float output.
6. Update the constants table: verify all existing constants are multiples of 20 or
   otherwise compatible with grid alignment (they don't need to be multiples of 20 themselves
   since they're deltas, but the resulting positions should land on the grid).

### Impact on existing constants

The existing constants after applying grid snapping:

| Constant | Current | Grid-compatible? | Notes |
|----------|---------|-------------------|-------|
| `GROUP_VERTICAL_GAP` | 18 | No -- 18 is not a multiple of 20. But it's a delta between groups, and if both group positions are on-grid, the gap between them will be whatever it needs to be. | Keep at 18; accept that inter-group gaps don't need to be multiples of 20 |
| `GROUP_HORIZONTAL_GAP` | 28 | Same as above -- delta, not a position | Keep at 28 |
| `GROUP_LEFT_MARGIN` | 34 | 34 is not a multiple of 20. This is a group x position. | Change to 40 (nearest grid-aligned value) |
| `GROUP_PADDING_TOP` | 40 | This is a delta from group edge to node center. If group.y is on-grid and padding is 40, node y is on-grid. | Keep at 40 |
| `GROUP_PADDING_BOTTOM` | 40 | Same | Keep at 40 |
| `GROUP_PADDING_LEFT` | 120 | Delta. If group.x is on-grid (40) and padding is 120, node x = 160, which is on-grid. | Keep at 120 |
| `GROUP_PADDING_RIGHT` | 90 | Delta used for calculating group width. Result: group.w = rightmost_x + 90 - group.x. If rightmost_x is on-grid (multiple of 20) and group.x is on-grid, then group.w = (mult of 20) + 90 - (mult of 20) = 90 + (mult of 20), which is NOT necessarily on-grid. | Change to 80 (nearest grid-friendly value) |
| `HORIZONTAL_GAP` | 50 | Edge-to-edge gap. center_to_center = w1/2 + 50 + w2/2. Node widths are multiples of 20 (from estimate-node-size.py line 234), so w/2 is mult of 10. 10 + 50 + 10 = 70, and position = prev + 70, which won't land on grid. | Change to 60 (widths are mult of 20, so w/2 is mult of 10; 10 + 60 + 10 = 80, which is mult of 20) |
| `BRANCH_VERTICAL_SPACING` | 60 | Position delta. If parent y is on-grid, parent_y + 60 is on-grid. | Keep at 60 |
| `ENTRY_NODE_STACKING` | 40->60 | Increasing to 60. If first node y is on-grid, next is on-grid. | Change to 60 |
| `SOURCE_NODE_SPACING` | 80 | On-grid delta | Keep at 80 |
| `PARALLEL_CHAIN_SPACING` | 60 | On-grid delta | Keep at 60 |
| `TEST_INJECT_OFFSET_Y` | 60 | On-grid delta | Keep at 60 |

**Wait -- let me reconsider the constants more carefully.**

Node widths from `estimate-node-size.py` are always `20 * math.ceil(...)`, so they're
multiples of 20. Half-widths are multiples of 10.

For horizontal positioning: `x_next = x_prev + w_prev/2 + GAP + w_next/2`
- `x_prev` on-grid (mult of 20)
- `w_prev/2` = mult of 10
- `w_next/2` = mult of 10
- Need: `x_prev + mult_10 + GAP + mult_10` = mult of 20
- So: `mult_20 + mult_10 + GAP + mult_10` = `mult_20 + 2*mult_10 + GAP`
- `2*mult_10` is mult of 20
- So: `mult_20 + mult_20 + GAP` = `mult_20 + GAP`
- For result to be mult of 20, GAP must be mult of 20

Current HORIZONTAL_GAP = 50 -- NOT a mult of 20. Change to **60**.

For group width: `group.w = rightmost_x + GROUP_PADDING_RIGHT - group.x`
- `rightmost_x` on-grid (mult 20), `group.x` on-grid (mult 20)
- `rightmost_x - group.x` = mult of 20
- For group.w to be mult of 20, GROUP_PADDING_RIGHT must be mult of 20
- Current: 90. Change to **80**.

For GROUP_LEFT_MARGIN (group.x):
- Current: 34. Change to **40** (nearest multiple of 20 that gives reasonable margin).

After these changes: first node x = GROUP_LEFT_MARGIN + GROUP_PADDING_LEFT = 40 + 120 = 160 (on-grid).

For GROUP_VERTICAL_GAP (18) and GROUP_HORIZONTAL_GAP (28):
- These are inter-group deltas. If group positions are on-grid, the gaps between
  them are determined by the positions, not by the gap constant directly.
- The algorithm says: `next_group.y = prev_group.y + prev_group.h + GAP`
- If prev_group.y and prev_group.h are both mult of 20, then `prev_group.y + prev_group.h`
  is mult of 20. Adding 18 gives a non-mult-of-20.
- Change GROUP_VERTICAL_GAP to **20** (nearest mult of 20).
- Change GROUP_HORIZONTAL_GAP to **20** (nearest mult of 20).

Revised constants:

| Constant | Old | New | Reason |
|----------|-----|-----|--------|
| `GROUP_VERTICAL_GAP` | 18 | 20 | Grid alignment |
| `GROUP_HORIZONTAL_GAP` | 28 | 20 | Grid alignment |
| `GROUP_LEFT_MARGIN` | 34 | 40 | Grid alignment |
| `GROUP_PADDING_RIGHT` | 90 | 80 | Grid alignment (group.w must be mult of 20) |
| `HORIZONTAL_GAP` | 50 | 60 | Grid alignment (node x must be mult of 20) |
| `ENTRY_NODE_STACKING` | 40 | 60 | Min vertical gap rule (was 10px edge gap, now 30px) |
| `GROUP_PADDING_TOP` | 40 | 40 | Already grid-compatible |
| `GROUP_PADDING_BOTTOM` | 40 | 40 | Already grid-compatible |
| `GROUP_PADDING_LEFT` | 120 | 120 | Already grid-compatible |
| `BRANCH_VERTICAL_SPACING` | 60 | 60 | Already grid-compatible |
| `SOURCE_NODE_SPACING` | 80 | 80 | Already grid-compatible |
| `PARALLEL_CHAIN_SPACING` | 60 | 60 | Already grid-compatible |
| `TEST_INJECT_OFFSET_Y` | 60 | 60 | Already grid-compatible |

## Implementation Steps

### Step 1: Update `.claude/skills/relayout-nodered-flows/SKILL.md`

This is the primary file -- all layout rules live here.

**1a. Add a "Grid Alignment" section** after the "Numeric Constants" section (after line 139).

New section:

```markdown
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
to the nearest grid point.
```

**1b. Update the constants table** (lines 99-139):

Changes to make:
- `GROUP_VERTICAL_GAP`: 18 -> 20
- `GROUP_HORIZONTAL_GAP`: 28 -> 20
- `GROUP_LEFT_MARGIN`: 34 -> 40
- `HORIZONTAL_GAP`: 50 -> 60
- `GROUP_PADDING_RIGHT`: 90 -> 80
- `ENTRY_NODE_STACKING`: 40 -> 60

**1c. Add `MIN_VERTICAL_NODE_GAP` constant** to the vertical spacing table:

```markdown
| `MIN_VERTICAL_NODE_GAP` | 30 px | Minimum edge-to-edge gap between any two vertically adjacent nodes. Verify after layout. |
```

**1d. Update the "Position columns left to right" section** (step 4, line 183).

Update the starting x calculation:
```
x_col0 = GROUP_LEFT_MARGIN + GROUP_PADDING_LEFT  (= 40 + 120 = 160)
```
(Was: 34 + 120 = 154)

**1e. Update the fan-out formula** (line 224):

The 2-output case says `parent_y - 30` and `parent_y + 30`. With the grid rule, if
parent_y is on-grid (mult of 20), then parent_y +/- 30 is NOT on-grid.

For 2 outputs with `BRANCH_VERTICAL_SPACING = 60`:
- Targets at `parent_y - 30` and `parent_y + 30` -- these are NOT multiples of 20 if parent_y is.
- Change to: targets at `parent_y - BRANCH_VERTICAL_SPACING/2` and `parent_y + BRANCH_VERTICAL_SPACING/2`,
  then snap to grid. `parent_y - 30` snaps to `parent_y - 40` or `parent_y - 20`.

Actually, the better approach: change the fan-out to use the general formula
`target_i_y = parent_y + (i - (N-1)/2) * BRANCH_VERTICAL_SPACING`, then snap each to grid.

For 2 outputs: targets at `parent_y - 30` and `parent_y + 30`.
- If parent_y = 300: targets 270 and 330. Snap: 280 and 340. Gap: 60 (ok, edge gap = 30).
- Hmm, but the targets are now no longer symmetric around parent_y.

Better: use 2 outputs spaced at 60px: `parent_y - 20` and `parent_y + 40`, or just
use the general formula and snap. The snap will naturally handle it. After snapping,
the parent node might need to be re-centered. Actually, the simplest approach is:

For fan-out, compute target positions, snap each to grid, then verify the parent is
visually centered (adjust parent_y if needed to be the midpoint of snapped targets,
then snap parent_y).

For 2 outputs: place at `parent_y - 40` and `parent_y + 20` (or `parent_y` and `parent_y + 60`).
The second option is simpler: first output at parent_y, second at parent_y + 60.
But the current aesthetic puts the parent at the center.

Let me think about this differently. The simplest grid-compatible fan-out:
- N outputs, spaced at BRANCH_VERTICAL_SPACING (60, which is mult of 20).
- First target at: `parent_y - ((N-1) * 60) / 2`, snapped to grid.
- For N=2: first at `parent_y - 30`, snap to `parent_y - 20` or `parent_y - 40`.
- For N=3: first at `parent_y - 60`, which IS on-grid (if parent_y is).

For N=2, a cleaner approach: use spacing of 40 instead of 60, giving targets at
parent_y - 20 and parent_y + 20 (both on-grid). But 40px c-to-c = 10px edge gap,
which violates the minimum.

Better: for N=2, use spacing of 60 but offset targets asymmetrically to stay on grid:
parent_y - 40 and parent_y + 20. Total spread = 60, first target below parent, second
above. That looks odd visually.

**Best approach**: Keep the general formula and add "snap to nearest grid point" as a
post-processing step. For 2 outputs from parent_y=300:
- target1 = 300 - 30 = 270, snap to 260 or 280
- target2 = 300 + 30 = 330, snap to 320 or 340
- Choosing snap-down: 260 and 320 (gap = 60, edge gap = 30, both on-grid)
- Or snap-up: 280 and 340 (gap = 60, same)
- Either way works. The snap direction should preserve the gap >= MIN_VERTICAL_NODE_GAP.

The cleanest rule: compute target positions from the formula, then snap each to grid.
The gap between snapped positions will be approximately 60 +/- up to 10px (due to
different snap directions), but always at least 40 (which gives 10px edge gap --
violates!).

Hmm, this shows the tension. Let me reconsider.

Actually: if we snap symmetrically (both snap in the same direction), the gap is preserved
exactly. E.g., 270->260 and 330->320, gap = 60. Or 270->280 and 330->340, gap = 60.
The key is to snap all targets in the same direction. The simplest rule: round each
target to nearest multiple of 20. If both snap down or both snap up, gap is preserved.
If they snap in opposite directions, gap could be 40 or 80.

For the 2-output case specifically, the safest formulation: use `parent_y - 40` and
`parent_y + 20`, which gives 60px gap. But the parent isn't centered. Or use
`parent_y - 20` and `parent_y + 40`, same issue.

**Final decision**: Change the fan-out formulation to ensure grid alignment by
construction. For N outputs:
- Spread = (N-1) * BRANCH_VERTICAL_SPACING
- First target y = parent_y - snap(spread / 2) (snap the offset, not the position)
- Subsequent targets: first_y + i * BRANCH_VERTICAL_SPACING

For N=2: spread = 60, snap(30) = 20 or 40.
- Option A: first at parent_y - 20, second at parent_y + 40 (gap 60, on-grid)
- Option B: first at parent_y - 40, second at parent_y + 20 (gap 60, on-grid)

I'll use the "snap to grid, then verify gaps" approach in the guidance rather than
trying to make the formula produce grid values directly. Add a post-computation step:
"Snap all computed positions to the 20px grid. Then verify that the edge-to-edge gap
between every pair of vertically adjacent nodes is at least MIN_VERTICAL_NODE_GAP (30px).
If snapping compressed a gap below the minimum, shift the lower node down to the next
grid point."

**1f. Update the group base y calculation** (line 235):

```
GROUP_LEFT_MARGIN + GROUP_PADDING_TOP = 40 + 40 = 80
```
(Was: 34 + 40 = 74)

**1g. Update the group bounding box formulas** (line 253):

```
group.x = leftmost_node_x - GROUP_PADDING_LEFT
group.y = topmost_node_y - GROUP_PADDING_TOP
group.w = (rightmost_node_x + GROUP_PADDING_RIGHT) - group.x
group.h = (bottommost_node_y + GROUP_PADDING_BOTTOM) - group.y
```

With the new constants: `group.x` = 160 - 120 = 40 (on-grid).
`group.w` = (rightmost + 80) - 40 = rightmost + 40, which is on-grid if rightmost is.

**1h. Add to the verification step** (Step 4, line 466):

Add a check:
```
6. **Check grid alignment**: every x, y, w, h value in the batch must be a multiple of 20
   and an integer. No floats, no off-grid values.
```

**1i. Update the sanity check** (around line 455):

Add grid check alongside the x=200/y=200 check:
```
**Sanity check before applying:** Scan your batch for:
- Any node that still has y=200 or x=200 (add-node defaults -- position was never calculated)
- Any position value that is not a multiple of 20 (off-grid)
- Any position value that is a float instead of an integer (e.g., 154.0 instead of 160)
```

**1j. Update the Quick Reference Checklist**:

Add a grid snap step:
```
5b. Snap all positions to 20px grid: snap(v) = int(round(v / 20) * 20)
```

And update step 9 to include grid check:
```
9.  Sanity check: no node has y=200 or x=200 (defaults); all positions are multiples of 20; all are integers
```

**1k. Update all worked examples** in the skill to use new constants:

- Change x_col0 from 154 to 160
- Change group.x from 34 to 40
- Change group.y calculations to use new inter-group gap (20 instead of 18)
- Ensure all example values are multiples of 20

### Step 2: Update `helper-scripts/modify-nodered-flows.py`

**2a. Add integer coercion to `write_normalized`** (line 81-94):

Add a step that coerces position fields to integers before writing. This is a safety net
that prevents floats from leaking into the JSON regardless of what the agent passes.

In `sort_keys_recursive` or as a separate pass, detect nodes (dicts with "id" and "type"
fields) and coerce their `x`, `y` to `int()`. For group nodes (type="group"), also coerce
`w` and `h`.

Alternatively, add a new function `coerce_positions(data)` called before `write_normalized`:

```python
POSITION_FIELDS = {"x", "y"}
GROUP_POSITION_FIELDS = {"x", "y", "w", "h"}

def coerce_positions(data):
    """Ensure position fields are integers, not floats."""
    for node in data:
        if not isinstance(node, dict):
            continue
        fields = GROUP_POSITION_FIELDS if node.get("type") == "group" else POSITION_FIELDS
        for field in fields:
            if field in node and isinstance(node[field], float):
                node[field] = int(round(node[field]))
```

Call this in `main()` before `write_normalized(data, args.flows)`, and also in `cmd_batch`
before the data replacement. This ensures ALL writes produce integer positions.

### Step 3: No changes needed to other files

- `CLAUDE.md`: Already references the relayout skill. No position-specific guidance to update.
- `docs/modifying-nodered-json.md`: References the relayout skill for positioning. No constants.
- `docs/exploring-nodered-json.md`: Read-only exploration docs. No layout guidance.
- `helper-scripts/estimate-node-size.py`: Sizes, not positions. Already produces integer widths
  (multiples of 20). Heights are not required to be grid-aligned.
- `docs/plans/*`: Historical records. Do not modify.

## Testing Strategy

### Test grid alignment of constants

Manually verify the arithmetic chain produces on-grid results:

```
GROUP_LEFT_MARGIN = 40 (mult of 20: yes)
GROUP_PADDING_LEFT = 120 (mult of 20: yes)
First node x = 40 + 120 = 160 (mult of 20: yes)

HORIZONTAL_GAP = 60 (mult of 20: yes)
Node widths: always mult of 20 (from estimate-node-size.py)
Half-widths: mult of 10
center_to_center = mult_10 + 60 + mult_10 = mult_20 + 60 = mult_20
Next node x = 160 + mult_20 = mult_20 (yes)

GROUP_PADDING_TOP = 40 (mult of 20: yes)
GROUP_VERTICAL_GAP = 20 (mult of 20: yes)
First group y = 40 (if first group top is at GROUP_LEFT_MARGIN = 40)
First node y = 40 + 40 = 80 (mult of 20: yes)

BRANCH_VERTICAL_SPACING = 60 (mult of 20: yes)
Branch target: 80 + 60 = 140 (mult of 20: yes)

SOURCE_NODE_SPACING = 80 (mult of 20: yes)
ENTRY_NODE_STACKING = 60 (mult of 20: yes)

Group bottom = bottommost_y + GROUP_PADDING_BOTTOM = mult_20 + 40 = mult_20
Next group top = bottom + GROUP_VERTICAL_GAP = mult_20 + 20 = mult_20
Next group first node = top + GROUP_PADDING_TOP = mult_20 + 40 = mult_20

GROUP_PADDING_RIGHT = 80 (mult of 20: yes)
group.w = (rightmost_x + 80) - group.x = mult_20 + 80 - mult_20 = 80 + mult_20 (yes)
group.h = (bottommost_y + 40) - group.y = mult_20 - mult_20 + 40 (yes, mult of 20)
```

All arithmetic checks out. Every position computed from these constants will be on-grid
when starting from on-grid values.

### Test minimum vertical gap

Verify that no constant produces an edge gap < 30px for standard 30h nodes:

```
ENTRY_NODE_STACKING = 60: edge gap = 60 - 30 = 30 (meets minimum)
BRANCH_VERTICAL_SPACING = 60: edge gap = 60 - 30 = 30 (meets minimum)
PARALLEL_CHAIN_SPACING = 60: edge gap = 60 - 30 = 30 (meets minimum)
SOURCE_NODE_SPACING = 80: edge gap = 80 - 30 = 50 (exceeds minimum)
TEST_INJECT_OFFSET_Y = 60: edge gap = 60 - 30 = 30 (meets minimum)
```

All pass.

### Test integer coercion

After implementing Step 2, create a test:
```bash
# Create a temporary flows file and update a node with float positions
python3 -c "
import json
data = [{'id': 'test1', 'type': 'inject', 'x': 200.0, 'y': 300.0, 'z': 'flow1', 'wires': [[]]}]
with open('/tmp/test-flows.json', 'w') as f:
    json.dump(data, f)
"
bash helper-scripts/modify-nodered-flows.sh /tmp/test-flows.json \
  update-node test1 --props '{"x": 160.0, "y": 280.0}'
# Verify output has integer positions, not 160.0 / 280.0
python3 -c "
import json
with open('/tmp/test-flows.json') as f:
    data = json.load(f)
node = data[0]
assert isinstance(node['x'], int), f'x is {type(node[\"x\"])}: {node[\"x\"]}'
assert isinstance(node['y'], int), f'y is {type(node[\"y\"])}: {node[\"y\"]}'
print('PASS: positions are integers')
"
```

### Verify the updated SKILL.md is internally consistent

Read through the entire updated SKILL.md and verify:
1. All worked examples use the new constants
2. No references to old constant values remain (34, 18, 28, 50, 90, 154, 74)
3. The grid alignment section is referenced where needed
4. The verification checklist includes grid checks

## Risks & Considerations

1. **Changing constants affects visual appearance**: The new spacing will look slightly
   different from the user's hand-crafted layouts. However, the user explicitly requested
   grid alignment, so this is expected. The changes are small (18->20, 28->20, 34->40,
   50->60, 90->80) and should produce visually similar results.

2. **Existing flows won't be retroactively aligned**: Only newly laid-out nodes will follow
   the grid. Existing positions (like y=899 or y=4484.5) will remain until those flows are
   re-laid-out. This is intentional -- the relayout skill only touches modified groups.

3. **The integer coercion in modify-nodered-flows.py affects ALL writes**: This means even
   non-position writes (where x/y happen to be present) will get coerced. This is safe
   because x/y/w/h should always be integers in Node-RED JSON. The coercion only fires
   for values that are already floats (not strings, not integers), so it's a no-op for
   properly typed data.

4. **ENTRY_NODE_STACKING increasing from 40 to 60 makes groups taller**: Groups with many
   stacked entry nodes (e.g., the TEST group with 7 inject nodes) will be taller. With the
   old spacing: 7 nodes spanning 6 * 40 = 240px. With new spacing: 6 * 60 = 360px. This is
   120px taller but ensures status text is never clipped.

5. **The fan-out snap issue**: For 2-output nodes, the formula `parent_y +/- 30` produces
   off-grid values. The "snap to grid then verify gaps" approach handles this gracefully.
   The guidance should use the general formula plus snap, rather than trying to make the
   formula itself produce grid values. The explicit example for 2 outputs should show the
   snap step.

6. **GROUP_HORIZONTAL_GAP changing from 28 to 20**: Side-by-side groups will be slightly
   closer together. The original 28px was chosen from observation; 20px is still visually
   adequate separation. The user explicitly wants grid alignment, which takes priority.

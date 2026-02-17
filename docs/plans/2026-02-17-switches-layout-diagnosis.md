# Diagnosis: Switches Flow Layout Breakage

## Summary

Starting in commit `ce2758a` (mynodered submodule, "Add LED brightness mirroring for all Inovelli light switches"), the layout of the Switches flow (`a21bcb9abb9ff4db`) became badly broken. New LED mirroring nodes were added to 5 existing groups and 3 new groups. The 3 new standalone groups are correctly laid out. The Bedroom Switch group (the first group on the flow) is correctly laid out. But in the remaining 4 existing groups that received new nodes, those nodes are positioned hundreds to thousands of pixels above their group bounding boxes.

## Root Cause

The agent calculated group dimensions and overlap cascading correctly, but **failed to write the correct y positions to the new nodes** in 4 of the 5 modified existing groups. The new nodes retained their default placeholder y=200 position from the `add-node` command. Only the Bedroom Switch group (which has no y-offset since it's the first group at y=19) and the 3 new standalone groups had their node y positions set correctly.

The evidence is definitive:

- **Group bounding boxes** were calculated as if the new nodes were at their intended positions (below existing nodes). The heights match exactly.
- **Overlap resolution** shifted all groups and their members down by cascading deltas. This shift was applied uniformly to both existing nodes and the misplaced new nodes.
- **New node y positions** all equal `200 + group_shift_delta`, proving they started at y=200 (the modify tool's default) and were only moved by the uniform group shift, never positioned properly within their groups.

| Group | Shift Delta | New Node y | = 200 + delta? |
|-------|------------|------------|----------------|
| Office Switch | +59 | 259 | 200 + 59 = 259 (yes) |
| Kitchen Island Switch | +138 | 338 | 200 + 138 = 338 (yes) |
| Main Bathroom Switch | +217 | 417 | 200 + 217 = 417 (yes) |
| Kitchen Counter Switch | +298 | 498 | 200 + 298 = 498 (yes) |

## Affected Groups

### Groups with broken layout (new nodes outside group bbox)

| Group | Group ID | Group y range | New nodes y | Overflow above |
|-------|----------|--------------|-------------|----------------|
| Office Switch | `665d665e80f3b268` | 558-1099 | 259 | 299px above |
| Kitchen Island Switch | `b848c5fadf01f8a1` | 1117-1578 | 338 | 779px above |
| Main Bathroom Switch | `db22a7aff79ea18f` | 1596-2237 | 417 | 1179px above |
| Kitchen Counter Switch | `56f75a37fa7bd249` | 3237-3498 | 498 | 2739px above |

### Groups with correct layout

| Group | Group ID | Notes |
|-------|----------|-------|
| Bedroom Switch | `3dd00e57cdd419d4` | First group, no shift needed. New nodes at y=500, correctly 80px below existing max y=420. |
| Kitchen Ceiling Switch (LED Mirroring) | `9504060c7f3aa5c0` | New standalone group. Nodes at y=3556, 40px below group top at 3516. Correct. |
| Entrance Switch (LED Mirroring) | `1743199edb8cea59` | New standalone group. Nodes at y=3654, 40px below group top at 3614. Correct. |
| Entrance Switch Slave (LED Mirroring) | `721ea6919c42dd45` | New standalone group. Nodes at y=3752, 40px below group top at 3712. Correct. |

## Detailed Before/After Comparison

### Office Switch (most illustrative example)

**Before ce2758a:**
- Group bbox: x=34, y=499, w=1032, h=464.5 (bottom=963.5)
- 17 nodes, y range: 540-920
- No LED mirroring nodes

**After ce2758a:**
- Group bbox: x=34, y=558, w=1000, h=541 (bottom=1099)
- 21 nodes (4 new LED mirroring nodes added)
- Existing nodes shifted uniformly by +59px (y range: 599-979)
- New LED mirroring nodes at y=259 (299px ABOVE group top)
- New nodes x positions are correct (154, 374, 554, 754)

**Intended positions for new nodes:** y=1059 (existing max 979 + 80px SOURCE_NODE_SPACING). This matches the group height calculation: (1059 + 40) - 558 = 541 = actual group height.

### Kitchen Counter Switch (worst case)

**Before:** Group at y=2939, nodes at y=2980-3080
**After:** Group at y=3237, nodes at y=498-3378
- New nodes at y=498 are **2739px above** the group's top edge
- The 4 new LED mirroring nodes occupy the same y=498 row, floating far above the canvas area where the group renders

## How Groups Overlap

Because the new nodes are rendered far above their groups, they visually overlap with other groups higher on the flow:

- **Office Switch new nodes (y=259)** overlap with the **Bedroom Switch group** (y=19 to 540)
- **Kitchen Island new nodes (y=338)** overlap with the **Bedroom Switch group** and **Office Switch group**
- **Main Bathroom new nodes (y=417)** overlap with the **Bedroom Switch group** and **Office Switch group**
- **Kitchen Counter new nodes (y=498)** overlap with the **Bedroom Switch group** (specifically near its new LED chain at y=500)

The side-by-side groups (Office Hue Remote at x=1154 beside Office Switch, and Kitchen Scenes at x=934 beside Kitchen Island) are correctly positioned relative to their neighbors and are not part of this issue -- those were always side-by-side, not stacked.

## Patterns Observed

1. **Only y positions are wrong, x positions are correct.** The horizontal layout (column x positions) was calculated correctly for all new nodes in all groups. Only the vertical placement failed.

2. **New standalone groups are correct.** The 3 new groups (Kitchen Ceiling, Entrance, Entrance Slave LED Mirroring) have nodes correctly positioned at group_top + GROUP_PADDING_TOP.

3. **The first existing group (Bedroom Switch) is correct.** Since this group has no shift delta (it's at y=19, the top of the flow), the default y=200 placeholder happened to be overwritten with the correct y=500 during relayout.

4. **Group dimensions were calculated correctly.** All 5 modified groups have heights that exactly match the expected height if the new nodes had been placed at their intended positions. This means the agent computed the correct layout but failed to apply the y coordinates.

5. **The error grows proportionally with distance from the top.** Groups further down the flow have larger shift deltas, so the new nodes end up further from their intended positions.

## Theory: What Went Wrong

The relayout was performed in multiple stages:

1. **Nodes were added** via `modify-nodered-flows.sh add-node` with x positions specified but y positions left at the default (200) -- or set to 200 explicitly.

2. **The agent calculated the correct intended positions** for all new nodes (we know this because the group dimensions match the intended layout).

3. **The batch update to set node positions** either:
   - (a) Was only executed for the Bedroom Switch group and the new standalone groups, with the other 4 groups skipped or forgotten, OR
   - (b) Was executed for all groups but with y=200 (the placeholder) used instead of the calculated values for those 4 groups

4. **Overlap resolution** correctly shifted all groups and their contents down by cascading deltas, but this operated on the already-wrong y=200 positions.

The commit message claims "Relaid out all modified/new groups with proper spacing" which suggests the agent believed it had done the relayout. The most likely explanation is that the agent ran the relayout calculations correctly but made an error in the batch `update-node` command that applied the positions -- either by omitting the y values or by using the wrong variable/value for the 4 groups that aren't at the top of the flow.

## Second Commit (ba1f48a)

The follow-up commit `ba1f48a` ("Fix LED mirroring showing stale brightness when lights turn off") only changed function node code (the `func` field contents). It did not touch any node positions, so it did not introduce or fix any layout issues. The layout problems exist entirely from `ce2758a`.

## What Needs to Be Fixed

For each of the 4 affected groups, the 4 new LED mirroring nodes need to be moved from their current positions (y=200+shift) to their intended positions (existing_max_y + 80). The group bounding boxes are already correct and do not need to change. The inter-group gaps are already correct (all 18px) and do not need adjustment.

| Group | Node IDs to fix | Current y | Correct y |
|-------|----------------|-----------|-----------|
| Office Switch | `22f5f3c19f649d4b`, `e453f845a970bc04`, `047da2389b44a66f`, `98fd2e3795054f51` | 259 | 1059 |
| Kitchen Island Switch | `4ecb4b9e807c5148`, `c33e8310e2ade558`, `c26c82fbb1f78c92`, `f56b04147ae07e13` | 338 | 1538 |
| Main Bathroom Switch | `6dedaa4d93b074ef`, `acac167dad2e28c3`, `f9db1ffd935c1bc5`, `9184e1b082af1944` | 417 | 2197 |
| Kitchen Counter Switch | `0292801aa4ec22fd`, `5d24f49ecc5f0190`, `1e5d2e93c4dc855e`, `eff12d545fac8c50` | 498 | 3458 |

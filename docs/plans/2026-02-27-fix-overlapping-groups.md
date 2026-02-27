# Plan: Fix Overlapping Groups and Add Overlap Prevention Guidance

## Problem Statement

Several groups across different flows overlap or have insufficient gaps between them.
The most critical issue is group `665d665e80f3b268` (Office Switch) overlapping group
`6875e536db1a7077` (Kitchen Scenes) on the Switches flow by 160x160 pixels. Additional
1px overlaps exist on the Bedtime and Main flows, introduced when Task 3 snapped
positions to the 20px grid.

## Current State Analysis

### Overlap 1: Switches Flow (critical, pre-existing)

- **Office Switch** (`665d665e80f3b268`): x=20, y=760, w=1080, h=740 (right=1100, bottom=1500)
- **Kitchen Scenes** (`6875e536db1a7077`): x=940, y=1320, w=1080, h=160 (right=2020, bottom=1480)
- Overlap region: 160px wide x 160px tall (x: 940-1100, y: 1320-1480)
- This overlap was present in production (nodered-last-downloaded.json had Office Switch
  right=1096, Kitchen Scenes x=934, so 162px overlap).

Kitchen Scenes is a **side-by-side group** -- its nodes are at x=1080-1920, well to
the right of Office Switch nodes (x=160-1000). Office Hue Remote (`6bbdfe6c1af815b0`)
is another side-by-side group at x=1160, y=800. The problem is Kitchen Scenes' left
padding extends to x=940 which intrudes into Office Switch's horizontal range.

### Overlap 2: Bedtime Flow (introduced by Task 3 grid snap)

- **When coming home...** (`bf2d44b53c68932d`): bottom=440
- **30 minute heads up** (`33619da71ec917dd`): y=439
- Overlap: 1px. In production, `y` was 439 with bottom at 421, so gap was 18px.
  After Task 3 snapped "When coming home" from h=189.5 to h=200, its bottom moved
  from 421 to 440, creating a 1px overlap.

### Overlap 3: Main Flow (introduced by Task 3 grid snap)

- **Handle dashboard buttons** (`cf54d2b180e5f846`): bottom=1701
- **Send notification...** (`09c855bd97c74125`): y=1700 (1px overlap)
- **Send notification...** bottom=1860
- **Temporarily turn on...** (`cb9aa43369eb41f0`): y=1859 (1px overlap)
- In production, these had 0.5px gaps. Task 3 grid snapping rounded positions
  such that the gaps became -1px.

### Additional Note: Widespread 18px Gaps

Many flows (Bedtime, Main, Tablets, Attention, Config, Scratchpad) have 18px gaps
between groups rather than the required 20px. These are pre-existing from the original
Node-RED editor layout. Fixing all of them would require cascading shifts across nearly
every flow. This plan does NOT address those except where they cascade from overlap fixes.

## Proposed Solution

Three fixes, each using batch `update-node` operations to shift groups and their member
nodes:

1. **Switches**: Move Kitchen Scenes group right by 180px so it sits side-by-side with
   Office Switch, separated by `GROUP_HORIZONTAL_GAP` (20px).

2. **Bedtime**: Shift "30 minute heads up" down by 21px (snapped to y=460), then cascade
   all 7 groups below it to maintain >= 20px gaps.

3. **Main**: Shift "Send notification" down by 40px (y=1740), then cascade the 3 groups
   below it.

4. **SKILL.md update**: Add guidance about checking for and preventing inter-group
   overlaps, including a step in the Quick Reference Checklist.

## Implementation Steps

### Step 1: Fix Switches -- Kitchen Scenes horizontal overlap

Kitchen Scenes group and all 8 member nodes shift right by `delta_x = +180`:

| Node / Group | Current x | New x |
|---|---|---|
| Group `6875e536db1a7077` | 940 | 1120 |
| `20e73d5cdd622a8c` (Kitchen Island Switch Event) | 1080 | 1260 |
| `0294d6b13028ae42` (Kitchen Ceiling Switch Event) | 1080 | 1260 |
| `a902b30972df0c15` (Inovelli Button subflow) | 1320 | 1500 |
| `da365617ca4568c4` (api-call-service) | 1720 | 1900 |
| `5233350ef1ed35ce` (Inovelli Interaction subflow) | 1520 | 1700 |
| `20d00467dda00ff5` (api-call-service) | 1920 | 2100 |
| `68f33ac241ddac2e` (Kitchen Counter Switch Event) | 1080 | 1260 |
| `f0a29bcff40c5ca9` (api-call-service) | 1720 | 1900 |

New Kitchen Scenes bbox: x=1120, y=1320, w=1080, h=160 (right=2200, bottom=1480).
Horizontal gap to Office Switch: 1120 - 1100 = 20px.

All new x values are multiples of 20. y values unchanged.

### Step 2: Fix Bedtime -- cascade from "30 minute heads up" down

Each group and all its member nodes shift by `delta_y`. The first group shifts to
eliminate the 1px overlap, and subsequent groups shift to maintain >= 20px gaps
(snapped to 20px grid).

| Group | Name | Current y | New y | delta_y | New bottom | Gap above |
|---|---|---|---|---|---|---|
| `33619da71ec917dd` | 30 minute heads up | 439 | 460 | +21 | 602 | 20 |
| `14d888192e1b4551` | Daily reset | 599 | 640 | +41 | 922 | 38 |
| `8d840afcd8e3de51` | Is wind down | 899 | 960 | +61 | 1042 | 38 |
| `3c5a78c3963230f2` | Update bedtime settings | 999 | 1080 | +81 | 1302 | 38 |
| `48d01165e2271cee` | When vacation mode | 1239 | 1340 | +101 | 1482 | 38 |
| `4d017e3a593b36af` | Siri Good Night | 1399 | 1520 | +121 | 1782 | 38 |
| `78d8669dd621e054` | Siri Stop Good Night | 1679 | 1820 | +141 | 1962 | 38 |
| `7a29ece76a555efb` | If home unoccupied | 1860 | 2000 | +140 | 2100 | 38 |

Gaps above range from 20-38px, all on 20px grid. The larger-than-20 gaps result from
the grid snapping requirement -- when a group's bottom is not on a 20px boundary
(e.g., bottom=602), the next group must snap to the next grid point above
`bottom + 20 = 622`, which is 640.

Total operations: 8 groups + 45 member nodes = 53 update-node commands.

### Step 3: Fix Main -- cascade from "Send notification" down

| Group | Name | Current y | New y | delta_y | New bottom | Gap above |
|---|---|---|---|---|---|---|
| `09c855bd97c74125` | Send notification | 1700 | 1740 | +40 | 1900 | 39 |
| `cb9aa43369eb41f0` | Temporarily turn on entrance light | 1859 | 1920 | +61 | 2662 | 20 |
| `78872d64f75efc97` | Siri Show Wifi | 2619 | 2700 | +81 | 2782 | 38 |
| `2ef3863a8e9dd958` | Reset Sonos bass | 2739 | 2820 | +81 | 3022 | 38 |

Total operations: 4 groups + 51 member nodes = 55 update-node commands.

### Step 4: Update SKILL.md with overlap prevention guidance

Add to the Quick Reference Checklist (after step 15) an explicit step about checking
for inter-group overlaps, including both vertical and horizontal overlap detection.
This codifies the overlap checking that should happen as part of every relayout.

Specific additions:
- After Step 15 in the Quick Reference Checklist, reinforce that overlap checking must
  include groups that aren't being directly modified but share x/y range with modified
  groups.
- In the "Resolve Group Overlaps" algorithm, add a note that side-by-side groups can be
  created when a group's width grows, not just when groups are inserted -- so width
  changes need horizontal overlap checks too.

## Execution

All three flow fixes should be done as separate batch operations (one per flow) using:

```bash
bash helper-scripts/modify-nodered-flows.sh mynodered/nodered.json batch <<'EOF'
[ ... update-node commands ... ]
EOF
```

Each batch should be dry-run first (`--dry-run`), reviewed, then applied.

After all three batches, verify with:
```bash
# Re-run the overlap analysis (the Python script from investigation)
# to confirm zero overlaps remain in the modified flows
```

## Testing Strategy

1. **Dry-run each batch** before applying to verify correct positions.
2. **After applying**, re-read affected groups with `group-nodes --summary` to confirm
   all node positions shifted correctly.
3. **Run the full overlap checker** (Python analysis from investigation) on the modified
   `nodered.json` to confirm no overlaps remain on Switches, Bedtime, or Main flows.
4. **Verify grid alignment**: all x, y, w, h values must be multiples of 20 and integers.
5. **Verify group containment**: every node's position falls within its group's bbox.
6. After modifying flows, run `summarize-nodered-flows-diff.sh --git` to check affected
   documentation, and update docs per the after-modifying-flows checklist.

## Risks & Considerations

- **Large cascade on Bedtime and Main**: Moving 8 groups on Bedtime and 4 groups on Main
  is a significant position change. However, since we're only translating groups uniformly
  (all nodes in a group shift by the same delta), the internal layout of each group is
  preserved. The visual result is just groups shifting down.

- **Pre-existing 18px gaps**: Many flows have 18px gaps between groups instead of 20px.
  These are inherited from the original Node-RED editor layout and exist in production.
  This plan intentionally does NOT fix all of them -- only gaps that cascade from the
  overlap fixes. Fixing all gaps globally would require touching nearly every flow and
  is better done as a separate, deliberate effort if desired.

- **19px gap on Bedtime**: The gap between "When bedtime begins" (bottom=221) and
  "When coming home" (y=240) is 19px, not 20px. Fixing this would require shifting
  "When coming home" to y=260 (gap=39px, excessive) or adjusting the first group's
  height. Since 19px is within 1px of the target and this gap existed in production
  (where it was even worse at 10.5px), this is left as-is.

- **Documentation updates**: Since only positions are changing (no functional changes
  to flows), flow documentation content should not need updating. However, the
  diff summary should still be checked in case any docs reference specific coordinates.

# Plan: Fix Group Overlap and Node Width Estimation in Relayout

## Problem Statement

Two layout issues after the dagre-based relayout was applied:

1. **Group overlap**: The newly created group "Cancel departure detection on switch press" (`089fa1f004fbf0b7`) is positioned on top of the existing "Sensor-based occupancy detection" group (`41eee6d57596f252`). They overlap by 1357x11 pixels.

2. **Node width estimation**: The dagre layout uses a character-width heuristic (`len(label)*7 + 55`) that slightly underestimates actual Node-RED rendered widths, causing nodes to appear visually closer (or overlapping) in the editor. Combined with `ranksep: 30` (only 30px between node ranks), this can make adjacent nodes look crowded or overlapping.

## Current State Analysis

### Group overlap diagnosis

The overlap is between these groups on the Occupancy Detection flow (`8ac252f63e58cd8d`):

```
Cancel departure detection: x=10  y=10  w=1391 h=100  bottom=110
Sensor-based occupancy:     x=44  y=99  w=4732 h=491  bottom=590
                            ^^^^  ^^^^
                            overlapping region: 1357x11px
```

**Root cause**: The `modify-nodered-flows.sh` `add-group` command places new groups at default position `x=10, y=10, w=200, h=100` (`helper-scripts/modify-nodered-flows.py`, `_cmd_add_group()`). The "Sensor-based occupancy detection" group was already at `y=99`. When the relayout ran, it expanded the new group's width from 200 to 1391 (correct -- dagre computed the layout), but the group's y position (10) and height (100) stayed the same because the dagre layout produced roughly the same height. The `shift_groups()` function in `relayout-nodered-flows.py:320-364` only shifts groups below a resized group when the group's bottom edge moved down (delta > 0). Since `old_bottom == new_bottom == 110`, delta was 0 and no shift occurred.

The `shift_groups` function has a fundamental gap: it assumes the only source of overlap is a group growing taller. It does NOT detect or resolve:
- Pre-existing overlap from groups placed at default positions
- Overlap from a group being placed above another group
- Overlap between groups that weren't relaid out

Additionally, there are 2 other pre-existing group overlaps (not caused by the relayout):
- Bedroom Switch / Office Switch on the Switches flow: 1032x4px overlap
- Two Config groups on the Config flow: 35x82px overlap

These pre-existing overlaps are minor and likely from manual editing in Node-RED; the plan focuses on preventing the relayout tool from creating or perpetuating overlaps.

### Node width estimation diagnosis

The current width estimation in `estimate_node_dimensions()` at `relayout-nodered-flows.py:153-172`:

```python
label = node.get("name", "") or node.get("type", "")
width = max(100, len(label) * 7 + 55)
```

This maps to Node-RED's actual formula: `max(NODE_WIDTH, textWidth + iconWidth + padding)` where:
- `NODE_WIDTH = 100` (minimum)
- `textWidth` is measured using canvas `measureText` with ~13px Helvetica Neue
- `iconWidth` is ~20-30px for the left icon
- padding is ~20-25px total (left + right + port area)

The constant `55` covers icon+padding, and `7` approximates per-character width. However:

1. **Per-character width is slightly low**: Helvetica Neue at 13px averages ~7.5px/char for mixed text. For labels with mostly uppercase or wide characters (M, W, m, w), it can be 8-9px/char. The `7` multiplier underestimates by ~0.5px/char, accumulating to 5-20px underestimate for typical labels.

2. **`ranksep: 30` is tight**: Even with perfect width estimation, 30px between node columns is visually tight in Node-RED. Nodes have visible borders, port indicators, and sometimes status text that make them feel wider than their calculated bounds.

3. **Missing width factors for specific node types**:
   - **Subflow instances** (`subflow:*`): Show a subflow badge icon on the left side. May need +10-15px.
   - **Nodes with status indicators**: Some nodes show colored status dots, which need a few extra pixels.
   - **Nodes with badges**: Certain node types show additional badges (e.g., "changed" indicators).

Concrete example from the "Cancel departure" group:

| Node | Label | Est Width | NR Approx Width | Delta |
|------|-------|-----------|-----------------|-------|
| Any ZHA event | server-events | 146px | ~153px | +7px |
| departure detection active? | switch | 244px | ~258px | +14px |
| get switch config | link call | 30px | 30px | 0 |
| if non-entrance switch | function | 209px | ~221px | +12px |
| set occupancy: switch cancelled departure | subflow | 342px | ~363px | +21px |

With `ranksep=30`, underestimating a 342px node by 21px means the visual gap to the next node is only ~9px instead of 30px.

## Proposed Solution

### Fix 1: Comprehensive group-overlap resolution after relayout

After dagre positions are applied to all groups that need relayout, run a full overlap-resolution pass on the entire flow. This replaces the current `shift_groups` approach (which only handles the specific case of a group growing taller) with a more general algorithm.

**Algorithm**: After all dagre-relaid groups have their new positions and dimensions:

1. For each flow tab, collect all top-level groups (those with `z` pointing to the flow, not nested inside another group).
2. Sort groups by `y` position (top to bottom).
3. Scan for vertical overlaps between consecutive groups (considering x-overlap too -- groups that don't overlap horizontally can be at the same y).
4. When overlap is found, shift the lower group (and all groups below it) down by enough to create a gap (e.g., 38px, matching the `GROUP_PAD_TOP` spacing).
5. When shifting a group, also shift all its member nodes (including nested groups).

This approach handles:
- Groups placed at default positions that overlap existing groups
- Groups that grew during relayout and now overlap their neighbors
- Pre-existing overlaps (optional -- could limit to only groups that were relaid out)

### Fix 2: Improved node width estimation

Update `estimate_node_dimensions()` with:

1. **Higher per-character width**: Use `8` instead of `7` to slightly overestimate. Overestimating is preferable to underestimating because extra space between nodes looks fine, but overlapping nodes look broken.

2. **Higher constant for icon + padding**: Use `60` instead of `55` to account for port indicators, status areas, and the slight extra padding in some node types.

3. **Subflow instance padding**: Add an extra 15px for `subflow:*` type nodes (they show a distinctive subflow badge).

4. **Higher minimum width**: Change from `100` to `120` to match common Node-RED rendering behavior.

5. **Increase `ranksep`**: Change from `30` to `50`. This is the most impactful single change -- it gives more breathing room between columns and absorbs width estimation errors gracefully. Node-RED's own auto-layout uses larger spacing.

6. **Increase `nodesep`**: Change from `10` to `20`. This gives more vertical space between parallel nodes.

### Formula comparison

Current: `max(100, len(label) * 7 + 55)` with `ranksep=30, nodesep=10`

Proposed: `max(120, len(label) * 8 + 60)` with `ranksep=50, nodesep=20`, plus +15 for subflow types

Example results:

| Label (len) | Current | Proposed | NR Approx |
|-------------|---------|----------|-----------|
| "Any ZHA event" (13) | 146 | 164 | ~153 |
| "departure detection active?" (27) | 244 | 276 | ~258 |
| "set occupancy: switch cancelled departure" (41) | 342 | 403 | ~363 |

The proposed formula slightly overestimates in all cases, which is the correct bias for layout purposes.

## Implementation Steps

### Step 1: Improve node dimension estimation

**File**: `/Users/drew/Projects/home/helper-scripts/relayout-nodered-flows.py`
**Function**: `estimate_node_dimensions()` (line 153-172)

Replace the current implementation with:

```python
def estimate_node_dimensions(node):
    """Heuristic width/height based on node type and label.

    Intentionally overestimates slightly -- extra spacing between nodes
    looks fine, but overlapping nodes look broken.
    """
    ntype = node.get("type", "")

    if ntype == "junction":
        return 10, 10

    if ntype in ("link in", "link out", "link call"):
        if node.get("l"):
            label = node.get("name", "")
            w = max(100, len(label) * 8 + 60)
            return w, 30
        return 30, 30

    label = node.get("name", "") or node.get("type", "")
    outputs = len(node.get("wires", []))
    # 8px/char slightly overestimates Helvetica Neue at 13px.
    # 60 covers icon (20-30px) + left/right padding (~20px) + port area (~10px).
    width = max(120, len(label) * 8 + 60)

    # Subflow instances show a subflow badge that adds width.
    if ntype.startswith("subflow:"):
        width += 15

    height = max(30, outputs * 13 + 17)
    return width, height
```

### Step 2: Increase dagre spacing settings

**File**: `/Users/drew/Projects/home/helper-scripts/relayout-nodered-flows.py`
**Constant**: `DAGRE_SETTINGS` (line 29-35)

Change to:

```python
DAGRE_SETTINGS = {
    "rankdir": "LR",
    "marginx": 10,
    "marginy": 10,
    "nodesep": 20,   # was 10 -- vertical space between parallel nodes
    "ranksep": 50,   # was 30 -- horizontal space between node columns
}
```

### Step 3: Replace `shift_groups` with comprehensive overlap resolution

**File**: `/Users/drew/Projects/home/helper-scripts/relayout-nodered-flows.py`
**Function**: `shift_groups()` (line 320-364)

Replace with a new function `resolve_group_overlaps()` that:

1. Takes the full `after_data`, `after_idx`, and the set of flow IDs that had groups relaid out.
2. For each affected flow, collects all top-level groups (not nested in another group).
3. Sorts by `y` position.
4. Scans pairs for vertical overlap (where they also overlap horizontally).
5. Shifts groups down to resolve overlaps, with a minimum gap of `GROUP_GAP` (e.g., 38px).
6. Shifts member nodes along with their groups.

```python
GROUP_GAP = 38  # Minimum vertical gap between non-overlapping groups

def resolve_group_overlaps(affected_flow_ids, after_data, after_idx, verbose=False):
    """Resolve vertical group overlaps on flows that had relayout changes.

    For each affected flow, sort groups top-to-bottom and push any
    overlapping group (and everything below it) downward.
    """
    by_id = after_idx["by_id"]

    for flow_id in affected_flow_ids:
        # Collect top-level groups on this flow (not nested inside another group).
        flow_groups = [
            n for n in after_data
            if n.get("type") == "group"
            and n.get("z") == flow_id
            and not n.get("g")  # not nested
        ]
        if len(flow_groups) < 2:
            continue

        # Sort by y position.
        flow_groups.sort(key=lambda g: g.get("y", 0))

        # Scan for overlaps and shift down.
        for i in range(1, len(flow_groups)):
            prev = flow_groups[i - 1]
            curr = flow_groups[i]

            prev_bottom = prev.get("y", 0) + prev.get("h", 0)
            curr_top = curr.get("y", 0)

            # Check horizontal overlap (groups that don't overlap in x can
            # share the same y range).
            px, pw = prev.get("x", 0), prev.get("w", 0)
            cx, cw = curr.get("x", 0), curr.get("w", 0)
            if px + pw <= cx or cx + cw <= px:
                continue  # No horizontal overlap, skip.

            gap = curr_top - prev_bottom
            if gap >= GROUP_GAP:
                continue  # Enough space, no shift needed.

            # Shift this group and everything below it down.
            shift = prev_bottom + GROUP_GAP - curr_top
            if verbose:
                pname = prev.get("name", "(unnamed)")
                cname = curr.get("name", "(unnamed)")
                print(f"  shifting '{cname}' down {int(shift)}px "
                      f"(was overlapping '{pname}')", file=sys.stderr)

            for j in range(i, len(flow_groups)):
                g = flow_groups[j]
                g["y"] = g.get("y", 0) + shift
                # Shift all member nodes.
                for mid in collect_group_node_ids(g["id"], after_idx):
                    member = by_id.get(mid, {})
                    if "y" in member:
                        member["y"] = member["y"] + shift
```

### Step 4: Update main() to use the new overlap resolution

**File**: `/Users/drew/Projects/home/helper-scripts/relayout-nodered-flows.py`
**Function**: `main()` (line 371-460)

After the dagre positioning loop, replace the `shift_groups` call with:

```python
    # Resolve group overlaps on affected flows.
    if relaid_info:
        affected_flows = set(flow_id for _, flow_id, _, _, _ in relaid_info)
        resolve_group_overlaps(affected_flows, after_data, after_idx, verbose=args.verbose)
```

Remove the old `shift_groups` function entirely.

### Step 5: Handle ungrouped nodes that might be in the way

This is a lower-priority enhancement. Currently, the overlap resolution only considers group-vs-group overlap. Ungrouped nodes on the flow could also be in the way of a shifted group. For now, this is acceptable since most automations are organized in groups. If it becomes an issue, a future enhancement could detect and shift ungrouped nodes too.

## Testing Strategy

### Test 1: Verify overlap resolution on the current flows

```bash
# Run relayout with verbose to see what it does
bash helper-scripts/relayout-nodered-flows.sh mynodered/nodered.json \
  --baseline mynodered/nodered-last-downloaded.json --dry-run --verbose
```

Expected: The "Cancel departure detection" group should be shifted so it no longer overlaps "Sensor-based occupancy detection".

### Test 2: Verify node widths are reasonable

```bash
# After running relayout, check spacing within the Cancel departure group
bash helper-scripts/query-nodered-flows.sh mynodered/nodered.json \
  group-nodes 089fa1f004fbf0b7 --full | python3 -c "
import json, sys
nodes = json.load(sys.stdin)
layoutable = [n for n in nodes if n.get('type') not in ('group', 'comment')]
layoutable.sort(key=lambda n: n.get('x', 0))
for i, n in enumerate(layoutable):
    name = n.get('name', '') or n.get('type', '')
    x = n.get('x', 0)
    if i + 1 < len(layoutable):
        next_x = layoutable[i+1].get('x', 0)
        # Estimate this node's width with the new formula
        ntype = n.get('type', '')
        label = n.get('name', '') or ntype
        if ntype in ('link in', 'link out', 'link call') and not n.get('l'):
            w = 30
        else:
            w = max(120, len(label) * 8 + 60)
            if ntype.startswith('subflow:'): w += 15
        gap = next_x - (x + w)
        print(f'{name:50s} gap_to_next={gap:6.1f}px')
"
```

Expected: All gaps should be approximately 50px (the new `ranksep` value).

### Test 3: Check that no new group overlaps exist

```bash
python3 -c "
import json
with open('mynodered/nodered.json') as f:
    data = json.load(f)
groups = [n for n in data if n.get('type') == 'group' and n.get('z')]
by_flow = {}
for g in groups:
    by_flow.setdefault(g['z'], []).append(g)
found = False
for flow_id, fgroups in by_flow.items():
    for i in range(len(fgroups)):
        for j in range(i+1, len(fgroups)):
            g1, g2 = fgroups[i], fgroups[j]
            x1,y1,w1,h1 = g1.get('x',0),g1.get('y',0),g1.get('w',0),g1.get('h',0)
            x2,y2,w2,h2 = g2.get('x',0),g2.get('y',0),g2.get('w',0),g2.get('h',0)
            if (x1 < x2+w2 and x1+w1 > x2 and y1 < y2+h2 and y1+h1 > y2):
                if g1.get('g') == g2['id'] or g2.get('g') == g1['id']:
                    continue
                found = True
                print(f'OVERLAP: {g1.get(\"name\")} vs {g2.get(\"name\")}')
if not found:
    print('No group overlaps found!')
"
```

### Test 4: Regression -- relayout twice should be stable

```bash
# Run relayout once
bash helper-scripts/relayout-nodered-flows.sh mynodered/nodered.json \
  --baseline mynodered/nodered-last-downloaded.json

# Copy result
cp mynodered/nodered.json /tmp/after-first-relayout.json

# Run relayout again (using first result as baseline)
bash helper-scripts/relayout-nodered-flows.sh mynodered/nodered.json \
  --baseline /tmp/after-first-relayout.json --verbose

# Should report "No groups need relayout" since only cosmetic fields changed
```

### Test 5: Upload and verify in Node-RED editor

After applying changes, upload flows and visually verify in the Node-RED editor that:
- Groups don't overlap
- Nodes within groups have comfortable spacing
- The layout looks reasonable for the "Cancel departure detection" group

## Risks & Considerations

1. **Wider layouts take more horizontal space**: Increasing `ranksep` from 30 to 50 and widening node estimates means groups will be wider. For groups with many sequential nodes (long chains), the group width could increase substantially. This is acceptable -- horizontal scrolling in Node-RED is easy, and readability is more important than compactness.

2. **Re-layout of existing groups changes their appearance**: Groups that were previously laid out with `ranksep=30` will get wider spacing if they're relaid out again. This only affects groups with structural changes, not position-only changes. The cosmetic field check (`COSMETIC_FIELDS = {"x", "y", "w", "h"}`) correctly prevents relayout of groups where only positions changed.

3. **Overlap resolution only runs on flows with relaid groups**: Pre-existing overlaps on other flows (like the Bedroom/Office switch overlap) won't be fixed unless those groups are also relaid out. This is intentional -- we shouldn't change layouts the user hasn't asked to modify.

4. **Overlap resolution sorts groups by y and pushes down**: This greedy top-to-bottom approach works well for the typical case (linear vertical stacking of groups). It would not handle complex 2D arrangements with groups at various x positions sharing y ranges. The horizontal overlap check (step 3 of the algorithm) prevents false positives for side-by-side groups.

5. **The overlap resolution shifts ALL groups below the overlapping one**: This could create a cascade effect where many groups are shifted. This is correct behavior -- if a group needs more room, everything below it should move down to preserve the overall vertical ordering.

6. **`GROUP_GAP = 38` choice**: This matches `GROUP_PAD_TOP` (35px) plus a small margin. It's the minimum gap for groups to look visually separate. Could be made configurable if needed.

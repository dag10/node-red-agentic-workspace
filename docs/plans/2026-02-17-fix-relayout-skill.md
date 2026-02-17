# Plan: Fix Relayout Skill for Adding Nodes to Existing Groups

## Problem Statement

When the relayout skill is used to position new nodes added to existing groups, the y-positions of the new nodes are not being set correctly. They remain at the default y=200 from `add-node`, and only receive the overlap-resolution shift delta. This was observed in commit `ce2758a` (mynodered submodule) where 8 LED mirroring chains were added -- the 4-node chains added to 4 of 5 existing groups ended up with their new nodes floating hundreds to thousands of pixels above their group bounding boxes.

The relayout skill is a SKILL.md file containing instructions for Claude agents (not executable code). The bug is in the instructions/algorithm, not in the helper scripts themselves.

## Current State Analysis

### Evidence from the diagnosis (`2026-02-17-switches-layout-diagnosis.md`)

The diagnosis definitively proved:
- New nodes in 4 of 5 existing groups have `y = 200 + shift_delta` (where 200 is the add-node default)
- The 1st existing group (Bedroom Switch, y=19, no shift needed) has correct y positions
- All 3 new standalone groups have correct y positions
- x positions are correct for all new nodes everywhere
- Group bounding boxes were calculated correctly (heights match the intended layout)

This means the agent:
1. Correctly computed x positions and applied them (the skill's x formulas are explicit)
2. Correctly computed group bounding boxes (matching the intended final layout)
3. **Did NOT apply y positions** for new nodes in 4 existing groups
4. Correctly applied overlap shift deltas to all nodes (including the still-at-y=200 ones)

### Root cause: The SKILL.md algorithm for "Add Nodes to an Existing Group" is vague about y-positioning

The skill at `.claude/skills/relayout-nodered-flows/SKILL.md` has a detailed "Algorithm: Add Nodes to an Existing Group" section (lines 280-305). Examining it reveals multiple gaps:

#### Gap 1: No explicit y formula for new independent chains

Step 4 lists four sub-cases for where new nodes fit:
- **Inserted mid-chain**: "same y as the chain" (clear, but only for mid-chain insertion)
- **New branch**: "y offset by BRANCH_VERTICAL_SPACING from the nearest sibling branch" (clear)
- **New source/entry node**: "stack below existing sources at ENTRY_NODE_STACKING spacing" (vague)
- **New tail node**: explicit x formula given, but y is implied to match the chain's y (unclear)

For the LED mirroring case, the new nodes are a **complete independent chain** (4 nodes: server-state-changed -> RBE -> function -> subflow instance) added below all existing nodes in the group. This doesn't cleanly fit any of the four sub-cases. The closest is "New source/entry node" but:

- It says `ENTRY_NODE_STACKING` (40px) which is for same-type stacking, not for spacing between independent chains (should be `SOURCE_NODE_SPACING` = 80px)
- It only discusses the source node position, not where to place the downstream nodes (columns 1, 2, 3) of the new chain
- It never provides an **absolute y formula** like `new_chain_y = max(all_existing_node_y_values) + SOURCE_NODE_SPACING`

Compare this to the x positioning, which has an explicit formula:
```
x_col(N+1) = x_col(N) + w_prev/2 + HORIZONTAL_GAP + w_next/2
```

There is no equivalent y formula for the "add chain to existing group" case.

#### Gap 2: No guidance for "parallel replicated chains" added to existing groups

The "Special Patterns" section describes "Parallel replicated chains (per-device logic)" (line 367) as a common pattern: "Identical chains repeated for each device, stacked at `PARALLEL_CHAIN_SPACING` (60 px)." The LED mirroring chains are exactly this pattern. But the special patterns section only describes the pattern -- it doesn't say how to apply it when adding new chains to an existing group that already has unrelated nodes above.

The agent needs to know: position the new chain at `max_existing_y + SOURCE_NODE_SPACING` (for the first new chain) or `previous_new_chain_y + PARALLEL_CHAIN_SPACING` (for subsequent parallel chains). This specific guidance is absent.

#### Gap 3: Quick Reference Checklist ordering creates a two-phase problem

The checklist (lines 406-419) shows:
```
9.  Dry-run batch update, review output
10. Apply batch update (remove --dry-run)
11. Verify: read back positions, check containment and spacing
12. Resolve overlaps with groups below if any group grew or was inserted
```

Step 12 comes AFTER step 10. Overlap resolution requires **additional** update-node commands (shifting groups and their members down). But the checklist doesn't make it explicit that step 12 generates a **second batch** of position updates that also needs to be dry-run'd and applied. An agent might:
- Build one batch with new node positions + group sizes
- Apply it
- Then compute overlap shifts but fail to generate/apply a second batch
- Or try to merge everything into one batch and get confused

The current structure encourages an error-prone two-phase approach without being explicit about the second batch.

#### Gap 4: The Bedroom Switch succeeded by coincidence

The Bedroom Switch group (y=19, first on the flow) is the only existing group where new node y positions were correct. The diagnosis says the new nodes are at y=500, which is 80px below existing max y=420.

For this group, no overlap shift was needed (it's the first group, nothing above it grew). So the new node y=500 was computed and applied correctly in the single batch. For the other 4 groups, the agent likely attempted to compute y positions based on the **pre-shift** existing node positions but then either:
- Forgot to include y in the update-node props (only included x)
- Or computed y values that were never applied because the batch was structured incorrectly

The Bedroom group working is consistent with the agent only completing the y calculation for the first group it processed and then losing track or making an error for subsequent groups. This is a classic pattern when instructions require repetitive manual computation across many items without a clear, repeatable formula.

### Why x positions worked but y didn't

The x positioning algorithm in the skill is procedural and formula-based:
```
x_col0 = GROUP_LEFT_MARGIN + GROUP_PADDING_LEFT = 34 + 120 = 154
x_col(N+1) = x_col(N) + w_prev/2 + HORIZONTAL_GAP + w_next/2
```

The agent can compute x for each node by following this formula mechanically. The same column x values apply regardless of which row (y) a chain is on.

The y positioning for existing groups has no equivalent procedural formula. The agent must:
1. Query existing node positions
2. Find the maximum y among existing nodes
3. Add SOURCE_NODE_SPACING (80px)
4. Set that as the y for all nodes in the new chain

This requires reasoning about the group's current state rather than following a formula. The skill's instructions describe the reasoning qualitatively but don't provide the formula.

## Proposed Solution

Rewrite the "Algorithm: Add Nodes to an Existing Group" section of SKILL.md to:

1. Add an explicit y-positioning formula for new chains added below existing nodes
2. Add a dedicated sub-case for "new independent chain" (the most common real-world case)
3. Clarify the relationship between node positioning, group resizing, and overlap resolution
4. Make the two-phase batch approach explicit (or better: combine into one batch with clear instructions)
5. Add a worked example for the most common scenario

Additionally, restructure the Quick Reference Checklist to make overlap resolution's output clearer.

## Implementation Steps

### Step 1: Rewrite "Algorithm: Add Nodes to an Existing Group" (SKILL.md lines 280-305)

Replace the current step 4 sub-cases with a more structured approach. Add a new sub-case for the most common real-world scenario: adding new independent chains to an existing group.

**New step 4 sub-cases:**

```
4. **Determine where new nodes fit** in the chain:
   - **New independent chain** (most common -- e.g., a new trigger->process->action pipeline
     added alongside existing chains): All nodes in the new chain go below existing nodes.
     - First new chain's y: `new_y = max_existing_y + SOURCE_NODE_SPACING` (where
       `max_existing_y` is the maximum y of any existing node in the group, and
       SOURCE_NODE_SPACING = 80 px).
     - Additional parallel chains: stack at `PARALLEL_CHAIN_SPACING` (60 px) intervals
       below the first new chain.
     - All nodes in a single chain share the same y (it's a horizontal pipeline).
     - Use the same column x values as the existing nodes where columns align, or
       compute new column x values using the edge-to-edge spacing formula.
   - **Inserted mid-chain** ...
   - **New branch from an existing node** ...
   - **New source/entry node** (additional trigger feeding into an existing chain):
     stack below existing sources at `SOURCE_NODE_SPACING` (80 px) if the new source
     is a different type, or `ENTRY_NODE_STACKING` (40 px) if it's the same type.
   - **New tail node** ...
```

The key addition is the **explicit formula** `new_y = max_existing_y + SOURCE_NODE_SPACING` and the instruction that all nodes in a horizontal chain share the same y.

### Step 2: Add an explicit "compute absolute y" instruction

After step 4 (determining relative positions), add a step that says:

```
4b. **Compute absolute y coordinates.** For each new node, the y coordinate must be
    an absolute canvas position, not a relative offset. Verify that every new node's
    y value is within the expected range for its group (it should be between
    `group.y + GROUP_PADDING_TOP` and `group.y + group.h - GROUP_PADDING_BOTTOM` after
    the group is resized). If any new node still has y=200 (the add-node default),
    that's a bug -- it means the y calculation was skipped.
```

This acts as a safety net: by explicitly calling out y=200 as a bug indicator, the agent will catch mistakes before applying the batch.

### Step 3: Restructure overlap resolution in the checklist

Change the Quick Reference Checklist to make the two-phase nature explicit:

```
9.  Dry-run batch update (node positions + group sizes), review output
10. Apply batch update (remove --dry-run)
11. Verify: read back positions, check containment and spacing
12. Resolve overlaps: if any group grew or was inserted, compute shift deltas for
    groups below. Build a SECOND batch of update-node commands to shift affected
    groups and ALL their member nodes (including newly positioned ones). Dry-run,
    review, then apply.
13. Final verify: read back positions, check inter-group spacing (18px gaps)
```

### Step 4: Add a worked example for "add chain to existing group"

Add a concrete example after the "Add Nodes to an Existing Group" algorithm that shows the complete calculation for one group. This should demonstrate:

1. Querying existing node positions
2. Finding max_existing_y
3. Computing new_y = max_existing_y + 80
4. Computing x positions using column formulas
5. Building the batch update-node JSON
6. Resizing the group
7. The overlap resolution step (if needed)

Example:

```
### Worked Example: Adding a 4-node chain to an existing group

Starting state: A group with existing nodes, max y = 420, group at (34, 19, 1000, 441).

New chain: server-state-changed -> RBE -> function -> subflow instance

1. New chain y = 420 + 80 = 500 (max_existing_y + SOURCE_NODE_SPACING)
2. Column x values (using node widths from estimate-node-size.sh):
   - Col 0: x = 154 (GROUP_LEFT_MARGIN + GROUP_PADDING_LEFT)
   - Col 1: x = 154 + server_w/2 + 50 + rbe_w/2
   - Col 2: x = col1_x + rbe_w/2 + 50 + func_w/2
   - Col 3: x = col2_x + func_w/2 + 50 + subflow_w/2
3. All 4 new nodes get y = 500
4. Updated group height: (500 + GROUP_PADDING_BOTTOM) - 19 = 521
   Updated group h = 521

Batch:
[
  {"command": "update-node", "args": {"node_id": "NEW_1", "props": {"x": 154, "y": 500}}},
  {"command": "update-node", "args": {"node_id": "NEW_2", "props": {"x": 374, "y": 500}}},
  {"command": "update-node", "args": {"node_id": "NEW_3", "props": {"x": 554, "y": 500}}},
  {"command": "update-node", "args": {"node_id": "NEW_4", "props": {"x": 754, "y": 500}}},
  {"command": "update-node", "args": {"node_id": "GROUP_ID", "props": {"x": 34, "y": 19, "w": 1000, "h": 521}}}
]

If the group below was at y=478 (old gap was 18px, now overlapping):
  delta = (19 + 521 + 18) - 478 = 80
  Shift that group and all groups below it down by 80px.
  Shift ALL their member nodes down by 80px too.
```

### Step 5: Clarify overlap resolution includes new nodes

In the "Algorithm: Resolve Group Overlaps" section (line 323), the instruction says:

```
5. **When shifting a group, translate ALL its member nodes by the same y delta.**
```

Add a clarification:

```
5. **When shifting a group, translate ALL its member nodes by the same y delta.**
   This includes newly added nodes that were just positioned in the previous step.
   Do not re-layout the group's internals -- just move everything uniformly.
```

### Step 6: Add a pre-apply sanity check instruction

Before the "Apply Positions" step (Step 3 in the skill, line 382), add:

```
**Sanity check before applying:** Scan your batch for any node that still has y=200
or x=200. These are the add-node defaults and almost certainly indicate a node whose
position was never calculated. Every new node must have explicit x and y values
computed from the layout algorithm.
```

### Step 7: Update CLAUDE.md guidance (no changes needed)

The current CLAUDE.md "After modifying flows" section (step 0) already correctly references the skill:

```
0. **Relayout modified groups** to fix node positions before committing.
   Read and follow the `/relayout-nodered-flows` skill (`.claude/skills/relayout-nodered-flows/SKILL.md`).
```

This is sufficient. No changes needed to CLAUDE.md.

### Step 8: Consider updating `docs/modifying-nodered-json.md`

The end-to-end workflow at line 578-579 says:

```
# 5. Relayout new/modified groups
# Follow the /relayout-nodered-flows skill to position new nodes and size groups
```

This is also sufficient. No changes needed.

## Specific File Changes

### `.claude/skills/relayout-nodered-flows/SKILL.md`

All changes are in this single file:

1. **Lines 280-305 (Add Nodes to an Existing Group)**: Rewrite step 4 to add "New independent chain" as the first (most common) sub-case with explicit y formula. Fix "New source/entry node" to specify SOURCE_NODE_SPACING for different-type sources. Add step 4b for absolute y verification.

2. **After line 305**: Add worked example showing the complete calculation for adding a chain to an existing group.

3. **Line 323**: Add clarification that shifted nodes include newly positioned ones.

4. **Before line 382 (Step 3: Apply Positions)**: Add sanity check instruction about y=200/x=200 defaults.

5. **Lines 406-419 (Quick Reference Checklist)**: Restructure steps 9-12 to make the two-phase batch explicit, and add step 13 for final verification.

## Testing Strategy

### Verify the fix addresses the root cause

1. **Read the updated SKILL.md** and mentally trace through the LED mirroring scenario:
   - 4 new nodes added to an existing group (e.g., Office Switch)
   - Existing nodes have max_y = 920
   - New chain y should be 920 + 80 = 1000
   - All 4 new nodes get y = 1000
   - Group height expands
   - Overlap resolution shifts the group and its members (including the y=1000 nodes) down

2. **Verify the worked example** is internally consistent: node y values fall within the group bbox, group dimensions match the expected padding, etc.

3. **Check that the Bedroom Switch case still works**: The first group (no shift) should still produce correct results with the updated algorithm.

4. **Test with a real modification**: After implementing, make a small test change to nodered.json (add a node to an existing group), follow the updated skill, and verify the positions are correct.

### Verify no regressions

1. **New standalone groups**: The "Layout a New Group" algorithm is not being changed. Verify that the worked example doesn't contradict it.

2. **Side-by-side groups**: The overlap resolution changes are additive (clarifications only). Verify the side-by-side algorithm is unaffected.

3. **Rewired nodes**: The "Handle Rewired Nodes" algorithm is not being changed.

## Risks & Considerations

1. **This is a skill (instructions), not code.** The "fix" is improving the clarity and specificity of natural language instructions. Even with perfect instructions, an agent could still make errors. The sanity check (step 4b and the pre-apply check) mitigates this by catching the most common failure mode (y=200 persisting).

2. **The worked example must be accurate.** An incorrect example would be worse than no example, as agents may copy it blindly. Double-check all arithmetic in the example.

3. **Overlap resolution as a second batch adds complexity.** An alternative design would be to compute all positions (including overlap shifts) upfront and apply in a single batch. This would require the agent to:
   - Position new nodes
   - Resize groups
   - Compute overlap deltas
   - Add deltas to ALL node positions (new + existing in shifted groups)
   - Apply everything at once

   This is more complex to describe but eliminates the two-phase problem. The current plan keeps the two-phase approach but makes it explicit. A future improvement could consolidate into a single batch.

4. **The "New source/entry node" sub-case previously said ENTRY_NODE_STACKING (40px).** Changing this to SOURCE_NODE_SPACING (80px) for different-type sources is correct but is a behavioral change. The existing sub-case description was already wrong for the different-type case (the constants table says SOURCE_NODE_SPACING = 80px for "different types"), so this is a bug fix not a change.

5. **The checklist change (adding step 13) makes the process longer.** But the additional step is just verification, which is critical for catching errors before they reach production.

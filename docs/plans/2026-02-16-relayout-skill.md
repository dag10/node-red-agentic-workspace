# Plan: Claude Skill for Node-RED Flow Relayout

## Problem Statement

After agents modify `nodered.json` (adding nodes, creating groups, rewiring flows), the new/changed nodes have default placeholder positions (x=200, y=200 for nodes; x=10, y=10, w=200, h=100 for groups). These need to be repositioned to match the user's careful hand-crafted layout conventions before committing and deploying.

The previous approach was a dagre-based script (`relayout-nodered-flows.sh` + JS), but it was too coarse -- it ran a generic graph layout algorithm without understanding the user's specific layout aesthetic. It has been deleted.

The new approach: a Claude skill (a markdown prompt file) that agents read and follow as instructions. The agent reads the nodered.json, understands what changed via the diff tool, then uses the modify tool's `update-node` command to set correct x/y/w/h values. This is inherently better suited than an algorithm because the agent can reason about context, node types, chain structure, and visual grouping in ways a layout algorithm cannot.

## Current State Analysis

- The old relayout scripts have been fully removed. No references remain in CLAUDE.md or upload-flows.sh.
- The modify tool (`modify-nodered-flows.sh`) sets default positions: nodes at (200, 200), groups at (10, 10, 200, 100).
- The `update-node` command can set `x`, `y` on any node and `x`, `y`, `w`, `h` on groups.
- Batch mode can update many nodes in one atomic operation.
- The diff summary tool (`summarize-nodered-flows-diff.sh`) can compare `nodered-last-downloaded.json` vs `nodered.json` to show what changed.
- The query tool (`query-nodered-flows.sh`) can read node positions, group membership, wiring, etc.
- The layout analysis (`docs/plans/2026-02-16-flow-layout-analysis.md`) contains precise numeric constants and patterns extracted from four hand-crafted flows.

### Key constraints of the coordinate system
- Node `x`/`y` = center point of the node
- Group `x`/`y` = top-left corner; `w`/`h` = dimensions
- All flows use left-to-right (LR) direction
- Node widths vary by type and label length (typically 120-200px wide, ~30px tall)
- Groups have a visible label bar at the top (accounted for in padding)

## Proposed Solution

Create a Claude skill at `.claude/skills/relayout-nodered-flows/SKILL.md` that agents invoke after modifying flows. The skill is a detailed markdown document with:

1. A diagnostic step (run the diff to understand what changed)
2. A conservative philosophy (only reposition what's necessary)
3. Precise numeric rules from the layout analysis
4. Step-by-step algorithms for different scenarios
5. A final verification step

The skill is invoked as `/relayout-nodered-flows` by the agent, or referenced in CLAUDE.md's "After modifying flows" section as a step agents must perform.

## Skill File Location

`.claude/skills/relayout-nodered-flows/SKILL.md`

This follows the convention of skills living under `.claude/skills/<name>/SKILL.md`.

## Implementation Steps

### Step 1: Create the skill file

Create `.claude/skills/relayout-nodered-flows/SKILL.md` with the content described in the "Skill Content Design" section below.

### Step 2: Update CLAUDE.md

Update the "After modifying flows" section in `/Users/drew/Projects/home/CLAUDE.md` to replace the old relayout script reference with the new skill. Currently CLAUDE.md has no relayout reference (it was already cleaned up when the scripts were deleted), so we need to ADD it back in. The section currently says:

```
### After modifying flows

After making changes to `mynodered/nodered.json`:

0. **Run the relayout tool** to fix node positions before committing:
   ...
```

Wait -- let me re-check the current state of CLAUDE.md's "After modifying flows" section.

Actually, from the CLAUDE.md content provided in context, the "After modifying flows" section currently reads:

```
### After modifying flows

After making changes to `mynodered/nodered.json`:

0. **Run the relayout tool** to fix node positions before committing:
   ```
   bash helper-scripts/relayout-nodered-flows.sh mynodered/nodered.json
   ```
   This must run before committing, while uncommitted changes exist. It compares
   against the last git commit to detect structural changes...
```

This still references the deleted script! It needs to be updated to reference the new skill instead.

Change step 0 to:

```
0. **Relayout modified groups** to fix node positions before committing.
   Invoke the `/relayout-nodered-flows` skill (or read `.claude/skills/relayout-nodered-flows/SKILL.md`
   and follow its instructions). This positions newly added nodes and groups according to
   the project's layout conventions, and adjusts existing groups to prevent overlaps.
```

### Step 3: Update helper-scripts section in CLAUDE.md

Remove the bullet for `helper-scripts/relayout-nodered-flows.sh` since it no longer exists. Currently in the Helper Scripts section:

```
- `helper-scripts/relayout-nodered-flows.sh <flows.json> [--baseline <file>] [--dry-run] [--verbose]` - Auto-relayout...
```

This should be removed entirely.

### Step 4: Update docs/modifying-nodered-json.md

The "End-to-end workflow" section in `docs/modifying-nodered-json.md` (line ~556-583) doesn't explicitly mention relayout, but the workflow steps should note that relayout happens via the skill after modifications and before committing. However, looking at the actual content, the workflow section at the bottom just shows the commands. We should add a step between "4. Verify the changes" and "5. Update documentation" for relayout.

Actually, reviewing the file more carefully, the end-to-end workflow doesn't mention relayout at all (it was handled automatically by the upload script before). Now that relayout is a manual skill-based step, we should add it to the workflow section.

Add after step 4 in the end-to-end workflow:

```bash
# 5. Relayout (fix node positions for newly added/modified groups)
# Follow the /relayout-nodered-flows skill instructions
```

And renumber subsequent steps.

## Skill Content Design

The skill file is the core deliverable. Here is the detailed design:

### Frontmatter

```yaml
---
name: relayout-nodered-flows
description: Position nodes and size groups in nodered.json after modifications. Reads the diff to understand what changed, then applies the project's layout conventions to new/modified nodes and groups.
---
```

### Skill Structure (sections)

#### 1. Philosophy and Scope

Establish the conservative approach:
- ALWAYS position newly created nodes properly
- ALWAYS size newly created groups properly
- Only move existing nodes when necessary (to resolve overlaps or maintain spacing)
- When existing nodes must move, prefer translating entire groups/subgraphs by a uniform offset
- Never touch nodes/groups that weren't affected by the current changes

#### 2. Understand the Changes

Instructions to run the diff tool and categorize changes:
```bash
bash helper-scripts/summarize-nodered-flows-diff.sh \
  mynodered/nodered-last-downloaded.json mynodered/nodered.json
```

Categorize into scenarios:
- **New group with new nodes**: Most common. Need full layout of the group.
- **New nodes added to existing group**: Position new nodes relative to existing ones.
- **Nodes rewired in existing group**: May need repositioning if topology changed significantly.
- **Existing group needs to move**: Because a group above it grew or a new group was inserted.

#### 3. Numeric Constants Reference

A clean reference table of all layout constants:

```
GROUP_VERTICAL_GAP        = 18    # px between vertically stacked groups
GROUP_HORIZONTAL_GAP      = 28    # px between side-by-side groups
GROUP_LEFT_MARGIN          = 34    # px from flow edge to group left edge (x value)

GROUP_PADDING_TOP          = 40    # px from group top edge to topmost node center
GROUP_PADDING_BOTTOM       = 40    # px from bottommost node center to group bottom edge
GROUP_PADDING_LEFT         = 120   # px from group left edge to leftmost node center
GROUP_PADDING_RIGHT        = 90    # px from rightmost node center to group right edge

HORIZONTAL_SPACING_DEFAULT = 200   # center-to-center for standard nodes
HORIZONTAL_SPACING_TIGHT   = 120   # for junctions, link in/out, link call
HORIZONTAL_SPACING_WIDE    = 260   # for wide nodes (server-state-changed, named inject)

BRANCH_VERTICAL_SPACING    = 60    # between branch outputs from a multi-output node
ENTRY_NODE_STACKING        = 40    # between stacked entry nodes of the same type
SOURCE_NODE_SPACING        = 80    # between entry nodes of different types
PARALLEL_CHAIN_SPACING     = 60    # between replicated identical chains

TEST_INJECT_OFFSET_Y       = 60    # how far below the main flow line test injects sit
```

#### 4. Node Width Estimation

Since spacing depends on node width and we don't have rendered widths, provide estimation rules:

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

Rule of thumb: estimate width as `max(100, 30 + len(name) * 7)` pixels, capped at 220. For junctions, always 10px. For link nodes, always 30px.

#### 5. Algorithm: Layout a New Group

This is the most common scenario. Step by step:

1. **Identify source nodes** in the group (nodes with no incoming wires from within the group). Use:
   ```bash
   bash helper-scripts/query-nodered-flows.sh mynodered/nodered.json \
     group-nodes <group_id> --sources --summary
   ```

2. **Topological sort** from sources. Use `connected --forward --summary` from each source to understand the chain structure. Build a mental model of columns (depth from source).

3. **Assign columns** based on longest-path-from-source:
   - Column 0: Source/entry nodes
   - Column 1: First downstream nodes
   - Column N: Nodes at depth N

4. **Position columns left to right**:
   - Column 0 starts at x = GROUP_LEFT_MARGIN + GROUP_PADDING_LEFT (= 34 + 120 = 154)
   - Each subsequent column: previous_x + horizontal_spacing
   - Use HORIZONTAL_SPACING_TIGHT for columns where the source node is a junction/link
   - Use HORIZONTAL_SPACING_WIDE for columns where the source is a wide trigger node
   - Use HORIZONTAL_SPACING_DEFAULT otherwise

5. **Position nodes within each column vertically**:
   - **Single node in column**: Place at the y of its upstream parent's output port
   - **Multiple nodes from same parent (fan-out)**: Center the parent vertically among its outputs. Space outputs at BRANCH_VERTICAL_SPACING (60px) apart. For 2 outputs: parent_y - 30 and parent_y + 30. For 3: parent_y - 60, parent_y, parent_y + 60. Etc.
   - **Multiple source nodes (column 0)**:
     - Same type: Stack at ENTRY_NODE_STACKING (40px) intervals
     - Different types: Stack at SOURCE_NODE_SPACING (80px) intervals
     - Test inject nodes go below production triggers at TEST_INJECT_OFFSET_Y (60px) below the nearest production source
   - **Parallel identical chains**: Space at PARALLEL_CHAIN_SPACING (60px)

6. **Determine the base y** for column 0:
   - If this is the first group on the flow, start at y = GROUP_LEFT_MARGIN + GROUP_PADDING_TOP (= 34 + 40 = 74)
   - If there are groups above, the topmost source node y = (bottom of previous group) + GROUP_VERTICAL_GAP + GROUP_PADDING_TOP

7. **Calculate group bounding box**:
   - x = leftmost_node_x - GROUP_PADDING_LEFT (typically = 34)
   - y = topmost_node_y - GROUP_PADDING_TOP
   - w = (rightmost_node_x + GROUP_PADDING_RIGHT) - x
   - h = (bottommost_node_y + GROUP_PADDING_BOTTOM) - y

8. **Apply the positions** using batch update-node:
   ```bash
   bash helper-scripts/modify-nodered-flows.sh mynodered/nodered.json batch <<'EOF'
   [
     {"command": "update-node", "args": {"node_id": "<id>", "props": {"x": N, "y": N}}},
     {"command": "update-node", "args": {"node_id": "<group_id>", "props": {"x": N, "y": N, "w": N, "h": N}}},
     ...
   ]
   EOF
   ```

#### 6. Algorithm: Add Nodes to an Existing Group

When new nodes are added to a group that already has positioned nodes:

1. **Read the existing group layout**: Query all nodes in the group with their positions.
2. **Identify which nodes are new** (they'll be at x=200, y=200 -- the default).
3. **Determine where new nodes fit** in the chain:
   - If inserted into a linear chain (between two existing nodes): Place at the midpoint x, same y as the chain. If there's not enough horizontal space, shift all downstream nodes right by HORIZONTAL_SPACING_DEFAULT.
   - If added as a new branch from an existing node: Place at the same x as the existing branch targets (or at the next column's x), with y offset by BRANCH_VERTICAL_SPACING from the nearest sibling branch.
   - If added as a new source/entry: Stack below existing sources at ENTRY_NODE_STACKING spacing.
   - If added as a new tail: Place to the right of the current rightmost node in the chain, same y.
4. **Resize the group** if the new nodes extend beyond the current bounding box. Expand w and/or h with appropriate padding.
5. **Check for downstream group overlaps** after resizing (see overlap resolution).

#### 7. Algorithm: Resolve Group Overlaps

After any layout changes, check if groups on the same flow overlap:

1. **List all groups on the affected flow** with their bounding boxes.
2. **Sort by y** (top to bottom).
3. **For each consecutive pair**, check if `group_above.y + group_above.h + GROUP_VERTICAL_GAP > group_below.y`.
4. **If overlap exists**: Shift the lower group (and all subsequent groups) down by the needed amount. This is a simple y translation -- add the overlap delta to the group's y and to all its member nodes' y values.
5. **Preserve relative internal layout**: When shifting a group, translate ALL its member nodes by the same delta. Don't re-layout the group's internals.

For side-by-side groups (same y range but different x):
- Check if horizontally adjacent groups overlap after width changes.
- If so, shift the right group's x (and all its nodes) rightward by the needed amount plus GROUP_HORIZONTAL_GAP.

#### 8. Algorithm: Handle Rewired Nodes

When existing nodes have been rewired but not repositioned:

1. If the wiring change is minor (e.g., adding one more output to a switch), the existing layout may be fine. Check if the new output targets have reasonable positions.
2. If major rewiring occurred (e.g., a node moved from one branch to another), it may need repositioning. But prefer minimal moves -- only reposition the specific nodes that moved, not the whole group.
3. When in doubt, leave existing positions alone. The user may prefer to manually adjust after deploying.

#### 9. Special Patterns

The skill should include guidance for recognizing and laying out common patterns:

- **Guard chain** (linear pipeline of checks): All nodes at same y, spaced horizontally.
- **Fan-out** (one node to many): Center the source, space outputs vertically at 60px.
- **Fan-in** (many sources to one): Stack sources vertically, merge at junction/next node.
- **Parallel replicated chains** (same logic per device): Stack at 60px vertical spacing.
- **Switch with symmetric branches**: Center switch at midpoint of branch y-range.
- **Subroutine groups** (called via link nodes): Place side-by-side with calling group using GROUP_HORIZONTAL_GAP.

#### 10. Verification

After applying positions:
1. Read back the affected groups with `group-nodes <id> --summary` to verify positions look reasonable.
2. Check that no two nodes in the same group share the exact same (x, y) unless they're supposed to (shouldn't happen).
3. Check that group bounding boxes properly contain all their member nodes.
4. Check inter-group spacing for overlaps on the flow.

## Updates to CLAUDE.md

### "After modifying flows" section (around line with "Run the relayout tool")

Replace step 0 from:
```
0. **Run the relayout tool** to fix node positions before committing:
   ```
   bash helper-scripts/relayout-nodered-flows.sh mynodered/nodered.json
   ```
   This must run before committing, while uncommitted changes exist. It compares
   against the last git commit to detect structural changes (added/removed/rewired
   nodes), then repositions nodes within affected groups using dagre layout. If you
   commit first, the relayout has no diff to detect and becomes a no-op.
```

To:
```
0. **Relayout modified groups** to fix node positions before committing.
   Read and follow the `/relayout-nodered-flows` skill (`.claude/skills/relayout-nodered-flows/SKILL.md`).
   This positions newly added nodes and groups according to the project's layout
   conventions, and adjusts existing groups to prevent overlaps. This must happen
   before committing, while uncommitted changes exist -- the skill uses the diff
   between `nodered-last-downloaded.json` and `nodered.json` to understand what changed.
```

### Helper Scripts section

Remove the bullet for `helper-scripts/relayout-nodered-flows.sh` since the script no longer exists.

### Upload script reference

The `upload-flows.sh` description mentions relayout running automatically. Check and update if needed. (From current code, upload-flows.sh no longer calls relayout, so the description should be fine.)

## Updates to docs/modifying-nodered-json.md

In the "End-to-end workflow" section (around line 556), add a relayout step. Current steps are:
1. Understand current state
2. Query existing automations
3. Make changes
4. Verify with diff summary
5. Update documentation
6. Commit, then upload

Add between steps 4 and 5:
```bash
# 5. Relayout new/modified groups
# Follow the /relayout-nodered-flows skill to position new nodes and groups
```

And renumber remaining steps to 6 and 7.

## Testing Strategy

Since this is a skill (markdown instructions), not code, testing is about verifying:

1. **The skill file is well-formed**: Frontmatter parses correctly, the name matches the directory.
2. **CLAUDE.md references are correct**: The "After modifying flows" section references the new skill; the old relayout script reference is removed.
3. **The workflow is coherent**: An agent following the skill step-by-step can actually produce correct layouts. This can be verified by:
   - Creating a test group with a few nodes
   - Following the skill instructions to position them
   - Comparing the result against the layout analysis constants
4. **The skill is discoverable**: Running `/relayout-nodered-flows` should find and use the skill.

## Risks & Considerations

1. **Agent context usage**: The skill requires the agent to read node positions, understand chain topology, calculate coordinates, and issue batch updates. This is computationally demanding on the agent's context. For very large groups (20+ nodes), the agent may need to work in stages.

2. **Node width estimation is imprecise**: Without knowing rendered widths, horizontal spacing will be approximate. The skill provides estimation rules, but the result won't be pixel-perfect compared to hand-layout. This is acceptable -- the goal is "good enough to deploy," not "identical to hand-crafted."

3. **Complex topologies**: Some groups have non-trivial topology (multiple merge points, cross-links within the group, diamond patterns). The skill provides general rules, but agents will need to reason about these on a case-by-case basis. The skill should emphasize that when the topology is complex, prioritize readability over rigid adherence to the numeric constants.

4. **The skill can't be unit-tested**: Unlike the old script, we can't run automated tests against the skill. Quality depends on the skill being well-written and agents being capable of following it. The verification step (read back positions, check for overlaps) acts as a runtime sanity check.

5. **Backward compatibility**: Flows modified before the skill existed have positions set by the old dagre script. These positions may not match the skill's conventions exactly. The skill should not touch these -- its conservative philosophy ensures it only modifies what the current diff indicates as changed.

6. **Side-by-side group placement**: The skill needs clear guidance on when to place groups side by side vs. vertically stacked. The rule from the analysis: subroutine/helper groups (called via link nodes from the main group) go side-by-side; independent automation groups go vertically stacked. The agent can determine this from the wiring (link-call from group A to group B suggests side-by-side).

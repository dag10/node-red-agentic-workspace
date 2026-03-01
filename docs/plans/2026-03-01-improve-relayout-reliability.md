# Plan: Improve Relayout Reliability

## Problem Statement

The recent Switches flow overlap fix (plan `2026-03-01-fix-switches-overlaps.md`) revealed systematic weaknesses in the relayout skill and surrounding tooling. 14 overlapping node pairs were found, caused by two root issues: (1) orphaned nodes left behind during refactors, and (2) subflow instance width underestimation leading to tight/overlapping horizontal spacing. The relayout skill's overlap check was advisory, the tools had no way to detect orphaned nodes, and the post-modification workflow in CLAUDE.md didn't mandate overlap verification beyond what the relayout skill already suggested.

This plan addresses all three areas: the relayout skill (SKILL.md), the helper scripts (estimate-node-size.py, query-nodered-flows.py), and the workflow/process documentation (CLAUDE.md, docs/exploring-nodered-json.md, docs/modifying-nodered-json.md).

## Current State Analysis

### Relayout Skill (SKILL.md)

- **Step 4: Verify** (line 559-627) includes overlap detection as checklist items 14-16, but the language is advisory ("Fix any issues before proceeding") rather than a hard gate.
- The overlap check is per-group (checklist item 14) and per-flow (item 16), which is correct.
- There is no mention of orphaned nodes, cleaning them up during refactors, or checking for them after modifications.
- Subflow instance sizing is handled correctly in principle (via `estimate-node-size.sh`) but there's no special emphasis on the fact that subflow instances can be much wider than typical nodes (up to 240px for long names).
- The "fan-out chains with tall branches" section (line 286-290) addresses vertical extent but doesn't mention the horizontal interleaving problem (two multi-output nodes in the same group whose output branches share y-rows).

### Helper Scripts

- `estimate-node-size.py` has the `overlaps` command (line 399-511) with `--gap`, `--flow`, `--group`, `--json` flags. Currently working well.
- `query-nodered-flows.py` has `--sources` flag and `head-nodes` command for finding entry points, but no dedicated "orphaned node" detector. The `--sources` flag finds nodes with no *internal* incoming wires (entry points from outside the scope), which is close but not exactly "orphaned" -- a true orphan has no incoming wires *at all* and isn't an event trigger type.
- No tool currently combines "no incoming wires" + "not an entry-point type" into a single query.

### CLAUDE.md Post-Modification Workflow

- The "After modifying flows" section (line 37-58) mentions relayout as step 0, then goes straight to documentation updates. There's no explicit overlap verification step in the CLAUDE.md workflow -- it relies entirely on the relayout skill to handle it.
- The "Before modifying flows" section has no guidance about checking for pre-existing orphaned nodes.
- The commit structure section has no mention of verifying overlap-free state before committing.

## Proposed Solution

Three categories of improvements, all designed to prevent the types of overlaps found in the Switches flow fix:

### A. Make overlap detection a hard requirement in the relayout skill

Change the Step 4 verification from advisory to a hard gate: if `overlaps --flow` reports any overlaps, the relayout is incomplete and must be fixed. The `--gap 30` check remains advisory (a warning, not a blocker).

### B. Add an `orphans` command to the query tool

Add a new command to `query-nodered-flows.py` that finds nodes with no incoming wires (from wires, link connections, or being a subflow input) AND whose type is not an event trigger (not in `NO_INPUT_TYPES` from estimate-node-size.py). These are likely orphaned nodes left behind during refactors. This gives agents a tool to identify cleanup candidates during refactors and to verify no orphans were left behind.

### C. Integrate overlap check into the post-modification workflow

Add an explicit overlap verification step to CLAUDE.md's "After modifying flows" section, between relayout (step 0) and documentation (step 1). This catches overlaps even when the relayout skill is not invoked (e.g., when only deleting nodes or making minor position adjustments).

## Implementation Steps

### Step 1: Add `orphans` command to `query-nodered-flows.py`

**File:** `/Users/drew/Projects/home/helper-scripts/query-nodered-flows.py`

Add a new command `orphans` that finds nodes meeting ALL of these criteria:
1. Has no incoming wires (not in `backward` index)
2. Has no incoming link connections (not a `link in` that receives from `link out` or `link call`)
3. Is not an event trigger type (not in the set: `inject`, `link in`, `server-events`, `server-state-changed`, `ha-time`, `poll-state`, `trigger-state`, `cronplus`, `complete`, `catch`, `status`, `ha-webhook`)
4. Is not a metadata type (`tab`, `subflow`, `group`, `comment`)
5. Is not a subflow definition's internal node that's on a subflow's `in` port (these are pseudo-entry-points within subflows)

The command should support `--flow`, `--group`, `--summary`, `--full`, and `--dont-follow-links` flags, consistent with existing commands.

**Implementation details:**

Add near the other `cmd_*` functions (around line 450):

```python
# Types that are legitimate entry points (no incoming wires expected).
# NOTE: This must stay in sync with NO_INPUT_TYPES in estimate-node-size.py.
_ENTRY_POINT_TYPES = {
    "inject", "link in", "server-events", "server-state-changed",
    "ha-time", "poll-state", "trigger-state", "cronplus",
    "complete", "catch", "status", "ha-webhook",
}
_ORPHAN_SKIP_TYPES = {"tab", "subflow", "group", "comment"}


def cmd_orphans(idx, args):
    """Find nodes with no incoming connections that aren't event triggers."""
    flags = set()
    flow_filter = None
    group_filter = None

    i = 0
    while i < len(args):
        if args[i] == "--flow" and i + 1 < len(args):
            flow_filter = args[i + 1]
            i += 2
        elif args[i] == "--group" and i + 1 < len(args):
            group_filter = args[i + 1]
            i += 2
        elif args[i] in ("--summary", "--full", "--dont-follow-links"):
            flags.add(args[i])
            i += 1
        else:
            die(f"unknown orphans argument: {args[i]}")
            i += 1

    follow_links = "--dont-follow-links" not in flags

    # Determine candidate set
    if group_filter:
        candidate_ids = set(collect_group_node_ids(group_filter, idx))
    elif flow_filter:
        candidate_ids = set(n["id"] for n in idx["by_z"].get(flow_filter, []))
    else:
        candidate_ids = set(idx["by_id"].keys())

    orphans = []
    for nid in candidate_ids:
        node = idx["by_id"].get(nid, {})
        ntype = node.get("type", "")

        # Skip metadata types
        if ntype in _ORPHAN_SKIP_TYPES:
            continue

        # Skip legitimate entry-point types
        if ntype in _ENTRY_POINT_TYPES:
            continue

        # Skip subflow instance internal "in" nodes (they receive from subflow inputs)
        # These are nodes whose z is a subflow definition
        z = node.get("z", "")
        z_node = idx["by_id"].get(z, {})
        if z_node.get("type") == "subflow":
            # Check if this node is wired from the subflow's in ports
            sf_in = z_node.get("in", [])
            is_subflow_input_target = False
            for in_port in sf_in:
                for wire_target in in_port.get("wires", []):
                    if wire_target.get("id") == nid:
                        is_subflow_input_target = True
                        break
                if is_subflow_input_target:
                    break
            if is_subflow_input_target:
                continue

        # Check for incoming wires
        has_incoming = len(idx["backward"].get(nid, [])) > 0

        # Check for incoming link connections (if following links)
        if not has_incoming and follow_links and ntype == "link in":
            has_incoming = (len(idx["link_in_to_out"].get(nid, [])) > 0 or
                          len(idx["link_in_to_call"].get(nid, [])) > 0)

        if not has_incoming:
            orphans.append(node)

    # Output
    output_nodes(orphans, flags, idx)
```

Add `"orphans"` to the `COMMANDS` dict, and add to the usage string:

```
  orphans [flags]                   Find nodes with no incoming connections
                                    that aren't event triggers (likely leftovers
                                    from refactors). Excludes inject, link in,
                                    server-state-changed, trigger-state, etc.
```

The `output_nodes` function referenced above is the existing pattern used by `cmd_flow_nodes`, `cmd_group_nodes`, etc. -- extract the common output logic if not already factored out, or inline the same `--summary`/`--full`/default-JSONL pattern.

**Testing:** Run `bash helper-scripts/query-nodered-flows.sh mynodered/nodered.json orphans --flow a21bcb9abb9ff4db --summary` on the current (post-fix) Switches flow. It should return zero orphaned nodes (since we deleted them all). On a pre-fix snapshot, it would have found the 8 orphaned api-call-service nodes.

### Step 2: Update the `overlaps` command JSON output to include group info

**File:** `/Users/drew/Projects/home/helper-scripts/estimate-node-size.py`

The JSON output already includes `"g"` (group ID) for each node in a pair (line 487, 494). This is sufficient. No changes needed to the overlaps command itself.

However, add a `--exit-code` flag that makes the command exit with code 1 when overlaps are found (exit 0 when clean). This enables scripted gate checks:

```python
# In cmd_overlaps, after parsing args, add:
exit_code_mode = False
# In the arg parser:
elif args[i] == "--exit-code":
    exit_code_mode = True
    i += 1

# At the end, after printing results:
if exit_code_mode and pairs:
    sys.exit(1)
```

Update the USAGE string to document `--exit-code`.

**File:** `/Users/drew/Projects/home/helper-scripts/estimate-node-size.sh` -- no changes needed (it just passes args through).

### Step 3: Update the Relayout Skill (SKILL.md) -- verification as a hard gate

**File:** `/Users/drew/Projects/home/.claude/skills/relayout-nodered-flows/SKILL.md`

#### 3a. Make overlap check a hard requirement

In "Step 4: Verify" (line 559), change the opening text and restructure items 14-16:

Replace the current Step 4 content (lines 559-627) with:

```markdown
## Step 4: Verify (hard gate -- must pass before proceeding)

After applying positions, verify the layout passes these checks. **Do not proceed
to documentation or committing until all checks pass.**

1. **Run the overlap detector on each modified group** (catches node-on-node collisions):
   ```bash
   bash helper-scripts/estimate-node-size.sh mynodered/nodered.json \
     overlaps --group <group_id>
   ```
   **This must report "No overlaps found." for every modified group.** If any
   overlaps are reported, fix them before continuing.

2. **Run the overlap detector on the entire flow** (catches cross-group overlaps):
   ```bash
   bash helper-scripts/estimate-node-size.sh mynodered/nodered.json \
     overlaps --flow <flow_id>
   ```
   **This must report "No overlaps found."** Cross-group overlaps can occur when
   nodes from different groups share similar y coordinates (e.g., link out nodes
   from one group overlapping with nodes from an adjacent group's branch).

3. **Check spacing violations** (advisory -- fix if practical, but not a hard blocker):
   ```bash
   bash helper-scripts/estimate-node-size.sh mynodered/nodered.json \
     overlaps --gap 30 --group <group_id>
   ```
   Pairs with gaps between 0-30px are very tight. Fix these if the affected nodes
   were part of the current modification; leave pre-existing tight spacing alone
   unless it's trivial to fix.

4. **Check inter-group spacing** using the `nearby` spatial query:
   ```bash
   bash helper-scripts/query-nodered-flows.sh mynodered/nodered.json \
     nearby <group_id> --margin 20 --summary
   ```
   If any groups appear in the results, they're within `GROUP_VERTICAL_GAP` (20 px) of
   the modified group and may need to be shifted.

5. **Check group containment**: every node's (x, y) should fall within its group's
   bounding box with appropriate padding.

6. **Check grid alignment**: every x, y, w, h value in the batch must be a multiple of 20
   and an integer. No floats, no off-grid values.

7. If anything fails checks 1-2, fix the positions and re-run the batch. If items 4-6
   need fixes, apply them as a follow-up batch.
```

#### 3b. Add orphaned node cleanup guidance

After the "Special Patterns" section (line 540) and before "Step 3: Apply Positions" (line 543), add a new section:

```markdown
## Cleanup: Identify and Remove Orphaned Nodes

When a modification replaces existing nodes with new ones (e.g., swapping direct
api-call-service chains for a subflow-based pattern), the old nodes may be left in
place as orphans -- they have no incoming wires but aren't event triggers, so they
serve no purpose. These orphans frequently cause overlaps because they sit at the
same coordinates as their replacement nodes.

**After any refactoring modification, check for orphans in affected groups:**

```bash
bash helper-scripts/query-nodered-flows.sh mynodered/nodered.json \
  orphans --group <group_id> --summary
```

Any nodes returned are candidates for deletion. Verify they're truly unused (no
incoming wires, not referenced by name from function nodes, etc.) and delete them
as part of the same batch that performs the refactor.

**When to check:**
- After replacing direct-action nodes with subflow instances
- After removing a branch from a switch/router node
- After any operation that restructures wiring in a group
- When investigating overlaps (orphans are the most common cause)
```

#### 3c. Add emphasis on subflow instance sizing

In "Step 2: Read the Affected Groups and Measure Node Sizes" (line 49), after the "Always gather sizes before calculating positions" paragraph (line 97), add:

```markdown
**Subflow instances can be much wider than typical nodes.** A subflow instance's
width depends on its display label, which is either its `name` property (if set)
or the subflow definition's name. Common examples:
- "Inovelli Interaction" subflow: 180x75px (5 outputs make it tall too)
- "Any On / All Off Router" subflow: 200x30px (long name)
- "Set Brightness for On Entities" subflow: 240x30px (very long name)

These widths mean subflow instances need significantly more horizontal clearance
than typical 100-160px nodes. When computing column spacing, **always use actual
measured widths from `estimate-node-size.sh`** -- never assume a default width.
The edge-to-edge gap formula (`w_prev/2 + HORIZONTAL_GAP + w_next/2`) automatically
handles this, but only if you measure first.
```

#### 3d. Add guidance for interleaving fan-out patterns

In the "Special Patterns" section (around line 507), add a new pattern:

```markdown
### Interleaving fan-out (two multi-output nodes in the same group)

When a group contains two multi-output nodes (e.g., two Inovelli Interaction subflow
instances) whose output branches share y coordinates, the branches can interleave
and cause overlaps. This is the hardest layout pattern to get right.

**Recognition:** Two nodes at different y values in the same column, each with 3+
outputs, where the lower node's outputs start within the vertical range of the
upper node's outputs.

**Strategy:**
1. Lay out the first (upper) node's branches normally.
2. Before laying out the second node's branches, compute the vertical extent of
   all branches from the first node (from topmost to bottommost node across all
   branches).
3. Start the second node's first branch at least `MIN_VERTICAL_NODE_GAP` (30px)
   below the bottommost node of the first node's branches.
4. If this isn't possible (the second node is already positioned within the first
   node's output range), spread the branches by assigning each multi-output node's
   targets to non-overlapping y ranges. Use `rect` queries to verify no overlaps
   exist in the target column's y range.

**Common instance:** Inovelli Interaction subflows in the Switches flow -- each
group has two Interaction instances (for Up and Down buttons), each with 5 outputs.
The Down instance's outputs must not overlap with the Up instance's outputs in the
downstream columns.
```

### Step 4: Update Quick Reference Checklist

In the "Quick Reference Checklist" section (line 599-627), update items 14-16 to reflect the hard-gate language:

Replace items 14-16 with:

```
14. **HARD GATE -- Run overlap detector**: `estimate-node-size.sh ... overlaps --group <id>` on each
    modified group. Must report "No overlaps found." Also `overlaps --flow <flow_id>` for cross-group
    overlaps. Fix any overlaps before proceeding. Then `overlaps --gap 30 --group <id>` for spacing
    warnings (advisory, fix if practical).
15. **Phase 2:** Resolve group overlaps -- use `nearby <group_id> --margin 20` on each modified
    group. If groups appear in results, compute shift deltas. Use
    `rect -inf <group_bottom> inf inf --flow <flow_id>` to find everything below that
    needs shifting. Build a SECOND batch of update-node commands to shift affected groups
    and ALL their member nodes. Dry-run, review, then apply.
16. **Final verify**: `overlaps --flow <flow_id>` should show no overlaps on the flow.
    `nearby <group_id> --margin 20` on each modified group should return no groups.
```

### Step 5: Update CLAUDE.md post-modification workflow

**File:** `/Users/drew/Projects/home/CLAUDE.md`

Update the "After modifying flows" section (lines 37-47). Replace with:

```markdown
### After modifying flows

After making changes to `mynodered/nodered.json`:

0. **Relayout modified groups** to fix node positions before committing.
   Read and follow the `/relayout-nodered-flows` skill (`.claude/skills/relayout-nodered-flows/SKILL.md`).
   This positions newly added nodes and groups according to the project's layout
   conventions, and adjusts existing groups to prevent overlaps. This must happen
   before committing, while uncommitted changes exist -- the skill uses the diff
   between `nodered-last-downloaded.json` and `nodered.json` to understand what changed.

0b. **Verify no overlaps exist** on every flow that was modified. This is a hard
    requirement -- do not commit flow changes that introduce overlaps.
    ```
    bash helper-scripts/estimate-node-size.sh mynodered/nodered.json \
      overlaps --flow <flow_id>
    ```
    This must report "No overlaps found." If overlaps are reported, fix them
    (reposition nodes, delete orphans, etc.) before proceeding. If you performed
    a refactor that replaced nodes, also check for orphaned nodes:
    ```
    bash helper-scripts/query-nodered-flows.sh mynodered/nodered.json \
      orphans --flow <flow_id> --summary
    ```
    Any orphans in modified groups should be deleted unless there's a clear reason
    to keep them.
```

The rest of the "After modifying flows" section (steps 1-3 for documentation) stays unchanged.

### Step 6: Update docs/exploring-nodered-json.md

**File:** `/Users/drew/Projects/home/docs/exploring-nodered-json.md`

Add a new section in the "Commands reference" area (after the `nearby` command, around line 322), documenting the `orphans` command:

```markdown
#### orphans [flags]

Find nodes that have no incoming connections and are not event trigger types.
These are likely leftover nodes from refactors -- they were replaced by new nodes
but never deleted, and now sit unused at their old positions (often causing
overlaps with the replacement nodes).

Excludes legitimate entry-point types: `inject`, `link in`, `server-events`,
`server-state-changed`, `ha-time`, `poll-state`, `trigger-state`, `cronplus`,
`complete`, `catch`, `status`, `ha-webhook`.

```
query-nodered-flows.sh flows.json orphans --flow <flow_id> --summary
query-nodered-flows.sh flows.json orphans --group <group_id> --summary
```

Flags:
- `--flow ID`: Only check nodes on this flow.
- `--group ID`: Only check nodes in this group (recursive).
- `--dont-follow-links`: Don't consider link connections as incoming.
- `--summary`, `--full`: Output format.
```

Also add a new workflow section after "Are any nodes overlapping on this flow?" (around line 474):

```markdown
### "Are there orphaned nodes left over from a refactor?"

After replacing nodes with a new pattern (e.g., direct api-call-service chains
replaced by subflow-based routing), check for orphans:

```
query-nodered-flows.sh flows.json orphans --flow <flow_id> --summary
```

Orphaned nodes often cause overlaps because they sit at the same coordinates as
their replacement nodes. Delete them as part of the refactor unless they serve
a clear purpose.
```

### Step 7: Update docs/modifying-nodered-json.md

**File:** `/Users/drew/Projects/home/docs/modifying-nodered-json.md`

In the "End-to-end workflow: modify, verify, deploy" section (around line 571), add an overlap verification step between step 5 (relayout) and step 6 (documentation):

```markdown
# 5b. Verify no overlaps on modified flows
bash helper-scripts/estimate-node-size.sh mynodered/nodered.json \
  overlaps --flow <flow_id>
# Must report "No overlaps found." Fix any overlaps before proceeding.

# 5c. Check for orphaned nodes (if you replaced/refactored existing nodes)
bash helper-scripts/query-nodered-flows.sh mynodered/nodered.json \
  orphans --flow <flow_id> --summary
# Delete any orphans found in modified groups
```

Also add a tip at the end of the Tips section:

```markdown
- **Check for orphans after refactors.** When replacing nodes with a new
  pattern, the old nodes may be left behind as orphans causing overlaps.
  Run `query-nodered-flows.sh ... orphans --flow <id> --summary` after
  any structural refactor and delete unused nodes.
```

### Step 8: Update CLAUDE.md helper script documentation

**File:** `/Users/drew/Projects/home/CLAUDE.md`

In the "Helper Scripts" section, update the `query-nodered-flows.sh` entry to include the new `orphans` command in the command list:

Change from:
```
Commands: `node`, `function`, `connected`, `head-nodes`, `tail-nodes`, `flow-nodes`, `group-nodes`, `subflow-nodes`, `subflow-instances`, `search`, `rect`, `nearby`.
```

To:
```
Commands: `node`, `function`, `connected`, `head-nodes`, `tail-nodes`, `flow-nodes`, `group-nodes`, `subflow-nodes`, `subflow-instances`, `search`, `rect`, `nearby`, `orphans`.
```

Also update the `estimate-node-size.sh` entry to mention the `--exit-code` flag if added.

## Testing Strategy

### Test the `orphans` command

1. **On the current (post-fix) Switches flow** -- should find zero orphans:
   ```bash
   bash helper-scripts/query-nodered-flows.sh mynodered/nodered.json \
     orphans --flow a21bcb9abb9ff4db --summary
   ```

2. **On a flow with known legitimate entry points** -- should not report event triggers as orphans:
   ```bash
   bash helper-scripts/query-nodered-flows.sh mynodered/nodered.json \
     orphans --flow cb6b6698a01398f9 --summary  # Main flow
   ```
   Verify that `server-state-changed`, `cronplus`, `inject`, etc. are NOT in the output.

3. **On the full flows file** -- spot-check results:
   ```bash
   bash helper-scripts/query-nodered-flows.sh mynodered/nodered.json \
     orphans --summary
   ```
   Manually verify a few results to confirm they're genuine orphans (no wires in, not event triggers).

4. **With `--group` filter** -- test scoping:
   ```bash
   bash helper-scripts/query-nodered-flows.sh mynodered/nodered.json \
     orphans --group <group_id> --summary
   ```

### Test the `--exit-code` flag on overlaps

```bash
bash helper-scripts/estimate-node-size.sh mynodered/nodered.json \
  overlaps --flow a21bcb9abb9ff4db --exit-code
echo $?  # Should be 0 (no overlaps on post-fix Switches flow)
```

### Verify documentation consistency

After all changes:
1. Re-read the full SKILL.md and verify the flow is logical: understand changes -> measure -> position -> verify (hard gate) -> proceed.
2. Re-read CLAUDE.md's "After modifying flows" section and verify steps 0, 0b, 1, 2, 3 are clear and ordered correctly.
3. Verify the `orphans` command is documented in all three places: exploring-nodered-json.md (reference), modifying-nodered-json.md (workflow), and CLAUDE.md (helper scripts list).

## Risks & Considerations

1. **The `orphans` command may have false positives.** Some nodes intentionally have no incoming wires but aren't in the `_ENTRY_POINT_TYPES` set -- for example, a `change` node that's wired as a standalone config setter triggered manually. These are rare. The command should be used as a "candidates for review" tool, not an automatic deletion list. The SKILL.md guidance says "verify they're truly unused" before deleting.

2. **Cross-reference NOTE between `NO_INPUT_TYPES` and `_ENTRY_POINT_TYPES`.** The estimate-node-size.py file defines `NO_INPUT_TYPES` (line 96-99) for sizing calculations, and the new `_ENTRY_POINT_TYPES` in query-nodered-flows.py must match. Add a cross-reference NOTE comment on both sides so future changes keep them in sync.

3. **The hard-gate overlap check adds a mandatory step.** This slightly increases the work required for every flow modification. The tradeoff is worth it -- overlaps in deployed flows are confusing and hard to find later. The check is fast (subsecond) and the fix when overlaps exist is usually straightforward.

4. **Subflow internal nodes.** The `orphans` command needs to handle subflow internals carefully. Nodes inside a subflow definition that receive from the subflow's `in` ports are connected via the subflow's `in[].wires` structure, not via the regular `wires` field. The implementation must check this to avoid false-flagging subflow-internal entry nodes.

5. **The `--exit-code` flag on overlaps changes the script's exit behavior.** It only activates when explicitly requested, so existing usage is unaffected. But it's important for enabling scripted gate checks in the future (e.g., a pre-commit hook).

6. **Backward compatibility.** All changes are additive (new command, new flag, new documentation sections). No existing behavior is removed or changed. The only "breaking" change is philosophical: overlap checks go from advisory to mandatory in the relayout skill's verification step. But since that skill is agent-facing guidance (not enforced by code), there's no actual breaking change.

## Summary of Files to Modify

| File | Change |
|------|--------|
| `helper-scripts/query-nodered-flows.py` | Add `orphans` command with `--flow`, `--group`, `--summary`, `--full`, `--dont-follow-links` |
| `helper-scripts/estimate-node-size.py` | Add `--exit-code` flag to `overlaps` command |
| `.claude/skills/relayout-nodered-flows/SKILL.md` | (a) Hard-gate Step 4 verification, (b) orphan cleanup section, (c) subflow sizing emphasis, (d) interleaving fan-out pattern, (e) updated checklist |
| `CLAUDE.md` | (a) Add step 0b overlap verification to post-modification workflow, (b) update query command list to include `orphans` |
| `docs/exploring-nodered-json.md` | Add `orphans` command reference and "orphaned nodes" workflow |
| `docs/modifying-nodered-json.md` | Add overlap verification and orphan check to end-to-end workflow, add tip |

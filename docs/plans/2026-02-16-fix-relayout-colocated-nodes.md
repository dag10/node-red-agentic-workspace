# Plan: Fix Relayout Not Running on Newly-Created Nodes

## Problem Statement

In submodule commit `9f53f31`, 12 new nodes and 1 new group were created via `modify-nodered-flows.sh`. All 12 nodes ended up with identical positions (`x: 200, y: 200`) and the new group with default dimensions (`x: 10, y: 10, w: 200, h: 100`). The `relayout-nodered-flows.sh` script should have repositioned them using dagre layout but didn't.

## Current State Analysis

### What was created

The commit added nodes across two groups on flow `8ac252f63e58cd8d`:

**New group `089fa1f004fbf0b7`** ("Cancel departure detection on switch press") -- 7 member nodes, all at (200, 200):
- `e54efc2a24b9d721` server-events "Any ZHA event"
- `3c390638cb57345c` switch "departure detection active?"
- `da2576e6ca7ea76d` link call "get switch config"
- `373b5ae103ed58ec` function "if non-entrance switch"
- `d38c84aa86cd61a1` change "occupied = true"
- `313399dc7878a242` subflow:a2d7acf593fe2434 "set occupancy: switch cancelled departure"
- `e20b42f5ef34544a` link out "to semaphore end"

**Existing group `41eee6d57596f252`** ("Sensor-based occupancy detection") -- 5 new nodes added, all at (200, 200):
- `ce936377e2fd2cec` change "set departure active"
- `8f75079cd9ae8c26` switch "departure still active?"
- `f2c56a9ed1d3f3bf` switch "departure still active?"
- `a822bf08aea5acc5` link out "cancelled-1"
- `2b78da4fe03c0c98` link out "cancelled-2"

### Why all nodes are at (200, 200)

The `modify-nodered-flows.py` `_cmd_add_node()` function (line 185-193) hardcodes default positions:

```python
node = {
    "id": new_id,
    "type": node_type,
    "z": flow_id,
    "name": name,
    "x": 200,
    "y": 200,
    "wires": wires,
}
```

Similarly, `_cmd_add_group()` (line 534-545) uses defaults:

```python
group = {
    "id": new_id,
    "type": "group",
    "z": flow_id,
    "name": name,
    "nodes": list(node_ids),
    "style": {"label": True},
    "x": 10,
    "y": 10,
    "w": 200,
    "h": 100,
}
```

This is by design -- the documentation explicitly says "Positions don't matter. The relayout tool handles node positioning before upload."

### Why relayout didn't fix the positions

**Root cause: The agent committed the changes before relayout had a chance to run.**

The relayout script (`relayout-nodered-flows.sh`, line 33) gets its baseline by comparing against the HEAD commit:

```bash
git -C "$file_dir" show "HEAD:$file_name" > "$BEFORE_FILE" 2>/dev/null || echo "[]" > "$BEFORE_FILE"
```

The intended workflow is:
1. Agent modifies `nodered.json` via `modify-nodered-flows.sh` (nodes get x=200, y=200)
2. User runs `upload-flows.sh`, which calls `relayout-nodered-flows.sh` before uploading
3. Relayout compares the working file against HEAD (the pre-modification commit)
4. Relayout detects new/changed nodes, runs dagre, updates positions in-place
5. Upload sends the relaid-out file to the server

What actually happened:
1. Agent modified `nodered.json` via `modify-nodered-flows.sh` (nodes at x=200, y=200)
2. Agent committed the changes to the submodule (commit `9f53f31`)
3. Now HEAD *is* the commit with x=200, y=200 nodes
4. When `upload-flows.sh` runs and calls `relayout-nodered-flows.sh`, it compares the file against HEAD
5. The file matches HEAD exactly -- no diff detected -- relayout is a no-op
6. Nodes stay at (200, 200)

**This is a sequencing problem between committing and relayouting.** The CLAUDE.md instructs agents to commit their changes (including nodered.json, docs, and CLAUDE.md updates) as a single commit. But `upload-flows.sh` expects to run relayout against uncommitted changes. Once committed, the relayout baseline is the same as the working file.

### Why this wasn't caught by documentation

The docs say:
- `docs/modifying-nodered-json.md` line 25: "Positions don't matter. The relayout tool handles node positioning before upload."
- `docs/modifying-nodered-json.md` line 583: "Upload (relayout runs automatically before upload)"
- `CLAUDE.md` line 84: "Automatically called by upload-flows.sh before upload."

But CLAUDE.md also says (in "Commit structure for flow modifications") that changes should be committed as a single commit containing nodered.json changes + doc updates. The agent follows this instruction and commits before upload. This creates a chicken-and-egg problem: the commit locks in the bad positions, and the post-commit relayout can't detect changes.

## Proposed Solution

There are two complementary fixes needed:

### Fix 1: Run relayout before committing (agent guidance)

The simplest immediate fix is to tell agents to run `relayout-nodered-flows.sh` **after modifying flows but before committing**. This ensures:
- The relayout runs while HEAD still points to the pre-modification state
- Position changes from dagre are included in the commit
- `upload-flows.sh`'s relayout call becomes a harmless no-op (correct behavior)

This requires updating:
- `CLAUDE.md` "After modifying flows" section -- add a step to run relayout before committing
- `docs/modifying-nodered-json.md` workflows section -- make the relayout step explicit

### Fix 2: Make relayout robust to already-committed changes (script fix)

The relayout script should also work when changes have already been committed. This is a safety net -- even if agents forget to run relayout before committing, upload should still fix positions.

**Approach:** Change `relayout-nodered-flows.sh` to compare against a smarter baseline. Instead of always using `HEAD:$file_name`, compare against the last known *deployed* state, which is `nodered-last-downloaded.json`. This file represents what's on the server and is only updated by `download-flows.sh` or `upload-flows.sh`. It won't be affected by agent commits.

However, this is more complex because:
- The relayout script is designed to be generic (it works on any file, not just `nodered.json`)
- It would need to know where `nodered-last-downloaded.json` is
- Multiple commits might accumulate between downloads

**Simpler alternative:** Compare against `HEAD~1` if `HEAD` and working file are identical (meaning changes were already committed). Or: add an optional `--baseline <file>` argument that `upload-flows.sh` can pass, defaulting to `HEAD:$file_name` when not specified.

**Recommended approach:** Add an optional `--baseline <file>` argument to the relayout script. When not provided, use the current `HEAD:$file_name` behavior. In `upload-flows.sh`, pass `nodered-last-downloaded.json` as the baseline. This is clean, backward-compatible, and handles both the "uncommitted changes" and "already committed" cases correctly.

## Implementation Steps

### Step 1: Add `--baseline` flag to `relayout-nodered-flows.sh`

**File:** `/Users/drew/Projects/home/helper-scripts/relayout-nodered-flows.sh`

Add an optional `--baseline <file>` argument. When provided, use that file as the "before" state instead of `HEAD:$file_name`. When not provided, keep the current git-based behavior.

```bash
# Parse --baseline from args before passing remainder to python
BASELINE=""
REMAINING_ARGS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --baseline)
      BASELINE="$2"
      shift 2
      ;;
    *)
      REMAINING_ARGS+=("$1")
      shift
      ;;
  esac
done

if [[ -n "$BASELINE" ]]; then
  cp "$BASELINE" "$BEFORE_FILE"
else
  git -C "$file_dir" show "HEAD:$file_name" > "$BEFORE_FILE" 2>/dev/null || echo "[]" > "$BEFORE_FILE"
fi
```

### Step 2: Update `upload-flows.sh` to pass baseline

**File:** `/Users/drew/Projects/home/upload-flows.sh`

Change line 23 from:
```bash
"$PROJECT_DIR/helper-scripts/relayout-nodered-flows.sh" "$FLOWS_FILE" || true
```
to:
```bash
"$PROJECT_DIR/helper-scripts/relayout-nodered-flows.sh" "$FLOWS_FILE" --baseline "$LAST_DOWNLOADED" || true
```

This requires moving the `LAST_DOWNLOADED` variable declaration (currently on line 26) above the relayout call.

### Step 3: Add relayout step to CLAUDE.md "After modifying flows" section

**File:** `/Users/drew/Projects/home/CLAUDE.md`

In the "After modifying flows" section (around line 34), add a step before the diff summary:

```markdown
### After modifying flows

After making changes to `mynodered/nodered.json`:

0. **Run the relayout tool** to fix node positions:
   ```
   bash helper-scripts/relayout-nodered-flows.sh mynodered/nodered.json
   ```
   This must run before committing, while uncommitted changes exist. It
   repositions nodes within modified groups using dagre layout.

1. **Run the diff summary** and review...
```

### Step 4: Update `docs/modifying-nodered-json.md`

**File:** `/Users/drew/Projects/home/docs/modifying-nodered-json.md`

In the "End-to-end workflow: modify, verify, deploy" section (line 558-585), add a relayout step between step 3 (make changes) and step 4 (verify):

```markdown
# 3.5. Run relayout (before committing!)
bash helper-scripts/relayout-nodered-flows.sh mynodered/nodered.json
```

Also update the Tips section (line 595) to change "Positions are irrelevant" to note that relayout must be run before committing:

```markdown
- **Positions are handled by relayout.** The relayout tool fixes positioning.
  Run it after making changes but before committing:
  `bash helper-scripts/relayout-nodered-flows.sh mynodered/nodered.json`
```

### Step 5: Update CLAUDE.md helper script description

**File:** `/Users/drew/Projects/home/CLAUDE.md`

Update the `relayout-nodered-flows.sh` description (line 84) to mention the `--baseline` flag:

```
- `helper-scripts/relayout-nodered-flows.sh <flows.json> [--baseline <file>] [--dry-run] [--verbose]` - ...
  Use `--baseline <file>` to compare against a specific file instead of the last git commit
  (used by upload-flows.sh to compare against nodered-last-downloaded.json).
```

### Step 6: Fix the existing colocated nodes

Run relayout on the current nodered.json to fix the positions from commit `9f53f31`. Since the relayout script compares against HEAD and the nodes are already committed, use the new `--baseline` flag (once implemented) or manually specify the before file:

```bash
# After implementing the --baseline flag:
bash helper-scripts/relayout-nodered-flows.sh mynodered/nodered.json \
  --baseline mynodered/nodered-last-downloaded.json
```

Or if running before the script changes are in place, invoke the Python script directly with a pre-modification baseline:

```bash
git -C mynodered show 9f53f31~1:nodered.json > /tmp/before.json
python3 helper-scripts/relayout-nodered-flows.py mynodered/nodered.json /tmp/before.json --verbose
```

## Testing Strategy

1. **Test the `--baseline` flag:**
   ```bash
   # With --baseline: should detect changes and relayout
   bash helper-scripts/relayout-nodered-flows.sh mynodered/nodered.json \
     --baseline mynodered/nodered-last-downloaded.json --dry-run --verbose

   # Without --baseline: should still work (git-based comparison)
   # First make a trivial uncommitted change, then:
   bash helper-scripts/relayout-nodered-flows.sh mynodered/nodered.json --dry-run --verbose
   ```

2. **Test upload-flows.sh integration:**
   - Verify that `upload-flows.sh` passes the baseline correctly
   - Verify relayout runs even when changes are already committed

3. **Verify colocated nodes are fixed:**
   - After running relayout, check that the 12 previously-colocated nodes have distinct (x, y) positions
   - Check that both groups (`089fa1f004fbf0b7` and `41eee6d57596f252`) were relaid out
   - Verify the existing (non-new) nodes in group `41eee6d57596f252` also got reasonable positions

4. **Regression test:**
   - Run relayout twice -- second run should be a no-op (only position changes, which are cosmetic)
   - Run relayout on an unmodified file -- should be a no-op

## Risks & Considerations

1. **Baseline file might not exist.** If `nodered-last-downloaded.json` doesn't exist when `upload-flows.sh` runs (first-time setup, edge case), the `--baseline` flag would fail. The script should fall back to the git-based comparison if the baseline file doesn't exist. Add a check:
   ```bash
   if [[ -f "$LAST_DOWNLOADED" ]]; then
     "$PROJECT_DIR/helper-scripts/relayout-nodered-flows.sh" "$FLOWS_FILE" --baseline "$LAST_DOWNLOADED" || true
   else
     "$PROJECT_DIR/helper-scripts/relayout-nodered-flows.sh" "$FLOWS_FILE" || true
   fi
   ```

2. **Multiple modification commits between downloads.** If an agent makes several commits before uploading, the baseline (`nodered-last-downloaded.json`) correctly reflects the pre-modification state for all of them. This is actually better than the git-based approach, which only catches the most recent uncommitted changes.

3. **Relayout changes existing node positions in group `41eee6d57596f252`.** The existing group already has many nodes with established positions. Running relayout on this group will reposition ALL member nodes (not just the new ones), which could disrupt the existing layout. This is acceptable -- dagre will produce a clean LR layout for the whole group. But it's worth noting that the visual result may differ from what the user had manually arranged.

4. **The `nodered-last-downloaded.json` baseline is conceptually correct for upload.** This file represents "what's on the server" -- exactly what we want to diff against when deciding what needs relayout before uploading. It sidesteps the entire commit-timing issue.

5. **Agent guidance is still important.** Even with the script fix, agents should run relayout before committing so that the committed positions are correct (not all at 200,200). The `--baseline` in `upload-flows.sh` is a safety net, not the primary mechanism. Committed positions matter because:
   - Users reviewing diffs see meaningful positions
   - The `nodered.json` file serves as documentation of the visual layout
   - If upload is deferred or done manually, the committed state should be correct

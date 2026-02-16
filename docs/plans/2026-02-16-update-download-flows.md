# Plan: Update download-flows.sh for separate download/working file pattern

## Problem Statement

`download-flows.sh` currently downloads flows to `nodered-last-downloaded.json` (line 6) but still uses git-based diffing and git-aware checks throughout the script. The script needs to be updated so that:

- `nodered-last-downloaded.json` is the immutable "what the server has" snapshot
- `nodered.json` is the working file for local edits and analysis
- Comparisons use file-vs-file diffs instead of git-based diffs
- After downloading and confirming no local divergence, `nodered-last-downloaded.json` is copied to `nodered.json`
- Both files are committed together

This mirrors the existing pattern where `nodered-last-analyzed.json` tracks the last successfully analyzed version.

## Current State Analysis

### File roles (as documented in CLAUDE.md lines 66-68)

- `nodered-last-downloaded.json` -- Last known deployed state from the server. Never modified locally except by downloading.
- `nodered-last-analyzed.json` -- Snapshot after last successful `/analyze-flows` run. Used for diffing in the analyze skill.
- `nodered.json` -- Working file. Synchronized from production, used for local edits and as the file read by query tools.

### Current download-flows.sh logic (with TODO locations)

The script has 5 `TODO(Claude):` comments at lines 20, 37, 43, 55, and 91 (the one on line 63 says "Update logic" but is the same theme). Here is the current flow:

1. **Lines 6**: `FLOWS_FILE` is already set to `nodered-last-downloaded.json` (done by user).
2. **Lines 16-28 (TODO #1, line 20)**: Local modification check. Currently uses `git status --porcelain` to see if `nodered.json` has uncommitted changes, then calls `check-nodered-flows-unchanged.sh` to compare against live server. Needs to instead compare `nodered-last-downloaded.json` vs `nodered.json` locally.
3. **Lines 33**: Downloads flows to `$FLOWS_FILE` (`nodered-last-downloaded.json`). Already correct.
4. **Lines 38-47 (TODO #2, line 37; TODO #3, line 43)**: Change detection. Currently checks if `nodered.json` is tracked in git and uses `git diff --quiet` to see if it changed. Needs to instead compare the freshly downloaded `nodered-last-downloaded.json` against the existing `nodered.json`.
5. **Line 55 (TODO #4)**: Missing copy step. After confirming no local divergence, needs to copy `nodered-last-downloaded.json` to `nodered.json`.
6. **Lines 58-78 (TODO on line 63)**: Claude analysis invocation. The `claude` command needs the `--allowedTools` updated to reflect the file structure.
7. **Lines 82-88**: Analysis completion check. Already correct -- compares `$FLOWS_FILE` (`nodered-last-downloaded.json`) against `nodered-last-analyzed.json`.
8. **Lines 91-99 (TODO #5, line 91)**: Commit step. Currently stages only `nodered.json` and `nodered-last-analyzed.json`. Needs to also stage `nodered-last-downloaded.json`.

### Reference pattern: analyze-flows skill (step 6)

The analyze-flows skill (`.claude/commands/analyze-flows.md`, lines 268-280) marks completion by:
```bash
cp mynodered/nodered.json mynodered/nodered-last-analyzed.json
git -C mynodered add nodered-last-analyzed.json
```
The download script checks this at line 84: `diff -q "$FLOWS_FILE" "$ANALYZED_FILE"`. This pattern works correctly with the new design because:
- After download, `nodered-last-downloaded.json` is copied to `nodered.json` (new step)
- Analysis reads from `nodered.json` (same as `nodered-last-downloaded.json` at this point)
- Analysis completion copies `nodered.json` to `nodered-last-analyzed.json`
- Post-analysis check: `nodered-last-downloaded.json` == `nodered-last-analyzed.json` confirms analysis ran on the right version

## Proposed Solution

Replace all git-based diffing with file-vs-file comparisons, add the copy step, and update the commit to include all three files.

## Implementation Steps

### Step 1: Update the local modification guard (lines 16-28)

**Old logic (lines 16-28):**
```bash
# If nodered.json has uncommitted changes, only block if those changes differ from
# the live flows. ...
if [[ -f "$FLOWS_FILE" ]] && \
   [[ -n "$(git -C "$MYNODERED_DIR" status --porcelain -- nodered.json)" ]]; then
  if ! "$PROJECT_DIR/helper-scripts/check-nodered-flows-unchanged.sh" "$FLOWS_FILE" 2>/dev/null; then
    echo "mynodered/nodered.json has local modifications that differ from the live flows." >&2
    echo "Please commit or discard them before downloading fresh flows." >&2
    exit 1
  fi
fi
```

**New logic:**
```bash
# Block if nodered.json has been locally modified (diverged from the last download).
# This protects against overwriting manual edits with a fresh download.
# On first run, nodered-last-downloaded.json won't exist yet, so skip the check.
if [[ -f "$FLOWS_FILE" ]] && [[ -f "$MYNODERED_DIR/nodered.json" ]]; then
  if ! diff -q "$FLOWS_FILE" "$MYNODERED_DIR/nodered.json" &>/dev/null; then
    echo "mynodered/nodered.json has local modifications that differ from the last download." >&2
    echo "Please commit or discard them before downloading fresh flows." >&2
    exit 1
  fi
fi
```

**Rationale:** Instead of checking git status + comparing against live server (expensive network call), we simply compare the two local files. If `nodered.json` differs from `nodered-last-downloaded.json`, the user has local edits that would be overwritten. If they match, it's safe to overwrite both.

**Edge cases:**
- **First download ever:** Neither file exists. The `[[ -f "$FLOWS_FILE" ]]` check handles this -- if `nodered-last-downloaded.json` doesn't exist, skip the guard entirely.
- **First download with new pattern:** `nodered-last-downloaded.json` doesn't exist yet but `nodered.json` does (from the old workflow). Same -- skip the guard, download will create `nodered-last-downloaded.json`.
- **Files are identical (retry scenario):** diff passes, we proceed. This covers the case where a previous download succeeded but analysis failed.

### Step 2: Update change detection (lines 38-47)

**Old logic (lines 38-47):**
```bash
is_new=false
if ! git -C "$MYNODERED_DIR" ls-files --error-unmatch nodered.json &>/dev/null; then
  is_new=true
fi

if [[ "$is_new" == false ]] && git -C "$MYNODERED_DIR" diff --quiet -- nodered.json; then
  echo "No changes since last download."
  exit 0
fi
```

**New logic:**
```bash
is_new=false
if [[ ! -f "$MYNODERED_DIR/nodered.json" ]]; then
  is_new=true
fi

if [[ "$is_new" == false ]] && diff -q "$FLOWS_FILE" "$MYNODERED_DIR/nodered.json" &>/dev/null; then
  echo "No changes since last download."
  exit 0
fi
```

**Rationale:** Instead of checking git tracking status, check if `nodered.json` exists on disk. Instead of `git diff`, compare the freshly downloaded `nodered-last-downloaded.json` against the existing `nodered.json`. If they match, nothing changed on the server.

**Edge cases:**
- **First download:** `nodered.json` doesn't exist, `is_new=true`, skip the "no changes" exit.
- **No changes on server:** `nodered-last-downloaded.json` == `nodered.json`, print message and exit. Note: the freshly downloaded file will still be on disk (replacing any prior `nodered-last-downloaded.json`), which is fine -- it's identical content.

### Step 3: Add the copy step (after line 55)

**Insert after the `is_new` / changed message block (lines 49-53), replacing the TODO at line 55:**
```bash
# Safe to update the working file now -- we verified no local divergence in step 1.
cp "$FLOWS_FILE" "$MYNODERED_DIR/nodered.json"
```

**Rationale:** At this point we know:
1. Before download, `nodered.json` was not locally diverged from `nodered-last-downloaded.json` (step 1 guard)
2. The download wrote fresh data to `nodered-last-downloaded.json` (step: download)
3. The fresh data differs from the old `nodered.json` (step 2 didn't exit)

So it's safe to overwrite `nodered.json` with the new data.

### Step 4: Update the claude invocation's `--allowedTools` (lines 64-78)

**Current (line 63):**
```bash
# TODO(Claude): Update logic now that we maintain a separate nodered-last-downloaded.json and nodered.json.
  claude \
    ...
```

The `--allowedTools` list on lines 66-78 does not need significant changes. The tools already allow:
- `Bash(helper-scripts/*)` -- covers all query/summary scripts
- `Bash(cp mynodered/nodered.json mynodered/nodered-last-analyzed.json)` -- still correct, analyze step 6 copies `nodered.json` to `nodered-last-analyzed.json`
- `Bash(md5 mynodered/nodered.json)` -- still correct, MD5 is taken of the working file
- `Bash(git -C mynodered add nodered-last-analyzed.json)` -- still correct

The only change needed is removing the TODO comment on line 63. The allowed tools are already correct because:
- The analyze-flows skill reads from `nodered.json` (now updated by our copy step)
- The analyze-flows skill diffs `nodered-last-analyzed.json` vs `nodered-last-downloaded.json` (both exist at this point)
- The analyze-flows step 6 copies `nodered.json` to `nodered-last-analyzed.json` and stages it

No new `--allowedTools` entries are needed.

### Step 5: Update the commit step (lines 91-99)

**Old logic (line 92):**
```bash
git -C "$MYNODERED_DIR" add nodered.json nodered-last-analyzed.json
```

**New logic:**
```bash
git -C "$MYNODERED_DIR" add nodered.json nodered-last-downloaded.json nodered-last-analyzed.json
```

**Rationale:** All three files should be committed together. `nodered-last-downloaded.json` is the new addition.

### Step 6: Remove all TODO(Claude) comments

Remove the `TODO(Claude):` comments on lines 20, 37, 43, 55, 63, and 91. The associated comment blocks (like the explanation on lines 17-19) should be replaced with updated comments reflecting the new logic.

### Step 7: Update CLAUDE.md description (NOT needed)

Looking at CLAUDE.md line 42, the description already says:
```
- `download-flows.sh` - User-facing script to download the latest Node-RED flows from Home Assistant into `mynodered/nodered-last-downloaded.json` and commit them to the submodule.
```

This was already updated by the user. No changes needed to CLAUDE.md.

## Summary of all changes to `download-flows.sh`

| Section | Lines | What changes |
|---------|-------|--------------|
| Local modification guard | 16-28 | Replace git status + server check with local `diff -q` of the two files |
| Change detection (is_new) | 38-41 | Replace `git ls-files` with `[[ ! -f ... ]]` |
| Change detection (diff) | 43-47 | Replace `git diff --quiet` with `diff -q` of the two files |
| Copy step | after 53 | Add `cp "$FLOWS_FILE" "$MYNODERED_DIR/nodered.json"` |
| Claude invocation | 63 | Remove TODO comment (no functional change needed) |
| Commit step | 92 | Add `nodered-last-downloaded.json` to `git add` |
| All TODOs | 20,37,43,55,63,91 | Remove all `TODO(Claude):` comments, update surrounding comments |

## Files Modified

1. `/Users/drew/Projects/home/download-flows.sh` -- All the changes above.

No other files need modification:
- `CLAUDE.md` -- Already updated by the user (line 42 says `nodered-last-downloaded.json`, lines 66-68 describe the three-file pattern).
- `helper-scripts/check-nodered-flows-unchanged.sh` -- No longer called by `download-flows.sh`. Still used by `upload-flows.sh`. No changes needed.
- `helper-scripts/download-nodered-flows.sh` -- Unchanged; it already accepts an output path argument.
- `.claude/commands/analyze-flows.md` -- Unchanged; it already diffs `nodered-last-analyzed.json` vs `nodered-last-downloaded.json` and copies `nodered.json` to `nodered-last-analyzed.json` in step 6.

## Testing Strategy

1. **Read the modified script** and trace through each code path mentally:
   - First download (no `nodered.json` or `nodered-last-downloaded.json` exist)
   - Repeat download with no server changes (should exit "No changes")
   - Download with server changes but no local edits (should succeed)
   - Download with local edits to `nodered.json` (should block)

2. **Verify the analysis integration** -- After the copy step, `nodered.json` should equal `nodered-last-downloaded.json`, so the analyze-flows query tool reads the right data. After analysis completes, `nodered-last-analyzed.json` should equal both. The post-analysis check (`diff -q "$FLOWS_FILE" "$ANALYZED_FILE"`) should pass.

3. **Run a real download** if the user wants to validate end-to-end (requires HA server access).

## Risks & Considerations

1. **No network call in the guard step.** The old logic called `check-nodered-flows-unchanged.sh` which downloads live flows and compares. The new logic only does a local file comparison. This is intentional and correct -- the guard's job is to protect against losing *local* edits, not to check server state. Server state is checked implicitly: we download fresh flows and compare against the working file.

2. **`nodered-last-downloaded.json` persists on "no changes" exit.** When the server has no changes, we still wrote the downloaded data to `nodered-last-downloaded.json` (line 33). Since the content is identical to what was already there, this is harmless. The file modification timestamp will update but git won't see a diff.

3. **Race condition between download and copy.** If the user makes a local edit to `nodered.json` between when the guard passes (step 1) and when the copy happens (step 3), the edit would be lost. This is the same risk as the old git-based approach and is acceptable -- the script runs in seconds and the user shouldn't be editing files concurrently.

4. **The `check-nodered-flows-unchanged.sh` helper is no longer used by this script.** It's still used by `upload-flows.sh` (line 28), so it should NOT be removed.

5. **First-time migration from old pattern.** If a user has `nodered.json` committed but no `nodered-last-downloaded.json`, the first run will:
   - Skip the guard (no `nodered-last-downloaded.json` exists)
   - Download to `nodered-last-downloaded.json`
   - Detect `nodered.json` exists, compare them
   - If server matches what's committed: "No changes since last download" and exit
   - If server has changes: proceed, copy, analyze, commit
   This is correct behavior for migration.

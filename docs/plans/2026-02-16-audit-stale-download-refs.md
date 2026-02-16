# Plan: Audit and fix stale references to old download-flows pattern

## Problem Statement

The project recently changed `download-flows.sh` to use a two-file pattern:
- `nodered-last-downloaded.json` -- immutable server snapshot, download target
- `nodered.json` -- working copy, updated by copying from the download file
- Change detection uses `diff -q` between the two files instead of git diff

The script itself and the "Inner project" section of CLAUDE.md have been updated, but other files across the project may still reference the old pattern (downloading directly to `nodered.json`, git-based diffing for download state).

## Audit Results

### Files with stale references that need updating

#### 1. `/Users/drew/Projects/home/CLAUDE.md` line 52 -- DOCUMENTATION FIX

**Stale reference:** The Helper Scripts section describes `download-nodered-flows.sh` with a default of `mynodered/nodered.json`:
```
- `helper-scripts/download-nodered-flows.sh [output.json]` - Downloads the full Node-RED flow export from HA to a JSON file (default: `mynodered/nodered.json`). Output is normalized for stable diffs. Requires `uv`.
```

**What it should say:** The default in the helper script's code (`helper-scripts/download-nodered-flows.sh` line 7) is indeed still `mynodered/nodered.json` -- this is the fallback default baked into the inner helper script itself. However, the outer `download-flows.sh` now always passes `mynodered/nodered-last-downloaded.json` as an explicit argument, so in practice this default is only hit if someone runs the inner helper directly. The CLAUDE.md description is technically accurate about the script's own default, but could be misleading because it suggests the download workflow targets `nodered.json`. Two options:

- **Option A (minimal):** Leave the CLAUDE.md description as-is, since it accurately describes `download-nodered-flows.sh`'s own default parameter. The script is documented as a low-level helper not called by humans directly.
- **Option B (clearer):** Update the description to note that `download-flows.sh` calls this with `nodered-last-downloaded.json`.

**Recommendation:** Option A -- leave as-is. The helper script description documents its own interface. The higher-level `download-flows.sh` description (line 42) already correctly says `nodered-last-downloaded.json`. Changing the helper's actual default code is out of scope (it would break backwards compatibility for anyone calling it directly).

#### 2. `/Users/drew/Projects/home/helper-scripts/download-nodered-flows.sh` line 7 -- CODE: LOW PRIORITY / OPTIONAL

**Stale reference:**
```bash
OUTPUT_FILE="${1:-mynodered/nodered.json}"
```

**Analysis:** This default is a fallback for when someone calls the inner helper script directly without arguments. Since `download-flows.sh` (the user-facing script) always passes `nodered-last-downloaded.json` explicitly, this default is never reached in the normal workflow. The old default of `nodered.json` could be confusing if someone runs the helper directly.

**Recommendation:** Change the default to `mynodered/nodered-last-downloaded.json` to align with the new pattern. This is a minor code fix.

#### 3. `/Users/drew/Projects/home/.claude/commands/analyze-flows.md` line 274 -- DOCUMENTATION FIX

**Stale reference:** In step 6 ("Mark analysis complete"), the command copies `nodered.json` to `nodered-last-analyzed.json`:
```bash
cp mynodered/nodered.json mynodered/nodered-last-analyzed.json
```

**Analysis:** This is actually correct behavior, not stale. The analyze skill works with `nodered.json` (the working copy), and when analysis completes, it snapshots the working copy as the last-analyzed version. The `download-flows.sh` script's post-analysis check verifies `nodered-last-downloaded.json == nodered-last-analyzed.json`, which works because at download time `nodered.json` equals `nodered-last-downloaded.json`.

**Verdict:** No change needed. This is correct as-is.

#### 4. `/Users/drew/Projects/home/upload-flows.sh` -- NO STALE REFERENCES

**Analysis:** `upload-flows.sh` (lines 1-50) works with `nodered.json` as the file to upload, which is correct -- you upload the working copy. It calls `check-nodered-flows-unchanged.sh` to compare the working copy against the live server before uploading. Nothing here references the download pattern.

**Verdict:** No change needed.

#### 5. `/Users/drew/Projects/home/init.sh` line 174 -- MINOR CONCERN

**Reference:**
```bash
if [[ ! -f "$MYNODERED_DIR/nodered.json" ]]; then
```

**Analysis:** This checks if `nodered.json` exists to decide whether to prompt for initial download. After the new pattern, `download-flows.sh` creates both `nodered-last-downloaded.json` and `nodered.json`. So checking for `nodered.json` is correct -- if it doesn't exist, the user hasn't downloaded yet.

**Verdict:** No change needed. The logic is correct.

#### 6. `/Users/drew/Projects/home/helper-scripts/check-nodered-flows-unchanged.sh` -- NO STALE REFERENCES

**Analysis:** This script is a general-purpose tool that downloads live flows and diffs them against any given file. It's now only used by `upload-flows.sh` (not by `download-flows.sh` anymore, which was the old pattern). The script itself is generic and has no hardcoded references to `nodered.json` or the download pattern.

**Verdict:** No change needed.

#### 7. `/Users/drew/Projects/home/helper-scripts/relayout-nodered-flows.sh` -- NO STALE REFERENCES

**Analysis:** Uses `git -C ... show "HEAD:$file_name"` to get the committed version of whatever file is passed to it. Called by `upload-flows.sh` with `nodered.json`. This git-based comparison is appropriate here -- it's comparing the working file against its committed state to detect layout-worthy changes, not doing download-state detection.

**Verdict:** No change needed.

#### 8. `/Users/drew/Projects/home/helper-scripts/summarize-nodered-flows-diff.sh` -- NO STALE REFERENCES

**Analysis:** Similar to relayout -- the `--git` mode uses `git show "HEAD:$file_name"` to compare a file against its committed version. This is used for the "After modifying flows" workflow, not for download detection. The two-argument mode compares any two files directly.

**Verdict:** No change needed.

#### 9. `/Users/drew/Projects/home/docs/exploring-nodered-json.md` -- NO STALE REFERENCES

**Analysis:** This doc references `mynodered/nodered.json` as the flows file to query, which is correct -- `nodered.json` is the working copy and the file all query/summary tools operate on.

**Verdict:** No change needed.

#### 10. `/Users/drew/Projects/home/.claude/commands/deep-dive.md` -- NO STALE REFERENCES

**Analysis:** References `mynodered/nodered.json` as the data file for queries, which is correct.

**Verdict:** No change needed.

#### 11. `/Users/drew/Projects/home/mynodered/CLAUDE.md` -- NO STALE REFERENCES

**Analysis:** This file describes flows and subflows. It doesn't describe the download workflow. The MD5 at the bottom references `nodered-last-downloaded.json` which is the new pattern. No stale references.

**Verdict:** No change needed.

#### 12. `~/.claude/skills/coordinate/SKILL.md` -- NO STALE REFERENCES

**Analysis:** Generic coordination skill. No references to nodered files or download patterns.

**Verdict:** No change needed.

#### 13. `~/.claude/agents/planning-agent/agent.md` and `~/.claude/agents/implementation-agent/agent.md` -- NO STALE REFERENCES

**Analysis:** Generic agent definitions. No references to nodered files or download patterns.

**Verdict:** No change needed.

#### 14. `/Users/drew/Projects/home/helper-scripts/upload-nodered-flows.sh` line 7 -- NO ISSUE

**Reference:**
```bash
INPUT_FILE="${1:-mynodered/nodered.json}"
```

**Analysis:** The upload helper's default is `mynodered/nodered.json`, which is correct -- you upload the working copy.

**Verdict:** No change needed.

### Files with git-based diffing that is NOT stale

Several scripts use git-based comparisons (`git show HEAD:...`, `git diff`) that are NOT related to the download workflow and should NOT be changed:

- `relayout-nodered-flows.sh` -- Uses `git show HEAD:$file_name` to get the committed baseline for detecting layout changes in the working copy. This is correct -- it compares local edits against what was committed, not against what was downloaded.
- `summarize-nodered-flows-diff.sh --git` -- Uses `git show HEAD:$file_name` to compare a file against its committed version. Used by the "After modifying flows" workflow to see what changed.

These git-based diffs serve a different purpose (tracking local edits) than the download-state detection that was changed.

## Proposed Solution

Only two files need changes:

1. **`/Users/drew/Projects/home/helper-scripts/download-nodered-flows.sh` line 7** -- Update the default output path from `mynodered/nodered.json` to `mynodered/nodered-last-downloaded.json`.
2. **`/Users/drew/Projects/home/CLAUDE.md` line 52** -- Update the Helper Scripts description of `download-nodered-flows.sh` to reflect the new default.

## Implementation Steps

### Step 1: Update default in `helper-scripts/download-nodered-flows.sh`

File: `/Users/drew/Projects/home/helper-scripts/download-nodered-flows.sh`
Line 7: Change from:
```bash
OUTPUT_FILE="${1:-mynodered/nodered.json}"
```
To:
```bash
OUTPUT_FILE="${1:-mynodered/nodered-last-downloaded.json}"
```

### Step 2: Update CLAUDE.md Helper Scripts description

File: `/Users/drew/Projects/home/CLAUDE.md`
Line 52: Change from:
```
- `helper-scripts/download-nodered-flows.sh [output.json]` - Downloads the full Node-RED flow export from HA to a JSON file (default: `mynodered/nodered.json`). Output is normalized for stable diffs. Requires `uv`.
```
To:
```
- `helper-scripts/download-nodered-flows.sh [output.json]` - Downloads the full Node-RED flow export from HA to a JSON file (default: `mynodered/nodered-last-downloaded.json`). Output is normalized for stable diffs. Requires `uv`.
```

## Testing Strategy

1. Read both modified files and confirm the changes are correct.
2. Verify that `download-flows.sh` still works by tracing through the code: it passes `"$FLOWS_FILE"` (which is `mynodered/nodered-last-downloaded.json`) to `download-nodered-flows.sh`, so the default is never used in that path. The default change only affects direct callers.
3. Search the entire project once more for any remaining `nodered.json` references that look stale (a final grep pass).

## Risks & Considerations

1. **Changing the helper's default is a minor breaking change** for anyone who calls `helper-scripts/download-nodered-flows.sh` directly without arguments. However, the CLAUDE.md documentation says helper scripts are "not intended to be called directly by humans," so this risk is minimal. The main callers (`download-flows.sh` and `check-nodered-flows-unchanged.sh`) both pass explicit paths.

2. **No code logic changes needed** beyond the default path. The `download-flows.sh` script was already fully updated in the previous task. All other scripts that use git-based diffing do so for legitimate non-download purposes (layout detection, edit tracking).

3. **The `check-nodered-flows-unchanged.sh` helper** is no longer called by `download-flows.sh` but is still actively used by `upload-flows.sh`. It should not be removed or modified.

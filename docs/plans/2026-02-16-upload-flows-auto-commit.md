# Plan: Auto-commit `nodered-last-downloaded.json` after upload

## Problem Statement

After `upload-flows.sh` uploads flows to Node-RED and copies `nodered.json` to `nodered-last-downloaded.json`, the updated snapshot file is left uncommitted in the submodule. This means the "last known deployed state" isn't tracked in git until the next `download-flows.sh` run. We should auto-commit `nodered-last-downloaded.json` in the `mynodered/` submodule immediately after the copy, so the deployed state is always recorded in version history.

## Current State Analysis

**`upload-flows.sh`** (lines 64-74):
1. Line 68: Uploads flows via `helper-scripts/upload-nodered-flows.sh`
2. Line 71: Copies `nodered.json` to `nodered-last-downloaded.json` (`cp "$FLOWS_FILE" "$LAST_DOWNLOADED"`)
3. Line 74: Prints "Deploy complete."

There is **no git logic** anywhere in `upload-flows.sh` currently. This is net-new.

**Existing pattern in `download-flows.sh`** (lines 87-94):
The download script commits to the submodule using:
```bash
git -C "$MYNODERED_DIR" add nodered.json nodered-last-downloaded.json nodered-last-analyzed.json
git -C "$MYNODERED_DIR" add docs/
git -C "$MYNODERED_DIR" commit -m "Latest changes downloaded from Home Assistant."
```

This pattern stages specific files and commits with a descriptive message. We should follow the same style but be more targeted -- only staging `nodered-last-downloaded.json`.

## Proposed Solution

Add a git commit after the `cp` on line 71 that stages **only** `nodered-last-downloaded.json` and commits it with the message "Deployed flows." This ensures:
- Only the snapshot file is committed, not any other uncommitted changes in the submodule
- The deployed state is immediately tracked in git history
- The commit message clearly indicates this was a deploy action (distinct from the download script's "Latest changes downloaded from Home Assistant.")

## Implementation Steps

1. **Modify `upload-flows.sh`** -- Add two lines after the `cp` on line 71 (before the final echo):

   ```bash
   # Now that our local flows are what's deployed, update the last-downloaded snapshot.
   cp "$FLOWS_FILE" "$LAST_DOWNLOADED"

   # Commit the updated snapshot to the submodule.
   git -C "$MYNODERED_DIR" add nodered-last-downloaded.json
   git -C "$MYNODERED_DIR" commit -m "Deployed flows."
   ```

   Insert the two `git` lines between the existing `cp` (line 71) and the final blank echo (line 73).

## Edge Cases & Design Decisions

**Other uncommitted changes in the submodule**: By using `git -C "$MYNODERED_DIR" add nodered-last-downloaded.json` (staging a specific file) rather than `git add -A` or `git add .`, we ensure only the snapshot file is included in the commit. Any other uncommitted or staged changes (e.g., uncommitted doc edits, modified `nodered.json`) are left untouched.

**First-time upload (no prior `nodered-last-downloaded.json`)**: The `cp` creates the file, `git add` stages it as a new file, and `git commit` works fine. No special handling needed.

**File unchanged (upload of identical flows)**: This case is already handled -- `upload-flows.sh` exits early on line 46-47 if local flows match the server. If we somehow reach the commit with no actual diff in `nodered-last-downloaded.json`, `git commit` would fail with "nothing to commit." However, this shouldn't happen in practice because we only reach the upload path when flows differ from the server. Still, for robustness, we could consider this -- but the existing `download-flows.sh` doesn't guard against it either, so it's consistent to not add a guard here.

**`set -e` behavior**: The script uses `set -euo pipefail`. If git commit fails (e.g., nothing to commit), the script would exit with an error. This is acceptable -- if the commit fails, something unexpected happened and the user should know. The upload itself already succeeded at that point, so the flows are deployed regardless.

## Testing Strategy

1. Make a change to `nodered.json`, run `upload-flows.sh`, confirm it creates a commit in `mynodered/` containing only `nodered-last-downloaded.json` with message "Deployed flows."
2. Verify `git -C mynodered log --oneline -1` shows "Deployed flows."
3. Verify `git -C mynodered diff --cached` is empty after the script completes (nothing left staged).
4. Verify other files in `mynodered/` that might have uncommitted changes are NOT included in the commit.

## Risks & Considerations

- **Low risk**: The change is additive (two new lines) and comes after the upload has already succeeded, so it can't break the deploy itself.
- **Git state assumption**: We assume the submodule is a valid git repo. This is already validated at the top of the script (lines 11-14 check for `.git`).
- **No push**: Consistent with the project's git workflow conventions -- we commit but never push automatically.

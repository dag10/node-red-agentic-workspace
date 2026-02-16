The user has just created a new file `mynodered/nodered-last-downloaded.json` as a copy of `mynodered/nodered.json`. The project already had a similar pattern with `nodered-last-analyzed.json` (used by /analyze-flows to track diffs).

Previously, `download-flows.sh` downloaded directly to `nodered.json` and relied on git-based diffing to detect changes. Now, the script should:
- Download to `nodered-last-downloaded.json` (this is already done on line 6)
- Use `nodered-last-downloaded.json` vs `nodered.json` comparisons instead of git-based diffing
- Copy `nodered-last-downloaded.json` to `nodered.json` after confirming no local divergence
- Commit both files

The file has 4 `TODO(Claude):` comments marking the spots that need updating.

The CLAUDE.md description of `download-flows.sh` says it downloads to `mynodered/nodered.json` -- this needs updating too. And the description of `nodered-last-downloaded.json` and `nodered.json` in CLAUDE.md's inner project section was recently updated to reflect the new roles of these files.

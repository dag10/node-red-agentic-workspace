The project just changed how `download-flows.sh` works. Previously it downloaded flows directly to `mynodered/nodered.json` and used git-based diffing to detect changes. Now:
- Downloads go to `mynodered/nodered-last-downloaded.json`
- `nodered.json` is the working copy, updated by copying from `nodered-last-downloaded.json`
- Change detection uses `diff -q` between the two files instead of git diff

`download-flows.sh` has already been updated (in a previous task). The CLAUDE.md in the project root has already been partially updated by the user -- the "Inner project" section describes the new roles of these files correctly. But the "Outer project" section's description of `download-flows.sh` still says it downloads to `nodered.json`.

Audit the ENTIRE project for any remaining stale references that assume the old pattern (downloading directly to nodered.json, or using git-based diffing of nodered.json for download state). Check:

1. CLAUDE.md (project root) -- the outer project section's download-flows.sh description
2. All helper scripts in helper-scripts/ -- especially check-nodered-flows-unchanged.sh which was used by the old download guard
3. All skill files -- check ~/.claude/skills/ and any .claude/ directory in the project
4. All agent files -- check ~/.claude/agents/
5. upload-flows.sh -- may reference download patterns
6. init.sh -- may set up initial download state
7. Any docs in docs/ that describe the download workflow
8. mynodered/CLAUDE.md if it exists -- may describe the download workflow

For each file, note:
- What the stale reference is
- What it should be updated to
- Whether it's a documentation fix or a logic/code fix

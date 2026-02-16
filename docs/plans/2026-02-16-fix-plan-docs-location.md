# Plan: Fix Plan File Storage Location Guidance

## Problem Statement

Plan files for automation changes were incorrectly stored in `./docs/plans/` (outer project) instead of `mynodered/docs/plans/` (inner project). The `## Plans` section in CLAUDE.md only mentions `/docs/plans` with no distinction between outer project plans and automation plans. Since `mynodered/` is a separate git submodule, automation-related plans should live inside it alongside the other automation docs.

The rule should be:
- `./docs/plans/` -- plans about the outer project's tools and infrastructure (scripts, tooling, etc.)
- `mynodered/docs/plans/` -- plans about the user's specific automations (flow changes, subflow changes, etc.)

## Current State Analysis

### CLAUDE.md `## Plans` section (lines 99-116)

The current guidance says:

```
When you create plan markdown files, save them as a sensibly-named plan in the /docs/plans directory,
in the format of `YYYY-MM-DD-sensible-plan-name.md`. Use the current system date.
Commit them in the same commit where the plan is implemented.
```

This is ambiguous -- it always points to `/docs/plans` with no mention of the inner project. Agents working on automation tasks follow this guidance and put their plans in the wrong repo.

### CLAUDE.md line 57 (in "Commit structure for flow modifications")

```
- Plan files (if applicable, these go in the outer repo's commit)
```

This explicitly tells agents that plan files go in the outer repo, which is incorrect for automation plans. Automation plans should be committed as part of the `mynodered/` submodule commit alongside the flow changes and doc updates.

### Coordinate skill (`~/.claude/skills/coordinate/SKILL.md` line 37-39)

```
- Target plan file path — check CLAUDE.md for project guidance on where to store plans
  (and whether companion prompt files are expected). If the project specifies a location, use it.
```

This correctly defers to CLAUDE.md, so no changes needed here. Fixing CLAUDE.md is sufficient.

### Plan files in `./docs/plans/` and their classification

| File | About | Correct Location |
|------|-------|-----------------|
| `2026-02-15-pre-upload-dagre-relayout.*` | Relayout script (outer project tool) | `./docs/plans/` (correct) |
| `2026-02-16-audit-stale-download-refs.*` | Fixing stale refs in scripts/CLAUDE.md | `./docs/plans/` (correct) |
| `2026-02-16-nodered-write-tools.*` | Design for modify-nodered-flows tool | `./docs/plans/` (correct) |
| `2026-02-16-nodered-write-tools-implementation.*` | Implementation details for write tool | `./docs/plans/` (correct) |
| `2026-02-16-update-download-flows.*` | Updating download-flows.sh script | `./docs/plans/` (correct) |
| `2026-02-16-upload-flows-auto-commit.*` | Updating upload-flows.sh script | `./docs/plans/` (correct) |
| **`2026-02-16-cancel-unoccupied-on-switch-press.*`** | **Modifying Occupancy Detection flow** | **Should be `mynodered/docs/plans/`** |

Only one plan is misplaced: `2026-02-16-cancel-unoccupied-on-switch-press.md` and its companion `.prompt.md`. This plan is entirely about modifying Node-RED automation flows (adding departure cancellation via switch press to the Occupancy Detection flow).

### `mynodered/docs/plans/` directory

Does not yet exist. Needs to be created.

## Proposed Solution

1. Update CLAUDE.md `## Plans` section to distinguish between outer and inner project plans.
2. Update CLAUDE.md line 57 to correct the guidance about where automation plan files are committed.
3. Create `mynodered/docs/plans/` directory.
4. Move the misplaced automation plan files from `./docs/plans/` to `mynodered/docs/plans/`.
5. Remove the moved files from outer repo git tracking.
6. Add the moved files to inner submodule git tracking.

## Implementation Steps

### Step 1: Update CLAUDE.md `## Plans` section (lines 99-116)

Replace the current Plans section with guidance that distinguishes the two plan locations.

**Current text (lines 99-103):**
```markdown
## Plans

When you create plan markdown files, save them as a sensibly-named plan in the /docs/plans directory,
in the format of `YYYY-MM-DD-sensible-plan-name.md`. Use the current system date.
Commit them in the same commit where the plan is implemented.
```

**New text:**
```markdown
## Plans

Plan files go in different locations depending on what they're about:

- **Outer project plans** (scripts, tooling, infrastructure) go in `docs/plans/`.
- **Automation plans** (Node-RED flow/subflow changes) go in `mynodered/docs/plans/`.

Use the format `YYYY-MM-DD-sensible-plan-name.md` with the current system date.
Commit plan files in the same commit where the plan is implemented. For automation
plans, this means they're part of the `mynodered/` submodule commit alongside the
flow changes and doc updates.
```

The rest of the Plans section (companion prompt files, investigating code via git blame) remains unchanged.

### Step 2: Update CLAUDE.md line 57 (commit structure for flow modifications)

**Current text:**
```
- Plan files (if applicable, these go in the outer repo's commit)
```

**New text:**
```
- Plan files (if applicable, in `mynodered/docs/plans/`)
```

This corrects the guidance so automation plan files are committed as part of the inner submodule, not the outer repo.

### Step 3: Create `mynodered/docs/plans/` directory and move files

1. Create directory `mynodered/docs/plans/`.
2. Move `docs/plans/2026-02-16-cancel-unoccupied-on-switch-press.md` to `mynodered/docs/plans/2026-02-16-cancel-unoccupied-on-switch-press.md`.
3. Move `docs/plans/2026-02-16-cancel-unoccupied-on-switch-press.prompt.md` to `mynodered/docs/plans/2026-02-16-cancel-unoccupied-on-switch-press.prompt.md`.
4. `git rm` the old files from the outer repo.
5. `git -C mynodered add docs/plans/` in the inner submodule.

### Step 4: Commit changes

This task involves changes in both repos:

**Outer repo commit** should contain:
- Updated `CLAUDE.md` (plan location guidance + commit structure bullet)
- Removal of the two misplaced plan files from `docs/plans/`
- This plan file (`docs/plans/2026-02-16-fix-plan-docs-location.md`) and its `.prompt.md`
- Updated submodule pointer for `mynodered/`

**Inner submodule commit** (done first, so the outer repo can reference the new submodule state) should contain:
- The two moved plan files in `mynodered/docs/plans/`

## Testing Strategy

1. Verify the moved files exist in `mynodered/docs/plans/` and are identical to the originals.
2. Verify the old files no longer exist in `./docs/plans/`.
3. Verify `git status` in the outer repo shows the removals and CLAUDE.md changes.
4. Verify `git -C mynodered status` shows the new files added.
5. Read back the updated CLAUDE.md to confirm the Plans section and line 57 read correctly.
6. Grep for any remaining references to the old plan file paths to ensure nothing is broken.

## Risks & Considerations

1. **Cross-repo file move**: Since `mynodered/` is a git submodule, this is effectively a delete in one repo and an add in another. The files need to be committed in the submodule first, then the outer repo commit includes the updated submodule pointer.

2. **No existing cross-references**: Grep confirms nothing in the codebase references the automation plan file by path, so no broken links to worry about.

3. **Future automation plans**: After this change, agents working on automation tasks will see the updated CLAUDE.md guidance and put their plans in `mynodered/docs/plans/`. The coordinate skill already defers to CLAUDE.md for plan location, so no changes needed there.

4. **The `nodered-write-tools-implementation.md` plan**: This plan is about implementing the `modify-nodered-flows` tool (an outer project script), even though the tool operates on inner project files. The plan itself is about outer project tooling, so it correctly stays in `./docs/plans/`.

5. **This plan file itself**: This plan (`2026-02-16-fix-plan-docs-location.md`) is about fixing CLAUDE.md guidance and moving files -- it's an outer project infrastructure change, so it correctly belongs in `./docs/plans/`.

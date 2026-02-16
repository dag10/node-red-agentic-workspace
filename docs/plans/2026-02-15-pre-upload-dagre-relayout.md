# Plan: Pre-Upload Dagre Relayout Script

## Context

After modifying Node-RED flows (adding/removing/rewiring nodes), positions can end up
overlapping or crowded. The user tested the `@bartbutenaers/node-red-autolayout-sidebar`
plugin and likes dagre LR with settings `{"rankdir":"LR","marginx":10,"marginy":10,
"nodesep":10,"ranksep":30}`. This plan integrates that same algorithm into a pre-upload
pass that automatically relays out groups containing modified nodes.

## Architecture

**Python main + JS dagre subprocess.** The Python script handles all Node-RED JSON logic
(change detection, dimension estimation, coordinate mapping, group shifting). A tiny JS
script (~15 lines) wraps `@dagrejs/dagre` and communicates via stdin/stdout JSON. This
ensures exact dagre results matching what the user validated in the plugin.

Dagre auto-installs into `helper-scripts/.dagre-deps/` on first run (like how Python
scripts use `uv run --with`). Node v23 and npm are already available on this system.

## Files to Create

### 1. `helper-scripts/dagre-layout.js` — Dagre wrapper

Reads a graph from stdin, runs dagre, writes positions to stdout. ~15 lines.

Input: `{"settings": {...}, "nodes": [{id, width, height}], "edges": [{source, target}]}`
Output: `{"width": N, "height": N, "nodes": {"id": {x, y}, ...}}`

### 2. `helper-scripts/relayout-nodered-flows.py` — Main logic

Imports `build_index` and `collect_group_node_ids` from `query-nodered-flows.py`
(same pattern as `summarize-nodered-flows-diff.py`).

**Usage:** `relayout-nodered-flows.py <flows.json> <before.json> [--dry-run] [--verbose]`

**Core functions:**

- **`find_groups_needing_relayout()`** — Compares before/after by node ID. A group needs
  relayout if any member node was added, removed, or had `wires`/`links` changed.
  Position-only changes do NOT trigger relayout (avoids infinite loops). Groups with < 2
  member nodes are skipped.

- **`estimate_node_dimensions(node)`** — Heuristic width/height from type + label:
  - Junction: 10x10
  - Link in/out: 30x30 (wider if label shown via `l: true`)
  - Standard: width = max(100, len(label) * 7 + 55), height = max(30, outputs * 13 + 17)

- **`build_dagre_graph(group_id)`** — Extracts group member nodes + intra-group edges
  from `wires` arrays. Also adds virtual edges for link-in/link-out `links` connections
  within the same group (improvement over the plugin which ignores these).

- **`run_dagre(graph)`** — Calls `node dagre-layout.js` via subprocess with `NODE_PATH`
  pointing to `.dagre-deps/node_modules`.

- **`apply_dagre_positions(group_id, dagre_result)`** — Maps dagre center coordinates to
  flow space. Anchors to the group's existing top-left corner. Adds padding for group
  label (~35px top) and borders (~15px sides/bottom). Updates group `w`/`h`.

- **`shift_groups(relaid_info_list)`** — For each relaid group (processed top to bottom):
  finds all groups on the same flow tab whose `y >= old_bottom` and shifts them + their
  member nodes by `height_delta`. Handles cascading when multiple relaid groups stack
  vertically.

- **`ensure_dagre_deps()`** — Runs `npm install --prefix .dagre-deps @dagrejs/dagre` if
  not already installed.

### 3. `helper-scripts/relayout-nodered-flows.sh` — Bash wrapper

Follows `summarize-nodered-flows-diff.sh` pattern:
- Extracts git HEAD version of the flows file as the baseline (`--git` style)
- Falls back to `[]` if no committed version (everything is new)
- Calls the Python script with both files

**Usage:** `relayout-nodered-flows.sh <flows.json> [--dry-run] [--verbose]`

## Files to Modify

### 4. `upload-flows.sh` — Add relayout step

Insert relayout call **before** the divergence check (line 22), so position changes are
included when checking local vs server. The relayout is non-fatal — if it fails (no npm,
dagre install error), upload proceeds with current layout.

```
# current:  check env → check file exists → check divergence → confirm → upload
# new:      check env → check file exists → RELAYOUT → check divergence → confirm → upload
```

### 5. `.gitignore` — Add `helper-scripts/.dagre-deps/`

### 6. `CLAUDE.md` — Document new helper script in the Helper Scripts section

## Key Design Decisions

1. **Trigger: wires/links changes only.** Position-only or cosmetic changes don't trigger
   relayout. This prevents relayout → position change → relayout loops.

2. **Group-scoped layout.** Each group is laid out independently. Nodes wired to nodes
   outside the group have those edges dropped from the dagre graph (same as the plugin).

3. **Anchored to top-left.** The group's top-left corner stays fixed during relayout.
   Only the width/height (and internal node positions) change.

4. **Vertical shifting only.** After relayout, groups below a resized group shift
   vertically. Horizontal shifting for side-by-side groups is not attempted (groups
   rarely grow horizontally in problematic ways).

5. **Non-fatal in upload pipeline.** Relayout failure doesn't block uploads.

## Verification

1. Run standalone: `helper-scripts/relayout-nodered-flows.sh mynodered/nodered.json --dry-run --verbose`
   — verify correct groups identified and positions are reasonable
2. Run without `--dry-run`, then `git diff mynodered/nodered.json` to inspect position changes
3. Upload to Node-RED and visually verify the layout looks good
4. Run a second time — verify it's a no-op (no groups need relayout since only positions changed)
5. Test the full `upload-flows.sh` pipeline end-to-end

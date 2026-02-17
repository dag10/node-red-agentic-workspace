# Plan: Node Size Estimation Helper Script

## Problem Statement

The previous relayout approach (removed in commit `f147231`) used an inline width estimation function (`estimate_node_dimensions`) that was too imprecise and caused horizontal overlaps. Its heuristic was `max(120, len(label) * 8 + 60)` -- a monospace approximation for a proportional font. This plan designs a standalone helper script that accurately estimates Node-RED node dimensions by replicating the exact sizing logic from Node-RED's editor source code.

## Current State Analysis

### How Node-RED Actually Calculates Node Size

All sizing logic lives in `packages/node_modules/@node-red/editor-client/src/js/ui/view.js` in the Node-RED GitHub repo. The key formulas are:

**Width** (lines ~688, ~4916):
```javascript
// For nodes with visible labels:
d.w = Math.max(node_width, 20 * Math.ceil((labelParts.width + 50 + (d._def.inputs > 0 ? 7 : 0)) / 20));

// For nodes with hidden labels (link nodes with l not set, or l: false):
d.w = node_height;  // = 30
```

Where:
- `node_width = 100` (minimum width)
- `node_height = 30` (also used as min width for hidden-label nodes)
- `labelParts.width` = DOM-measured text width of the label in the "red-ui-flow-node-label" CSS class
- `+50` = space for icon area (~30px left) + right padding (~20px)
- `+7` = extra space for the input port notch (only when the node type has inputs)
- Result is rounded up to the nearest multiple of 20

**Height** (lines ~689, ~4904):
```javascript
// For nodes with visible labels:
d.h = Math.max(6 + 24 * labelParts.lines.length, (d.outputs || 0) * 15, 30);

// For nodes with hidden labels:
d.h = Math.max(node_height, (d.outputs || 0) * 15);  // node_height = 30
```

Where:
- `6 + 24 * lines` = text area height (24px per line + 6px padding)
- `outputs * 15` = height needed for evenly spaced output ports
- Minimum height is 30px

**Junction nodes**: Always exactly 10x10 px (rendered as a small diamond).

**Label determination** (from `RED.utils.getNodeLabel` in `ui/utils.js`, line 1219):
- Most nodes: `node.name || fallback_from_type_definition`
- Subflow instances: `node.name || subflow_definition.name`
- Link nodes: label visibility controlled by `node.l` property; when hidden, dimensions shrink to 30x30
- Inject nodes: `node.name + suffix` where suffix is "  ↻" if repeating, " 1" if fire-once (these add to width)

**Label visibility** (from view.js, line 680):
```javascript
var isLink = (nn.type === "link in" || nn.type === "link out");
var hideLabel = nn.hasOwnProperty('l') ? !nn.l : isLink;
```

**Font** (from `sass/colors.scss` and `sass/flow.scss`):
- Family: `'Helvetica Neue', Arial, Helvetica, sans-serif`
- Size: `14px`
- Weight: `normal` (400)
- The editor measures text by creating a `<span>` with class `red-ui-flow-node-label` and reading `offsetWidth`

### Button Nodes and Group Bounding Boxes

Some node types have a clickable button that extends beyond the node rect:
- **inject**: Left-aligned button, adds 25px to the left (transform `translate(-25, 2)`, button width 32px)
- **debug**: Right-aligned button (`align: "right"`), adds at x=94

Buttons do NOT affect the node's `w` property. However, when computing **group bounding boxes**, buttons ARE accounted for (from `ui/group.js`, line 575):
```javascript
group.x = Math.min(group.x, n.x - n.w/2 - 25 - ((n._def.button && n._def.align !== "right") ? 20 : 0));
group.w = Math.max(group.w, n.x + n.w/2 + 25 + ((n._def.button && n._def.align == "right") ? 20 : 0) - group.x);
```

This means inject nodes need 20px extra on the left, and debug nodes need 20px extra on the right, when computing group boundaries. The standard per-side padding in the group bounding box is 25px.

### Old Estimation vs. Reality

The old `estimate_node_dimensions` used `len(label) * 8 + 60` -- treating all characters as 8px wide. In reality:
- 'i' and 'l' are 3px wide at 14px Helvetica Neue
- 'W' and 'M' are 12-13px wide
- Average lowercase is ~7px, average uppercase is ~10px
- A label like "iiiii" (5 chars) should measure ~16px, not ~40px (old estimate)
- A label like "WWWWW" (5 chars) should measure ~65px, not ~40px (old estimate)

The old code also missed: rounding to 20px grid, the +7 for input ports, the +50 constant, minimum width of 100px, and per-character width variations.

### Existing Script Patterns

Helper scripts follow a bash-wrapper-calls-Python pattern:
- `query-nodered-flows.sh` -> `query-nodered-flows.py`
- `modify-nodered-flows.sh` -> `modify-nodered-flows.py`
- `summarize-nodered-flows.sh` -> `summarize-nodered-flows.py`

The bash wrapper validates arguments, checks file existence, then `exec python3` into the Python script.

## Proposed Solution

Create `helper-scripts/estimate-node-size.sh` (bash wrapper) and `helper-scripts/estimate-node-size.py` (Python implementation) that:

1. Loads a flows JSON file
2. Given a node or group ID, computes its rendered dimensions
3. For nodes: outputs `width height` (two integers)
4. For groups: outputs `width height` (calculated from member nodes)
5. Supports batch mode for multiple IDs at once (used by relayout)
6. Uses Pillow to measure text in Helvetica Neue 14px for accurate proportional font metrics

### Text Width Strategy

Two approaches, in order of preference:

**Approach A: Pillow font measurement (preferred).** Use Pillow's `ImageFont.truetype()` to load Helvetica Neue at 14px and measure each label with `getlength()`. This is the most accurate since it uses the actual font file. On macOS, the font is at `/System/Library/Fonts/HelveticaNeue.ttc`. On Linux, it falls back to a precomputed character width table.

**Approach B: Precomputed character width table (fallback).** If Pillow/font is unavailable, use a hardcoded lookup table of per-character advance widths at 14px Helvetica Neue. This table is derived from Pillow measurements and covers ASCII printable characters. Unknown characters use average width.

The script uses Approach A when Pillow and the font are available, and falls back to Approach B otherwise. Since this project already uses `uv` for running Python scripts, we can use `uv run --with Pillow` to get Pillow without polluting the system.

Actually, looking at existing scripts, they use plain `python3` (not `uv run`). The `uv` is used only for scripts that need external Python packages (like `requests` in `download-nodered-flows.py`). Since we want Pillow for accuracy but must also work without it, the script should:
- Try to import Pillow
- If available, use it for font measurement
- If not, fall back to the character width table

This way the script works with plain `python3` (using the fallback table) and gives better accuracy when Pillow is installed.

### Node Type Knowledge

The script needs to know:

1. **Which node types have inputs** (for the +7 in width formula). Rather than hardcoding a list, the script can look at whether the node is wired to from other nodes (has incoming wires). But actually, the Node-RED formula uses `_def.inputs > 0`, which is a type-level property. We can approximate this:
   - Types with `inputs=0`: `inject`, `link in`, `server-events`, `server-state-changed`, `ha-time`, `poll-state`, `trigger-state`, `cronplus`, `complete`, `catch`, `status`, `ha-webhook`
   - Subflow instances: check `len(subflow_def.in)` from the flows JSON
   - Everything else: assume `inputs >= 1`
   - Fallback: if we see incoming wires to a node, it has inputs

2. **Label determination** by node type:
   - Most types: `node.name || type_name` (e.g., "function", "delay", "switch", "change")
   - Subflow instances (`subflow:XXXX`): `node.name || subflow_def.name`
   - HA nodes: `node.name || type-specific_default` (e.g., "API", "current_state: entity_id")
   - Inject: `node.name + suffix` (where suffix = " 1" if `once`, "\t↻" if `repeat` or `crontab`)
   - Debug: `node.name || "msg." + node.property` or `"debug"` for complete msg

3. **Button nodes** (for group calculations):
   - `inject`: left-aligned button
   - `debug`: right-aligned button

### API Design

```
Usage: estimate-node-size.sh <flows.json> <command> [args...]

Commands:
  node <node_id>              Output: width height
  group <group_id>            Output: width height (bounding box of members + padding)
  batch                       Read JSON array of IDs from stdin, output JSON results

Examples:
  bash helper-scripts/estimate-node-size.sh mynodered/nodered.json node abc123
  # Output: 160 30

  bash helper-scripts/estimate-node-size.sh mynodered/nodered.json group def456
  # Output: 800 400

  echo '["id1","id2","id3"]' | bash helper-scripts/estimate-node-size.sh mynodered/nodered.json batch
  # Output: {"id1": {"w": 160, "h": 30}, "id2": {"w": 200, "h": 45}, ...}
```

The batch mode is the primary interface for the relayout system, which needs dimensions for all nodes in a group at once. It returns a JSON object for easy parsing.

An additional mode that's very useful for relayout:

```
  group-layout <group_id>     Output: JSON with all member node sizes + group bbox
```

This returns everything the relayout tool needs in one call: every member node's estimated width/height, plus the computed group bounding box (accounting for node positions, sizes, buttons, and padding).

## Implementation Steps

### Step 1: Create `helper-scripts/estimate-node-size.py`

The Python script with the following structure:

```python
"""Estimate rendered dimensions of Node-RED nodes and groups.

Replicates the exact sizing logic from Node-RED's editor (view.js)
to produce pixel-accurate width/height estimates for nodes, and
bounding-box dimensions for groups.

Usage: Called by estimate-node-size.sh, not directly.
"""
```

#### 1a. Character width table (fallback)

Hardcode a dictionary of character -> advance width at 14px Helvetica Neue, measured via Pillow. Cover ASCII 32-126 plus common Unicode characters (arrows, etc.). Unknown characters use the average width (~7.5px).

```python
# Measured from Helvetica Neue at 14px using Pillow getlength()
CHAR_WIDTHS_14PX = {
    ' ': 3.9, '!': 4.4, '"': 5.6, '#': 8.4, '$': 7.8, '%': 11.7, ...
    'A': 10.2, 'B': 9.5, ...
    'a': 7.8, 'b': 8.1, ...
    # etc.
}
DEFAULT_CHAR_WIDTH = 7.5
```

Actually, let me refine this. The Pillow measurements showed integer values because `getbbox` returns integers. Let me use `getlength` which returns floats for more precision. The character width table should use the `getlength` values.

#### 1b. Text measurement function

```python
def measure_text_width(text):
    """Measure text width in pixels at 14px Helvetica Neue."""
    # Try Pillow first
    if _pillow_font:
        return _pillow_font.getlength(text)
    # Fallback to character width table
    return sum(CHAR_WIDTHS_14PX.get(c, DEFAULT_CHAR_WIDTH) for c in text)
```

#### 1c. Label determination

```python
def get_node_label(node, flows_data, subflow_defs):
    """Determine the label text that Node-RED would display for a node."""
    ntype = node.get("type", "")
    name = node.get("name", "")

    if ntype == "junction":
        return ""  # Junctions have no label

    if ntype == "tab" or ntype == "group":
        return name or node.get("label", "")

    # Subflow instances
    if ntype.startswith("subflow:"):
        sf_id = ntype[8:]
        sf_def = subflow_defs.get(sf_id)
        if sf_def:
            return name or sf_def.get("name", ntype)
        return name or ntype

    # Inject nodes have suffix
    if ntype == "inject":
        suffix = ""
        if node.get("once"):
            suffix = " \u00b9"  # superscript 1
        if (node.get("repeat") and node.get("repeat") != "0") or node.get("crontab"):
            suffix = "\t\u21bb"  # tab + clockwise arrow
        return (name or "inject") + suffix

    # Debug nodes
    if ntype == "debug":
        if name:
            return name
        prop = node.get("property", "payload")
        target_type = node.get("targetType", "msg")
        if target_type == "msg":
            return "msg." + prop
        return "debug"

    # HA nodes with entity-specific fallbacks
    if ntype == "api-call-service":
        return name or "API"
    if ntype == "api-current-state":
        return name or ("current_state: " + node.get("entity_id", ""))
    if ntype == "server-state-changed":
        # events-state: uses entities list or entity_id
        return name or ntype
    if ntype == "trigger-state":
        return name or ntype
    if ntype == "poll-state":
        entity = node.get("entity_id", "")
        return name or ("poll state: " + entity)
    if ntype == "ha-time":
        entity = node.get("entityId", "")
        prop = node.get("property", "state")
        return name or (entity + "." + prop if entity else "time")

    # Generic fallback: name or type
    return name or ntype
```

#### 1d. Node dimension calculation

```python
NODE_WIDTH_MIN = 100
NODE_HEIGHT = 30

# Types known to have inputs=0
NO_INPUT_TYPES = {
    "inject", "link in", "server-events", "server-state-changed",
    "ha-time", "poll-state", "trigger-state", "cronplus",
    "complete", "catch", "status", "ha-webhook",
}

def has_inputs(node, subflow_defs):
    """Whether this node type has input ports."""
    ntype = node.get("type", "")
    if ntype in NO_INPUT_TYPES:
        return False
    if ntype.startswith("subflow:"):
        sf_id = ntype[8:]
        sf_def = subflow_defs.get(sf_id)
        if sf_def:
            return len(sf_def.get("in", [])) > 0
        return True  # assume has inputs if we can't find the def
    return True  # most types have inputs

def is_label_hidden(node):
    """Whether the node's label is hidden."""
    ntype = node.get("type", "")
    is_link = ntype in ("link in", "link out")
    if "l" in node:
        return not node["l"]
    return is_link

def estimate_node_size(node, flows_data, subflow_defs):
    """Return (width, height) in pixels for a node."""
    ntype = node.get("type", "")

    # Junctions are always 10x10
    if ntype == "junction":
        return 10, 10

    if is_label_hidden(node):
        outputs = node.get("outputs", len(node.get("wires", [])))
        w = NODE_HEIGHT  # 30
        h = max(NODE_HEIGHT, outputs * 15)
        return w, h

    label = get_node_label(node, flows_data, subflow_defs)

    # Handle multi-line labels (split on "\n " -- literal backslash-n-space)
    lines = label.split("\\n ")
    # Measure widest line
    text_width = max(measure_text_width(line.strip()) for line in lines) if lines else 0
    num_lines = len(lines)

    # Width formula
    inputs_extra = 7 if has_inputs(node, subflow_defs) else 0
    import math
    w = max(NODE_WIDTH_MIN, 20 * math.ceil((text_width + 50 + inputs_extra) / 20))

    # Height formula
    outputs = node.get("outputs", len(node.get("wires", [])))
    h = max(6 + 24 * num_lines, outputs * 15, 30)

    return w, h
```

#### 1e. Group bounding box calculation

For groups, we need to calculate the bounding box from member nodes:

```python
# Group padding constants (from Node-RED group.js addToGroup)
GROUP_NODE_PADDING = 25  # padding from node center +/- half-width to group edge

# Button extras
BUTTON_EXTRA = 20  # extra padding for button nodes

BUTTON_LEFT_TYPES = {"inject"}  # left-aligned button
BUTTON_RIGHT_TYPES = {"debug"}  # right-aligned button

def estimate_group_size(group, flows_data, idx, subflow_defs):
    """Return (width, height) for a group, calculated from member nodes."""
    member_ids = collect_group_node_ids(group["id"], idx)

    min_x = float('inf')
    max_x = float('-inf')
    min_y = float('inf')
    max_y = float('-inf')

    for mid in member_ids:
        node = idx["by_id"].get(mid)
        if not node or node.get("type") in ("group", "comment"):
            continue

        x = node.get("x", 0)
        y = node.get("y", 0)
        w, h = estimate_node_size(node, flows_data, subflow_defs)

        # Left edge (accounting for button)
        left_extra = BUTTON_EXTRA if node.get("type") in BUTTON_LEFT_TYPES else 0
        left = x - w / 2 - GROUP_NODE_PADDING - left_extra

        # Right edge (accounting for button)
        right_extra = BUTTON_EXTRA if node.get("type") in BUTTON_RIGHT_TYPES else 0
        right = x + w / 2 + GROUP_NODE_PADDING + right_extra

        top = y - h / 2 - GROUP_NODE_PADDING
        bottom = y + h / 2 + GROUP_NODE_PADDING

        min_x = min(min_x, left)
        max_x = max(max_x, right)
        min_y = min(min_y, top)
        max_y = max(max_y, bottom)

    if min_x == float('inf'):
        return 0, 0

    return int(max_x - min_x), int(max_y - min_y)
```

#### 1f. Command handlers

- `node <id>`: Print `width height`
- `group <id>`: Print `width height`
- `batch`: Read JSON from stdin with list of IDs, output JSON dict
- `group-layout <id>`: Output JSON with all member node sizes

#### 1g. Main and argument parsing

Standard argparse setup, loading the flows JSON once and building indexes.

### Step 2: Create `helper-scripts/estimate-node-size.sh`

Bash wrapper following the same pattern as other scripts:

```bash
#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: estimate-node-size.sh <flows.json> <command> [args...]" >&2
  exit 1
fi

FLOWS_FILE="$1"

if [[ ! -f "$FLOWS_FILE" ]]; then
  echo "Error: file not found: $FLOWS_FILE" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/estimate-node-size.py" "$@"
```

### Step 3: Generate accurate character width table

Run a one-time Pillow measurement to produce the hardcoded fallback table:

```python
from PIL import ImageFont
font = ImageFont.truetype('/System/Library/Fonts/HelveticaNeue.ttc', 14)
for code in range(32, 127):
    c = chr(code)
    w = font.getlength(c)
    print(f"    {c!r}: {w},")
```

This table goes directly into the Python script as a constant dict.

### Step 4: Update CLAUDE.md

Add the new script to the Helper Scripts section:

```
- `helper-scripts/estimate-node-size.sh <flows.json> <command> [args...]` - Estimates
  the rendered pixel dimensions of Node-RED nodes and groups. Replicates the exact
  sizing formulas from Node-RED's editor. Commands: `node <id>` (outputs `width height`),
  `group <id>` (bounding box from members), `batch` (JSON from stdin), `group-layout <id>`
  (all member sizes + bbox). Used by the relayout system.
```

### Step 5: Update the relayout skill

Update `.claude/skills/relayout-nodered-flows/SKILL.md` to reference this script
instead of the inline width estimation table. Change the "Node Width Estimation"
section to point to this script, and update the relayout algorithm descriptions
to call `estimate-node-size.sh` for accurate dimensions.

## Implementation Details

### Handling the `outputs` field

The `outputs` field in the exported JSON may or may not be present. For some node types:
- `switch`: `outputs` is explicit in the JSON (varies by rule count)
- `function`: `outputs` is explicit
- `api-current-state`: `outputs` may be 1 or 2 depending on `halt_if`
- Most nodes: default 1 output

When `outputs` is not in the JSON, fall back to `len(node.get("wires", []))` since each output port has an entry in the wires array.

### Handling HA node labels accurately

For `server-state-changed` (events-state) nodes without a name, the label logic in the HA plugin is complex -- it builds a label from the entities list. Since the exported JSON has `entities` as an object, we can replicate this:

```python
if ntype in ("server-state-changed", "trigger-state"):
    if not name:
        entities = node.get("entities", {})
        entity_ids = []
        for key, ids in entities.items():
            if isinstance(ids, list):
                entity_ids.extend(ids)
        if entity_ids:
            return ", ".join(entity_ids[:3]) + ("..." if len(entity_ids) > 3 else "")
        # Older format
        entity_id = node.get("entity_id", "")
        return entity_id or ntype
```

However, for simplicity and because most nodes in the user's flows have explicit names, we can start with `name || type` as the fallback and add type-specific logic for the most common cases.

### Edge case: `link call` nodes

Link call nodes are special -- they display differently depending on whether they have a label. Without `l: true`, they show as compact circles (like link in/out). With labels, they show the label text. The sizing follows the same `is_label_hidden` logic.

But link call is NOT a "link" type in the `isLink` check:
```javascript
var isLink = (nn.type === "link in" || nn.type === "link out");
```

So `link call` always has `hideLabel = nn.hasOwnProperty('l') ? !nn.l : false`. This means link call labels are visible by default (they're not treated as link nodes for label hiding). If no name is set, the label would be empty/type-name.

Actually, looking more carefully at the code, `link call` is rendered as a regular node with label "link call" if no name is given. Let me correct: `link call` is NOT in the `isLink` check, so its label is always visible. The label would be `node.name || "link call"`.

Wait, but the old code had `link call` at width 30. Let me re-check. The user's link call nodes:

```python
# link call has no special 'l' handling since it's not "link in" or "link out"
# So hideLabel = node.hasOwnProperty('l') ? !node.l : false
# If 'l' is not set, hideLabel = false (label is visible)
```

But many link call nodes have empty names. So the label would be "link call" and the width would be `max(100, 20*ceil((measure_text("link call")+50+7)/20))`. Let me check: "link call" at 14px is about 51px, so `51+50+7=108`, ceil(108/20)=6, `20*6=120`. So link call width = 120px, not 30px.

Hmm, but in the existing flows they look compact. Let me check if there's something else going on. Actually, I realize the HA Node-RED palette might register `link call` differently, or the label might be shorter. Let me check the actual core node definition.

Actually, looking at the Node-RED source again:

```javascript
function getNodeLabel(node,defaultLabel) {
    ...
    l = node._def.label;
    try {
        l = (typeof l === "function" ? l.call(node) : l)||defaultLabel;
    } catch(err) {
        l = defaultLabel;
    }
    ...
}
```

And `defaultLabel` is passed as the node type. For `link call`, the `_def.label` would come from the link node registration. Let me check.

Looking at the Node-RED 60-link.html for link call:

The link nodes are all registered in the same file. `link call` has `label: function() { return this.name || RED._("link.call"); }`. The `RED._("link.call")` is an i18n lookup that likely returns "link call" in English.

So yes, link call with no name has label "link call" and visible label, giving width 120px. This matches what I see in actual Node-RED.

### Subflow port nodes

Subflow in/out port nodes (type="subflow") have `w=40, h=40`. These appear only inside subflow definitions and are sized differently from regular nodes:

```javascript
d.h = 40;
// ... width also becomes 40 if label is hidden, or measured from label
```

We should handle these as a special case.

### Output Format Considerations

For the relayout system, the most useful output format for `group-layout` would be:

```json
{
  "group": {"id": "abc", "w": 800, "h": 400},
  "nodes": {
    "node1": {"w": 160, "h": 30, "has_button": "left"},
    "node2": {"w": 200, "h": 45, "has_button": null},
    ...
  }
}
```

The `has_button` field tells the relayout tool whether to account for extra space when computing group bounds (inject = "left", debug = "right", others = null).

## Testing Strategy

### Unit tests via direct invocation

Test against known nodes in the user's flows:

```bash
# Test a named function node
bash helper-scripts/estimate-node-size.sh mynodered/nodered.json node <function_node_id>
# Expected: ~120 30 (for short name) or larger for long names

# Test a junction
bash helper-scripts/estimate-node-size.sh mynodered/nodered.json node <junction_id>
# Expected: 10 10

# Test a link node with hidden label
bash helper-scripts/estimate-node-size.sh mynodered/nodered.json node <link_out_id>
# Expected: 30 30

# Test a link node with visible label
bash helper-scripts/estimate-node-size.sh mynodered/nodered.json node <link_in_with_l_true>
# Expected: wider than 30

# Test a multi-output node (switch with 5 rules)
bash helper-scripts/estimate-node-size.sh mynodered/nodered.json node <switch_id>
# Expected: width based on label, height = max(30, 5*15) = 75
```

### Cross-validation with browser

For the most critical validation, open Node-RED in a browser, inspect a node's SVG element to see its actual `width` and `height` attributes, and compare with our estimates. The script should produce values within 0-20px of the browser (since both round to nearest 20 for width).

### Batch mode test

```bash
echo '["node1","node2","junction1"]' | \
  bash helper-scripts/estimate-node-size.sh mynodered/nodered.json batch
# Should output valid JSON with all three nodes' dimensions
```

### Group size test

Compare estimated group dimensions with the actual `w` and `h` values that would be set if the group were auto-fitted in the Node-RED editor.

## Risks & Considerations

1. **Font availability**: The Pillow approach requires the Helvetica Neue font file. On macOS it's at `/System/Library/Fonts/HelveticaNeue.ttc`. On Linux or in CI, this font won't exist -- the fallback character width table handles this case. The table should be accurate to within ~1px per character.

2. **Browser rendering differences**: The browser's `offsetWidth` may differ slightly from Pillow's measurement due to subpixel rendering, font hinting, and kerning differences. Since Node-RED rounds width to the nearest multiple of 20, small differences (1-3px) rarely affect the final result.

3. **HA node label complexity**: Some HA node types (events-state, trigger-state) have complex label functions that examine entity lists. We approximate these; for most nodes the user sets an explicit name anyway.

4. **Node types we don't know about**: Third-party nodes may have custom label functions. The fallback of `name || type` is reasonable. If accuracy for a specific type becomes important, we add it to the label determination function.

5. **The `outputs` field**: Some node types dynamically determine outputs (e.g., switch nodes with variable rule counts). The exported JSON should always have the correct `outputs` value or we can count `wires` array length.

6. **Multi-line labels**: The `\n ` (backslash-n-space, literal) line break is rare but supported. The implementation handles it correctly by splitting on `\\n ` and measuring the widest line.

7. **Unicode characters**: The inject node suffix includes Unicode characters like ↻ (U+21BB) and ¹ (U+00B9). The character width table needs to include these, or the Pillow font measurement handles them automatically.

8. **Performance**: The script loads the entire flows JSON and builds an index for every invocation. For a single node, this is fast (~100ms). For batch mode with many nodes, the index is built once and reused. This should be fine for the relayout use case.

# Plan: Fix Missing Default Fields for HA Node Types in add-node

## Problem Statement

When `modify-nodered-flows.sh add-node` creates an `api-current-state` node, it only
sets the fields the agent explicitly passes in `--props`. If the agent omits fields that
Node-RED's runtime considers required (even though the UI would auto-populate them for
new nodes), the deploy fails at runtime.

Concrete bug: commit `889c9c5` in mynodered added an `api-current-state` node
(`2a7b4da289b1c1c7`, "is sun up?") that was missing `for`, `forType`, and `forUnits`.
When deployed via `upload-flows.sh`, Node-RED threw `InputError: Invalid for value:
undefined`. Redeploying from the Node-RED web UI fixed it by auto-populating `"for": ""`
and `"forType": "num"` (commit `9164022`).

This is the second occurrence of this class of bug -- the first was `api-call-service`
nodes missing `version: 7` and its associated fields (`areaId`, `deviceId`, etc.),
fixed in commit `0c99238`. The existing doc warning about version-specific fields
(commit `9658247`) tells agents to copy from template nodes, but the agent in this case
DID reference template node `82c829b2068f9e44` (which has all the right fields) and
still missed `for`/`forType`/`forUnits` when transcribing the props.

## Current State Analysis

### How add-node works (`helper-scripts/modify-nodered-flows.py:180-249`)

`_cmd_add_node` builds a minimal node with core fields (`id`, `type`, `z`, `name`, `x`,
`y`, `wires`) and then:
1. Adds `g` if a group is specified
2. Auto-sets `server` for HA node types (via `HA_SERVER_NODE_TYPES` set, line 37-41)
3. Shallow-merges `props` over the base fields

There is no type-specific default injection. The node gets exactly what the agent
passes, plus the auto-generated core fields and server.

### Fields commonly missed by agents

The pattern is clear: agents see the "important" fields (entity_id, halt_if, version,
outputProperties) and copy those, but miss "boring" fields that look like they'd default
to something sensible:

- `api-current-state` v3: `for`, `forType`, `forUnits` (the "for how long" condition)
- `api-call-service` v7: `version`, `areaId`, `deviceId`, `floorId`, `labelId`,
  `debugenabled` (version and v7-specific targeting arrays)

The docs already warn about this, but the warning is insufficient -- it tells agents
to copy from templates, but doesn't prevent the field-omission error that happens when
agents selectively copy fields.

### Full required field sets for common HA node types

Based on analysis of all 41 `api-current-state` nodes, 167 `api-call-service` nodes,
49 `server-state-changed` nodes, and others in the current flows:

**`api-current-state` v3** (41 nodes in flows):
```
blockInputOverrides: false
entity_id: ""
entity_location: "data"
for: "0"
forType: "num"
forUnits: "minutes"
halt_if: ""
halt_if_compare: "is"
halt_if_type: "str"
outputProperties: [
  {"property": "payload", "propertyType": "msg", "value": "", "valueType": "entityState"},
  {"property": "data", "propertyType": "msg", "value": "", "valueType": "entity"}
]
outputs: 1
override_data: "msg"
override_payload: "msg"
override_topic: false
state_location: "payload"
state_type: "str"
version: 3
```

**`api-call-service` v7** (167 nodes):
```
action: ""
areaId: []
blockInputOverrides: false
data: ""
dataType: "jsonata"
debugenabled: false
deviceId: []
domain: ""
entityId: []
floorId: []
labelId: []
mergeContext: ""
mustacheAltTags: false
outputProperties: []
queue: "none"
service: ""
version: 7
```

**`server-state-changed` v6** (49 nodes):
```
entities: {"entity": [], "regex": [], "substring": []}
exposeAsEntityConfig: ""
for: "0"
forType: "num"
forUnits: "minutes"
ifState: ""
ifStateOperator: "is"
ifStateType: "str"
ignoreCurrentStateUnavailable: false
ignoreCurrentStateUnknown: false
ignorePrevStateNull: false
ignorePrevStateUnavailable: false
ignorePrevStateUnknown: false
outputInitially: false
outputOnlyOnStateChange: false
outputProperties: [
  {"property": "payload", "propertyType": "msg", "value": "", "valueType": "entityState"},
  {"property": "data", "propertyType": "msg", "value": "", "valueType": "eventData"},
  {"property": "topic", "propertyType": "msg", "value": "", "valueType": "triggerId"}
]
outputs: 1
stateType: "str"
version: 6
```

**`trigger-state` v5** (1 node):
```
constraints: []
customOutputs: []
debugEnabled: false
enableInput: false
entities: {"entity": [], "regex": [], "substring": []}
exposeAsEntityConfig: ""
inputs: 0
outputInitially: false
outputs: 2
stateType: "str"
version: 5
```

**`poll-state` v3** (3 nodes):
```
entityId: ""
exposeAsEntityConfig: ""
ifState: ""
ifStateOperator: "is"
ifStateType: "str"
outputInitially: false
outputOnChanged: false
outputProperties: [
  {"property": "payload", "propertyType": "msg", "value": "", "valueType": "entityState"},
  {"property": "data", "propertyType": "msg", "value": "", "valueType": "entity"},
  {"property": "topic", "propertyType": "msg", "value": "", "valueType": "triggerId"}
]
outputs: 1
stateType: "str"
updateInterval: "5"
updateIntervalType: "num"
updateIntervalUnits: "minutes"
version: 3
```

## Proposed Solution

**Both approaches: script-level defaults AND doc-level field reference.**

### Approach: Script-level default injection in `modify-nodered-flows.py`

Add a `HA_NODE_DEFAULTS` dict in `modify-nodered-flows.py` that maps `(type, version)`
pairs to a dict of default field values. In `_cmd_add_node`, after building the base
node and before merging props, inject these defaults for recognized HA node types. The
agent's `--props` then override any defaults they want to customize.

The merge order becomes:
1. Base fields (id, type, z, name, x, y, wires)
2. HA defaults for the node type (if recognized)
3. Agent-supplied props (overrides everything)

This means:
- If an agent passes `--props '{"entity_id": "sun.sun", "halt_if": "above_horizon"}'`
  for an `api-current-state`, the node gets all the defaults (`for`, `forType`,
  `forUnits`, `version`, `outputProperties`, etc.) plus the agent's overrides.
- If an agent explicitly passes `"for": "5"`, that overrides the default `"0"`.
- The agent can still pass ALL fields manually (the old way) and nothing changes.
- Unknown/new node types without entries in the defaults dict work exactly as before.

**Version handling:** The defaults dict keys on `(type, version)`. If the agent passes
`version` in props, the script uses that version's defaults. If no `version` in props,
it uses the highest known version for that type. This way agents don't need to remember
to pass `version` -- they get the latest known defaults automatically, and can override
with an older version if needed.

### Approach: Doc-level field reference

Update `docs/modifying-nodered-json.md` to include a concrete reference table of
required fields for common HA node types with their default values. This serves as both
documentation and a fallback for node types not yet in the defaults dict.

## Implementation Steps

### Step 1: Add `HA_NODE_DEFAULTS` to `modify-nodered-flows.py`

In `helper-scripts/modify-nodered-flows.py`, after the existing constants section
(around line 47), add a new dict:

```python
# Default fields for known HA node type versions.
# NOTE: These defaults are injected by _cmd_add_node for recognized HA node types.
# The agent's --props are merged OVER these, so any explicit prop wins.
# If adding a new node type or version, derive defaults from an existing node
# of that type in the flows (query-nodered-flows.sh ... search --type <type>).
HA_NODE_DEFAULTS = {
    ("api-current-state", 3): {
        "version": 3,
        "blockInputOverrides": False,
        "entity_id": "",
        "entity_location": "data",
        "for": "0",
        "forType": "num",
        "forUnits": "minutes",
        "halt_if": "",
        "halt_if_compare": "is",
        "halt_if_type": "str",
        "outputProperties": [
            {"property": "payload", "propertyType": "msg", "value": "", "valueType": "entityState"},
            {"property": "data", "propertyType": "msg", "value": "", "valueType": "entity"},
        ],
        "override_data": "msg",
        "override_payload": "msg",
        "override_topic": False,
        "state_location": "payload",
        "state_type": "str",
    },
    ("api-call-service", 7): {
        "version": 7,
        "action": "",
        "areaId": [],
        "blockInputOverrides": False,
        "data": "",
        "dataType": "jsonata",
        "debugenabled": False,
        "deviceId": [],
        "domain": "",
        "entityId": [],
        "floorId": [],
        "labelId": [],
        "mergeContext": "",
        "mustacheAltTags": False,
        "outputProperties": [],
        "queue": "none",
        "service": "",
    },
    ("server-state-changed", 6): {
        "version": 6,
        "entities": {"entity": [], "regex": [], "substring": []},
        "exposeAsEntityConfig": "",
        "for": "0",
        "forType": "num",
        "forUnits": "minutes",
        "ifState": "",
        "ifStateOperator": "is",
        "ifStateType": "str",
        "ignoreCurrentStateUnavailable": False,
        "ignoreCurrentStateUnknown": False,
        "ignorePrevStateNull": False,
        "ignorePrevStateUnavailable": False,
        "ignorePrevStateUnknown": False,
        "outputInitially": False,
        "outputOnlyOnStateChange": False,
        "outputProperties": [
            {"property": "payload", "propertyType": "msg", "value": "", "valueType": "entityState"},
            {"property": "data", "propertyType": "msg", "value": "", "valueType": "eventData"},
            {"property": "topic", "propertyType": "msg", "value": "", "valueType": "triggerId"},
        ],
        "stateType": "str",
    },
    ("trigger-state", 5): {
        "version": 5,
        "constraints": [],
        "customOutputs": [],
        "debugEnabled": False,
        "enableInput": False,
        "entities": {"entity": [], "regex": [], "substring": []},
        "exposeAsEntityConfig": "",
        "inputs": 0,
        "outputInitially": False,
        "stateType": "str",
    },
    ("poll-state", 3): {
        "version": 3,
        "entityId": "",
        "exposeAsEntityConfig": "",
        "ifState": "",
        "ifStateOperator": "is",
        "ifStateType": "str",
        "outputInitially": False,
        "outputOnChanged": False,
        "outputProperties": [
            {"property": "payload", "propertyType": "msg", "value": "", "valueType": "entityState"},
            {"property": "data", "propertyType": "msg", "value": "", "valueType": "entity"},
            {"property": "topic", "propertyType": "msg", "value": "", "valueType": "triggerId"},
        ],
        "stateType": "str",
        "updateInterval": "5",
        "updateIntervalType": "num",
        "updateIntervalUnits": "minutes",
    },
}

# Index: node_type -> {version: defaults_dict, ...}
# Built once at import time for fast lookup.
_HA_DEFAULTS_BY_TYPE = {}
for (ntype, ver), defaults in HA_NODE_DEFAULTS.items():
    _HA_DEFAULTS_BY_TYPE.setdefault(ntype, {})[ver] = defaults
```

### Step 2: Add a helper to resolve defaults for a node type

```python
def _get_ha_defaults(node_type, props):
    """Get HA default fields for a node type, or empty dict if unknown.

    If props includes 'version', uses that version's defaults.
    Otherwise uses the highest known version for the type.
    """
    versions = _HA_DEFAULTS_BY_TYPE.get(node_type)
    if not versions:
        return {}
    requested_version = props.get("version")
    if requested_version is not None and requested_version in versions:
        return versions[requested_version]
    # Use highest known version
    return versions[max(versions)]
```

### Step 3: Modify `_cmd_add_node` to inject defaults

In `_cmd_add_node` (line 180-249), after building the base `node` dict and auto-setting
the server, but before the `node.update(props)` line (line 225), add:

```python
    # Inject HA node type defaults (agent props will override).
    ha_defaults = _get_ha_defaults(node_type, props)
    if ha_defaults:
        # Apply defaults first, then agent props override.
        for key, value in ha_defaults.items():
            if key not in node:  # Don't override core fields already set
                node[key] = copy.deepcopy(value)  # Deep copy to avoid shared refs
```

Wait -- since `node.update(props)` happens right after, and we want props to override
defaults, we should apply defaults to the node dict BEFORE the props merge. The current
code is:

```python
    node = { "id": ..., "type": ..., "z": ..., "name": ..., ... }
    if group_id: node["g"] = group_id
    if node_type in HA_SERVER_NODE_TYPES: node["server"] = server_id
    node.update(props)  # Agent props override everything
```

We change it to:

```python
    node = { "id": ..., "type": ..., "z": ..., "name": ..., ... }
    if group_id: node["g"] = group_id
    if node_type in HA_SERVER_NODE_TYPES: node["server"] = server_id
    # Inject HA node type defaults before agent props.
    ha_defaults = _get_ha_defaults(node_type, props)
    for key, value in ha_defaults.items():
        if key not in node:
            node[key] = copy.deepcopy(value)
    node.update(props)  # Agent props override defaults
```

This ensures:
1. Core fields (id, type, z, name, x, y, wires, g, server) are set first
2. HA defaults fill in type-specific fields
3. Agent props override anything they explicitly set

### Step 4: Add a `--no-defaults` flag (optional safety valve)

Add `--no-defaults` to `add-node` argparse and batch args. When set, skip the HA
defaults injection. This lets agents opt out if the defaults are wrong for their
use case. Default is to inject defaults (opt-out, not opt-in).

On reflection, this adds complexity for a rare case. Skip this for now -- agents can
always override any default by passing the field in props. If a default value is wrong,
the agent just passes the correct value.

### Step 5: Update `docs/modifying-nodered-json.md`

Update the "Before You Start" section and the `add-node` documentation to reflect that
HA node type defaults are now auto-injected:

1. **"Before You Start"** -- Change the versioned schemas bullet to note that common HA
   node types now get defaults auto-injected, but agents should still query template
   nodes for the correct field VALUES (entity_id, halt_if, domain, etc.). The defaults
   provide safe structural fields; the agent provides the semantic content.

2. **`add-node` Behavior section** -- Update to say:
   - For recognized HA node types (`api-current-state` v3, `api-call-service` v7,
     `server-state-changed` v6, `trigger-state` v5, `poll-state` v3), default fields
     are auto-injected before props are merged.
   - Agent props always override defaults.
   - For unrecognized node types/versions, behavior is unchanged -- agent must provide
     all required fields.

3. **Add a "HA Node Type Defaults Reference" section** at the end listing all known
   types with their default fields and values. This serves as documentation even if the
   auto-injection handles it -- agents can see what they're getting and know which
   fields to override.

4. **Tips section** -- Update the existing tip about version-specific fields to note the
   auto-injection. Keep the advice to query template nodes for reference.

### Step 6: Update the `add-node` output to show when defaults were applied

Modify the output message to indicate when defaults were injected, e.g.:

```
added <id> api-current-state "is sun up?" on=<flow_id> group=<group_id> (defaults: api-current-state v3)
```

This gives agents visibility that defaults were applied, and which version was used.

### Step 7: Handle `outputs` interaction with defaults

The existing code has special handling for `outputs` (line 191-196, 228-231):
- Default is 1 output (or 0 for debug/link-out types)
- If `outputs` is in props, it determines the wires array size

With HA defaults, some types have default `outputs` values (e.g., `trigger-state` v5
defaults to `outputs: 2`). The wires array should match. The current logic already
handles this correctly:

1. Base code sets `outputs = 1` (or 0) and builds `wires` from it
2. If `"outputs"` in props, it uses that value -- props includes HA defaults since
   they're merged in before the check... wait, no. The outputs/wires logic runs BEFORE
   the merge.

Looking more carefully at the code flow:

```python
    # Determine output count (lines 191-196)
    outputs = 1
    if node_type in ZERO_OUTPUT_TYPES: outputs = 0
    if "outputs" in props: outputs = int(props["outputs"])
    wires = [[] for _ in range(outputs)]

    # ... build node with wires ...

    # HA defaults injected here (new code)
    # node.update(props)

    # Ensure wires matches outputs (lines 228-231)
    if "outputs" in props and "wires" not in props:
        needed = int(props["outputs"])
        while len(node["wires"]) < needed: node["wires"].append([])
```

The issue: the outputs check at line 191-196 checks `props` (the agent's props), not
the merged result. If the agent doesn't pass `outputs` but the HA defaults include it,
the wires array won't be sized correctly.

Fix: After injecting HA defaults, re-check if `outputs` changed. Actually, simpler:
merge the HA defaults INTO props before the existing logic runs (rather than into the
node dict). This way the existing outputs logic naturally sees the combined defaults +
agent props.

**Revised approach for Step 3:**

Instead of injecting defaults into the node dict, merge defaults into `props` first,
letting agent values win:

```python
def _cmd_add_node(data, *, node_type, flow_id, name="", group_id=None,
                  props=None, dry_run=False):
    if props is None:
        props = {}

    # Merge HA defaults under agent props (agent wins).
    ha_defaults = _get_ha_defaults(node_type, props)
    if ha_defaults:
        merged_props = copy.deepcopy(ha_defaults)
        merged_props.update(props)
        props = merged_props

    # ... rest of existing logic unchanged ...
```

This is cleaner because ALL the existing logic (outputs, wires, the server auto-set,
the `node.update(props)` call) works naturally with the combined props. The outputs
check on line 195 (`if "outputs" in props`) will correctly see outputs from defaults.

## Testing Strategy

### Unit tests for default injection

1. **Test: `api-current-state` with minimal props gets all defaults**
   ```bash
   bash helper-scripts/modify-nodered-flows.sh mynodered/nodered.json add-node \
     api-current-state --on <flow_id> --name "test" \
     --props '{"entity_id": "sun.sun", "halt_if": "above_horizon"}' --dry-run
   ```
   Then verify the resulting node (use a test copy of the flows) has `for`, `forType`,
   `forUnits`, `version`, etc.

2. **Test: Agent props override defaults**
   Pass `--props '{"for": "5", "forUnits": "seconds"}'` and verify those values win
   over the defaults of `"0"` and `"minutes"`.

3. **Test: `api-call-service` with minimal props gets v7 defaults**
   ```bash
   bash helper-scripts/modify-nodered-flows.sh mynodered/nodered.json add-node \
     api-call-service --on <flow_id> --name "test" \
     --props '{"domain": "light", "service": "turn_on", "action": "light.turn_on"}' \
     --dry-run
   ```
   Verify `version: 7`, `areaId: []`, etc. are present.

4. **Test: Unknown node type has no defaults injected**
   ```bash
   bash helper-scripts/modify-nodered-flows.sh mynodered/nodered.json add-node \
     function --on <flow_id> --name "test" --dry-run
   ```
   Verify only core fields are set (no spurious defaults).

5. **Test: Outputs and wires are correct**
   For `trigger-state` (default outputs: 2), verify that the wires array has 2 ports.
   For `api-current-state` (default outputs: 1), verify wires has 1 port. If agent
   passes `"outputs": 2`, verify 2 ports.

### Integration test

After implementing, recreate the exact scenario that caused the original bug:
create an `api-current-state` node with the same props the agent used in commit
`889c9c5`, and verify the resulting JSON includes `for`, `forType`, and `forUnits`.

### Regression check

Run the dry-run on a few existing batch operations to verify they still produce
the same output (agent-supplied values should still win over defaults).

## Risks & Considerations

1. **Default values could drift from Node-RED's actual defaults.** If a future
   node-red-contrib-home-assistant-websocket update changes default values or adds
   new required fields, our hardcoded defaults will be stale. Mitigation: the defaults
   dict is clearly documented and easy to update. Agents still get told to query
   template nodes, which catches new fields.

2. **Shallow merge means nested objects in defaults are replaced wholesale by props.**
   For example, if defaults have `outputProperties: [{...}, {...}]` and the agent passes
   `outputProperties: [{...}]`, the agent's value replaces the entire array. This is
   the existing behavior and is documented. No change needed.

3. **The `import copy` is already present** (line 14) -- used by cmd_batch's deepcopy.
   The new code uses `copy.deepcopy` for HA defaults, which is fine.

4. **Outputs default mismatch.** Some node types have non-1 default outputs (e.g.,
   `trigger-state` v5 defaults to 2). The revised approach (merging defaults into props
   before the outputs logic) handles this correctly. But if the HA_NODE_DEFAULTS outputs
   value is wrong, nodes could get the wrong number of output ports. Mitigation: the
   defaults are derived from actual production nodes.

5. **Performance is negligible.** The defaults dict is tiny and looked up once per
   add-node call. The deepcopy is on small dicts.

6. **Backward compatibility.** Agents that already pass all required fields will see
   no change -- their props override all defaults. Agents that pass partial props will
   now get correct defaults instead of missing fields. This is strictly better.

# Plan: Cancel Departure Detection on Any Light Switch Press

## Problem Statement

When the front door opens with entrance motion detected (suggesting departure), the occupancy detection system waits for the door to close (up to 2 minutes), then waits 2.5 minutes for motion sensors to clear, then evaluates whether anyone is still home. If the motion sensors don't detect the person during this window (sensor coverage gaps, user is in a dead spot, etc.), the system marks the home as unoccupied and runs `script.turn_off_everything` -- turning off all lights and stopping all media.

The user wants a cancellation mechanism: pressing ANY light switch button in the home during the departure detection window should cancel the pending "becoming unoccupied" logic. The user will fix the sensor coverage issues separately; this task is only about adding the cancellation escape hatch.

## Current State Analysis

### Departure detection flow (Occupancy Detection flow `8ac252f63e58cd8d`, group `41eee6d57596f252`)

The departure path through sensor-based occupancy detection:

1. **Front door opens** -- `server-state-changed` "Front door opens" (`db9df7d6e955dce8`) fires when `binary_sensor.front_door` changes to "on"
2. **Semaphore acquire** -- Semaphore subflow (`7a253225f4d8ae8a`) prevents concurrent detection cycles
3. **Check entrance motion** -- `api-current-state` (`5c508ff4251c8449`) checks `binary_sensor.entrance_motion`. If motion exists (output 1), someone is likely leaving (they walked from inside toward the door). If no motion (output 2), someone is arriving (from outside).
4. **Check auto-detection enabled** -- `api-current-state` (`9488cf3948bd3942`) checks `input_boolean.automatic_occupancy_detection`. If disabled (output 2), skips to semaphore end.
5. **Junction** (`70ca0e02343053fe`) -- fans to disabled notification and the wait node
6. **Wait for door to close** -- `ha-wait-until` (`7763a88923e3a9af`) waits up to 2 minutes for `binary_sensor.front_door` to become "off". Timeout (output 2) sends a notification and releases the semaphore.
7. **Wait 2.5min** -- `delay` (`ad25772d8833bbe9`) pauses 150 seconds for motion sensors to clear
8. **Get active motion sensors** -- `ha-get-entities` (`1292b6b07cc0c381`) queries all motion entities with state=on
9. **Filter unreliable sensors** -- Function (`26915c20606516d0`) removes browsermod and ecobee sensors
10. **Evaluate** -- Switch (`708b3bfb635802ed`) checks if any motion remains. If yes: still occupied. If no: set unoccupied.
11. **Set occupancy** -- Various `set occupancy` subflow instances write the result
12. **Semaphore end** -- Link in (`3a44190bd9701b01`) -> change "clear semaphore" (`e87b4c2f90c3d80b`) -> semaphore subflow (releases lock)

**The critical window is steps 6-7**: up to 4.5 minutes where the system is waiting. A switch press during this time means someone is home and actively using lights, so departure should be cancelled.

### Switch event infrastructure

All Inovelli switches and the Hue remote communicate via ZHA. Every button press fires a `zha_event` on the HA event bus. The existing infrastructure uses `server-events` nodes (type `zha_event`) inside the Inovelli Switch Event subflow (`886281ab0c2f1008`), with one instance per switch.

The 10 light-controlling switches (excluding the 2 entrance switches which control occupancy, not lights):
- bedroom_switch, bedroom_outlet_switch
- kitchen_island_switch, kitchen_ceiling_switch, kitchen_counter_switch
- living_room_outlet_switch
- main_bathroom_switch
- office_switch
- office_hue_remote
- (entrance switches are excluded -- they control occupancy, not lights)

All ZHA events have `msg.payload.event.device_ieee` identifying the device. The Inovelli config registry on the Config flow (`30a523c20e60e17d`) maps switch names to IEEE addresses.

### Semaphore behavior

The semaphore (`cd08b3ef64156323`) is a state machine with states: cleared, set, blocked. Sending `msg.semaphore = "clear"` transitions from any state to "cleared" -- so clearing an already-cleared semaphore is safe (idempotent).

## Proposed Solution

Add a new group on the Occupancy Detection flow that listens for any `zha_event` and cancels the in-progress departure detection. The design uses a **flow context variable** (`departure_detection_active`) as a gate, with **checkpoint nodes** inserted into the existing departure path to catch and divert in-flight messages after cancellation.

### Why this approach

- **Flow variable + checkpoints** is simpler and more robust than trying to externally reset `ha-wait-until` nodes (which don't support reset) or directly wiring into mid-chain delay nodes.
- The semaphore remains the authoritative concurrency control -- we don't bypass it.
- Cancelled messages that are still in-flight (stuck in a wait or delay) are harmlessly caught at checkpoints and diverted to semaphore end.
- Double-releasing the semaphore is safe due to the state machine's idempotent clear transition.

### How cancellation works, step by step

1. When departure detection enters the "might be leaving" path (after junction `70ca0e02343053fe`), a new change node sets `flow.departure_detection_active = true`.
2. A new `server-events` node listens for ALL `zha_event` events. A function node checks `flow.departure_detection_active` -- if false, drops the message. If true, it also checks the event's `device_ieee` against the Inovelli config to confirm it's from any registered switch (excluding entrance switches, since those have their own occupancy semantics). If it matches, it sets `flow.departure_detection_active = false` and passes the message.
3. The cancellation path then: (a) sets `msg.payload = true` and calls `set occupancy` with details "switch press cancelled departure detection" and source "sensors", (b) routes to Semaphore End to release the lock.
4. Checkpoint nodes are inserted after `ha-wait-until` (output 1, door closed) and after `delay` to test `flow.departure_detection_active`. If false (cancelled), they divert to Semaphore End.
5. At Semaphore End, the existing "clear semaphore" change node (`e87b4c2f90c3d80b`) is updated to also set `flow.departure_detection_active = false`.

### Edge case: person presses a switch and then actually leaves

This is acceptable behavior. If someone presses a switch (cancelling departure detection) and then leaves, the system will not auto-detect the departure from this door-open event. However:
- The *next* door-open event will trigger a fresh departure detection cycle.
- The user can manually mark as unoccupied via the entrance switch aux button (single press) or the dashboard.
- This is a conscious trade-off: false negatives (staying occupied when nobody's home) are far less annoying than false positives (turning off all lights while someone is home).

### Edge case: entrance switch presses

Entrance switch presses are explicitly excluded from cancellation triggers. The entrance switches have their own occupancy semantics (aux single = leaving, aux double = arriving, etc.) and those actions are handled by the existing "Handle front door pushbutton / aux button" group (`c81124976d600281`). Including them would create confusing interactions -- e.g., someone pressing the entrance aux button to say "I'm leaving" would paradoxically cancel the departure detection.

### Edge case: front door pushbutton

The front door pushbutton is not a ZHA device -- it communicates via `nodered.command` events, not `zha_event`. It is not included in the cancellation triggers. This is fine because the front door pushbutton only toggles christmas lights, which is not a strong signal of presence.

## Implementation Steps

All changes are on the Occupancy Detection flow (`8ac252f63e58cd8d`).

### Step 1: Add "set departure active" change node on the departure path

Insert a change node between junction `70ca0e02343053fe` and `ha-wait-until` `7763a88923e3a9af` that sets `flow.departure_detection_active` to `true`.

**Operations:**
1. `add-node` change node "set departure active" on flow `8ac252f63e58cd8d`, group `41eee6d57596f252`, with rules to set `flow.departure_detection_active` = `true` (boolean)
2. `unwire` junction `70ca0e02343053fe` from `7763a88923e3a9af`
3. `wire` junction `70ca0e02343053fe` to new change node
4. `wire` new change node to `7763a88923e3a9af`

### Step 2: Clear departure flag at semaphore end

Update the existing "clear semaphore" change node (`e87b4c2f90c3d80b`) to also set `flow.departure_detection_active` = `false`.

**Operations:**
1. `update-node` `e87b4c2f90c3d80b` -- add a rule to set `flow.departure_detection_active` to `false` (boolean). Must pass the full `rules` array including the existing `msg.semaphore = "clear"` rule plus the new rule.

### Step 3: Add checkpoint after ha-wait-until (door closed path)

Insert a switch node between `ha-wait-until` output 1 (`7763a88923e3a9af`) and delay `ad25772d8833bbe9` that checks `flow.departure_detection_active`. If true, continues to delay. If false (cancelled), routes to Semaphore End.

**Operations:**
1. `add-node` switch node "departure still active?" on flow `8ac252f63e58cd8d`, group `41eee6d57596f252`, with 2 rules:
   - Rule 1: `flow.departure_detection_active` is true -> output 1 (continue)
   - Rule 2: otherwise -> output 2 (cancelled)
   Props: `{"property": "departure_detection_active", "propertyType": "flow", "outputs": 2, "rules": [{"t": "true"}, {"t": "else"}]}`
2. `add-node` link out "link out cancel-1" on flow `8ac252f63e58cd8d`, group `41eee6d57596f252` (mode=link, connects to Semaphore End)
3. `unwire` `7763a88923e3a9af` from `ad25772d8833bbe9`
4. `wire` `7763a88923e3a9af` to switch node (output 0)
5. `wire` switch node output 0 to `ad25772d8833bbe9`
6. `wire` switch node output 1 to link out node
7. `link` link out node to `3a44190bd9701b01` (Semaphore End link in)

### Step 4: Add checkpoint after delay

Insert a switch node between delay `ad25772d8833bbe9` and `ha-get-entities` `1292b6b07cc0c381` that checks `flow.departure_detection_active`. Same pattern as step 3.

**Operations:**
1. `add-node` switch node "departure still active?" on flow `8ac252f63e58cd8d`, group `41eee6d57596f252`, same props as step 3
2. `add-node` link out "link out cancel-2" on flow `8ac252f63e58cd8d`, group `41eee6d57596f252`
3. `unwire` `ad25772d8833bbe9` from `1292b6b07cc0c381`
4. `wire` `ad25772d8833bbe9` to switch node output 0
5. `wire` switch node output 0 to `1292b6b07cc0c381`
6. `wire` switch node output 1 to link out node
7. `link` link out node to `3a44190bd9701b01`

### Step 5: Add "Cancel departure on switch press" group

Create a new group on the Occupancy Detection flow with nodes that listen for any ZHA switch event and cancel active departure detection.

**Nodes needed:**

1. **`server-events` "Any switch press"** -- Listens for `zha_event`. Same config as the one inside the Inovelli Switch Event subflow (`079484cc748525fc`) but placed directly on the flow rather than in a subflow instance, since we want to catch events from ALL switches in a single listener.
   - `eventType`: `"zha_event"`
   - Standard output properties (payload = eventData, topic = event_type)

2. **`link call` "get switch config"** -- Calls the Inovelli config link-in (`4e61895429d01613`) on the Config flow to get the switch registry. This is the same pattern used by every Inovelli Switch Event subflow instance.

3. **`function` "if departure active and non-entrance switch"** -- The core logic function:
   ```javascript
   // Check if departure detection is active
   const active = flow.get('departure_detection_active');
   if (!active) return null;

   // Check if this event is from a registered switch (but not entrance switches)
   const config = msg.inovelli_config;
   if (!config || !config.switches) return null;

   const ieee = msg.payload?.event?.device_ieee;
   if (!ieee) return null;

   // Check all switches except entrance switches
   const exclude = ['entrance_switch', 'entrance_switch_slave'];
   for (const [name, sw] of Object.entries(config.switches)) {
       if (exclude.includes(name)) continue;
       if (sw.ieee === ieee) {
           flow.set('departure_detection_active', false);
           node.warn(`Departure detection cancelled by ${sw.label} press`);
           return msg;
       }
   }

   return null;
   ```

4. **`change` "occupied = true"** -- Sets `msg.payload = true`

5. **`subflow:a2d7acf593fe2434` "set occupancy"** -- A `set occupancy` subflow instance with env vars:
   - `OCCUPANCY_DETAILS`: `"switch press cancelled departure detection"`
   - `OCCUPANCY_SOURCE`: `"sensors"` (keeping source as sensors since this is part of the sensor-based detection system)
   - `UPDATE_OCCUPANCY`: `true`

6. **`link out` to Semaphore End** -- Routes to Semaphore End (`3a44190bd9701b01`) to release the lock

**Wiring:**
- server-events -> link call -> function -> change -> set occupancy -> link out -> Semaphore End

**Operations (as batch):**
1. `add-group` "Cancel departure detection on switch press" on flow `8ac252f63e58cd8d`
2. `add-node` server-events with zha_event config, in group
3. `add-node` link call, in group
4. `add-node` function "if departure active and non-entrance switch", in group
5. `add-node` change "occupied = true", in group, with rule setting `msg.payload = true`
6. `add-node` subflow:a2d7acf593fe2434, in group, with env vars for occupancy details/source
7. `add-node` link out, in group
8. Wire: server-events -> link call -> function -> change -> set occupancy (output 1, success) -> link out
9. Link: link call to inovelli config link-in (`4e61895429d01613`)
10. Link: link out to Semaphore End (`3a44190bd9701b01`)

Note: The set occupancy subflow has 2 outputs (success and timeout). Only output 1 (success) is wired to the link out. Output 2 (timeout) is left unwired -- if the occupancy write times out, the semaphore will eventually be released by the next detection cycle or by the in-flight message reaching a checkpoint.

### Step 6: Set function code

Use `set-function` to set the JavaScript body for the function node created in step 5.

### Step 7: Verify changes

Run `bash helper-scripts/summarize-nodered-flows-diff.sh --git mynodered/nodered.json` to verify all changes are correct and identify documentation that needs updating.

### Step 8: Update documentation

Based on the diff summary's AFFECTED DOCUMENTATION section, update:
- `mynodered/docs/flows/8ac252f63e58cd8d.md` (Occupancy Detection flow) -- add the new group, document the cancellation mechanism, update the sensor-based detection group description
- `mynodered/docs/occupancy.md` -- add section on departure cancellation via switch press
- `mynodered/CLAUDE.md` -- update the Occupancy Detection flow summary paragraph
- Any other docs referenced by changed node IDs

## Implementation Detail: Batch Operations

The implementation should be done as two batches:

**Batch 1: Modify existing sensor-based detection group (Steps 1-4)**

```json
[
  // Step 1: Add "set departure active" node
  {"command": "add-node", "args": {"type": "change", "on": "8ac252f63e58cd8d",
    "group": "41eee6d57596f252", "name": "set departure active",
    "props": {"rules": [{"t": "set", "p": "departure_detection_active", "pt": "flow", "to": "true", "tot": "bool"}]}}},
  {"command": "unwire", "args": {"source": "70ca0e02343053fe", "target": "7763a88923e3a9af"}},
  {"command": "wire", "args": {"source": "70ca0e02343053fe", "target": "$0"}},
  {"command": "wire", "args": {"source": "$0", "target": "7763a88923e3a9af"}},

  // Step 2: Update clear semaphore to also clear departure flag
  {"command": "update-node", "args": {"node_id": "e87b4c2f90c3d80b",
    "props": {"rules": [
      {"t": "set", "p": "semaphore", "pt": "msg", "to": "clear", "tot": "str"},
      {"t": "set", "p": "departure_detection_active", "pt": "flow", "to": "false", "tot": "bool"}
    ]}}},

  // Step 3: Add checkpoint after ha-wait-until
  {"command": "add-node", "args": {"type": "switch", "on": "8ac252f63e58cd8d",
    "group": "41eee6d57596f252", "name": "departure still active?",
    "props": {"property": "departure_detection_active", "propertyType": "flow",
      "outputs": 2, "checkall": "true",
      "rules": [{"t": "true"}, {"t": "else"}]}}},
  {"command": "add-node", "args": {"type": "link out", "on": "8ac252f63e58cd8d",
    "group": "41eee6d57596f252", "name": "cancelled-1",
    "props": {"mode": "link"}}},
  {"command": "unwire", "args": {"source": "7763a88923e3a9af", "target": "ad25772d8833bbe9"}},
  {"command": "wire", "args": {"source": "7763a88923e3a9af", "target": "$1"}},
  {"command": "wire", "args": {"source": "$1", "target": "ad25772d8833bbe9", "port": 0}},
  {"command": "wire", "args": {"source": "$1", "target": "$2", "port": 1}},
  {"command": "link", "args": {"source": "$2", "target": "3a44190bd9701b01"}},

  // Step 4: Add checkpoint after delay
  {"command": "add-node", "args": {"type": "switch", "on": "8ac252f63e58cd8d",
    "group": "41eee6d57596f252", "name": "departure still active?",
    "props": {"property": "departure_detection_active", "propertyType": "flow",
      "outputs": 2, "checkall": "true",
      "rules": [{"t": "true"}, {"t": "else"}]}}},
  {"command": "add-node", "args": {"type": "link out", "on": "8ac252f63e58cd8d",
    "group": "41eee6d57596f252", "name": "cancelled-2",
    "props": {"mode": "link"}}},
  {"command": "unwire", "args": {"source": "ad25772d8833bbe9", "target": "1292b6b07cc0c381"}},
  {"command": "wire", "args": {"source": "ad25772d8833bbe9", "target": "$3"}},
  {"command": "wire", "args": {"source": "$3", "target": "1292b6b07cc0c381", "port": 0}},
  {"command": "wire", "args": {"source": "$3", "target": "$4", "port": 1}},
  {"command": "link", "args": {"source": "$4", "target": "3a44190bd9701b01"}}
]
```

**Batch 2: Add new cancellation group (Step 5)**

```json
[
  {"command": "add-group", "args": {"on": "8ac252f63e58cd8d",
    "name": "Cancel departure detection on switch press"}},
  {"command": "add-node", "args": {"type": "server-events", "on": "8ac252f63e58cd8d",
    "group": "$0", "name": "Any ZHA event",
    "props": {"eventType": "zha_event", "waitForRunning": true,
      "outputProperties": [
        {"property": "payload", "propertyType": "msg", "value": "", "valueType": "eventData"},
        {"property": "topic", "propertyType": "msg", "value": "$outputData(\"eventData\").event_type", "valueType": "jsonata"}
      ]}}},
  {"command": "add-node", "args": {"type": "link call", "on": "8ac252f63e58cd8d",
    "group": "$0", "name": "get switch config",
    "props": {"timeout": "30"}}},
  {"command": "add-node", "args": {"type": "function", "on": "8ac252f63e58cd8d",
    "group": "$0", "name": "if departure active and non-entrance switch",
    "props": {"outputs": 1}}},
  {"command": "add-node", "args": {"type": "change", "on": "8ac252f63e58cd8d",
    "group": "$0", "name": "occupied = true",
    "props": {"rules": [{"t": "set", "p": "payload", "pt": "msg", "to": "true", "tot": "bool"}]}}},
  {"command": "add-node", "args": {"type": "subflow:a2d7acf593fe2434", "on": "8ac252f63e58cd8d",
    "group": "$0", "name": "set occupancy: switch cancelled departure",
    "props": {"env": [
      {"name": "OCCUPANCY_DETAILS", "type": "str", "value": "switch press cancelled departure detection"},
      {"name": "OCCUPANCY_SOURCE", "type": "str", "value": "sensors"},
      {"name": "UPDATE_OCCUPANCY", "type": "bool", "value": "true"}
    ]}}},
  {"command": "add-node", "args": {"type": "link out", "on": "8ac252f63e58cd8d",
    "group": "$0", "name": "to semaphore end",
    "props": {"mode": "link"}}},
  {"command": "wire", "args": {"source": "$1", "target": "$2"}},
  {"command": "wire", "args": {"source": "$2", "target": "$3"}},
  {"command": "wire", "args": {"source": "$3", "target": "$4"}},
  {"command": "wire", "args": {"source": "$4", "target": "$5"}},
  {"command": "wire", "args": {"source": "$5", "target": "$6"}},
  {"command": "link", "args": {"source": "$2", "target": "4e61895429d01613"}},
  {"command": "link", "args": {"source": "$6", "target": "3a44190bd9701b01"}}
]
```

**Step 6: Set function code** (separate command after batch 2 to use the generated node ID)

## Testing Strategy

1. **Verify with diff summary**: Run `bash helper-scripts/summarize-nodered-flows-diff.sh --git mynodered/nodered.json` and review all changes.

2. **Functional test after deploy**:
   - Open the front door (trigger `binary_sensor.front_door` = on) while inside (entrance motion detected)
   - Wait a few seconds, then press any light switch (e.g., bedroom switch up)
   - Verify: lights should NOT turn off, occupancy should remain true, logbook should show "switch press cancelled departure detection"
   - Verify: the semaphore is released (open the door again and confirm detection runs normally)

3. **Normal departure still works**:
   - Open the front door while inside, actually leave (don't press any switches)
   - Verify: after the 2+2.5 min wait, occupancy is evaluated normally

4. **Edge case -- entrance switch press during detection**:
   - Open the front door, then press the entrance switch aux button
   - Verify: the entrance switch action runs its own occupancy logic (e.g., aux single press = set unoccupied), and departure detection is NOT cancelled by the entrance switch press (only non-entrance switches cancel it)

5. **Edge case -- auto-detection disabled**:
   - Disable automatic occupancy detection, open front door
   - Verify: no departure detection runs (the flow exits before setting the departure_detection_active flag)

## Risks & Considerations

1. **Performance of the ZHA event listener**: The new `server-events` node for `zha_event` will fire on EVERY ZHA event in the home, not just switches. This includes sensor updates, device heartbeats, etc. However, the function node immediately drops messages when `departure_detection_active` is false (which is the vast majority of the time), so the performance impact is negligible. This is the same pattern already used by all 13 Inovelli Switch Event subflow instances.

2. **Link call to config on every ZHA event**: The link call to get the Inovelli config is made for every ZHA event that arrives while departure detection is active. This is at most ~4.5 minutes per departure cycle. The config call is lightweight (just a change node returning a JSON object). To minimize unnecessary calls, the function node checks `departure_detection_active` first, and the link call is only reached after the server-events node fires. If this becomes a concern, the flow could be optimized by moving the departure-active check before the link call (using a switch node on the flow variable instead of checking in the function), but this is premature optimization.

   **Optimization note**: Actually, looking at this more carefully, the link call happens for EVERY zha_event while departure is active, not just switch presses. A better ordering would be: server-events -> switch node checking flow.departure_detection_active -> link call -> function. This way, the link call only fires during the ~4.5 minute window, not on every ZHA event all the time. I'll implement it this way.

3. **Race condition: switch press arrives just as occupancy is being set**: If a switch press cancels departure while the in-flight message is at the motion sensor check, both paths may try to set occupancy. The set occupancy subflow uses a semaphore internally, so concurrent writes are serialized. Both writes would set occupied=true (the cancellation sets it explicitly, and the in-flight message would see motion from the switch user), so the end state is correct.

4. **The departure_detection_active variable persists across Node-RED restarts**: Flow context variables are not persistent by default in Node-RED (they reset to undefined on restart). This is fine -- on restart, the variable will be undefined/falsy, so the cancellation listener won't fire. Any in-progress departure detection would also be lost on restart, so the checkpoint nodes would see undefined (falsy) and divert to semaphore end, which is the correct safe behavior.

5. **Adding nodes to existing group `41eee6d57596f252`**: Steps 1-4 add nodes to the existing sensor-based detection group. This is appropriate since these are modifications to the existing detection logic. Step 5 creates a separate group for the cancellation listener, keeping it visually distinct.

## Revised Batch 2 (with optimization from Risk #2)

Move the departure-active check before the link call to avoid unnecessary config lookups:

```json
[
  {"command": "add-group", "args": {"on": "8ac252f63e58cd8d",
    "name": "Cancel departure detection on switch press"}},
  {"command": "add-node", "args": {"type": "server-events", "on": "8ac252f63e58cd8d",
    "group": "$0", "name": "Any ZHA event",
    "props": {"eventType": "zha_event", "waitForRunning": true,
      "outputProperties": [
        {"property": "payload", "propertyType": "msg", "value": "", "valueType": "eventData"},
        {"property": "topic", "propertyType": "msg", "value": "$outputData(\"eventData\").event_type", "valueType": "jsonata"}
      ]}}},
  {"command": "add-node", "args": {"type": "switch", "on": "8ac252f63e58cd8d",
    "group": "$0", "name": "departure detection active?",
    "props": {"property": "departure_detection_active", "propertyType": "flow",
      "outputs": 1, "checkall": "true",
      "rules": [{"t": "true"}]}}},
  {"command": "add-node", "args": {"type": "link call", "on": "8ac252f63e58cd8d",
    "group": "$0", "name": "get switch config",
    "props": {"timeout": "30"}}},
  {"command": "add-node", "args": {"type": "function", "on": "8ac252f63e58cd8d",
    "group": "$0", "name": "if non-entrance switch",
    "props": {"outputs": 1}}},
  {"command": "add-node", "args": {"type": "change", "on": "8ac252f63e58cd8d",
    "group": "$0", "name": "occupied = true",
    "props": {"rules": [{"t": "set", "p": "payload", "pt": "msg", "to": "true", "tot": "bool"}]}}},
  {"command": "add-node", "args": {"type": "subflow:a2d7acf593fe2434", "on": "8ac252f63e58cd8d",
    "group": "$0", "name": "set occupancy: switch cancelled departure",
    "props": {"env": [
      {"name": "OCCUPANCY_DETAILS", "type": "str", "value": "switch press cancelled departure detection"},
      {"name": "OCCUPANCY_SOURCE", "type": "str", "value": "sensors"},
      {"name": "UPDATE_OCCUPANCY", "type": "bool", "value": "true"}
    ]}}},
  {"command": "add-node", "args": {"type": "link out", "on": "8ac252f63e58cd8d",
    "group": "$0", "name": "to semaphore end",
    "props": {"mode": "link"}}},
  {"command": "wire", "args": {"source": "$1", "target": "$2"}},
  {"command": "wire", "args": {"source": "$2", "target": "$3"}},
  {"command": "wire", "args": {"source": "$3", "target": "$4"}},
  {"command": "wire", "args": {"source": "$4", "target": "$5"}},
  {"command": "wire", "args": {"source": "$5", "target": "$6"}},
  {"command": "wire", "args": {"source": "$6", "target": "$7"}},
  {"command": "link", "args": {"source": "$3", "target": "4e61895429d01613"}},
  {"command": "link", "args": {"source": "$7", "target": "3a44190bd9701b01"}}
]
```

**Updated function code** (node $4, "if non-entrance switch"):
```javascript
const config = msg.inovelli_config;
if (!config || !config.switches) return null;

const ieee = msg.payload?.event?.device_ieee;
if (!ieee) return null;

// NOTE: entrance switches are excluded because they have their own
// occupancy semantics in the "Handle front door pushbutton / aux button"
// group (c81124976d600281). Including them would conflict with those actions.
const exclude = ['entrance_switch', 'entrance_switch_slave'];
for (const [name, sw] of Object.entries(config.switches)) {
    if (exclude.includes(name)) continue;
    if (sw.ieee === ieee) {
        flow.set('departure_detection_active', false);
        node.warn(`Departure detection cancelled by ${sw.label} press`);
        return msg;
    }
}

return null;
```

This revised version ensures the link call (config lookup) only happens during the active departure detection window, not on every ZHA event. The switch node acts as a cheap gate using the flow variable before doing any work.

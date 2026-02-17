# Plan: Flow Layout Analysis for Automated Relayout Tool

## Problem Statement

The user hand-lays-out their Node-RED flows with great care. Before building an automated relayout tool, we need to deeply understand the layout patterns and best practices visible in their best-looking flows. This analysis examines four flows -- Bedtime, Tablets, Switches, and Vacation Mode -- to extract precise numeric layout rules.

## How Node-RED Coordinates Work

In Node-RED, every node has `x` and `y` coordinates representing its center point. Nodes also have implicit widths based on their type and label text (typically ~120-200px wide, ~30px tall). Group nodes have explicit `x`, `y`, `w`, `h` properties defining their bounding box. The `x`/`y` on a group is its top-left corner.

---

## Flow 1: Bedtime (id=30ef4572600b70c4)

### Group Layout Summary

| Group | x | y | w | h | Nodes |
|-------|-----|------|------|-----|-------|
| When bedtime begins | 74 | 19 | 1232 | 202 | 11 |
| When coming home past bedtime | 74 | 231.5 | 1132 | 189.5 | 8 |
| 30 minute heads up | 74 | 439 | 632 | 142 | 4 |
| Daily reset and confirmation | 34 | 599 | 1132 | 282 | 11 |
| Is wind down enabled? | 64 | 899 | 1102 | 82 | 7 |
| Update bedtime settings from UI | 54 | 999 | 712 | 222 | 5 |
| When vacation mode turns on | 54 | 1239 | 1032 | 142 | 4 |
| Implement Siri Good Night | 54 | 1399 | 832 | 262 | 9 |
| Implement Siri Stop Good Night | 54 | 1679 | 592 | 142 | 3 |
| If home becomes unoccupied | 54 | 1851.5 | 552 | 97 | 2 |

### Inter-group Spacing (Bedtime)

Groups are stacked **vertically** with the following gaps between bottom of one and top of next:

| From -> To | Gap (pixels) |
|-----------|-------------|
| When bedtime begins (y=19, h=202, bottom=221) -> When coming home (y=231.5) | **10.5** |
| When coming home (bottom=421) -> 30 min heads up (y=439) | **18** |
| 30 min heads up (bottom=581) -> Daily reset (y=599) | **18** |
| Daily reset (bottom=881) -> Is wind down (y=899) | **18** |
| Is wind down (bottom=981) -> Update bedtime settings (y=999) | **18** |
| Update bedtime settings (bottom=1221) -> When vacation mode (y=1239) | **18** |
| When vacation mode (bottom=1381) -> Implement Siri Good Night (y=1399) | **18** |
| Implement Siri Good Night (bottom=1661) -> Stop Good Night (y=1679) | **18** |
| Stop Good Night (bottom=1821) -> If home unoccupied (y=1851.5) | **30.5** |

**Pattern**: Nearly all inter-group gaps are exactly **18px**. This appears to be a deliberate standard. The first gap (10.5) and last gap (30.5) are slight deviations.

### Group Left-edge Alignment (Bedtime)

Groups are left-aligned but not perfectly -- left edges (x values) are: 74, 74, 74, 34, 64, 54, 54, 54, 54, 54.

- Some groups start at x=74 (the first three)
- Most of the remaining start at x=54
- One starts at x=34, one at x=64

The typical left margin is **~54-74px**. This suggests the user approximately left-aligns groups but doesn't enforce a single pixel-perfect x value.

### Intra-group Analysis: "30 minute heads up" (4 nodes, 632w x 142h)

**Group box**: x=74, y=439, w=632, h=142

| Node | Type | x | y |
|------|------|-----|-----|
| ha-time "when it's almost bedtime" | ha-time | 210 | 480 |
| inject "test heads up" | inject | 230 | 540 |
| link call | link call | 430 | 480 |
| api-call-service (notify) | api-call-service | 610 | 480 |

**Layout pattern**: Left-to-right flow at y=480 for the main chain (ha-time -> link call -> api-call-service). The test inject sits below at y=540, offset +60px vertically. Both entry nodes (ha-time and inject) feed into the link call.

**Horizontal spacing**:
- ha-time (x=210) -> link call (x=430): gap = **220px**
- link call (x=430) -> api-call-service (x=610): gap = **180px**

**Node-to-group-edge padding**:
- Left padding: node x=210 minus group left (x=74) = **136px** (from group edge to node center)
- Right padding: group right (74+632=706) minus rightmost node (x=610) = **96px** (from node center to group edge)
- Top padding: node y=480 minus group top (y=439) = **41px**
- Bottom padding: group bottom (439+142=581) minus lowest node (y=540) = **41px**

### Intra-group Analysis: "Is wind down enabled?" (7 nodes, 1102w x 82h)

**Group box**: x=64, y=899, w=1102, h=82

| Node | Type | x | y |
|------|------|-----|-----|
| link in "is enabled" | link in | 105 | 940 |
| api-current-state "is bedtime enabled?" | api-current-state | 260 | 940 |
| api-current-state "is Drew home?" | api-current-state | 480 | 940 |
| junction | junction | 620 | 940 |
| subflow "is home occupied?" | subflow | 730 | 940 |
| api-current-state "is bedroom door open?" | api-current-state | 970 | 940 |
| link out (return) | link out | 1125 | 940 |

**Layout pattern**: A perfectly horizontal chain -- ALL nodes at y=940. This is a "pipeline" or "guard chain" pattern where each node checks a condition and passes to the next.

**Horizontal spacing** (center-to-center):
- link in (105) -> api-current-state (260): **155px**
- api-current-state (260) -> api-current-state (480): **220px**
- api-current-state (480) -> junction (620): **140px**
- junction (620) -> subflow (730): **110px**
- subflow (730) -> api-current-state (970): **240px**
- api-current-state (970) -> link out (1125): **155px**

Average horizontal spacing: ~170px, but with significant variation (110-240). This suggests spacing is partly determined by node label width.

**Top/bottom padding**: All nodes at y=940, group y=899 to y+h=981. Vertical center of group = 940. **Nodes are vertically centered in the group.**

### Intra-group Analysis: "When bedtime begins" (11 nodes, 1232w x 202h)

**Group box**: x=74, y=19, w=1232, h=202

| Node | Type | x | y |
|------|------|-----|-----|
| ha-time "when it's bedtime" | ha-time | 190 | 80 |
| inject "simulate bedtime time" | inject | 220 | 140 |
| inject "force test" | inject | 380 | 180 |
| link call | link call | 410 | 80 |
| junction | junction | 480 | 120 |
| api-get-history "toothbrush..." | api-get-history | 670 | 120 |
| api-call-service (alarm start) | api-call-service | 640 | 160 |
| debug "raw toothbrush history" | debug | 940 | 60 |
| function "was toothbrush used..." | function | 1010 | 120 |
| api-call-service (good teeth) | api-call-service | 1210 | 60 |
| api-call-service (brush teeth) | api-call-service | 1210 | 180 |

**Layout pattern**: Left-to-right with vertical branching. The main flow goes ha-time -> link call -> junction -> splits to: (1) api-get-history -> function -> two branch outputs, and (2) api-call-service (alarm start). The function outputs fan vertically: output 1 (yes, brushed) goes to y=60, output 2 (no) goes to y=180.

**Branching pattern**: When a node has 2 outputs, downstream nodes are positioned:
- Output 1 (top): same y or above current node
- Output 2 (bottom): below current node
- The vertical spread from the function (y=120) to outputs is **-60px** (up to y=60) and **+60px** (down to y=180)

**Test inject positions**: Test nodes (inject "simulate" at x=220,y=140 and inject "force test" at x=380,y=180) sit below the main flow line (y=80), offset by +60px and +100px respectively. They connect to the main chain but don't interfere visually with the primary flow path.

### Intra-group Analysis: "Daily reset and confirmation" (11 nodes, 1132w x 282h)

**Group box**: x=34, y=599, w=1132, h=282

Main chain at varying y values:
- ha-time (170, 640) -> api-current-state (420, 640) [vacation check, output2 passes] -> api-current-state (410, 720) [bedtime check, output1 passes] -> junction (420, 780) -> api-call-service "enable bedtime" (520, 780) -> api-call-service "set bedtime" (690, 840) -> function "construct notification" (860, 740) -> api-call-service "notify" (1070, 740)

**The chain descends diagonally** as it progresses left-to-right: starting at y=640, dipping to y=840, then coming back up to y=740. This is because conditional checks create a staircase pattern where "pass" outputs route further down.

Secondary entry points:
- server-state-changed "Vacation Mode Turned Off" at (170, 780)
- inject "test reset" at (320, 820)
- inject "test notify" at (660, 720) -- connects directly to the function node mid-chain

**Pattern**: Multiple entry points (time trigger, state trigger, test inject) converge at different points in the chain. Test injects connect at the point in the chain they're meant to test -- "test reset" connects to the junction before the reset actions, "test notify" connects to the function that constructs the notification.

### Intra-group Analysis: "Implement Siri Good Night shortcut" (9 nodes, 832w x 262h)

**Group box**: x=54, y=1399, w=832, h=262

| Node | Type | x | y |
|------|------|-----|-----|
| server-events "Good Night" | server-events | 180 | 1500 |
| subflow "Go To Sleep" tablet | subflow | 210 | 1560 |
| junction | junction | 400 | 1500 |
| api-call-service (turn off everything) | api-call-service | 590 | 1440 |
| api-call-service (alarm stop) | api-call-service | 600 | 1500 |
| delay | delay | 540 | 1560 |
| change "turn thinksmart3 off" | change | 600 | 1620 |
| api-call-service (sleep sounds) | api-call-service | 750 | 1560 |
| link out "Turn tablet on/off" | link out | 775 | 1620 |

**Layout pattern**: Two source nodes merge into a junction, then fan out to 4 parallel actions. The junction's 4 outputs go to nodes at y=1440, 1500, 1560, 1620 -- evenly spaced at **60px** vertical intervals. This is a classic "fan-out" pattern.

**Fan-out vertical spacing**: **60px** between each branch

### Intra-group Analysis: "When coming home past bedtime" (8 nodes, 1132w x 189.5h)

**Group box**: x=74, y=231.5, w=1132, h=189.5

| Node | Type | x | y |
|------|------|-----|-----|
| subflow occupancy changed | subflow | 190 | 280 |
| inject "simulate coming home" | inject | 240 | 340 |
| junction | junction | 400 | 280 |
| function "is it recently past bedtime?" | function | 540 | 280 |
| link call | link call | 770 | 280 |
| api-call-service (notify) | api-call-service | 510 | 360 |
| function "get time 10min from now" | function | 750 | 380 |
| api-call-service "snooze alarm" | api-call-service | 1050 | 360 |

**Pattern**: Main chain at y=280, with a secondary branch dropping to y=360/380. The function "is it recently past bedtime?" has two outputs: output 1 (yes) continues at y=280 via link call, then the link call returns and feeds a notify at y=360 -> function -> service call. The inject test sits below the main line at y=340.

### Bedtime Flow Synthesis

1. **Groups are vertically stacked** with ~18px gaps
2. **Groups are roughly left-aligned** at x~54-74
3. **Main flow direction is left-to-right** (LR layout)
4. **All nodes in a linear chain share the same y** coordinate
5. **Branch outputs fan vertically** with ~60px spacing per branch
6. **Test inject nodes sit below** the main flow line, offset +60px
7. **Guard chains** (multiple sequential checks) are perfectly horizontal at one y level
8. **Conditional branches** route pass/fail outputs to different y levels
9. **Node-to-group-edge padding**: ~40px top/bottom, ~100-140px left (to node center), ~90-100px right

---

## Flow 2: Vacation Mode (id=befc63f6568616bb)

### Group Layout Summary

| Group | x | y | w | h | Nodes |
|-------|-----|------|------|-----|-------|
| Automate or suggest vacation mode | 14 | 19 | 2052 | 442 | 17 |
| Prompt to disable vacation mode | 34 | 484 | 972 | 112 | 4 |
| Handle push notification responses | 34 | 619 | 972 | 162 | 8 |

### Inter-group Spacing (Vacation Mode)

| From -> To | Gap |
|-----------|-----|
| Automate (bottom=461) -> Prompt (y=484) | **23** |
| Prompt (bottom=596) -> Handle (y=619) | **23** |

**Pattern**: Consistent **23px** gap between groups. Slightly larger than Bedtime's 18px.

### Group Alignment

All groups are left-aligned at x=14 or x=34. The first group starts at x=14 (further left); the bottom two at x=34.

### Intra-group Analysis: "Automate or suggest vacation mode" (17 nodes, 2052w x 442h)

**Group box**: x=14, y=19, w=2052, h=442

This is the largest group -- a complex multi-stage pipeline:

**Main horizontal chain (y=60)**:
- poll-state (130, 60) -> junction (520, 60) -> api-current-state "get vacation mode" (630, 60) -> api-current-state "get home coordinates" (860, 60) -> function "calculate miles" (1120, 60) -> change "save distance" (1410, 60)

Then a vertical drop via junction (940, 280) to:
- function "determine action" (1110, 280) -- 3 outputs fanning vertically:
  - Output 1 (y=220): api-call-service "send disable?" (1440, 220)
  - Output 2 (y=280): api-call-service "send enable?" (1440, 280)
  - Output 3: api-current-state "if auto allowed" (1460, 360) -> api-call-service "send notification" (1540, 420) -> delay (1750, 420) -> api-call-service "enable vacation" (1940, 420)

**Additional nodes**:
- inject "test" at (110, 120) -- below poll-state, feeds same junction
- api-current-state at (320, 120) -- feeds junction
- function "determine action (Pre Chat-GPT)" at (580, 340) -- a disabled/legacy node, positioned out of the way below the main flow

**Spacing observations**:
- Main chain horizontal spacing: ~130-270px between node centers (variable, based on node width)
- The fan-out from "determine action" spreads outputs at y=220, y=280, y=360 -- spacing of **60px** and then **80px**
- The secondary chain at y=420 continues rightward for the "auto enable" path

**Pattern**: This group demonstrates a "pipeline with decision diamond" layout. The linear pipeline runs left-to-right across the top, then drops down to a decision function, which fans out to multiple action paths.

### Intra-group Analysis: "Prompt to disable vacation mode" (4 nodes, 972w x 112h)

**Group box**: x=34, y=484, w=972, h=112

| Node | Type | x | y |
|------|------|-----|-----|
| subflow occupancy changed | subflow | 150 | 540 |
| subflow occupancy source | subflow | 450 | 540 |
| api-current-state "if vacation mode on" | api-current-state | 700 | 540 |
| api-call-service (notify) | api-call-service | 910 | 540 |

**All nodes at y=540** -- perfectly horizontal chain. Same pattern as the "Is wind down enabled?" group in Bedtime.

**Horizontal spacing**: 150->450 (**300px**), 450->700 (**250px**), 700->910 (**210px**)

### Intra-group Analysis: "Handle push notification responses" (8 nodes, 972w x 162h)

**Group box**: x=34, y=619, w=972, h=162

| Node | Type | x | y |
|------|------|-----|-----|
| server-events "On notification action" | server-events | 160 | 700 |
| switch | switch | 350 | 700 |
| api-call-service (disable confirm) | api-call-service | 530 | 660 |
| api-call-service (enable confirm) | api-call-service | 530 | 740 |
| delay | delay | 690 | 660 |
| delay | delay | 690 | 740 |
| api-call-service "disable vacation" | api-call-service | 880 | 660 |
| api-call-service "enable vacation" | api-call-service | 880 | 740 |

**Layout pattern**: Two parallel horizontal chains after a switch. The switch at y=700 fans to two branches:
- **Upper branch** at y=660: notify -> delay -> disable
- **Lower branch** at y=740: notify -> delay -> enable

**Branch vertical spacing**: **80px** between the two parallel paths (660 and 740).

**Horizontal spacing within branches**: 530->690 (**160px**), 690->880 (**190px**)

The switch node at y=700 is centered vertically between the two branches (660 and 740, average=700). This is a deliberate centering pattern.

### Vacation Mode Flow Synthesis

1. **Inter-group gap**: ~23px (slightly larger than Bedtime's 18px)
2. **Linear chains are perfectly horizontal** (all same y)
3. **Switch fan-out**: Branches are vertically symmetric around the switch node
4. **Branch spacing**: ~60-80px between parallel paths
5. **Complex pipelines**: Long horizontal chains with a vertical drop to decision logic

---

## Flow 3: Switches (id=a21bcb9abb9ff4db)

### Group Layout Summary

| Group | x | y | w | h | Nodes |
|-------|-----|------|------|-----|-------|
| Bedroom Switch | 34 | 19 | 1032 | 464.5 | 13 |
| Office Switch | 34 | 479 | 1032 | 464.5 | 17 |
| Kitchen Island Switch | 34 | 959 | 872 | 382 | 10 |
| Kitchen Scenes | 934 | 959 | 1072 | 164.5 | 8 |
| Main Bathroom Switch | 34 | 1359 | 1032 | 562 | 17 |
| Bedroom Outlet Switch | 34 | 1939 | 892 | 344.5 | 6 |
| Living Room Outlet Switch | 34 | 2299 | 872 | 602 | 14 |
| Kitchen Counter Switch | 34 | 2919 | 852 | 204.5 | 4 |
| TEST: Set a switch's LEDs | 34 | 3159 | 992 | 362 | 12 |
| Office Hue Remote | 1154 | 539 | 1152 | 242 | 11 |

### Inter-group Spacing (Switches)

Most groups are left-aligned at x=34 and stacked vertically:

| From -> To | Gap |
|-----------|-----|
| Bedroom Switch (bottom=483.5) -> Office Switch (y=479) | **-4.5** (overlap!) |
| Office Switch (bottom=943.5) -> Kitchen Island (y=959) | **15.5** |
| Kitchen Island (bottom=1341) -> Main Bathroom (y=1359) | **18** |
| Main Bathroom (bottom=1921) -> Bedroom Outlet (y=1939) | **18** |
| Bedroom Outlet (bottom=2283.5) -> Living Room Outlet (y=2299) | **15.5** |
| Living Room Outlet (bottom=2901) -> Kitchen Counter (y=2919) | **18** |
| Kitchen Counter (bottom=3123.5) -> TEST LEDs (y=3159) | **35.5** |

**Pattern**: Most gaps are ~18px (matching Bedtime). Some are ~15.5px or vary. There's even a slight overlap at the top.

### Side-by-side Groups

Two notable cases of groups placed **horizontally adjacent** rather than vertically stacked:

1. **Kitchen Scenes** (x=934, y=959) sits to the **right** of Kitchen Island Switch (x=34, y=959). They share the same y-coordinate. The gap: Kitchen Island right edge (34+872=906) to Kitchen Scenes left edge (934) = **28px horizontal gap**.

2. **Office Hue Remote** (x=1154, y=539) sits to the **right** of Office Switch (x=34, y=479). Vertical overlap: Office Switch goes from y=479 to y=943.5; Office Hue Remote goes from y=539 to y=781. They overlap vertically. Horizontal gap: Office Switch right (34+1032=1066) to Hue Remote left (1154) = **88px horizontal gap**.

**Pattern**: Related groups (Kitchen Island + Kitchen Scenes, Office Switch + Office Hue Remote) can be placed side-by-side when they share a functional relationship. The Hue Remote feeds into the Office Switch via link nodes.

### Intra-group Analysis: "Bedroom Switch" (13 nodes, 1032w x 464.5h)

This group represents the canonical **switch handler** pattern used across all switch groups:

**Structure**:
```
Switch Event (x=160, y=300)
  -> Inovelli Button subflow (x=370, y=300)
    -> Output 1 (up press): Inovelli Interaction (x=570, y=120) -> actions at x=770-960, y=60-120
    -> Output 2 (down press): Inovelli Interaction (x=570, y=300) -> actions at x=770-960, y=240-300
    -> Output 3 (aux press): Inovelli Interaction (x=570, y=420) -> actions at x=770-960, y=380
```

**Horizontal column positions** (center x):
- Column 1 (source): x~160-180
- Column 2 (button subflow): x~370-380
- Column 3 (interaction subflow): x~570-580
- Column 4 (primary actions): x~770-800
- Column 5 (secondary/chained actions): x~960

**Column spacing**: ~200px between columns

**Vertical fan-out from Inovelli Button**:
- 3 outputs at y=120, y=300, y=420
- Spacing between outputs: **180px** and **120px**
- Note: the "center" output (y=300) is at the same y as the entry node

**Inovelli Interaction fan-out** (from each interaction subflow):
- Multiple outputs at ~60px vertical spacing
- E.g., from the top interaction (y=120): outputs at y=60, y=120
- From the middle interaction (y=300): outputs at y=240, y=300

**Pattern**: The switch handler is a tree: source -> button -> interaction -> actions. Each level fans out vertically. The entry node sits at the vertical center of the group. Actions (api-call-service) are terminal nodes at the right edge. Chained actions (scene after light) extend further right.

### Intra-group Analysis: "Kitchen Scenes" (8 nodes, 1072w x 164.5h)

**Group box**: x=934, y=959, w=1072, h=164.5

| Node | Type | x | y |
|------|------|-----|-----|
| Kitchen Island Switch Event | subflow | 1080 | 1000 |
| Kitchen Ceiling Switch Event | subflow | 1080 | 1040 |
| Kitchen Counter Switch Event | subflow | 1080 | 1080 |
| Inovelli Button | subflow | 1320 | 1040 |
| Inovelli Interaction | subflow | 1510 | 1060 |
| scene starlight | api-call-service | 1720 | 1040 |
| scene prism | api-call-service | 1720 | 1080 |
| turn off ceiling+counter | api-call-service | 1910 | 1060 |

**Three entry nodes** merge into one Inovelli Button subflow:
- They're stacked at x=1080, y=1000/1040/1080 -- **40px vertical spacing** for multiple entry nodes

**Horizontal spacing**: ~200-240px between columns, consistent with other switch groups.

### Intra-group Analysis: "TEST: Set a switch's LEDs" (12 nodes, 992w x 362h)

**Group box**: x=34, y=3159, w=992, h=362

7 inject nodes stacked vertically:
- y=3200, 3240, 3280, 3320, 3360, 3400, 3440 -- **40px spacing** between inject nodes
- All at x~150-180 (left column)

All feed a junction (x=460, y=3400), then link call (x=580, y=3400), then function (x=610, y=3480), then debug + api-call-service at x=800/850.

**Pattern for many-entry-node groups**: Stack all inject/source nodes vertically with 40px spacing, merge via junction, then continue LR.

### Switches Flow Synthesis

1. **Column-based layout**: Nodes align in vertical columns at ~200px horizontal spacing
2. **Repeating switch handler template**: source -> button -> interaction -> actions
3. **Fan-out spacing**: ~60px per branch for fine-grained, ~180px for major branches
4. **Multiple entry nodes**: Stacked at 40px vertical spacing, merged via junction
5. **Side-by-side groups**: Related groups placed horizontally adjacent with ~28-88px gaps
6. **Left alignment at x=34** for most groups
7. **Inter-group gap**: ~18px (consistent with Bedtime)

---

## Flow 4: Tablets (id=5add56611053750d)

### Group Layout Summary

| Group | x | y | w | h | Nodes |
|-------|-----|------|------|-----|-------|
| Set kiosk brightness | 34 | 39 | 1112 | 422 | 19 |
| Subroutine to set brightness | 1174 | 39 | 712 | 362 | 9 |
| Brightness tester | 34 | 479 | 772 | 482 | 19 |
| Subroutine to turn display on/off | 834 | 479 | 1212 | 302 | 12 |
| Tablet "Display Off" buttons | 834 | 799 | 772 | 202 | 9 |
| On/Off Tester | 34 | 979 | 432 | 202 | 5 |
| When user disables auto brightness | 34 | 1199 | 932 | 202 | 6 |
| keep tablet browsermod on | 34 | 1419 | 792 | 82 | 2 |
| Navigate tablet back | 34 | 1519 | 952 | 262 | 12 |

### Inter-group Spacing (Tablets)

Vertically stacked groups (left column, x~34):

| From -> To | Gap |
|-----------|-----|
| Set kiosk (bottom=461) -> Brightness tester (y=479) | **18** |
| Brightness tester (bottom=961) -> On/Off Tester (y=979) | **18** |
| On/Off Tester (bottom=1181) -> When user disables (y=1199) | **18** |
| When user disables (bottom=1401) -> browsermod (y=1419) | **18** |
| browsermod (bottom=1501) -> Navigate tablet (y=1519) | **18** |

**All exactly 18px!** This is the most consistent spacing across all flows.

### Side-by-side Groups (Tablets)

The Tablets flow uses a two-column layout:

**Left column** (x=34): Set kiosk, Brightness tester, On/Off Tester, When user disables, browsermod, Navigate tablet

**Right column**:
- Subroutine to set brightness (x=1174, y=39) -- adjacent to Set kiosk
- Subroutine to turn display on/off (x=834, y=479) -- adjacent to Brightness tester
- Tablet Display Off buttons (x=834, y=799) -- below display on/off subroutine

Horizontal gaps between side-by-side groups:
- Set kiosk right (34+1112=1146) to Subroutine set brightness left (1174): **28px**
- Brightness tester right (34+772=806) to Subroutine display on/off left (834): **28px**

**Pattern**: Side-by-side groups are separated by exactly **28px** horizontally. This matches the Switches flow's Kitchen Scenes gap.

Vertical relationships in right column:
- Subroutine display on/off (bottom=781) -> Display Off buttons (y=799): **18px** gap

### Intra-group Analysis: "Set kiosk tablet's brightness" (19 nodes, 1112w x 422h)

This is the most complex group by node count. Key coordinate data:

**Multiple source nodes at left** (x~90-300):
- server-state-changed "User interaction" (x=160, y=80)
- server-state-changed "Lights change" (x=160, y=160)
- server-state-changed "Auto brightness toggle" (x=160, y=240)
- server-state-changed "Sun changes" (x=160, y=320)
- inject "test" (x=140, y=400)

These are stacked at **80px vertical spacing**, all at similar x~140-160.

**Convergence via junctions**: Multiple junctions merge the sources:
- 4 change nodes at x~300-400 (setting tablet= values) at y=80, y=160, y=240, y=320
- A junction at (x=560, y=80) and additional junction at (x=680, y=240)
- api-current-state at (x=490, y=80)

Then function "determine brightness" at (x=750, y=120) -> junction -> link out "set tablet brightness" (x=1050)

Plus a delay and additional fan for different tablet targets.

**Entry node spacing**: When multiple source nodes of the same type are stacked, spacing is **80px**. When they're different types that merge, spacing is **60-80px**.

### Intra-group Analysis: "On/Off Tester" (5 nodes, 432w x 202h)

**Group box**: x=34, y=979, w=432, h=202

| Node | Type | x | y |
|------|------|-----|-----|
| inject "Fire Screen Off" | inject | 130 | 1060 |
| inject "Fire Screen On" | inject | 130 | 1020 |
| inject "ThinkSmart1 Screen Off" | inject | 160 | 1140 |
| inject "ThinkSmart1 Screen On" | inject | 160 | 1100 |
| link out | link out | 365 | 1060 |

**Pattern**: Two pairs of inject nodes (On/Off for each device), stacked with 40px spacing within pairs and ~40-80px between pairs. All feed one link out node.

### Intra-group Analysis: "Navigate tablet back" (12 nodes, 952w x 262h)

**Group box**: x=34, y=1519, w=952, h=262

4 parallel paths, one per tablet:
- Each path: server-state-changed -> api-current-state -> api-call-service
- Paths at y=1560, 1620, 1680, 1740 -- **60px spacing** between parallel paths

All 4 server-state-changed nodes at x~180, api-current-state at x~510-520, api-call-service at x~800.

**Pattern**: Perfectly parallel identical chains with 60px vertical spacing. A "replicated" pattern where the same logic is applied per-device.

### Intra-group Analysis: "When user disables auto brightness" (6 nodes, 932w x 202h)

**Group box**: x=34, y=1199, w=932, h=202

| Node | Type | x | y |
|------|------|-----|-----|
| server-state-changed | server-state-changed | 260 | 1300 |
| change "50%" (kiosk) | change | 560 | 1240 |
| change "50%" (ts1) | change | 560 | 1300 |
| change "50%" (ts2) | change | 560 | 1360 |
| change "50%" (ts3) | change | 700 | 1240 |
| link out | link out | 870 | 1300 |

**Pattern**: One source fans to 4 change nodes (one per tablet), but they're NOT purely vertical -- they form a 2x2 grid. Nodes at (560,1240), (560,1300), (560,1360), and (700,1240). Wait -- looking at the actual node names -- the server-state-changed has 4 outputs fanning to 4 change nodes. The change nodes set tablet-specific values then all connect to the same link out.

Actually, re-checking: the server-state-changed at x=260 has 4 outputs going to 4 change nodes. The change nodes at x=560 are at y=1240, 1300, 1360; the 4th is at x=700 but labeled differently. Let me re-examine the actual wiring: the server-state-changed fans to 4 devices, each getting a change node to set its entity, then all feed a single link out.

### Intra-group Analysis: "keep tablet browsermod on" (2 nodes, 792w x 82h)

**Group box**: x=34, y=1419, w=792, h=82

| Node | Type | x | y |
|------|------|-----|-----|
| server-state-changed | server-state-changed | 300 | 1460 |
| api-call-service | api-call-service | 660 | 1460 |

Two nodes at y=1460. Horizontal spacing: 300->660 = **360px**. Simple 2-node linear chain, perfectly horizontal.

**Padding**: Group vertical center = 1419+41=1460. Nodes are exactly at vertical center. Group h=82, so top padding = 41px, bottom padding = 41px.

### Tablets Flow Synthesis

1. **Two-column layout** for related groups (main + subroutine)
2. **Exactly 28px horizontal gap** between side-by-side groups
3. **Exactly 18px vertical gap** between stacked groups
4. **Parallel replicated chains**: 60px vertical spacing between identical per-device paths
5. **Multiple sources stacked at 80px** spacing when same type
6. **Simple 2-node chains**: nodes are vertically centered in group with 41px padding
7. **Tester groups** sit near the groups they test

---

## Cross-Flow Synthesis

### Universal Layout Rules

#### 1. Group Stacking Direction: Vertical

Groups are primarily **stacked vertically** (top to bottom). The vertical gap between consecutive groups is:

| Metric | Value |
|--------|-------|
| **Standard gap** | **18px** |
| Most common in | Bedtime (7/9 gaps), Tablets (5/5 gaps), Switches (~5/8 gaps) |
| Alternative gaps observed | 23px (Vacation Mode), 15.5px, 10.5px, 28px (rare) |

**Rule: Use 18px vertical gap between vertically stacked groups.**

#### 2. Group Left Alignment

Groups in a vertical stack are left-aligned. The most common left-edge x values:

| x value | Frequency |
|---------|-----------|
| 34 | Most common (Switches, Tablets, Vacation Mode) |
| 54 | Common (Bedtime lower groups) |
| 74 | Less common (Bedtime top groups) |
| 14 | Rare (Vacation Mode top group) |

**Rule: Default group left edge at x=34.** The variation (34-74) suggests 34 is the minimum/default and slight rightward shifts occur naturally.

#### 3. Side-by-Side Groups

Related groups (e.g., main automation + subroutine, switch + remote) can be placed horizontally adjacent:

| Horizontal gap | Where observed |
|----------------|----------------|
| **28px** | Tablets (2 instances), Switches (Kitchen Island -> Kitchen Scenes) |
| **88px** | Switches (Office Switch -> Office Hue Remote) |

**Rule: Use 28px horizontal gap between side-by-side groups.** The 88px case is an outlier that may reflect a visual preference for more separation when the right group is on a different row than the left group's entry.

#### 4. Node Flow Direction: Left-to-Right

All flows use **left-to-right (LR)** direction. Source/trigger nodes are at the left, terminal/action nodes at the right.

#### 5. Horizontal Spacing Between Nodes

Center-to-center horizontal spacing between consecutive nodes in a chain:

| Context | Observed spacing | Typical range |
|---------|-----------------|---------------|
| Small nodes (junction, link) -> next | 110-155px | ~120px |
| Standard nodes (api-call-service, function) | 160-220px | ~190px |
| Wide nodes (server-state-changed, inject with name) | 200-300px | ~220px |
| Switch group columns | ~200px consistent | ~200px |

**Rule: Use ~200px center-to-center horizontal spacing as default.** Adjust based on node width: narrower nodes (junctions, links) can be closer (~120px), wider nodes (named triggers) need more space (~240px).

More precisely, it appears the user targets approximately **60-80px of visible gap** between the right edge of one node and the left edge of the next. Since typical node widths are 120-200px, this produces center-to-center distances of ~180-280px.

#### 6. Vertical Spacing for Branches/Fan-out

When a node has multiple outputs, downstream nodes are spaced vertically:

| Context | Vertical spacing |
|---------|-----------------|
| 2-output branch (switch, conditional) | **60-80px** per branch |
| 3+ output fan (Inovelli Button, function) | **60px** per output (tight), **120-180px** (for major branches) |
| Parallel identical chains (per-device) | **60px** between chains |
| Multiple entry nodes (same type, stacked) | **40px** between nodes |
| Multiple entry nodes (different types) | **60-80px** between nodes |
| Switch with 2 symmetric outputs | Branches at **-40** and **+40** from switch y (or **-20/+20** from center) |

**Key rules:**
- **40px**: Spacing between stacked inject/source nodes of the same type
- **60px**: Spacing between parallel branches or replicated chains
- **80px**: Spacing between major source nodes of different types

#### 7. Node Alignment Within Chains

- **Linear chains**: All nodes share the exact same y coordinate
- **Branching**: The "primary" path continues at the same y as the source node; secondary paths shift up or down
- **Conditional (2-output)**: Pass output often continues at same y; fail output shifts down by 60px
- **Test inject nodes**: Positioned below the main flow line by 60px, connecting to the appropriate point in the chain

#### 8. Group Box to Node Relationship

The group bounding box wraps around its member nodes with consistent padding:

| Measurement | Typical value |
|-------------|---------------|
| Top padding (group top to topmost node center) | **~40px** |
| Bottom padding (bottommost node center to group bottom) | **~40px** |
| Left padding (group left to leftmost node center) | **~100-140px** |
| Right padding (rightmost node center to group right) | **~80-100px** |

**Note**: Left padding is larger because source nodes (triggers, injects) tend to have wide labels. Right padding is smaller because terminal nodes (api-call-service) have narrower visual footprints.

For very small groups (2 nodes, h=82), top and bottom padding are both **~41px**, centering the nodes vertically.

#### 9. Junction and Link Node Positioning

- **Junctions** sit on the flow line at the same y as surrounding nodes. They're used to merge multiple inputs or split to multiple outputs.
- **Link in** nodes sit at the left edge of a group, at the group's vertical center
- **Link out (return)** nodes sit at the right edge of a group, at the group's vertical center
- **Link out (link mode)** nodes sit at the right edge after the last action node, at the same y as their input

#### 10. Multi-Output Node Centering

When a node (like a switch) fans to N outputs:
- The source node is positioned at the **vertical center** of its output range
- Example: switch at y=700 with outputs at y=660 and y=740 (center = 700)
- Example: Inovelli Button at y=300 with outputs at y=120, y=300, y=420 (center ≈ 280, close to 300)

---

## Proposed Numeric Constants for Layout Tool

```
# Inter-group spacing
GROUP_VERTICAL_GAP = 18          # px between vertically stacked groups
GROUP_HORIZONTAL_GAP = 28        # px between side-by-side groups
GROUP_LEFT_MARGIN = 34           # px from flow edge to group left edge

# Node-to-group padding
GROUP_PADDING_TOP = 40           # px from group top to topmost node center
GROUP_PADDING_BOTTOM = 40        # px from bottommost node center to group bottom
GROUP_PADDING_LEFT = 120         # px from group left to leftmost node center
GROUP_PADDING_RIGHT = 90         # px from rightmost node center to group right

# Horizontal spacing (center-to-center)
NODE_HORIZONTAL_SPACING = 200    # default for standard nodes
NODE_HORIZONTAL_SPACING_TIGHT = 120  # for junctions, links, small nodes
NODE_HORIZONTAL_SPACING_WIDE = 260   # for wide trigger/event nodes

# Vertical spacing
BRANCH_VERTICAL_SPACING = 60     # spacing between branch outputs
ENTRY_NODE_STACKING = 40         # spacing between stacked entry nodes (same type)
SOURCE_NODE_SPACING = 80         # spacing between different-type source nodes
PARALLEL_CHAIN_SPACING = 60      # spacing between replicated identical chains

# Special positioning
TEST_INJECT_OFFSET_Y = 60        # how far below main flow line test injects sit
```

### Layout Algorithm Sketch

1. **For each group**: Identify source nodes (no incoming connections from within group)
2. **Topological sort** all nodes within the group (BFS from sources)
3. **Assign columns** based on longest-path-from-source (column 0, 1, 2, ...)
4. **Position columns** left-to-right at NODE_HORIZONTAL_SPACING intervals, starting at GROUP_PADDING_LEFT
5. **Within each column**:
   - If only one node, place at the vertical center of its parent's output port
   - If multiple nodes, stack with BRANCH_VERTICAL_SPACING
6. **Source nodes** (column 0):
   - Stack with ENTRY_NODE_STACKING or SOURCE_NODE_SPACING
   - Test inject nodes go below production triggers
7. **Multi-output fan**: Center the source node vertically among its outputs
8. **Calculate group box**: Set x/y/w/h based on node positions plus padding constants
9. **Position groups on flow**: Stack vertically with GROUP_VERTICAL_GAP; place related subroutines side-by-side with GROUP_HORIZONTAL_GAP

### Important Caveats

1. **Node widths vary**: The spacing rules assume knowledge of rendered node width, which depends on the node's label text and type. The layout tool may need a width estimation function.

2. **This analysis covers hand-laid-out flows**: The user's layout is optimized for readability. An automated tool should replicate these patterns but may need heuristics for edge cases (e.g., very deep chains, groups with 20+ nodes).

3. **Group label height**: Groups with `style.label: true` (all observed groups) have a visible label bar at the top. The GROUP_PADDING_TOP of 40px accounts for this.

4. **Disabled nodes**: Disabled nodes (like the "Pre Chat-GPT" function in Vacation Mode) are positioned out of the way but still within the group. The layout tool should treat them normally but could optionally place them at the bottom.

5. **The dagre relayout tool already exists**: The existing `relayout-nodered-flows.sh` uses dagre for layout. This analysis provides the target aesthetic parameters that dagre should be configured with to match the user's hand-laid-out style.

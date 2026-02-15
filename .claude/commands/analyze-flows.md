# Analyze Node-RED Flow Changes

You are updating the automation documentation in `mynodered/docs/` to reflect the
current state of `mynodered/nodered.json`.

**Process note:** Fire off each subagent sequentially, not in parallel.

## 1. Load context

Read these files before doing anything else:

1. `CLAUDE.md` — project structure, doc format specs, and tool references.
2. `mynodered/CLAUDE.md` (if it exists) — user-specific context about their home,
   naming conventions, or preferences that should inform how you describe automations.
3. `docs/exploring-nodered-json.md` — how to use the query tool to drill into flows.

## 2. Run the diff summary

```bash
helper-scripts/summarize-nodered-flows-diff.sh --git mynodered/nodered.json
```

### How to consume the output

The output is large. Don't read every section linearly — work from the bottom up:

1. **AFFECTED DOCUMENTATION** (last section) — this is your work list. It tells you
   exactly which doc files need creating or updating and why. If it says "no
   documentation updates needed," you're done.

2. **CHANGE OVERVIEW** (first section) — understand the scale. "First import" means
   you're generating all docs from scratch. Otherwise, note the counts to calibrate
   how much work to expect.

3. **DETAILED CHANGES BY FLOW / BY SUBFLOW** — for each item in your work list,
   these sections tell you which nodes were added/removed/modified and which fields
   changed. This tells you what parts of existing docs to revise.

4. **ENTITY REFERENCE CHANGES, FUNCTION CODE CHANGES, WIRING CHANGES** — check
   these for specific details you'll need when writing the doc updates.

5. **The tagged summary sections** (FLOWS, SUBFLOWS, GROUPS) — use these for
   orientation. Items tagged [NEW] need new docs written. Items tagged [MODIFIED]
   need existing docs updated. Untagged items can be left alone.

## 3. Investigate and write docs

For each file in your AFFECTED DOCUMENTATION work list, investigate the flow or
subflow using the query tool, then write or update the doc.

### Node IDs are documentation anchors

Pepper node IDs liberally throughout all documentation. Every node mentioned by name
should also include its ID in parentheses — entry points, switch nodes, function nodes,
action nodes, subflow instances, groups, etc. This serves two purposes: future agents
can immediately query any node they read about without searching, and IDs make the docs
greppable. Don't relegate IDs to a separate reference section; put them inline where
the node is discussed.

Good: "The motion sensor trigger (`abc123`) fires when `binary_sensor.hall_motion` changes..."
Bad: "The motion sensor trigger fires when the hall motion sensor changes..."

### Investigating a flow

Use the query tool at `helper-scripts/query-nodered-flows.sh mynodered/nodered.json`.

For a flow you need to document (whether new or modified):

1. Get the full group layout and entry points:
   ```
   query-nodered-flows.sh ... flow-nodes <flow_id> --sources --summary
   ```
2. For each group, get its entry points and trace downstream:
   ```
   query-nodered-flows.sh ... group-nodes <group_id> --sources --summary
   query-nodered-flows.sh ... connected <source_id> --forward --summary
   ```
3. For key nodes (switches, api-call-service, change nodes), inspect their config:
   ```
   query-nodered-flows.sh ... node <node_id>
   ```
4. For function nodes, read the JavaScript:
   ```
   query-nodered-flows.sh ... function <node_id>
   ```
5. For tail nodes (endpoints), see what actions the automation takes:
   ```
   query-nodered-flows.sh ... tail-nodes <source_id> --summary
   ```

For a **modified** flow where existing docs exist, read the existing doc first
(`mynodered/docs/flows/<flow_id>.md`), then focus your investigation on the
specific changes from the DETAILED CHANGES section. You don't need to re-investigate
unchanged groups — just verify the existing descriptions still hold and update the
parts that changed.

### Investigating a subflow

1. Look inside the subflow:
   ```
   query-nodered-flows.sh ... subflow-nodes <subflow_id> --summary
   ```
2. Find where it's used:
   ```
   query-nodered-flows.sh ... subflow-instances <subflow_id> --summary
   ```
3. Inspect key internal nodes for behavior details.

### Doc format: `mynodered/docs/overview.md`

A high-level summary of the entire automation setup. Structure:

- One-paragraph introduction summarizing the user's automation approach (update this
  based on any user context from `mynodered/CLAUDE.md`).
- **Flows** section: list every flow with its ID, a 1-3 sentence summary of what it
  does, and a link to its detailed doc (`flows/<flow_id>.md`).
- **Subflows** section: list every subflow with its ID, a 1-2 sentence summary, and
  a link to its detailed doc (`subflows/<subflow_id>.md`).

When updating an existing overview, preserve summaries for unchanged flows/subflows.
Add entries for new ones, remove entries for deleted ones, and revise summaries for
modified ones.

### Doc format: `mynodered/docs/flows/<flow_id>.md`

A detailed overview of a single flow. Structure:

- Title: `# <flow label>`
- 1-2 sentence summary of the flow's overall purpose.
- For each **group** in the flow (in logical order):
  - `## <group name>`
  - Summary of what this group does.
  - **Entry points**: list each source node with its type, name, and ID. Describe
    what triggers it (which entity, what schedule, etc. — get this from the node's
    config via the query tool).
  - **What happens**: from each entry point, describe the downstream chain with node
    IDs inline — what decisions are made (switch nodes), what transformations happen
    (change/function nodes), and what actions are taken (api-call-service nodes with
    which entities). Include the ID of every node you mention.
- If there are **ungrouped source nodes**, document them in a separate section.
- **Entity references**: list all HA entities this flow interacts with, grouped by
  how they're used (triggers, state checks, actions).

### Doc format: `mynodered/docs/subflows/<subflow_id>.md`

A detailed overview of a single subflow. Structure:

- Title: `# <subflow name>`
- Summary of what the subflow does and why it exists.
- **Ports**: describe each input and output — what data is expected/produced.
- **Internal logic**: how the subflow processes messages. Describe the key nodes
  and decision points, with node IDs inline for every node mentioned.
- **Usage**: where this subflow is instantiated (list flows that use it, with
  context on how each uses it).
- **When to use**: guidance on when this subflow is the right tool for the job.

## 4. Quality checklist

Before finishing, verify:

- [ ] Every flow listed in the diff summary has a corresponding doc file.
- [ ] Every subflow listed in the diff summary has a corresponding doc file.
- [ ] `overview.md` lists all flows and subflows with accurate summaries.
- [ ] Node IDs appear inline throughout the prose (not just in lists) — every node,
      group, and subflow instance mentioned by name also has its ID.
- [ ] Entity IDs mentioned in the docs match what's actually in the flows.
- [ ] Descriptions of function node logic match the actual JavaScript code.
- [ ] No docs reference nodes, groups, or flows that were removed.

## 5. Mark analysis complete

After passing the quality checklist, mark this analysis as complete by snapshotting
the flows file you analyzed and staging it:

```bash
cp mynodered/nodered.json mynodered/nodered-analyzed.json
git -C mynodered add nodered-analyzed.json
```

This checkpoint tells the calling script that you successfully analyzed this exact
version of the flows. If you don't reach this step, the caller knows the analysis
didn't finish and can retry.

# Deep-Dive Documentation

You are creating or updating a deep-dive document in `mynodered/docs/`.

**Arguments:** `$ARGUMENTS`

## 0. No-args mode: suggest and run deep-dives

If the arguments are empty (no name provided at all), switch to suggestion mode
instead of creating a document.

### Identify candidates

1. Read `CLAUDE.md` for project structure and tool references.
2. Read `mynodered/CLAUDE.md` to understand the full automation landscape — all
   flows, subflows, and any existing deep-dive docs already listed in the
   "Deep-Dive Documentation" section.
3. Check which `mynodered/docs/*.md` files already exist (these are the deep-dives
   that have already been written — don't suggest duplicates).
4. Look at the flow and subflow summaries to identify cross-cutting themes,
   complex subsystems, or recurring patterns that span multiple flows and would
   benefit from a unified deep-dive document. Good candidates are topics where:
   - Multiple flows interact with the same subsystem (e.g., occupancy is used by
     bedtime, vacation, thermostat, etc.)
   - A complex pipeline spans several subflows and isn't fully explained by any
     single flow doc (e.g., the Inovelli switch event → button → interaction →
     action chain)
   - There's meaningful "glue" logic that connects flows in non-obvious ways
     (e.g., link nodes, shared entities, command subflows)
   - The user has custom patterns or conventions that would be valuable to
     document for future agents

### Present and execute

5. Present 3-5 suggestions to the user using `AskUserQuestion` with
   `multiSelect: true`. Each suggestion becomes an option:
   - **label**: the deep-dive name (e.g., "occupancy")
   - **description**: a brief rationale — why this topic is valuable and which
     flows/subflows it draws from
   Include a final option: label "Skip for now", description "Don't run any
   deep-dives right now."
6. If the user selects "Skip for now" (or selects nothing), stop.
7. For each suggestion the user selects, spawn a new **opus** subagent (via the
   Task tool) to run the full `/deep-dive <name> <scope>` command. The subagent
   prompt must include:
   - The name and scope for the deep-dive
   - Instructions to read `CLAUDE.md`, `mynodered/CLAUDE.md`, and
     `docs/exploring-nodered-json.md` before starting
   - The full deep-dive skill instructions (steps 1-6 from this file)
   Fire these sequentially, not in parallel.

Then stop after the last subagent finishes.

---

If arguments are provided, continue with the normal flow below.

The first word is the document name (e.g., `occupancy`), and everything after it
is the scope/purpose description. If only a name is given with no description,
and the document already exists, preserve its existing scope.

The output file is `mynodered/docs/<name>.md`.

## 1. Load context

Read these files before doing anything else:

1. `CLAUDE.md` — project structure, tool references, and style guidelines.
2. `mynodered/CLAUDE.md` (if it exists) — user-specific context about their home,
   automations, naming conventions, and the full list of flows and subflows.
3. `docs/exploring-nodered-json.md` — how to use the query and summarize tools.

## 2. Parse arguments

Extract the document name and scope from the arguments:
- **Name**: the first whitespace-delimited token. This becomes the filename
  (`mynodered/docs/<name>.md`).
- **Scope**: everything after the name. This is the purpose/scope description
  for the document.

If no scope is provided:
- If the document already exists and has a "Scope" section, preserve it as-is.
- If the document doesn't exist, stop and ask the user to provide a scope
  description. Don't guess.

If the document already exists, read it fully before starting research. Note
which sections exist and what content is already there — you'll update in place
rather than rewriting from scratch (unless the content is substantially wrong).

## 3. Research

This is the core of the skill. You need to deeply understand the topic described
by the scope, drawing from the actual Node-RED flows data and Home Assistant
configuration.

### Research strategy

1. **Start broad.** Read `mynodered/CLAUDE.md` to identify which flows and
   subflows are relevant to the topic. The scope description should guide which
   parts of the automation system to focus on.

2. **Read existing docs.** For each relevant flow and subflow, read its doc file
   in `mynodered/docs/flows/` or `mynodered/docs/subflows/`. These give you a
   solid foundation without needing to re-derive everything from raw JSON.

3. **Drill into the data.** Use the query tool at
   `helper-scripts/query-nodered-flows.sh mynodered/nodered.json` to investigate
   specifics that the existing docs don't cover, or to verify/deepen your
   understanding. Key commands:
   - `flow-nodes <id> --full` — load all nodes in a flow
   - `subflow-nodes <id> --full` — load all nodes in a subflow
   - `node <id>` — inspect a specific node's configuration
   - `function <id>` — read a function node's JavaScript
   - `connected <id> --forward --summary` — trace downstream from a node
   - `search --name "pattern" --summary` — find nodes by name
   - `subflow-instances <id> --summary` — find where a subflow is used

4. **Check HA scripts.** If the topic involves Home Assistant scripts (service
   calls to `script.*`), use `helper-scripts/get-ha-script.sh <name>` to dump
   and understand the script's YAML.

5. **Check HA entities.** If the topic involves specific HA entities, use the
   Home Assistant MCP tools (`search_entities_tool`, `get_entity`, `get_history`)
   to understand entity configuration and current state.

6. **Grep for cross-references.** Use grep to find mentions of relevant entity
   IDs, node IDs, or keywords across the flows JSON and existing docs. This
   catches connections that might not be obvious from reading individual flow docs.

### Ask the user when uncertain

During research, you will encounter things that are ambiguous, unclear, or where
the user's intent isn't obvious from the data alone. **Don't guess — ask.**

Use the `AskUserQuestion` tool to clarify. Batch multiple questions into a single
call whenever possible (up to 4 questions per call) to avoid back-and-forth.

Examples of things worth asking about:
- **Purpose/intent**: "This group has a disabled cron trigger and an active one
  with different timing — is the disabled one obsolete or a fallback?"
- **Naming/terminology**: "Several entities use the prefix `attn_` — does this
  refer to 'attention' as in mindfulness, or something else?"
- **Scope boundaries**: "The occupancy system touches bedtime, vacation mode, and
  thermostat logic. Should this deep-dive cover how those consumers use occupancy,
  or just the detection/state management side?"
- **Design decisions**: "Occupancy state is stored as a JSON blob in an
  input_text entity rather than separate entities — is there a reason for this?"
- **Accuracy**: "The doc says X, but the flow data shows Y — which is correct?"

Don't ask about things you can answer definitively from the data. Do ask when
the "why" behind a design choice matters for the doc and isn't self-evident, or
when the scope could reasonably be interpreted multiple ways.

### Required context for subagents

If you spawn subagents to help with research, every subagent prompt MUST include:

1. **Read `CLAUDE.md`** — project structure and conventions.
2. **Read `mynodered/CLAUDE.md`** — user context and automation overview.
3. **Read `docs/exploring-nodered-json.md`** — guide to using the query tool.
4. The specific research question or section the subagent is responsible for.
5. Any relevant flow/subflow IDs and entity IDs the subagent should focus on.

### Node IDs are documentation anchors

Pepper node IDs liberally throughout the document. Every node mentioned by name
should also include its ID in parentheses. This makes the doc greppable and lets
future agents immediately query any node they read about.

Good: "The motion sensor trigger (`abc123`) fires when `binary_sensor.hall_motion` changes..."
Bad: "The motion sensor trigger fires when the hall motion sensor changes..."

## 4. Write the document

Structure the document as follows:

```markdown
# <Title>

## Scope

<The scope/purpose description from the arguments, or preserved from the
existing document.>

## <Topic sections>

<The main content. Structure this based on what makes sense for the topic.
Use headers, subheaders, and lists to organize the information clearly.
Include node IDs inline wherever nodes are mentioned.>

## Related Flows and Subflows

<List flows and subflows relevant to this topic with their IDs and brief
descriptions of how they relate.>
```

The exact structure of the topic sections depends on the scope. Some examples:
- A deep-dive on "occupancy" might have sections for detection mechanisms,
  state management, automations that react to occupancy, and edge cases.
- A deep-dive on "notifications" might cover notification types, the actionable
  notification subflow, which flows send notifications, and response handling.
- A deep-dive on "switches" might cover the Inovelli event pipeline, button
  mappings per room, and configuration management.

Write for an audience that understands Home Assistant and Node-RED but doesn't
know this specific setup. Explain the "why" behind design decisions when apparent.

### Updating an existing document

When updating rather than creating:
- Preserve any sections that are still accurate.
- Update sections where the underlying flows have changed.
- Add new sections for newly relevant content.
- Remove sections for things that no longer exist.
- Keep the existing scope unless a new one was provided.

## 5. Update the deep-dive directory in `mynodered/CLAUDE.md`

After writing the document, update `mynodered/CLAUDE.md` to include an entry for
this deep-dive doc in the "Deep-Dive Documentation" section.

If the section doesn't exist yet, create it between the "Analysis" section (which
contains the Flows and Subflows subsections) and the "Version" section. Use this
format:

```markdown
## Deep-Dive Documentation

These files contain detailed documentation for complex subsystems. Load them into
context when working on related features or exploring related functionality.

NOTE: During analysis (`/analyze-flows` command), if there are changes to items
listed in the "Update when" subsection for each doc below, re-run a subagent with
the corresponding `/deep-dive` to make sure the document is still up to date.

### [docs/<name>.md](./docs/<name>.md) — <One-line description>

Load when:
- <list topics/tasks that should cause future Claude agents to load this doc>

Update when:
- <list docs/flows/ or docs/subflows/ files whose changes affect this deep-dive>
- <list deeply critical associated nodes — not every node, but source nodes or
  key decision points for core behavior related to this topic>
```

If the section already exists, add or update just the entry for this document.
Don't touch entries for other deep-dive docs.

**How to fill in the subsections:**

- **One-line description**: A concise summary of the document's topic (derived
  from the scope).
- **Load when**: Think about what tasks or questions would benefit from reading
  this doc. Examples: "working on occupancy-related automations", "debugging
  notification delivery", "modifying switch button mappings".
- **Update when**: List the specific `docs/flows/<id>.md` and
  `docs/subflows/<id>.md` files that cover the systems this deep-dive draws from.
  Also list critical node IDs (source nodes, key function nodes, important switch
  nodes) whose changes would meaningfully affect this document's accuracy. The
  purpose is to let `/analyze-flows` know when to trigger a re-run of this
  deep-dive.

## 6. Verify

Before finishing, verify:

- [ ] The scope section accurately describes the document's purpose.
- [ ] Node IDs appear inline throughout — every node, group, and subflow
      instance mentioned by name also has its ID.
- [ ] Entity IDs mentioned in the doc match what's actually in the flows.
- [ ] Cross-references to other flows/subflows are accurate.
- [ ] The document covers the full scope described, not just a subset.
- [ ] Descriptions of function node logic match the actual JavaScript code.
- [ ] `mynodered/CLAUDE.md` has an accurate entry for this doc in the
      "Deep-Dive Documentation" section with correct "Load when" and
      "Update when" lists.

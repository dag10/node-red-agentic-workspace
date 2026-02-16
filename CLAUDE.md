# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a project with a nested subproject.

**The outer project** (this repo) is a shared harness/toolset for using Claude Code to work with Node-RED automations on Home Assistant. It contains scripts, tooling, and documentation that are common to all users. Many people use this same repo with their own personal Home Assistant instances.

**The inner project** (`mynodered/` submodule) is a private per-user repo that tracks an individual's Node-RED flows — essentially their entire home's automations. Each person has their own private repo for this, since the content is personal to their home setup.

HA integration is available through the project MCP.

### Working with automations

When working on automation tasks (the inner project), agents should:

1. Read both `CLAUDE.md` (this file) and `mynodered/CLAUDE.md` (if it exists). The inner CLAUDE.md may contain context about the user's personal home setup, naming conventions, or automation preferences. It'll also have a list of all docs in docs/flows and docs/subflows.
2. Load `docs/exploring-nodered-json.md` for guidance on using the flow analysis tools.
3. **Query the live Home Assistant server when curious.** The Home Assistant MCP is configured for this project. When exploring flows and trying to understand automations — especially during `/deep-dive` or `/analyze-flows` — if something isn't clear from the Node-RED JSON or HA script YAML alone, query HA directly: search for entities, check entity states and attributes, look at history, browse domains, etc. Don't make modifications while exploring, but curiosity is encouraged — understanding what an entity actually is, what values it holds, or how a domain is structured often reveals context that the static flow data can't.

### After modifying flows

After making changes to `mynodered/nodered.json`, always update the documentation:

1. **Run the diff summary** and review the **AFFECTED DOCUMENTATION** section at the bottom:
   ```
   bash helper-scripts/summarize-nodered-flows-diff.sh --git mynodered/nodered.json
   ```
   This lists flow/subflow docs that need updating, plus any other docs (deep-dives, topic docs) that reference changed node IDs.

2. **Update every listed doc** to reflect your changes. For flow/subflow docs (`docs/flows/*.md`, `docs/subflows/*.md`), update the relevant sections. For deep-dive docs (`docs/occupancy.md`, `docs/switches.md`, etc.), update the prose to match the new behavior.

3. **Update `mynodered/CLAUDE.md`**: revise any flow/subflow summary paragraphs that are now inaccurate, and update the MD5 hash at the bottom (`md5 mynodered/nodered.json`).

## Project structure

### Outer project (this repo)

- `init.sh` - First-time setup: configures `.env`, sets up the `mynodered/` submodule, and verifies the HA MCP connection.
- `download-flows.sh` - User-facing script to download the latest Node-RED flows from Home Assistant into `mynodered/nodered-last-downloaded.json` and commit them to the submodule. Users should run this at the start of a session before working on automations.
- `upload-flows.sh` - User-facing script to upload `mynodered/nodered.json` to the Node-RED server and trigger a full deploy. Compares local flows against the server first, confirms with the user, then uploads. Always does a full replacement of all nodes.
- `helper-scripts/` - Shell scripts called by Claude or by other scripts (not intended to be called directly by humans).
- `docs/` - Documentation for the outer project's tools and subsystems.
- `/.env` - Gitignored file containing settings for talking to Home Assistant.

### Helper Scripts

- `helper-scripts/check-env.sh` - Sourced by other scripts to load `.env` and verify required env vars are set.
- `helper-scripts/run-hass-mcp.sh` - Runs the Home Assistant MCP server (used by the project MCP config).
- `helper-scripts/download-nodered-flows.sh [output.json]` - Downloads the full Node-RED flow export from HA to a JSON file (default: `mynodered/nodered-last-downloaded.json`). Output is normalized for stable diffs. Requires `uv`.
- `helper-scripts/upload-nodered-flows.sh [input.json]` - Uploads a flows JSON file (default: `mynodered/nodered.json`) to Node-RED and triggers a full deploy. Requires `uv`.
- `helper-scripts/normalize-json.sh <file.json> [output.json]` - Normalizes a JSON file (sorts keys, sorts arrays of objects by `id`). In-place if no output path given.
- `helper-scripts/check-nodered-flows-unchanged.sh <flows.json>` - Downloads live flows and diffs against the given file. Exits 0 if they match, 1 if diverged (prints diff to stderr). Use before uploading modified flows to catch concurrent edits.
- `helper-scripts/summarize-nodered-flows.sh <flows.json>` - Prints a summary of flows and subflows from a flows JSON file.
- `helper-scripts/summarize-nodered-flows-diff.sh <before.json> <after.json>` or `--git <flows.json>` - Diff-aware summary comparing two flow versions. Includes everything from the regular summary (with [NEW]/[MODIFIED] tags), plus detailed per-flow/subflow change breakdowns, entity reference changes, function code changes, wiring changes, and a list of which documentation files need updating. With `--git`, compares the file on disk against its last committed version.
- `helper-scripts/query-nodered-flows.sh <flows.json> <command> [args...]` - Extracts specific subsets of a flows JSON: individual nodes, connected subgraphs, flow/group contents, subflow instances, function source code, and flexible search. Commands: `node`, `function`, `connected`, `head-nodes`, `tail-nodes`, `flow-nodes`, `group-nodes`, `subflow-nodes`, `subflow-instances`, `search`. Use `--summary` for compact one-liners. Use `--full` for a pretty-printed JSON array of all matching nodes. Use `--sources` with `flow-nodes`/`group-nodes` to get only entry-point nodes.
- `helper-scripts/relayout-nodered-flows.sh <flows.json> [--dry-run] [--verbose]` - Auto-relayout Node-RED groups containing modified nodes using dagre LR layout. Compares the file on disk against its last committed version, identifies groups with structural changes (added/removed/rewired nodes — not position-only), and runs dagre to reposition nodes within those groups. Groups below resized groups are shifted vertically to avoid overlap. Automatically called by `upload-flows.sh` before upload. Requires Node.js; installs `@dagrejs/dagre` into `helper-scripts/.dagre-deps/` on first run.
- `helper-scripts/get-ha-script.sh <script_name>` - Dumps the YAML definition of a Home Assistant script (the classic HA YAML scripts, not Node-RED flows). Accepts either `script.foo` or just `foo`. Use this when a Node-RED flow calls out to an HA script (via `script.turn_on` or similar) and you need to understand what that script does. Read-only — this project does not modify HA scripts.

### Inner project (mynodered/ submodule)

The `mynodered/` directory is a git submodule containing the user's personal Node-RED data.

- `mynodered/nodered-last-downloaded.json` - The full Node-RED flows export as last downloaded from the Home Assistant server (downloaded via `download-flows.sh`). This file should never be modified locally in any way besides downloading the flows from the server, so it always represents the last known deployed state, useful for diffing.
- `mynodered/nodered-last-analyzed.json` - The full Node-RED flows export as last last successfully analyzed from the /analyze-flows claude command. This copy is maintained because the user might only run /analyze-flows every so often compared to how often they download updated flows that were modified on Home Assistant itself. So `nodered-last-downloaded.json` is expected to potentially update more frequently than `nodered-last-analyzed.json`, so this file is used for the analyze skill to successfully diff.
- `mynodered/nodered.json` - The full Node-RED flows export that is ultimately synchronized from production, and is our working file to make local changes on before committing and eventually deploying them.
- `mynodered/CLAUDE.md` - User-specific context about their home, automations, naming conventions, or preferences. Agents working on automations should always check for and read this file. Also includes a high-level summary of all automations, based on the summary script output. Lists all flows and subflows with summary paragraphs and links to their detailed docs.
- `mynodered/docs/` - Documentation describing the user's automations:
  - `docs/flows/<flow_id>.md` - Detailed overview of each flow: all groups, source nodes within each group (and ungrouped source nodes), and a summary of downstream nodes and their effects from each source.
  - `docs/subflows/<subflow_id>.md` - Detailed overview of each subflow: what it does, examples of where it's used, when to use it and why.

## Plans

When you create plan markdown files, save them as a sensibly-named plan in the /docs/plans directory,
in the format of `YYYY-MM-DD-sensible-plan-name.md`. Use the current system date.
Commit them in the same commit where the plan is implemented.

Each plan should have a companion prompt file: `YYYY-MM-DD-sensible-plan-name.prompt.md`.
This file captures the user prompt (or the relevant portion) that led to the plan, preserving
the original request for future context. The prompt file should contain the raw user prompt text
with minimal formatting -- just enough to be readable. If multiple tasks come from a single user
prompt, each task's `.prompt.md` should contain the relevant portion of the original prompt
(including the full prompt is also acceptable when excerpting would lose useful context).

When investigating code for building a plan, you might sometimes encounter lines of code or whole systems
who seem surprising or non-trivial. It's often to useful to understand the context and intent of why they
were written, and whether they're a bug, still needed, or even more important than you thought.
Two useful ways to do this, once you git blame the code to see what commit(s) it came from:
- Read the commit description and some other changes from that commit.
- Read the plan md file that was checked in during that commit, or the earliest commit the code originated from.

## Environment variables

- `HOMEASSISTANT_URL` - The URL to talk to home assistant (possibly `http://homeassistant.local:8123`)
- `HOMEASSISTANT_TOKEN` - The long-lived API token for talking to Home Assistant.

The env variables are loaded from .env for all scripts in the helper-scripts dir. Env vars already declared when invoking a script take precedence.

If you add/change env vars, make sure you update helper-scripts/check-env.sh and init.sh.

## Deep-dive documentation

The outer `docs/` directory contains detailed guides for specific tools and subsystems. These are
too long for CLAUDE.md but essential for effective use. Load the relevant doc when you start
a task involving that system.

- `docs/exploring-nodered-json.md` — How to use `summarize-nodered-flows.sh` and
  `query-nodered-flows.sh` to navigate Node-RED flows. **Load when:** working with
  `mynodered/nodered.json`, planning or implementing flow changes, or investigating
  automations.

The inner `mynodered/docs/` directory contains detailed info about the user's node-red automations. There's deep-dive docs at the top level for certain topics, and docs for all flows and subflows known.

## Style guidelines

### Comments: Why, Not What

Don't write comments that describe what code is doing—assume the reader can read code. Instead, write comments when:

- The **why** isn't obvious (e.g., working around a bug, non-obvious performance reason)
- Code might seem out of place without context about how something else works
- There's a UX side-effect or business reason that isn't evident from the code itself

### Special Comment Conventions

Code comments with specific prefixes have different meanings and require different handling:

**`NOTE:` comments** -- Preserve these. A `// NOTE:` comment explains a non-obvious design decision, gotcha, or invariant. When editing code near a NOTE comment:
- Keep the comment if it still applies to the code
- Move it if you're moving the code it describes
- Only remove it if the thing it describes no longer exists or is no longer true
- Never silently drop a NOTE comment during a refactor

**Cross-reference NOTEs**: When you write code that is codependent on code elsewhere in the codebase -- where changing one side requires changing the other, but the type system won't catch the mismatch -- add a `// NOTE:` comment on both sides linking to the other. Common examples:
- String-based lookups that must match declarations elsewhere (e.g., GLSL uniform names, API path strings)
- Parallel data structures that must stay in sync (e.g., enum values + exhaustive arrays)
- Build-time config that must match type declarations (e.g., Vite `define` + `env.d.ts`)
- AST parsers or regex-based tools that depend on source code structure
- Numeric constants shared with external systems (e.g., Steam Client API values)

**`TODO(Claude):` comments** -- Act on these when relevant. A `// TODO(Claude):` is a deferred directive from the user. When working on code that contains one:
- If the current task is related, do what it says and remove the comment
- If the current task is unrelated, leave it in place
- Treat the parenthetical as a conditional: `TODO(Claude, when directed)` means only act on it when explicitly asked
- When writing new TODO(Claude) comments, prefer the explicit conditional form (e.g., `TODO(Claude, when directed):`) to make the trigger condition clear

**`TODO(drew):` or `TODO(anyname):` comments** -- Ignore these. Comments attributed to a human (e.g., `// TODO(drew):`) are reminders for that person. Do not act on them, do not remove them, do not address them in your work. Pretend they are not there.

**Plain `TODO:` comments** (no attribution) -- Treat like any other code comment. Do not proactively fix TODOs unless the current task specifically involves the code they describe. Do not remove them.

### Git Workflow

Do not commit unless explicitly asked. Stage and commit only when the user says to.

### Commit Message Format

When creating git commits, use this format:

```
<one-liner of what functionally changed>

[Optional context paragraph if the one-liner isn't self-explanatory—explain the why/what in 1-2 sentences. Omit if obvious.]

Changes:
- <Concise bullets of individual changes>
- <Include architectural changes, refactors, behavioral/feature changes>
- <Note significant file moves/renames>

Co-Authored-By: Claude <noreply@anthropic.com>
```

**Example:**
```
Add somescript.sh to fetch the latest flows.

The user or agent previously had to manually fetch flows and save them to a file. This
script will handle that for them, and guide the user or agent along any errors
that arise.

Changes:
- Created somescript.sh to fetch flows.
- Updated SomeSkill and CLAUDE.md to use this script instead of its own instructions.
- Fixed a bug in otherscript.sh (which somescript.sh uses) that caused <blah> to happen.

Co-Authored-By: Claude <noreply@anthropic.com>
```

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This project is a workspace with tooling for Claude Code to be guided to interact with Home Assistant and create/modify Node-RED automations (this part is WIP).

HA integration is available through the project MCP.

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

## Project structure

- `scripts/` - Shell scripts, to be directly called by Claude or by other scripts.
- `/.env` - Gitignored file containing settings for talking to Home Assistant.

### Scripts

- `scripts/check-env.sh` - Sourced by other scripts to load `.env` and verify required env vars are set.
- `scripts/run-hass-mcp.sh` - Runs the Home Assistant MCP server (used by the project MCP config).
- `scripts/download-nodered-flows.sh [output.json]` - Downloads the full Node-RED flow export from HA to a JSON file (default: `mynodered/nodered.json`). Output is normalized for stable diffs. Requires `uv`.
- `scripts/normalize-json.sh <file.json> [output.json]` - Normalizes a JSON file (sorts keys, sorts arrays of objects by `id`). In-place if no output path given.
- `scripts/check-nodered-flows-unchanged.sh <flows.json>` - Downloads live flows and diffs against the given file. Exits 0 if they match, 1 if diverged (prints diff to stderr). Use before uploading modified flows to catch concurrent edits.
- `scripts/summarize-nodered-flows.sh <flows.json>` - Prints a summary of flows and subflows from a flows JSON file.
- `scripts/query-nodered-flows.sh <flows.json> <command> [args...]` - Extracts specific subsets of a flows JSON: individual nodes, connected subgraphs, flow/group contents, subflow instances, function source code, and flexible search. Commands: `node`, `function`, `connected`, `head-nodes`, `tail-nodes`, `flow-nodes`, `group-nodes`, `subflow-nodes`, `subflow-instances`, `search`. Use `--summary` for compact one-liners. Use `--sources` with `flow-nodes`/`group-nodes` to get only entry-point nodes.

## Environment variables

- `HOMEASSISTANT_URL` - The URL to talk to home assistant (possibly `http://homeassistant.local:8123`)
- `HOMEASSISTANT_TOKEN` - The long-lived API token for talking to Home Assistant.

The env variables are loaded from .env for all scripts in the scripts dir. Env vars already declared when invoking a script take precedence.

If you add/change env vars, make sure you update scripts/check-env.sh and init.sh.

## Deep-dive documentation

The `docs/` directory contains detailed guides for specific tools and subsystems. These are
too long for CLAUDE.md but essential for effective use. Load the relevant doc when you start
a task involving that system.

- `docs/exploring-nodered-json.md` — How to use `summarize-nodered-flows.sh` and
  `query-nodered-flows.sh` to navigate Node-RED flows. **Load when:** working with
  `mynodered/nodered.json`, planning or implementing flow changes, or investigating
  automations.

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

# /planify — Convert a plan into the project's standard format

You are converting a plan into the standard format used by this project. Follow these steps exactly:

## Step 1: Find the next plan number
Run `ls plans/` and find the highest numeric prefix. The new plan number is that + 1.

## Step 2: Read the source plan
Read the plan file provided by the user (or the plan from the current conversation context). Understand its full scope.

## Step 3: Rewrite the plan

Convert the source plan into the standard format below. Every section is **required**.

### Required sections

#### `# Plan: <Title>`
Short descriptive title.

#### `## Context`
What problem this solves, why it's needed. Key design constraints as bullet points.

#### `## Architecture`
ASCII diagram showing how components connect. Show existing vs new parts.

#### `## New File Structure`
Tree listing of new/modified/deleted files with one-line descriptions per file.

#### `## Detailed Design`
Numbered sections (`### 1. path/to/file.py — Description`) with:
- Purpose and responsibilities
- Key classes/functions with **actual signatures** (not pseudocode)
- Important implementation notes

#### `## Phase-by-Phase Execution`
Each phase follows a strict TDD cycle:

```
RED → GREEN → REVIEW+FIX CYCLE → FULL SUITE → COMMIT
```

Each phase must have ALL of these sub-sections:

**Goal**: One sentence describing what this phase achieves.

**RED — Write failing tests**:
A table of specific test function names and what each checks:

| Test | What it checks |
|------|----------------|
| `test_function_name` | Description of the property being tested |

The test file path must be specified. Tests MUST fail initially (ImportError or AssertionError).
Run command: `cd <project_root> && uv run pytest <test_file> -v` — expect FAIL.
> **Note:** Adapt `cd backend` to the plan's working directory (e.g., `cd athena`, `cd .`) if the plan targets a different project root.

**GREEN — Implement**:
Numbered steps with specific files to create/modify and what to implement in each.
Run command: `cd <project_root> && uv run pytest <test_file> -v` — expect PASS.

**REVIEW+FIX CYCLE**:
This is a **loop**, not a single step. It uses the Claude Code Agent tool to spawn an Opus 4.6 sub-agent that reviews code, fixes issues, re-reviews, and repeats until clean — all within a single agent invocation.

Each phase MUST include an inline Agent tool call description block **right here**, tailored to that phase. The prompt must specify:
- Which files to review (the files created/modified in this phase)
- Phase-specific review concerns (e.g., "Is the bar boundary alignment correct?", "Is the SQL schema missing constraints?")
- What to fix if issues are found
- To run `cd backend && uv run pytest tests/ -v` after each fix
- To keep looping (review → fix → re-run tests) until review is clean and all tests pass

Format it as a description block inside the phase:
```
Launch Agent (subagent_type: "general-purpose", model: "claude-opus-4-6"):
  "Review Phase N of plans/<N>-<slug>.md: <phase goal>.
   Files to review: <list of files created/modified in this phase>.
   Check: all tests pass (cd backend && uv run pytest tests/ -v), code matches plan spec, no regressions.
   Phase-specific: <concrete review concerns for this phase>.
   If issues found: fix them, re-run tests, and review again. Repeat until review is clean.
   When review is clean and all tests pass, report DONE with a summary of changes made."
```

**FULL SUITE**: `cd backend && uv run pytest tests/ -v` — no regressions from prior phases.

**COMMIT**: `/commit` with message `"Phase N: <description>"`

**Files Created / Modified / Deleted**: Explicit lists.

#### `## Verification`
Final end-to-end verification commands (bash, curl, browser checks) to confirm the entire plan is complete.

## Step 4: Write the plan
Write the formatted plan to `plans/<N>-<slug>.md` where N is the next number and slug is a kebab-case name.

## Important rules
- Every phase MUST follow the RED → GREEN → REVIEW+FIX CYCLE → FULL SUITE → COMMIT flow
- The REVIEW+FIX CYCLE Agent sub-agent prompt MUST be inline inside each phase — NOT in a separate section at the bottom
- Test tables must list specific test function names and what they verify
- Code blocks must show actual function signatures, not pseudocode
- File paths must be real paths relative to the project root
- Each sub-agent review prompt must be scoped to that phase's files and tests only — no generic "review everything"
- Phases that are pure refactors (no new logic) may skip the RED step but MUST still have REVIEW+FIX CYCLE + FULL SUITE + COMMIT

## Execution model
- Each phase MUST be executed by a **separate Agent** (subagent_type: "general-purpose", model: "claude-opus-4-6"). This ensures each phase gets a fresh, full context window and avoids context exhaustion across a multi-phase plan.
- The orchestrating conversation should launch one Agent per phase, wait for it to complete, then launch the next.
- Add a note at the top of the `## Phase-by-Phase Execution` section in the generated plan:

```
> **Execution note:** Each phase below should be executed by a separate Agent invocation
> (subagent_type: "general-purpose", model: "claude-opus-4-6") to ensure a full context window per phase.
> The orchestrator launches one Agent per phase sequentially.
```

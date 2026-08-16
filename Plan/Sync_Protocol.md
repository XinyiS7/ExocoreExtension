# Sync Protocol — ExoCore Multi-Agent Collaboration

> **Purpose**: Shared operating rules for all agents (Claude Code, Gemini, G045, etc.) working in this repository.
> Load this file at session start to align with the current collaboration standard.

---

## Environment

- **Primary shell**: WSL/Ubuntu (Bash)
- **Python interpreter**: `/e/Miniconda3/envs/exocore_project/python.exe` (full path required in Git Bash; in WSL use the conda env activated in shell)
- **Command chaining**: `&&` (Linux syntax — never use `;` for sequential-dependent commands)
- **Working directory**: `/mnt/d/Alicia/ExoCore`

---

## Step 1 — Initialization

Before starting any task:

1. Read the task label or issue description carefully.
2. Verify environment: confirm WSL/Ubuntu context, not PowerShell.
3. Load relevant context files:
   - `CLAUDE.md` — architecture, conventions, anti-hallucination rules
   - `Plan/ExoCore_Pending_Tasks.md` — current task queue
   - `Plan/ExoCore_Worklog.md` — recent activity log
   - Any task-specific plan file if one exists

---

## Step 2 — Planning

**Plan before touching code.**

1. Write or update a plan file in `/Plan/` (e.g., `Plan/MyFeature_Plan.md`).
2. The plan MUST define:
   - **What**: exact functionality to add or change
   - **Where**: architectural layer (View / Service / Model / Serializer / Tool)
   - **Why**: motivation or constraint
   - **Steps**: ordered, atomic implementation steps
3. **Request review** of the plan before beginning implementation. Do not proceed until the plan is approved.

---

## Step 3 — Agent Coordination (Executor & Auditor)

To prevent race conditions, redundant work, or interrupted commands, agents must use `tmux-bridge` to coordinate strictly:

1. **Role Assignment**: After plan review, the user will designate one agent as the **Executor** (primary implementer) and the other as the **Auditor** (reviewer/helper).
2. **Pre-Execution Notice**: Before touching any code, the Executor MUST message the Auditor outlining the specific files/changes they are about to start. (e.g., "I am starting on `services.py`, please stand by.")
3. **Post-Execution Handover**: After finishing the scoped changes, the Executor MUST message the Auditor to review the work.
4. **Role Stability**: If the Executor encounters an error and asks the Auditor for help, **their roles do NOT change**. The Executor retains write-control, and the Auditor provides guidance. Roles persist through a whole block/module unless the user explicitly reassigns them.
5. **Parallel Exemption**: When two agents are confirmed to be working on **completely disjoint file sets** (e.g., one in Lua, one in Python/Bridge), they may proceed simultaneously without waiting for individual action notices, provided the architectural boundary was clear in the approved Plan.

---

## Step 4 — Principles

### First Principles Thinking
1. Identify the scope and scalability requirements.
2. Decompose into the smallest concrete sub-problems.
3. Build a solution from the ground up — no cargo-culting from prior patterns unless they genuinely fit.

### High Cohesion / Low Coupling
- Each module owns one concern; logic must not leak across layer boundaries.
- Views are thin (routing + request parsing only). Services own all business logic.
- Never write ORM queries or LLM calls directly inside a View.

### Anti-Hallucination (CRITICAL)
- **Never assume** a class, method, field, or API shape exists. Verify by reading source or grepping.
- No mock data, stub responses, or invented structures unless explicitly directed.

---

## Step 5 — Implementation

### Fail-fast Rule
- If an approach fails **twice** in a row: **stop**, log the failure with the error message, and ask for help. Do not retry blindly.

### Atomic Commits
Commit at each logical milestone, not at the end of the whole task. Suggested boundaries:
- After model/migration changes
- After service layer implementation
- After view/serializer wiring
- After tests pass

Commit message format: short imperative summary (≤72 chars), e.g.:
```
Add MemoryEntry scope auto-classification in async processor
```

### Code Quality During Implementation
- Remove dead code, unused imports, and redundant comments as you go.
- No silent failures — all errors must be logged or surfaced.
- Follow the quote convention: ASCII double quotes `"` as the outermost delimiter.

---

## Step 6 — Post-Review Checklist

Before running any test or requesting final review:

- [ ] All new imports resolve to real, existing symbols (grep to verify)
- [ ] All referenced model fields, methods, and serializer keys confirmed in source
- [ ] Data-flow traced end-to-end: request → view → service → model → response
- [ ] No cross-layer leaks introduced
- [ ] No `print()` debug statements left in production paths
- [ ] Migrations generated if models changed

---

## Step 7 — Completion

When a task is done:

1. **Update worklog**: append a summary entry to `Plan/ExoCore_Worklog.md`.
2. **Update task list**: mark the task complete in `Plan/ExoCore_Pending_Tasks.md`.
3. **Archive plan**: move completed plan files to `Plan/Archived/` if no longer active.
4. **Context compression**: summarize key decisions and outcomes — do not leave raw debug output or scratch notes in plan files.
5. Confirm with the requesting agent or user that the task is closed.

---

## Quick Reference

| Rule | Short form |
|------|-----------|
| Plan before code | Write `/Plan/<name>.md` first |
| Agent Coordination | Executor codes, Auditor reviews. Notice before/after. Roles are stable. |
| Fail twice → stop | Log error, ask for help |
| Thin views | All logic in Services |
| Verify before writing | Grep/Read, never assume |
| Atomic commits | One milestone = one commit |
| Clean up on done | Worklog + archive + compress |
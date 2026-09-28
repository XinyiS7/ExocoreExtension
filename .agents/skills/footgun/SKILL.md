---
name: footgun
description: Route recurring precautions to DevelopLog/warnings.md and diagnosed incidents to DevelopLog/DebugLog.md; use when an error appears or knowledge must be recorded
compatibility: pi
metadata:
  scope: exocore
---

# Skill: Fault Routing Protocol

`footgun` is a routing protocol, not a catalogue of mistakes.

- `[Alicia / approved]` Stable precautions belong in `DevelopLog/warnings.md`.
- `[Alicia / approved]` Diagnosed incidents, evidence chains, and architectural failures belong in `DevelopLog/DebugLog.md`.
- Historical cases must not be appended to this skill.

## 1. Before Work

Do not read this file as a substitute for project history. For M/H construction work, search both logs using the affected module, framework, symbol, and failure terms:

```bash
rg -n "<module|framework|error|invariant>" DevelopLog/warnings.md DevelopLog/DebugLog.md
```

Use the results differently:

- `warnings.md`: apply the relevant preflight check or precaution before editing/running.
- `DebugLog.md`: understand the prior evidence and root invariant; verify that the current failure is materially the same before reusing the old correction.

For L-risk documentation/skill/config work, a targeted warning search is sufficient unless an error appears.

## 2. Route a New Observation

### Route A — `DevelopLog/warnings.md`

Use a warning when all are true:

- the knowledge is a stable, recurring precaution;
- it can prevent failure before or during work;
- the corrective check is short and actionable;
- a full evidence narrative is unnecessary.

Typical subjects: shell/runtime differences, encoding, framework test semantics, known dependency behavior, provider wire-contract restrictions, or configuration switches that alter tests.

A warning entry contains only:

```markdown
### [YYYY-MM-DD] WARNING: <short name>
- **Context**: <modules/frameworks>
- **Precaution**: <what must be checked or avoided>
- **Quick Check**: <short command or observable condition>
- **Attribution**: [model / name]
```

### Route B — `DevelopLog/DebugLog.md`

Use DebugLog when any is true:

- root cause was unclear or required multiple diagnostic attempts;
- behavior crosses modules, transactions, persistence, concurrency, scheduler, provider, or process boundaries;
- the obvious/local correction failed or created sibling regressions;
- evidence is needed to distinguish the actual cause from plausible alternatives;
- the finding changes an architectural invariant or future debugging strategy.

A DebugLog entry records phenomenon, inference and evidence, confirmed root cause, correction, verification, affected versions/paths, and the reusable lesson. Preserve multi-author attribution for discovery, diagnosis, implementation, and approval.

### Route C — Do Not Persist

Do not create either entry for:

- spelling or formatting mistakes;
- one-off command typos with no reusable environment lesson;
- an already documented case with no new constraint;
- speculative causes that were not confirmed;
- session narration, emotional commentary, or generic advice.

If an existing entry needs one new constraint, update that entry rather than adding a near-duplicate.

## 3. Failure Escalation

1. **Known warning match**: apply the preflight/correction and verify the observable condition.
2. **Known DebugLog match**: compare versions, entry path, state, timing, and side effects before reusing the correction.
3. **New clear failure**: fix minimally, verify, then decide whether it has reusable warning value.
4. **Unclear, repeated, or architectural failure**: stop local patching and load the `debug`/diagnosis workflow. Record in DebugLog after the root cause is confirmed.
5. **Acceptance FAIL**: follow `builder-workflow` repair mode. The second failure of the same invariant requires a state/path/timing matrix; the third consecutive checkpoint FAIL enters Acceptance Adviser escalation.

Never use an empty catch, silent fallback, or a passing command as evidence that an exception path succeeded.

## 4. Knowledge Quality Gate

Before saving an entry, verify:

- the referenced class, field, method, setting, and command exist in current source;
- the entry says which versions/state conditions matter;
- the precaution does not contradict current project instructions or a newer DebugLog entry;
- no credentials, private session text, proprietary data, or unsanitized external query are included;
- attribution distinguishes contributor roles where more than one person/model participated.

After recording:

- run a targeted `rg` to ensure the entry is discoverable by likely module/error terms;
- avoid copying the same incident into this skill, both logs, and a Plan;
- use a Plan/acceptance report for task-specific chronology; use Engram only for durable cross-session decisions/root causes.

## 5. Ownership Summary

| Artifact | Owns | Does not own |
|---|---|---|
| `footgun` skill | classification and escalation rules | incident history |
| `DevelopLog/warnings.md` | concise recurring precautions | long diagnosis narratives |
| `DevelopLog/DebugLog.md` | confirmed root-cause/evidence records | preflight checklist catalogue |
| `Plan/` | task scope, sequence, acceptance evidence, chronology | global error taxonomy |
| Engram | durable cross-session decisions and root causes | session流水账 |

[gpt-5.6-sol / Solaire — 2026-08-10; routing boundary approved by Alicia]

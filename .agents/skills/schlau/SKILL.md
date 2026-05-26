# Skill: Smart Error Management (schlau)

## 1. Description
A systematic approach to error handling and knowledge persistence. This skill categorizes errors by resolution difficulty and ensures that every "lesson learned" is archived in a standardized format to prevent repetitive debugging.

## 2. The Three-Tier Error Protocol

### Tier 1: Known Pattern
- **Condition**: The error or a close variant already exists in `./DevelopLog/warnings.md` or `./DevelopLog/DebugLog.md`.
- **Action**: Apply the documented fix directly. Do not re-investigate from scratch.
- **Logging**: If the fix required adaptation, append a brief update note to the existing entry.

### Tier 2: New Error — Cause is Clear
- **Condition**: The error is new but the root cause is immediately apparent within 1-2 attempts.
- **Action**: Resolve, then log.
- **Logging**: Append a concise "Precaution" entry to the top of `./DevelopLog/warnings.md`. Focus on "What to avoid" and "The quick fix."

### Tier 3: Unclear Cause or Architectural Impact
- **Condition**: Root cause is not apparent after 2 attempts, OR the error implicates system architecture, data integrity, or multiple components.
- **Action**: **STOP immediately.** Do not keep guessing.
- **Review sequence**:
  1. Check `./DevelopLog/warnings.md` for related patterns.
  2. Check `./DevelopLog/DebugLog.md` for prior deep-dives on the same subsystem.
  3. If still unresolved, consult the user or the designated Collaborator Agent.
- **Logging**: After resolution, create or update `./DevelopLog/DebugLog.md` using the Deep-Dive template.

---

## 3. Standardized Documentation Formats

### [Template] ./DevelopLog/warnings.md
*Always append new entries to the TOP, separated by a horizontal rule.*

```markdown
---
### [YYYY-MM-DD] WARNING: {Short Error Name/Type}
- **Context**: {File/Component being worked on}
- **Precaution**: {Why it happened and what to check next time}
- **Quick Fix**: `Code or command snippet`
---
```

### [Template] ./DevelopLog/DebugLog.md
*Always append new entries to the TOP.*

```markdown
# DEBUG: {Issue Title} ({Status: Resolved/Pending})
- **Date**: YYYY-MM-DD
- **Phenomenon**: {Description of the error messages, behavior, or logs}
- **Inference & Evidence**:
    1. {Inference A}: {Why I think this? Supporting logs/code}
    2. {Inference B}: ...
- **Correction Plan**:
    - [Plan A]: {Implementation details}
    - [Plan B]: {Alternative approach}
- **Correction Result**: {Which plan worked? Final status and verification step}
---
```

## 4. Operational Mandate
The agent must prioritize "Persistence of Knowledge" over "Speed of Execution." A bug solved but not recorded is technical debt — every resolved issue must leave a trace.

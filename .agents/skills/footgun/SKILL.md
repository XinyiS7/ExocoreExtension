# Skill: Footgun

Quick-reference catalogue of environment-specific mistakes that waste time when repeated.
**Check this before running shell commands or editing Python files.**

## Shell Mistakes

### [2026-05-12] Assuming Common Python Packages are Installed
- **Context**: Python scripts or Django codebase tools (e.g., `agents/tools.py`).
- **Precaution**: Do not assume common packages like `psutil` or `requests` are present in the virtual environment. Always check `requirements.txt` before importing them dynamically, or you might cause silent `ModuleNotFoundError`s.
- **Quick Fix**: Prefer Python standard library fallbacks (e.g., `subprocess.run(["tasklist", ...])` instead of `psutil` on Windows) if the dependency isn't explicitly required.

### [2026-04-29] WSL Path in Bash Tool
- **Context**: Bash tool runs WSL bash, not Git Bash. Django management commands + file paths.
- **Precaution**: Django commands and Windows path operations MUST use **PowerShell**, not Bash. Git commands can use both, but prefer PS for consistency.
- **Quick Fix**: Use `PowerShell` tool: `cd D:\Alicia\ExoCore_Project\ExoCore; python.exe manage.py <cmd>`

### [2026-04-29] Smart Quotes in Python Source
- **Context**: Editing Python files with Chinese docstrings via Edit tool.
- **Precaution**: `"` `"` (U+201C/U+201D) and `'` `'` (U+2018/U+2019) cause `SyntaxError` in Python. The Edit tool may auto-convert typed ASCII quotes when mixed with Chinese text.
- **Quick Fix**: `$content -replace [char]0x201C, '"' -replace [char]0x201D, '"' -replace [char]0x2018, "'" -replace [char]0x2019, "'"`

### PowerShell Command Chaining
- **Precaution**: Do NOT use `&&` to chain commands (causes `ParserError`). Use `;` instead.
- **Quick Fix**: `git add . ; git commit -m "..."`

### Unix vs Windows Tools
- **Precaution**: DO NOT use `find .` for file searching; it invokes the Windows string search utility. Use `Get-ChildItem` or Claude Code's `Glob`/`Grep` tools.

### Virtual Environment Hazards
- **Precaution**: Recursive file operations often fail on `.venv/lib64` due to symlink loops. Always exclude `.venv` or target specific app directories.

### Conda Interpreter
- **Precaution**: Conda env `exocore_project` is pre-activated in WezTerm. Use `python.exe` directly.

---

## Tool Loop Mistakes

### [2026-05-18] Gemini/OpenAI Tool Loop Conflation
- **Context**: `agents/services.py` — Superior tool loop (`_run_tool_loop`) and simple tool loop (`_stream_with_tools`).
- **Precaution**: Gemini and OpenAI have FUNDAMENTALLY different tool passback mechanisms:
  - **Gemini**: thinking goes in user-FR `[prior_reasoning]` text parts; response content goes in model turn as regular content. NEVER put thinking on the model turn.
  - **OpenAI/DeepSeek**: thinking MUST be `reasoning_content` on the assistant message. Content goes as `content` on the assistant message. Omitting `reasoning_content` causes 400 errors from DeepSeek.
- **Quick Fix**: Use `LLMGateway.build_gemini_tool_round()` / `build_openai_tool_round()` instead of calling `make_fc_assistant_turn` + `make_tool_result_turns` directly. The builders encapsulate all platform-specific parameter routing.
- **Design Principle**: Think of the model's flow as `.think → .say → tool → .think → .say → final`. Thinking is CoT (not output, user can't see). Response content IS output (user sees it, DB records it). The model must see its own intermediate content as proper output to continue coherently.

---

## The Three-Tier Error Protocol

### Tier 1: Known Pattern
- **Condition**: The error or a close variant already exists in this file or `./DevelopLog/DebugLog.md`.
- **Action**: Apply the documented fix directly. Do not re-investigate from scratch.
- **Logging**: If the fix required adaptation, append a brief update note.

### Tier 2: New Error - Cause is Clear
- **Condition**: The error is new but root cause is immediately apparent within 1-2 attempts.
- **Action**: Resolve, then log.
- **Logging**: Append to the top of the relevant section above. Focus on "What to avoid" and "The quick fix."

### Tier 3: Unclear Cause or Architectural Impact
- **Condition**: Root cause not apparent after 2 attempts, OR implicates system architecture, data integrity, or multiple components.
- **Action**: **STOP immediately.** Do not keep guessing.
- **Review sequence**:
  1. Check this file for related patterns.
  2. Check `./DevelopLog/DebugLog.md` for prior deep-dives.
  3. If still unresolved, consult the user.
- **Logging**: After resolution, create or update `./DevelopLog/DebugLog.md` using the template below.

---

## Standardized Documentation Formats

### [Template] Shell Mistakes Entry
*Append to the TOP of the Shell Mistakes section.*

```markdown
### [YYYY-MM-DD] {Short Error Name}
- **Context**: {File/Component}
- **Precaution**: {Why it happened, what to check}
- **Quick Fix**: `Code or command snippet`
```

### [Template] ./DevelopLog/DebugLog.md
*Append new entries to the TOP.*

```markdown
# DEBUG: {Issue Title} ({Status})
- **Date**: YYYY-MM-DD
- **Phenomenon**: {Error messages, behavior, logs}
- **Inference & Evidence**:
    1. {Inference}: {Why I think this? Evidence}
- **Correction Plan**:
    - [Plan A]: {Details}
- **Correction Result**: {What worked? Verification step}
```

## Operational Mandate
Prioritize **Persistence of Knowledge** over **Speed of Execution**. A bug solved but not recorded is technical debt.

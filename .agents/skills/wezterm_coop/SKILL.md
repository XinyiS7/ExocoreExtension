# Skill: WezTerm Multi-Agent Cooperation (wezterm_coop)

## 1. Description
Standards and operational procedures for high-fidelity multi-agent collaboration within the WezTerm environment. This skill ensures synchronization between the Primary Agent (Executor) and the Auditor Agent across panes.

2. Environment Standards
Primary Shell: WezTerm running git bash is the absolute priority. All agents must default to standard Bash syntax (e.g., echo, tail, forward slashes /) for system operations.

Fallback Shell: powershell-gramma is the fallback ONLY if Git Bash is strictly unavailable.

Python Environment: Conda environment exocore_project must be pre-activated.

Command Syntax: Use python directly for script execution. Do NOT use absolute interpreter paths unless troubleshooting environment desync.

3. Collaboration Protocol
Primary Agent (Executor): Responsible for research, strategy, and execution. Runs in the primary working pane.

Auditor Agent: Responsible for security audit, architectural review, and safety confirmation. Runs in the designated auditor pane (configured per session).

Mandatory Audit: Every file modification or database schema change performed by the Primary Agent MUST be reviewed and approved by the Auditor before finalization.

WezTerm cross-pane protocol (read → send → verify → submit):
**Primary**: Git Bash (Priority):
```bash
wezterm cli list                                                 # 1. discover pane IDs
wezterm cli get-text --pane-id <id> | tail -n 20                 # 2. READ before acting
echo -e "[from: <agent>]\n<message>" | wezterm cli send-text --pane-id <id> --no-paste 
                                                                 # 3. SEND (no Enter yet)
wezterm cli get-text --pane-id <id> | tail -n 10                 # 4. VERIFY text landed
echo -ne "\n" | wezterm cli send-text --pane-id <id> --no-paste  # 5. SUBMIT (Enter)
```
Fallback: PowerShell (Only if Bash is unavailable):
```powershell
wezterm cli list                                                 # 1. discover pane IDs
(wezterm cli get-text --pane-id <id>) -split "`n" | Select-Object -Last 20 
                                                                 # 2. READ before acting
Write-Output "[from: <agent>]`n<message>" | wezterm cli send-text --pane-id <id> --no-paste 
                                                                 # 3. SEND (no Enter yet)
(wezterm cli get-text --pane-id <id>) -split "`n" | Select-Object -Last 10 
                                                                 # 4. VERIFY text landed
wezterm cli send-text --pane-id <id> --no-paste "`r"             # 5. SUBMIT (Enter)
```

## 4. Operational Workflow

### Phase 1: Context Synchronization
- Before starting a new task, the Primary Agent must read the active `Plan/*.md` files and the agent's context file (`CLAUDE.md` / `GEMINI.md` as applicable) to align with the global state.
- The Primary Agent must provide a concise "Work Plan" to the user and wait for acknowledgment.

### Phase 2: Audited Execution
1. **Prepare**: The Primary Agent prepares the code change or SQL command.
2. **Review**: The Primary Agent presents the proposed change to the user (who bridges it to the Auditor for review).
3. **Act**: Only after receiving the "Audit Passed" signal, the Primary Agent applies the change.
4. **Log**: Update `Plan/ExoCore_Worklog.md` immediately after successful execution.

### Phase 3: State Persistence
- The Primary Agent must use `state_snapshot` in session summaries to preserve the `task_state`, `active_constraints`, and `artifact_trail` for the next session.

## 5. Security & Safety
- **Credential Protection**: Never print or commit `.env` content.
- **Environment Isolation**: Always exclude `.venv`, `.git`, and `chroma_db` from recursive searches to prevent infinite loops or data leakage.
- **Error Logging**: Any environment-specific failure (e.g., PowerShell syntax error) must be recorded in the "Agent Operational Memo & Error Log" section of the agent's operational context file.

## 6. Success Metrics
- Zero un-audited file modifications.
- 100% synchronization between `Worklog` and actual repository state.
- Successful execution of `python test_rag.py` after retrieval-related changes.

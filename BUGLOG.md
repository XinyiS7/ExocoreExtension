# ExoCore Extension - Debug Log

## Issue 1: Command Queue File Path Resolution Failure
**Symptom:** `PollCmdQueue failed to open: exo_cmd_queue.txt Error: nil`
**Reasoning:** Klei's sandbox enforces strict pathing. Earlier, `if GLOBAL.TheSim and GLOBAL.TheSim.GetGamePersistentSavePath` was used to check if the C-userdata had the method before calling it. However, indexing a missing method on Klei's C-userdata might raise an exception, completely aborting that line and skipping the path resolution logic entirely (meaning the `Evaluated queue path:` print statement was never reached). Because it aborted, it fell back to just `exo_cmd_queue.txt` which failed to open in whatever the default working directory is.
**Fix:** Wrapped the method call entirely in `GLOBAL.pcall(function() return GLOBAL.TheSim:GetGamePersistentSavePath() end)`. This safely attempts the function call, catches any userdata exceptions, and successfully extracts the path if available.
**Result:** Code modified in `dst_mod_source/modmain.lua`. Awaiting user test.

## Issue 2: Incorrect Player State (Health/Hunger/Sanity)
**Symptom:** `[EXO_STATE]` reports correct weather/time but wrong player stats. User reported "actual sanity 159, hunger 67". Alternatively, user sees exactly "100" for these values when manually triggering via console in-game.
**Reasoning:** 
1. **Client/Server Split:** In "Host Game" mode, the game runs both a Server and a Client locally. The `ExportState` periodic task was running on both. On the Server, it correctly read `components.health` and wrote real values to `Master/server_log.txt`. On the Client, `components` is `nil`, triggering the `or 100` fallback and spamming the in-game `client_log.txt` with 100s. The AI Python script was actually reading the correct Server log, but the user was seeing the faulty Client log, causing confusion.
**Fix:** Wrapped the `AddGamePostInit` periodic tasks in `modmain.lua` with `if GLOBAL.TheWorld.ismastersim then` so it only executes on the Server. Increased sync frequency from 30s to 10s.
**Result:** Code modified. Client console spam stopped. AI gets fresh data.

## Issue 3: Missing In-Game Messages & Chat Sync
**Symptom:** AI responses appear in Python console but not in game. Player chat in-game doesn't trigger AI.
**Reasoning:** 
1. **Chat Log Location:** The player's chat was being routed to `D:\Documents\Klei\DoNotStarveTogether\client_chat_log.txt` rather than `Cluster_4\Master\server_chat_log.txt`. Python was listening to the wrong file.
2. **Multiline Lua Parsing:** Python sent `if ... then ... end` multiline blocks to `exo_cmd_queue.txt`. `modmain.lua` parsed the queue using `gmatch("[^\n]+")` (line-by-line), causing a syntax error on execution.
**Fix:** 
1. Pointed `_resolve_chat_file` in `extension.py` to check for `client_chat_log.txt` in the root DST directory first.
2. Flattened the Lua message response in `extension.py` to a single `c_announce("[Alessandro] ...")` command, making it syntactically safe and globally visible. Added `c_announce` feedback for when the AI is triggered.
**Result:** Code modified, awaiting confirmation on chat trigger. Commands still failing to execute (see Issue 4).

## Issue 4: Command Queue Ignored / Sandbox I/O Restriction
**Symptom:** Python successfully writes commands (`c_announce`, `c_sethealth(1)`) to `Cluster_4/Master/exo_cmd_queue.txt`. The file accumulates lines and is never emptied by the game, meaning the commands are never executed.
**Reasoning:** 
1. **Sandbox Restriction:** DST's Lua sandbox heavily restricts or outright blocks standard `io.open` for security, even if the path prefix (`APP:Klei/...`) is technically correct. The `io.open` call silently fails (returns `nil` for the file handle).
2. **Directory Mismatch:** `TheSim:GetGamePersistentSavePath()` typically resolves to the `save/` subdirectory (e.g., `Cluster_4/Master/save/`), while Python is writing to the `Master/` root. 
**Proposed Solution:** Abandon standard Lua `io.open`. Instead, use Klei's official async I/O API: `GLOBAL.TheSim:GetPersistentString()` and `GLOBAL.TheSim:SetPersistentString()`. Python must be updated to write the queue file into the `Master/save/` folder to align with this API.
**Result:** Pending implementation.


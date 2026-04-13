-- ============================================================
-- ExoCore DST Bridge mod
-- ============================================================
-- OUT (Python reads):  server_log.txt  — [EXO_STATE] JSON dumps
-- IN  (Python writes): exo_cmd_queue.txt — one Lua command per line
-- ============================================================

-- Relative path — resolves to the shard's working directory (Master/)
-- Python locates it via _resolve_log_dir() + "exo_cmd_queue.txt"
local CMD_QUEUE_FILE = "exo_cmd_queue.txt"

-- ----------------------------------------------------------
-- State export (game → Python direction)
-- ----------------------------------------------------------

local function ExportState(is_forced)
    -- ThePlayer is nil on a dedicated server (server-side process has no local player).
    -- Fall back to the first entry in AllPlayers so dedicated servers work too.
    local player = GLOBAL.ThePlayer
    if player == nil and GLOBAL.AllPlayers and #GLOBAL.AllPlayers > 0 then
        player = GLOBAL.AllPlayers[1]
    end
    if player == nil then return end

    local state = {
        health    = player.components.health  and player.components.health:GetPercent()  * 100 or 100,
        hunger    = player.components.hunger  and player.components.hunger:GetPercent()  * 100 or 100,
        sanity    = player.components.sanity  and player.components.sanity:GetPercent()  * 100 or 100,
        time      = GLOBAL.TheWorld.state.phase,
        day       = GLOBAL.TheWorld.state.cycles + 1,
        is_raining = GLOBAL.TheWorld.state.israining,
        is_forced = is_forced or false,
    }

    print("[EXO_STATE] " .. GLOBAL.json.encode(state))
end

-- Manual sync: F8 — only on listen-server / local host, not headless dedicated
if not GLOBAL.TheNet:IsDedicated() then
    GLOBAL.TheInput:AddKeyUpHandler(GLOBAL.KEY_F8, function()
        print("[ExoCore] F8 Pressed - Forcing state export...")
        ExportState(true)
    end)
end

-- ----------------------------------------------------------
-- Command queue polling (Python → game direction)
-- ----------------------------------------------------------

local function PollCmdQueue()
    -- io is not directly in the mod sandbox; access via GLOBAL (same pattern as pcall)
    local f = GLOBAL.io.open(CMD_QUEUE_FILE, "r")
    if not f then return end

    local content = f:read("*a")
    f:close()

    if not content or content == "" then return end

    local w = GLOBAL.io.open(CMD_QUEUE_FILE, "w")
    if w then w:close() end

    for line in content:gmatch("[^\n]+") do
        line = line:match("^%s*(.-)%s*$")
        if line ~= "" then
            local fn, err = loadstring(line)
            if fn then
                local ok, run_err = pcall(fn)
                if ok then
                    print("[ExoCore CMD] OK: " .. line)
                else
                    print("[ExoCore CMD] Runtime error: " .. tostring(run_err))
                end
            else
                print("[ExoCore CMD] Compile error: " .. tostring(err))
            end
        end
    end
end

-- ----------------------------------------------------------
-- Defer task registration to next tick after world is ready.
-- Calling DoPeriodicTask directly inside AddGamePostInit fires
-- during world init and can corrupt internal scheduler state.
-- DoTaskInTime(0, ...) pushes registration to the first clean tick.
-- ----------------------------------------------------------

AddGamePostInit(function()
    -- AddGamePostInit fires on the client frontend too (TheWorld is nil there).
    -- Only register tasks when an actual world exists (dedicated server / listen server).
    if GLOBAL.TheWorld == nil then return end

    GLOBAL.TheWorld:DoTaskInTime(0, function()
        GLOBAL.TheWorld:DoPeriodicTask(30, function() ExportState(false) end)
        GLOBAL.TheWorld:DoPeriodicTask(1, function()
            local ok, err = GLOBAL.pcall(PollCmdQueue)
            if not ok then print("[ExoCore] PollCmdQueue error: " .. tostring(err)) end
        end)
        print("[ExoCore] Tasks registered — state export + command queue active.")
    end)
    print("[ExoCore] World ready.")
end)

print("[ExoCore] Mod initialized.")

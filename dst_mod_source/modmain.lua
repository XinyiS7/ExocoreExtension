-- ============================================================
-- ExoCore DST Bridge mod
-- ============================================================
-- OUT (Python reads):  server_log.txt  — [EXO_STATE] JSON dumps
-- IN  (Python writes): exo_cmd_queue.txt — one Lua command per line
-- ============================================================

local CMD_QUEUE_FILE = "exo_cmd_queue.txt"

-- ----------------------------------------------------------
-- State export (game → Python direction)
-- ----------------------------------------------------------

local function ExportState(is_forced)
    local player = GLOBAL.ThePlayer
    if player == nil and GLOBAL.AllPlayers and #GLOBAL.AllPlayers > 0 then
        player = GLOBAL.AllPlayers[1]
    end
    if player == nil then return end

    local health_val = player.components.health and player.components.health.currenthealth or 100
    local hunger_val = player.components.hunger and player.components.hunger.current or 100
    local sanity_val = player.components.sanity and player.components.sanity.current or 100

    local state = {
        health    = health_val,
        hunger    = hunger_val,
        sanity    = sanity_val,
        time      = GLOBAL.TheWorld.state.phase,
        day       = GLOBAL.TheWorld.state.cycles + 1,
        is_raining = GLOBAL.TheWorld.state.israining,
        is_forced = is_forced or false,
    }

    print("[EXO_STATE] " .. GLOBAL.json.encode(state))
end

if not GLOBAL.TheNet:IsDedicated() then
    GLOBAL.TheInput:AddKeyUpHandler(GLOBAL.KEY_F8, function()
        print("[ExoCore] F8 Pressed - Forcing state export...")
        ExportState(true)
    end)
end

-- ----------------------------------------------------------
-- Command Execution Helper
-- ----------------------------------------------------------

local function ExecuteLuaLine(line)
    line = line:match("^%s*(.-)%s*$")
    if line == "" then return end

    local fn, err = GLOBAL.loadstring(line)
    if fn then
        local target = GLOBAL.ThePlayer or (GLOBAL.AllPlayers and GLOBAL.AllPlayers[1])
        
        -- Create a dedicated environment for the command
        local env = {
            ThePlayer = target,
            TheNet = GLOBAL.TheNet,
            TheWorld = GLOBAL.TheWorld,
            AllPlayers = GLOBAL.AllPlayers,
            -- Wrap helpers to ensure they use our target player
            c_give = function(prefab, count) 
                if GLOBAL.c_give then 
                    -- Force the helper to use our target
                    local old = GLOBAL.ConsoleCommandPlayer
                    GLOBAL.ConsoleCommandPlayer = function() return target end
                    GLOBAL.c_give(prefab, count)
                    GLOBAL.ConsoleCommandPlayer = old
                end 
            end,
            c_announce = GLOBAL.c_announce or function(msg) if GLOBAL.TheNet then GLOBAL.TheNet:Announce(msg) end end,
            c_spawn = GLOBAL.c_spawn,
            c_sethealth = function(v) if target and target.components.health then target.components.health:SetPercent(v) end end,
            c_sethunger = function(v) if target and target.components.hunger then target.components.hunger:SetPercent(v) end end,
            c_setsanity = function(v) if target and target.components.sanity then target.components.sanity:SetPercent(v) end end,
        }
        GLOBAL.setmetatable(env, { __index = GLOBAL })
        GLOBAL.setfenv(fn, env)
        
        local ok, run_err = GLOBAL.pcall(fn)
        if ok then
            print("[ExoCore CMD] OK: " .. line .. " (Target: " .. GLOBAL.tostring(target) .. ")")
        else
            print("[ExoCore CMD] Runtime error: " .. GLOBAL.tostring(run_err))
        end
    else
        print("[ExoCore CMD] Compile error: " .. GLOBAL.tostring(err))
    end
end

-- ----------------------------------------------------------
-- Command queue polling (Python → game direction)
-- ----------------------------------------------------------

local function PollCmdQueue()
    -- Use Klei's official asynchronous persistent string API.
    -- This inherently looks in the save/ directory of the active shard
    -- and bypasses strict io.open sandbox restrictions.
    GLOBAL.TheSim:GetPersistentString(CMD_QUEUE_FILE, function(success, content)
        if success and content and content ~= "" then
            -- Immediately clear the file so we don't double-execute
            GLOBAL.TheSim:SetPersistentString(CMD_QUEUE_FILE, "", false, function() end)
            
            for line in content:gmatch("[^\n]+") do
                ExecuteLuaLine(line)
            end
        end
    end)
end

-- ----------------------------------------------------------
-- Chat Hook (Game Chat → Command Execution)
-- ----------------------------------------------------------

-- Add a chat hook to allow executing commands via prefix !
-- This works even if the external file polling fails.
-- Example: "!c_give('log', 10)" in game chat.
local function OnSay(guid, userid, name, message, mode, ...)
    if message and message:sub(1, 1) == "!" then
        local command = message:sub(2)
        print("[ExoCore ChatCMD] Executing: " .. command .. " from " .. name)
        ExecuteLuaLine(command)
    end
end

-- ----------------------------------------------------------
-- Initialization
-- ----------------------------------------------------------

AddGamePostInit(function()
    if GLOBAL.TheWorld == nil then return end

    GLOBAL.TheWorld:DoTaskInTime(0, function()
        -- ONLY run the background polling and state dumping on the Server!
        -- This prevents the Client (which lacks components) from logging '100's to the in-game console.
        if GLOBAL.TheWorld.ismastersim then
            -- Increased sync frequency to 10 seconds for tighter AI response
            GLOBAL.TheWorld:DoPeriodicTask(10, function() ExportState(false) end)
            
            -- Poll queue every 1 second
            GLOBAL.TheWorld:DoPeriodicTask(1, function()
                local ok, err = GLOBAL.pcall(PollCmdQueue)
                if not ok then print("[ExoCore] PollCmdQueue error: " .. GLOBAL.tostring(err)) end
            end)
            
            print("[ExoCore Server] Tasks registered — state export (10s) + command queue (1s) active.")
        else
            print("[ExoCore Client] Running in client mode. Suppressing background state exports.")
        end
        
        -- Register chat hook (this can run everywhere, it filters internally)
        if GLOBAL.TheNet and GLOBAL.TheNet.IsDedicated and GLOBAL.TheNet:IsDedicated() then
            -- On dedicated servers, we hook into Networking_Say
            GLOBAL.TheWorld:ListenForEvent("networking_say", function(world, data)
                if data and data.message then
                    OnSay(data.guid, data.userid, data.name, data.message, data.mode)
                end
            end)
        else
            -- On non-dedicated, we can use the same event
            GLOBAL.TheWorld:ListenForEvent("networking_say", function(world, data)
                if data and data.message then
                    OnSay(data.guid, data.userid, data.name, data.message, data.mode)
                end
            end)
        end

        print("[ExoCore] Tasks registered — state export + command queue + chat hook active.")
    end)
    print("[ExoCore] World ready.")
end)

print("[ExoCore] Mod initialized.")

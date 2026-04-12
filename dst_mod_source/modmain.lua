local function ExportState(is_forced)
    local player = GLOBAL.ThePlayer
    if player == nil then return end

    local state = {
        health = player.components.health and player.components.health:GetPercent() * 100 or 100,
        hunger = player.components.hunger and player.components.hunger:GetPercent() * 100 or 100,
        sanity = player.components.sanity and player.components.sanity:GetPercent() * 100 or 100,
        time = GLOBAL.TheWorld.state.phase,
        day = GLOBAL.TheWorld.state.cycles + 1,
        is_raining = GLOBAL.TheWorld.state.israining,
        is_forced = is_forced or false
    }

    print("[EXO_STATE] " .. GLOBAL.json.encode(state))
end

-- Key listener for manual sync (F8)
GLOBAL.TheInput:AddKeyUpHandler(GLOBAL.KEY_F8, function()
    print("[ExoCore] F8 Pressed - Forcing state export...")
    ExportState(true)
end)

-- Auto-export every 30 seconds
GLOBAL.TheWorld:DoPeriodicTask(30, function()
    ExportState(false)
end)

print("[ExoCore] Mod initialized and exporting state.")

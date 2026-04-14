# DST Game Knowledge & Commands

## Basic Commands
- `c_give("item_code", count)`: Give item to player's inventory.
- `c_spawn("prefab_code", count)`: Spawn entity at cursor.
- `c_sethealth(percent)`: Set player health (percent is 0.0 to 1.0, e.g., 1 is 100%).
- `c_sethunger(percent)`: Set player hunger (percent is 0.0 to 1.0).
- `c_setsanity(percent)`: Set player sanity (percent is 0.0 to 1.0).
- `TheWorld:PushEvent("ms_nextphase")`: Skip to next day phase.

## Common Item Codes
- Resources: `log`, `twigs`, `cutgrass`, `flint`, `rocks`.
- Food: `berries`, `carrot`, `meat`, `cookedmeat`, `healingsalve`.
- Tools: `axe`, `pickaxe`, `shovel`.
- Light: `torch`, `campfire`.

## Mod Specifics (Stub)
- TBD: Add custom mod item codes here.

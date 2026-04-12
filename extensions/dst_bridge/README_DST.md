# DST Bridge Extension - 使用手册

## 1. 架构原理
本扩展采用 **"感知-决策-执行"** 三段式结构：
- **感知 (Watcher)**: 监控本地 `state.json` 文件。
- **决策 (ExoCore)**: 使用 Gemini 2.5 Flash 模型，结合 `knowledge.md` 和滑动窗口上下文进行推理。
- **执行 (Executor)**: 解析模型回复中的 `[EXEC]` 标签，并通过 stdin 将 Lua 代码注入游戏。

## 2. 游戏端 Mod 协议
你的 Lua Mod 需要定时执行以下操作：
```lua
local data = {
    health = ThePlayer.components.health.currenthealth,
    hunger = ThePlayer.components.hunger.currentquery,
    time = TheWorld.state.phase, -- "day", "dusk", "night"
    inventory = {"log", "flint"}, -- 举例
}
-- 将 data 编码为 JSON 并保存到 state.json
```

## 3. 触发规则
目前在 `extension.py` 中定义了以下自动咨询触发点：
- `health < 50`
- `time == "dusk"`
- 用户手动点击 "Sync Now"

## 4. 扩展指令格式
Alessandro (AI) 被告知使用以下格式下达指令：
- **聊天**: 直接回复文本。
- **执行**: 使用 `[EXEC] ... [/EXEC]` 包裹 Lua 代码。
  - 例如: `[EXEC] c_give("log", 10) [/EXEC]`

## 5. 知识库自定义
编辑 `knowledge.md` 可以告诉模型关于这个存档的特殊信息（如 Mod 物品 ID、你的生存目标等）。

## 6. 配置项
- **路径**: 在 `extension.py` 的 `__init__` 中修改 `state_file` 路径。
- **上下文**: 在 `context_manager.py` 中修改 `max_history` 调整记忆长度。

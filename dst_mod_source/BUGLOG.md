# ExoCore DST Bridge Mod — Bug Record

## 症状
服务器启动后约 1 秒内出现 `[IPC] Received shutdown signal.`，无任何 Lua 报错（服务器日志干净）。

---

## Bug 1 — `DoPeriodicTask` 在 `AddGamePostInit` 内直接调用导致调度器损坏

**错误行为**：在 `AddGamePostInit` 回调中直接调用 `TheWorld:DoPeriodicTask()`，在世界初始化期间触发，破坏内部调度器状态，导致服务器无声崩溃。

**修复**：用 `TheWorld:DoTaskInTime(0, fn)` 将任务注册推迟到下一个干净的 tick。

```lua
-- ❌ 崩溃
AddGamePostInit(function()
    GLOBAL.TheWorld:DoPeriodicTask(30, ExportState)
end)

-- ✅ 正确
AddGamePostInit(function()
    GLOBAL.TheWorld:DoTaskInTime(0, function()
        GLOBAL.TheWorld:DoPeriodicTask(30, ExportState)
    end)
end)
```

---

## Bug 2 — `AddGamePostInit` 在客户端前端触发，`TheWorld` 为 nil

**错误信息**：
```
[00:00:10]: error calling gamepostinit in mod ExoCore Bridge Mod:
modmain.lua:83: attempt to index field 'TheWorld' (a nil value)
[00:00:10]: Disabling ExoCore Bridge Mod because it had an error.
```

**根本原因**：`AddGamePostInit` 在专用服务器和客户端（主菜单界面）上都会触发。客户端前端没有世界（`TheWorld == nil`），`DoTaskInTime` 调用直接 nil 崩溃。mod 被禁用后，整个会话启动失败，服务器日志只显示 IPC shutdown，看不到真正的 Lua 错误（因为错误发生在客户端日志里）。

**为什么难以发现**：服务器日志里完全看不到客户端错误，只能看到 IPC shutdown 的下游效果。

**修复**：在 `AddGamePostInit` 顶部加 nil guard。

```lua
AddGamePostInit(function()
    if GLOBAL.TheWorld == nil then return end  -- 跳过客户端前端
    GLOBAL.TheWorld:DoTaskInTime(0, function()
        -- ...
    end)
end)
```

---

## Bug 3 — `pcall` 在 mod 沙盒中不可用

**错误信息**：
```
modmain.lua:90: attempt to call global 'pcall' (a nil value)
```

**根本原因**：DST mod 沙盒环境中，标准 Lua 全局函数（如 `pcall`、`tostring`）不在直接作用域内，需要通过 `GLOBAL` 访问。

**修复**：
```lua
-- ❌ 崩溃
local ok, err = pcall(PollCmdQueue)

-- ✅ 正确
local ok, err = GLOBAL.pcall(PollCmdQueue)
```

---

## Bug 4 — `io` 在 mod 沙盒中不可用

**错误信息**：
```
[ExoCore] PollCmdQueue error: [string "../mods/ExoCore Bridge Mod/modmain.lua"]:46:
attempt to index global 'io' (a nil value)
```

**根本原因**：与 Bug 3（`pcall`）同理。DST mod 沙盒不暴露标准 Lua 全局库 `io`，须通过 `GLOBAL.io` 访问。

**修复**：
```lua
-- ❌ 崩溃
local f = io.open(CMD_QUEUE_FILE, "r")
local w = io.open(CMD_QUEUE_FILE, "w")

-- ✅ 正确
local f = GLOBAL.io.open(CMD_QUEUE_FILE, "r")
local w = GLOBAL.io.open(CMD_QUEUE_FILE, "w")
```

**通用规则**：mod 沙盒内所有标准 Lua 全局（`io`、`os`、`pcall`、`tostring` 等）均需通过 `GLOBAL` 访问，否则为 nil。

---

## 诊断方法

服务器无声崩溃时，使用**二分法 modmain.lua**逐步注释代码段，找到最小崩溃复现步骤。同时检查**客户端日志**（而非只看服务器日志），因为客户端 mod 错误不会出现在服务器日志中。

---

## Bug 5 — `loadstring` 加载的代码环境受限

**症状**：AI 回复能被 Python 接收，但 `TheNet:Announce` 和 `c_give` 等上帝指令在游戏中无效且无报错。

**根本原因**：`loadstring` 创建的函数默认运行在 mod 的 local 环境中，无法访问游戏真正的全局变量（如 `TheNet`）。

**修复**：使用 `GLOBAL.setfenv(fn, GLOBAL)` 显式将加载的代码环境切换到游戏全局环境。

```lua
local fn, err = GLOBAL.loadstring(line)
if fn then
    GLOBAL.setfenv(fn, GLOBAL) -- 注入全局环境
    GLOBAL.pcall(fn)
end
```

---

## Bug 6 — `GLOBAL.` 前缀遗漏导致的静默失败

**症状**：`PollCmdQueue` 在执行过程中可能崩溃，导致后续指令无法处理。

**根本原因**：在 `PollCmdQueue` 内部和 `DoPeriodicTask` 的回调中，部分 `loadstring`, `pcall`, `tostring` 遗漏了 `GLOBAL.` 前缀。

**修复**：确保所有沙盒外函数均通过 `GLOBAL.` 访问。

---

## Bug 7 — Lua 沙盒对 `io.open` 的严格读写限制导致 IPC 队列失效

**症状**：Python 能够正确将 `c_announce` 写入到 `Cluster_4/Master/exo_cmd_queue.txt`，但游戏内毫无反应。外部的文本文件内容不断累积，说明游戏中的 `PollCmdQueue` 根本没有成功读取并清空它。

**根本原因**：
1. **沙盒限制**：即便我们通过 `TheSim:GetGamePersistentSavePath()` 拿到了被沙盒认可的 `APP:Klei/...` 路径，DST 的安全策略通常也禁止使用标准的 `GLOBAL.io.open` 读取非官方格式或特定目录外的文件，导致 `io.open` 默默返回 `nil` 并触发错误日志。
2. **目录错位**：`GetGamePersistentSavePath` 指向的是存档底层的 `save/` 文件夹（例如 `Master/save/`），而 Python 此时是把文件写在 `Master/` 目录下。

**修复计划**：
废弃不可靠的 `io.open`。改用 Klei 官方允许的文件 I/O API：`GLOBAL.TheSim:GetPersistentString()` 和 `GLOBAL.TheSim:SetPersistentString()`。
这两个 API 强制在 `save/` 目录下读写。因此，需要：
1. Python 端：将 `exo_cmd_queue.txt` 写入到 `Cluster_4/Master/save/exo_cmd_queue.txt`。
2. Lua 端：使用 `GetPersistentString("exo_cmd_queue.txt", callback)` 来读取并清空指令。

---

*记录日期：2026-04-14*


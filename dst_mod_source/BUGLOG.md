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

*记录日期：2026-04-12*

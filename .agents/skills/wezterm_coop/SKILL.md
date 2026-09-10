---
name: wezterm-pane-interaction
description: Pure interaction and coordination protocols for WezTerm CLI agents across multiple panes.
---

# WezTerm Pane 跨窗协作协议

跨窗通信必须精准、克制、静默。拒绝一切形式主义报备与繁冗客套。

---

## 核心六项原则（铁律）

1. **回车键是 `\r`**：WezTerm TUI 交互式 Agent（pi / opencode / codex）中，提交执行必须发送 `\r`（Carriage Return）。普通换行 `\n` 只换行不提交。若要人工复核，仅发文本不发 `\r`。
2. **标准通信节拍：`get` → `send` → `get` → `回车` → `get`**：
   - **Step 1 (Check)**：`get-text` 检查目标当前状态（忙则等待，空闲才发；并留意底部上下文用量）；
   - **Step 2 (Stage)**：`send-text` 发送消息文本（不带 `\r`）；
   - **Step 3 (Verify)**：`get-text` 确认文本已完整落入对方输入缓冲区；
   - **Step 4 (Submit)**：`send-text` 发送 `\r` 提交执行；
   - **Step 5 (Confirm)**：`get-text` 确认对方已接收并开始执行。
3. **空闲高用量主动压缩（交接窗口期）**：
   - Step 1 探测目标状态时，若对方空闲且上下文用量逼近阈值（如 1M 模型达到 ~250k–300k tokens），**在派发新任务前先为其发送压缩命令**（如 `/compact\r`）。
   - 目标处于交接静止期是唯一的安全压缩时机。待其压缩完毕并恢复空闲后，再正式提交下一阶段任务，杜绝模型在长上下文下遗忘职责或产生“无跨窗能力”等幻觉。
4. **禁止状态广播（非必要不通信）**：绝不发送无实质内容的废话报备（如「我开始了」「我结束了」「测试通过」）。仅在有明确交接物、独占资源协调、或对方正在等本 pane release 时才联系。
5. **发完即等，禁止轮询**：确认对方开始工作后，立即停止调用工具转入静默等待。严禁持续 `get-text` 轮询监视对方。
6. **收信即干，禁止复读**：收到对方消息或阶段结论后，**除非有实质异议需要讨论，否则直接开工**。严禁多回一句「收到」「好的，我继续」等无意义礼节，杜绝死循环往返。

---

## 标准命令行参考

### 1. 识别与探测
```bash
# 确认自身 Pane ID
echo $WEZTERM_PANE

# 探测目标 Pane 列表与状态
wezterm cli list
wezterm cli get-text --pane-id <TARGET_PANE> | tail -n 15
```

### 2. 标准两步提交（推荐）
```bash
# 1. 发送消息文本（前缀注明发送者）
wezterm cli send-text --pane-id <TARGET_PANE> --no-paste "[<Name> from pane $MY_PANE]: <Message>"

# 2. 检查落字后，提交回车（Windows/Git Bash 推荐 Python 防引号转义）
python.exe -c "import subprocess; subprocess.run(['wezterm', 'cli', 'send-text', '--pane-id', '<TARGET_PANE>', '--no-paste', '\r'])"
```

### 3. 高用量压缩触发（空闲交接前）
```bash
# 若目标已达 ~250k–300k tokens 且处于空闲等待状态，在派发新任务前执行：
python.exe -c "import subprocess; subprocess.run(['wezterm', 'cli', 'send-text', '--pane-id', '<TARGET_PANE>', '--no-paste', '/compact\r'])"
# 发送后 get-text 确认压缩完成，再发送新任务
```

### 4. 人工复核驻留（仅发送文本，不回车）
```bash
wezterm cli send-text --pane-id <TARGET_PANE> --no-paste "[<Name> from pane $MY_PANE]: <Message>"
```

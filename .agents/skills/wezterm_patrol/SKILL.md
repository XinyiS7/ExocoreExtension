---
name: wezterm-patrol
description: Automated inspection, safety clearance (Allow? confirmation), and lifecycle monitoring for WezTerm worker panes during unattended or overnight sessions.
---

# WezTerm 自动化巡查与夜间值守规约 (wezterm-patrol)

用于长期离线、夜间挂机或无人看守时，对 WezTerm 跨窗格施工流水线进行自动化巡查、安全放行、撞限续跑与悬挂交接补发。

---

## 一、 核心准则（铁律）

1. **精准识别与安全放行**：
   - **放行范围**：仅放行**明确无害的工程动作**（单测套件运行、临时探针清理如 `rm -f /tmp/*.ts`、静态检查 `tsc/lint/build`、项目内安全读写）。
   - **阻断保留**：涉及破坏性 Git 操作（如 `git reset --hard`、`git clean -fd`）、密钥/生产环境改动、未明外部网络请求时，**严禁自动放行**，保持挂起并记录告警。
   - **回车提交**：安全弹窗预选为 `→ Yes` 时，通过 Python 或原生 CLI 发送 `\r`；发完立即 `get-text` 校验是否已解除阻断并恢复 `Working`。
2. **撞限降频续跑 (Rate Limit Cool-off Pulse)**：
   - 当检测到某个窗格出现 `usage limit`、`rate limit`、`insufficient quota` 时，**不要直接注销巡查**。
   - **自动降频**：将巡查间隔降级为半小时一次（如 `*/30 * * * *`）。
   - **探针续跑**：每 30 分钟向撞限窗格发送探针消息：`工作继续\r`。
   - **自动升频**：一旦检测到该窗格已恢复工作（状态恢复为 `Working` 或输出恢复滚动），立即恢复标准 5 分钟巡查（`*/5 * * * *`）。
3. **悬挂交接补发 (Dangling Handoff Bridge)**：
   - 当发现窗格 A 已输出明确方案/校准/交付结论且处于空闲停滞状态，但目标窗格 B 明确在等待 A 的输出，且连续两轮巡查（>10 分钟）仍未收到时：
   - **判定为模型长上下文遗忘或交接中断**。不必唤醒窗格 A 进行多轮争辩（容易诱发“无跨窗能力”等幻觉）。
   - **巡查者直接桥接代发**：提取窗格 A 的核心交付/校准文本，直接代表 A 发送至窗格 B：
     `[Patrol Bridge from Pane <A> -> Pane <B>]: <交接内容与结论>\r`
   - 发送后确认窗格 B 开始工作，打通阻塞流水线。
4. **全局终验收口**：
   - 仅当所有施工窗格均已完成任务并正式进入最终交付状态（如全线 `PASS 终验交付` / 所有流水线静默休眠），且无挂起任务时，才真正注销巡查并向人类呈递收口报告。
5. **静默旁路，绝不越权**：
   - 巡查者是旁路守护者与管线连通器，**在各窗格正常工作期间严禁发送无关指令或广播无意义报备**。巡查中不介入非停滞状态下的正常模型交流。

---

## 二、 典型阻断与特征处置

| 模式 | 特征文本 | 处置方式 |
| :--- | :--- | :--- |
| **复合命令确认** | `rm in compound command` / `Allow?` | 校验命令为临时文件清理后，发送 `\r` 选中 `→ Yes` |
| **工具授权询问** | `Allow execute command? [y/n]` | 校验安全后发送 `y\r` 或 `\r` |
| **配额超限/撞限** | `usage limit reached` / `rate limit` / `quota exceeded` | 降频至 30 分钟巡查，每 30 分钟发送 `工作继续\r` 尝试续跑 |
| **悬挂交接(遗忘发信)** | Pane A 方案已输出且 idle；Pane B 持续等待 >10m | 巡查者直接桥接代发：`[Patrol Bridge from Pane A -> B]: <内容>\r` |
| **全局流水线终验** | 全窗格 `PASS 终验交付` / 无施工活动 | 注销巡查定时器，向人类呈递收口报告 |

---

## 三、 标准操作命令参考

### 1. 跨窗状态探测
```bash
wezterm cli get-text --pane-id <PANE_ID> | tail -n 25
```

### 2. 安全回车放行（Windows/Git Bash 推荐 Python 防转义）
```bash
python.exe -c "import subprocess; subprocess.run(['wezterm', 'cli', 'send-text', '--pane-id', '<PANE_ID>', '--no-paste', '\r'])"
```

### 3. 撞限续跑探针（每 30 分钟）
```bash
python.exe -c "import subprocess; subprocess.run(['wezterm', 'cli', 'send-text', '--pane-id', '<PANE_ID>', '--no-paste', '工作继续\r'])"
```

### 4. 悬挂交接桥接代发
```bash
# 格式：[Patrol Bridge from Pane <SRC> -> Pane <TGT>]: <Summary>
python.exe -c "import subprocess; subprocess.run(['wezterm', 'cli', 'send-text', '--pane-id', '<TGT_PANE>', '--no-paste', '[Patrol Bridge from Pane <SRC> -> Pane <TGT>]: <Summary>\r'])"
```

### 5. AGY 原生调度示例
```json
// 标准巡查
{
  "CronExpression": "*/5 * * * *",
  "Prompt": "巡查 WezTerm Pane <IDs>。处理安全 allow 弹窗；检测是否撞限（转 30m 续跑探针）；检测是否有 Pane 停滞遗忘发信（代发交接）；若全线 PASS 终验则注销。"
}

// 撞限降频续跑
{
  "CronExpression": "*/30 * * * *",
  "Prompt": "撞限降频巡查：向撞限 Pane <ID> 发送 '工作继续\r' 探针；若已恢复工作则切回 5 分钟巡查。"
}
```

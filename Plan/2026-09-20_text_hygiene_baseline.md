# 2026-09-20 ExoCore-Extension 文本卫生基线（补齐漏做的第四仓）

> **期望效果：** 行尾/编码不再依赖各机器 `core.autocrlf`；本仓与伞仓 / ExoCore / ExoCore-Desktop 同构；
> 顺手收敛工作区行尾积习并清掉 5 个误入仓库的垃圾文件。
> **依据：** 伞仓 `c19cdf9` / 后端 `f111393b` / Desktop `01118cf`（2026-09-18 三仓基线）；本仓体检见下。
> **施工方：** Ecki — 2026-09-20（Alicia：声明加上、工作区一起收敛、四个小东西能删就删）

## 背景

2026-09-18 三仓同构基线时漏了本仓：此前既无 `.gitattributes` 也无 `.editorconfig`，
行尾完全依赖 `core.autocrlf=true` 的机器默认。

## 施工步骤

### Step 1：基线（两个新文件）
- `.gitattributes`：与三家同构（py/md/json/toml/yml/yaml/sh → LF；ps1/bat/cmd → CRLF；
  png/jpg/jpeg/gif/webp/ico/pdf/zip → binary）；本仓专属加一项 `*.exe binary`（本仓 tracked 两个 vendored exe）。
  **不为 `*.lua` 加规则**：`test.lua` 是 UTF-16LE（显式 text 规则反而会去碰它），
  `modinfo/modmain.lua` 在 `text=auto` 下已被正确判为 text + LF。
- `.editorconfig`：与伞仓逐字一致。
- 不装检测器脚本 / hook（与伞仓「故意不装」的决定一致）。

### Step 2：声明
- 本仓 `AGENTS.md` 新增 `## Text baseline` 小节；
- 伞仓 `AGENTS.md` 同步：第 53 行把 `ExoCore-Extension/**` 补进嵌套仓列表，第 56 行「三仓」→「四仓」；
  伞仓 `AGENT.md` 是 byte-identical 镜像，必须同改并校验 md5。

### Step 3：工作区行尾收敛（索引零变化，纯工作区）
对体检出的 CRLF / mixed 文件重写为 LF（索引本就是 LF，故 `git status` 不变）：
`.agents/skills/*/SKILL.md` ×5、`BUGLOG.md`、`Plan/Sync_Protocol.md`、`Plan/WezTerm_HITL_Blueprint.md`、
`agent_registry.json`、`extensions/clipboard_capture/config.py`、`extensions/wez_bridge/wezterm_cli.py`、
`docs/superpowers/plans/2026-05-26-unified-extension-agent-management.md`、
`extensions/wez_bridge/PENDING_TASKS.md`、`.idea/{modules.xml,vcs.xml,ExocoreExtension.iml}`。
例外：`.idea/.gitignore` 是**裸 CR** 行尾（整个文件被当作一行，规则失效）→ 归一为 LF 属**内容修复**，会进索引。

### Step 4：删除误入仓库的垃圾
| 文件 | 正面证据 |
|---|---|
| `__pycache__/config.cpython-312.pyc` | 编译缓存；`*.pyc` / `__pycache__/` 已在 `.gitignore`；0 引用 |
| `test.lua` | UTF-16LE scratch（136 B）；0 引用 |
| `.idea/workspace.xml` | IDE 本地状态；`.idea/.gitignore` 自身就写 `/workspace.xml` 该忽略；0 引用 |
| `main_error.txt` / `main_output.txt` | 0 字节调试重定向残留；0 引用 |

**不动**（同样可疑但证据不足 / 可能含用户配置，报告里单独列出）：`.idea/inspectionProfiles/*`、
`.idea/modules.xml`、`.idea/vcs.xml`、`.idea/ExocoreExtension.iml`、`.idea/.gitignore`。

## 不做（Scope 边界）

- 不做**内容级**清理（15 处缺末尾换行 / 13 处尾随空格不动——留给 `.editorconfig` 生效后由编辑器保存处理；
  大面积清尾随空格会给并行窗口制造 diff 噪音）；
- 不动 `.gitignore`（他人在途改动：+3 行 `.env` 规则）；
- 不动 `Plan/2026-09-07_*.md`、`extensions/uhh_mail/`（均非本次改动）；
- 不改任何代码 / 测试。

## 后续（同日授权，已落地）

初稿的两条「不做」在执行中被 Alicia 后续授权推翻，记录在此以免误导：

| 追加事项 | 提交 | 说明 |
|---|---|---|
| 提交 `extensions/uhh_mail/`（WIP 扩展） | `5fc193a` | 只提交 5 个源文件；`.env`（凭据）与 `__pycache__/**` 经 `check-ignore` + dry-run 证实排除；明文密钥扫描无命中 |
| 收编 `.gitignore` 的 `.env` / `*.env` / `.env.*` 规则 | `43a63d0` | 该规则是 `uhh_mail/.env` 的实际防护；此前只存在于工作区，随 reset/checkout 即失效 |
| 清除其余 tracked `.idea/` 文件 | `9b76d9e`、`8253ecb` | 含 `Project_Default.xml`（唯一含自定义设置者：PyPep8Naming 的 N806 豁免，Alicia 确认可删）与 `.gitignore` / `.iml` / `modules.xml` / `vcs.xml` / `profiles_settings.xml`；`git ls-files .idea/` 现为空 |

结果：卫生瑕疵 `37 → 25`（CRLF / mixed / UTF-16 全清零；余下 13 处尾随空格 + 12 处缺末尾换行按计划留给 `.editorconfig` 生效后的编辑器保存）；`pytest tests/` 125 passed。

## 验证

1. `git status` 仅显示预期改动（无 renormalize 噪音 —— 已用 `-c core.attributesFile` 试挂预演过）；
2. `git ls-files --eol` 分布：文本 = `attr/text eol=lf`，两个 ps1 = `attr/text eol=crlf`，二进制 = `attr/-text`；
3. 归一后字节复测：目标文件 CRLF 计数为 0；`.idea/.gitignore` 可解析为多行；
4. 删除的 5 个路径从 `git ls-files` 消失且 0 引用（已核）；
5. 本仓测试套件仍绿（本次未改代码，作为仓库健康基线）。

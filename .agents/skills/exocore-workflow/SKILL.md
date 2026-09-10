---
name: exocore-workflow
description: ExoCore-specific engineering and architecture change workflow. Governs impact analysis, real DB baseline protection, permission models, and update logging.
compatibility: pi, opencode, agy
metadata:
  scope: exocore
---

# ExoCore 核心工程改动规范 (exocore-workflow)

针对 ExoCore 跨模块体系（Django 后端 + Desktop 前端 + Windows 扩展 + 真实数据与记忆系统）的专项工程规范。在修改共享签名、模型/契约、权限或生命周期时强制执行。

---

## 一、 改动前：影响面探查与基线确认

### 1. Insight 影响面强制查询
涉及以下改动前，必须使用 Insight 查明调用链与下游依赖，严禁凭盲目局部搜索改动：
- Django Model / Migration / Serializer / View / Service
- API Endpoint 路径、入参、响应结构体、SSE 事件格式
- LLM 工具声明（`tools.py`）、`engines/model_registry.py`、Memory/Retrieval 逻辑
- 调度器 Job、信号（signals）、以及跨模块文件契约（`ExoCoreData/`）

```bash
# 查询类或方法的上下游关系
python.exe .agent/insight/query_insight.py --target <ClassNameOrMethod>
# 查询文件级别的级联影响
python.exe .agent/insight/query_insight.py --file <path>
```
核验链条：**Model 变更 → Serializer 映射 → View/Endpoint → 前端 SPAs (Desktop) / Windows Extension 消费点**。

### 2. 真实数据库基线检查（Real DB Discipline）
- **基线恒为 8 条**：真实库 `AgentPreset` 严禁新增、删除或篡改主键（底层已由 PostgreSQL trigger 物理防护）。
- **开工与收工强制核验**：在 `ExoCore/` 根目录下执行：
  ```bash
  bash .agent/check_real_db_baseline.sh
  ```
  必须确认终端输出 `OK: AgentPreset baseline 8 rows`。
- **探测与测试规则**：
  - 如需真实库实例做只读或字段级测试，**仅允许复用归档预设**（id=3 `Archived Chat` 或 id=4 `Archived G045 Chat`）；
  - 测试完毕必须还原配置并将 `is_visible` 设为 false；
  - 真实库数据写入与清理一律走 Django ORM，严禁裸 SQL DDL/INSERT。

---

## 二、 核心架构约束：G045 权限本位

- **本体为唯一事实源**：G045（Alessandro）的工具集（`shell` + `smart_read`）是全权限本体。
- **单向收窄原则**：其他路径限定工具（`my_workspace_*`, `project_*`）只是对本体做目录 scope 收窄，底层走同一执行引擎。
- **严禁能力倒挂**：绝对禁止“派生有而本体没有”；所有工具白名单、过滤缓存必须以本体为基准；新增能力优先赋予本体，G045 只增不减。

---

## 三、 改动中：行为承接与下游防线

### 1. 目的承接律（代码不只是字符替换）
旧代码的存在皆有其业务目的。改动前必须逐行明确：**旧代码解决了什么问题 → 新设计下由什么机制承接 → 有无下游遗漏**。
- **禁止静默移除观测与副作用**：看似“走不到”或不影响主流程的 collector、telemetry、private_log、状态写入等分支，往往承载着监控或外部联动。改变调用路径时，必须在新路径等价承接其目的，严禁直接删除了事。
- **关联模式同步搜索**：改动某一通用设计（如 Task 解析方式、Tool 结构），必须全局搜索同目录及关联模块，确保兄弟实现同步演进，拒绝局部打补丁。

---

## 四、 改动后：提交审查与 Update Log 纪律

### 1. Update Log 记录准则（仅限重大里程碑）
`Plan/ExoCore_update_log.md`（或前端 `Update_log.md`）是高层架构与版本历史记录，**绝非日常碎屑流水账**：
- **必须记录**：重大架构重构、全新独立功能模块接入、跨端核心公共契约变更、破坏性生命周期升级。
- **严禁记录**：日常 Bug 修复、局部单测调整、样式/CSS 微调、临时排错过程。日常开发足迹交由对应 Checkpoint 交付记录承载，保持 Update Log 干净高尚。

### 2. 提交前 Diff 隔离
```bash
git diff --stat
git diff <file>
```
逐文件审查，确认每一处改动均为本次既定意图。顺手发现的无关问题单独建 issue 或另起提交，绝不混入当前变更。

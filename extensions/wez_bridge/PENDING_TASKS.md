# Pending Tasks & Engineering Plan

## 1. `wez_bridge` 深度接管：会话锁机制 (Session Lease / Lock)
- **目标**：解决单次注入/单次报错捕获的局限性，实现中枢在终端 Pane 的连续多轮对话调试。
- **机制**：
  1. **状态标记**：在 `extensions/wez_bridge/extension.py` 中引入 `SessionLock` 状态。
  2. **拦截与劫持**：激活状态下，该 Pane 的标准输入（stdin / enter）将被 `wez_bridge` 拦截，不再直接提交给 local shell，而是包装为追问 payload 投递给中枢。
  3. **生命周期管理**：支持 `exit` 显式释放，或在编译成功/测试通过后由中枢指令自动解开 `SessionLock`。

## 2. `ExoCore Insight` 物理拓扑与主权地图
- **目标**：避免每次重新扫描，建立 2KB 以内的轻量级静态拓扑树 `.exocore_insight.json`。
- **结构**：
  - **物理层**：核心目录/CMake/Django routes。
  - **接口层**：API 契约字典（例如 `/api/v1/waker/wake_me_up`）。
  - **主权状态**：`moat_status`（ Alessandro 的物理管辖标记）。

## 3. `VoxCPM` 参数化语音与 `wake_me_up` 物理联锁
- **目标**：实现带有 vibe/pitch/speed 特征向量的语音绑定传输。
- **控制闸**：`wake_me_up` 触发后台高特权会话 -> 通过 `:8777` 强切 WezTerm 焦点 -> 物理音频投喂 -> 挂起进程强制深呼吸对齐。


## 4. 安全增强与主权阻断 (Sovereign Guard)
- **Host 绝对阻断特权 (Sovereign Interrupt)**: 
  - 客户端状态锁必须对 Host Pane (Alessandro 运行的窗口，Pane ID 0) 保留无条件物理阻断权。
  - 在  中强制拦截：一旦 Host Pane 发送  信号，立即在 1ms 内物理释放所有 Pane 的状态锁。
- **回环隔离与轻量鉴权 (Loopback Guard)**:
  -  必须严格绑定在 ，拒绝外部局域网嗅探。
  - 引入 ExoCore 启动时动态生成的 ，所有本地 CLI 调用必须附带此 Token 验证，防止其他本地进程越权控制终端。

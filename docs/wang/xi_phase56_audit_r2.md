# xi Phase 5 回归审计（`074a5e0`）

审计目标：验证上轮提出的 Phase 5 `3 个 blocker + 3 个 should-fix` 是否关闭。

结论：**不是 zero blockers。**

这次修复确实关闭了大部分问题：
- `question_reply` WS 入站路由已补
- `OpsPanel` 的 panel 内 mode switch 现在会发 `mode_switch`
- VNC URL 现在可配置
- `ws_server` 已新增 `send_benchmark()`
- `useWebSocket.disconnect()` 不再自动重连
- `DiagPanel` 的日志字段映射已经向真实结构化日志 schema 靠拢

但我认为还剩 **2 个 blocker + 2 个 should-fix**。

## 已关闭

### 1. `question_reply` WS 路由已接通

涉及：
- `web-console-v2/src/components/TaskPanel.vue:39-45`
- `ws_server/server.py:31-32`
- `ws_server/server.py:157-167`

这次 `TaskPanel.reply()` 已不再伪装成普通 `command_submit`，而是会发送：
- `type = "question_reply"`
- `message_id`
- `task_id`
- `answer`

`ws_server` 也新增了：
- `InboundHandler.on_question_reply(...)`
- `_handle_inbound(...): elif msg_type == "question_reply": ...`

所以“点击待回答按钮 -> 后端收到结构化 reply”这条链路本身已经补上。

### 2. `OpsPanel` 内部的 mode switch 现在会同步到后端

涉及：
- `web-console-v2/src/components/OpsPanel.vue:22-35`
- `web-console-v2/src/App.vue:25`

这次 `OpsPanel` 已从只做本地 `$emit(...)` 改成：
- `props.send('mode_switch', { mode })`
- 同时再 `emit('mode-switch', mode)` 更新前端本地布局

也就是说，**从 OpsPanel 按钮触发**的模式切换现在确实会同步给 `ws_server`。

### 3. VNC URL 不再是写死的 `about:blank`

涉及：
- `web-console-v2/src/components/OpsPanel.vue:28-30`

现在 `vncUrl` 改成：
- `?vnc_url=` query param 优先
- 否则默认 `/vnc/vnc.html`

这比上轮的空壳状态明显前进，至少已经不是完全不可用的硬编码空地址。

### 4. benchmark 和 log-entry 的主要协议补丁已到位

涉及：
- `ws_server/server.py:196-197`
- `web-console-v2/src/components/DiagPanel.vue:62-76`

这次：
- `ws_server` 新增了 `send_benchmark()`
- `DiagPanel` 开始监听独立 `benchmark` 消息
- 同时保留了对 `world_snapshot.data.benchmark` 的兼容
- `log_entry` 也开始映射 `level / component / message / timestamp`

所以我上轮指出的“完全依赖未声明 benchmark 契约”和“日志字段完全错位”这两个点，已经不是原来的状态了。

### 5. `disconnect()` 不再触发意外重连

涉及：
- `web-console-v2/src/composables/useWebSocket.js:13-18`
- `web-console-v2/src/composables/useWebSocket.js:45-50`

`useWebSocket` 现在加了 `intentionalDisconnect` guard。  
显式 `disconnect()` 后，`onclose` 不会再无条件排新的 reconnect timer。

这条 should-fix 可以清掉。

## Remaining findings

### 1. Blocker — Header 主模式切换按钮仍然不会发 `mode_switch`，前后端模式仍可能失同步

涉及：
- `web-console-v2/src/App.vue:9-11`
- `web-console-v2/src/App.vue:43-48`
- `web-console-v2/src/components/OpsPanel.vue:32-35`

这次修的只是 `OpsPanel` 里的两个按钮。  
但真正一直显示在顶部的主切换按钮仍然走：

- `@click="toggleMode"`
- `toggleMode()` 只改本地 `mode.value`

它**没有**调用：
- `send('mode_switch', { mode })`

这会留下一个非常具体的失同步路径：
- 用户点击 header 按钮切到 debug
- 前端布局变了
- 后端完全不知道 mode 已切换

而且一旦进入 debug 视图，`OpsPanel` 已经不可见，用户只能继续用 header 按钮切回 user。  
所以当前最显眼、最常用的模式切换入口仍然是“只切前端，不切后端”。

按 Wang 这轮“OpsPanel: VNC 可配置 + mode_switch WS 同步”的回归目标，这个 blocker 还没完全关。

### 2. Blocker — `TaskPanel` 虽然接了 `task_list.pending_questions`，但 `ws_server.send_task_list()` 仍不会发送它，pending-question 初始化路径仍不完整

涉及：
- `web-console-v2/src/components/TaskPanel.vue:48-50`
- `ws_server/server.py:202-203`

前端这次确实开始读取：
- `msg.data.pending_questions`

但后端 formal helper 还是：
- `send_task_list(tasks) -> {"tasks": tasks}`

也就是：
- `task_list` 这条正式 helper 路径仍然**不可能**带出 `pending_questions`

这会留下一个集成问题：
- 如果调用方按 `send_task_list()` 这条正式 helper 更新左侧任务栏
- `TaskPanel` 的 pending question 区域仍然不会得到初始化数据
- 只能依赖另一个隐式路径 `world_snapshot.pending_questions`

而这恰好说明 Wang 要求的 “`task_list/world_snapshot` 填充” 并没有双向都闭合。  
目前只是一边前端准备读，一边后端 helper 还没真正发。

按我对上轮 blocker 的定义，这个问题仍足以阻止我把 pending-question 面板清成 fully integrated。

## Remaining should-fix

### 1. `ChatView` / `TaskPanel` 的时效性标注仍然会冻结

涉及：
- `web-console-v2/src/components/ChatView.vue:18-19`
- `web-console-v2/src/components/TaskPanel.vue:28-29`
- `web-console-v2/src/composables/useTimeAgo.js:13-18`

这轮没有改 `time-ago` 机制。  
两个组件仍然只是直接调用 `formatTimeAgo()`，没有订阅 `useTimeAgo()` 的定时 tick。

结果仍然是：
- 如果界面没有别的 reactive 更新
- `just now / 5s ago / 1m ago` 不会自己刷新

### 2. `DiagPanel` 的日志颜色映射仍然没有和结构化日志级别完全对齐

涉及：
- `web-console-v2/src/components/DiagPanel.vue:64-69`
- `web-console-v2/src/components/DiagPanel.vue:83-86`

这次虽然字段映射已经改成：
- `level`
- `component`
- `message`
- `timestamp`

但样式仍然写的是：
- `.log-entry.error`
- `.log-entry.warning`

而真实结构化日志级别是：
- `ERROR`
- `WARN`
- `INFO`
- `DEBUG`

也就是说 UI 上：
- 标签内容基本对了
- 但 `ERROR/WARN` 的颜色 class 仍然不会命中

这已经不是 blocker，但还没完全 polish 完。

## 本地验证

我跑了：
- `npm run build`（在 `web-console-v2/`）
- `python3 tests/test_ws_and_review.py`

另外做了源码/协议对照审计：
- `web-console-v2/src/App.vue`
- `web-console-v2/src/composables/useWebSocket.js`
- `web-console-v2/src/components/TaskPanel.vue`
- `web-console-v2/src/components/OpsPanel.vue`
- `web-console-v2/src/components/DiagPanel.vue`
- `ws_server/server.py`

## 结论

这轮不能清成 `zero blockers`。

我当前的审计口径是：
- 已关闭：`question_reply` 路由、`send_benchmark()`、VNC 可配置、panel 内 mode sync、disconnect 不重连、日志字段主映射
- 未关闭：**2 个 blocker**
  - header 主模式切换仍不发 `mode_switch`
  - `send_task_list()` 仍不携带 `pending_questions`
- 未关闭：**2 个 should-fix**
  - time-ago 标签不会自动刷新
  - `DiagPanel` 日志颜色 class 未对齐真实日志级别

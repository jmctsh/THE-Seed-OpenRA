# System Drift Analysis + Live Test & Debug Guide

Date: 2026-04-01 | Author: wang

---

## Part 1: Design vs Implementation — Drift Map

### 完全实现 (No Drift)

| 设计点 | 状态 |
|---|---|
| 三级架构 Kernel/TaskAgent/Job | ✅ 完全按设计 |
| Task kind (instant/managed) | ✅ |
| Task Agent tool 列表 (start/patch/pause/resume/abort/complete/create_constraint/remove_constraint/query_world/query_planner/cancel_tasks) | ✅ 全部注册 |
| NormalizedActor 字段 (mobility/combat_value/can_attack/can_harvest/weapon_range) | ✅ |
| 声明式资源模型 + 优先级抢占 | ✅ |
| ExpertSignal schema (kind/summary/world_delta/expert_state/result/data/decision) | ✅ |
| Event 类型 (9 种全部实现) | ✅ |
| Adjutant 三路分类 (command/reply/query) | ✅ |
| Pending question 超时 + default_if_timeout | ✅ Kernel 持有定时器 |
| GameLoop 10Hz + 分层 tick_interval | ✅ |
| 错误恢复策略 (LLM failover/GameAPI reconnect/WorldModel stale) | ✅ |

### 有意简化 (Intentional Simplification)

| 设计点 | 设计 | 实际 | 影响 |
|---|---|---|---|
| **UnitRegistry** | 独立组件，启动链第二步 | 不存在。WorldModel 内联 `_normalize_actor` | **P0 — Issue 8 的根因**。没有全局名称注册表导致 LLM→GameAPI 名称不匹配 |
| **Information Expert 分离** | ThreatAssessor/EconomyAnalyzer/MapSemantics 独立类 | 全部内联在 WorldModel.world_summary() | P2 — 可扩展性受限，但当前功能够用 |
| **Context 注入策略** | "启动全量 / Signal delta / 长时间无事件压缩摘要" | 每次 wake 都发全量 context | P3 — token 浪费，但 Qwen 3.5 上下文够用 |

### 未实现 (Gap)

| 设计点 | 设计 | 实际 | 影响 | 优先级 |
|---|---|---|---|---|
| **Planner Expert** | ReconRoutePlanner/AttackRoutePlanner/ProductionAdvisor | Stub（返回"Phase 3+"） | 中 — Task Agent 只能靠 LLM 自己规划 | P3 |
| **Adjutant 多问题拆分** | "放弃进攻，改目标" → 拆分路由给 TaskA+TaskB | 只匹配最高优先级的 1 个 pending question | 低 — 多 Task 并发场景少 | P3 |
| **语音 ASR+TTS** | 基础框架支持 | 未实现 | 低 — 非核心 | P4 |

### 实现偏移 (Unexpected Drift)

| 设计点 | 设计 | 实际偏移 | 根因 | 影响 |
|---|---|---|---|---|
| **建筑/单位名称** | design.md 用英文全称 (PowerPlant/Barracks) | GameAPI 用内部代号 (POWR/BARR) | 缺少 UnitRegistry 翻译层 | **P0 — 所有生产/建造命令失败** |
| **auto_place_building** | 未在设计中明确 | EconomyExpert 默认不放置建筑 | GameAPI.produce 的 auto_place 默认 False | **P0 — 建筑造完但不放置** |
| **命令反馈通道** | Adjutant → query_response | 命令 ack 走了 player_notification | 实现时把 command 和 query 路由搞混 | **已修** (commit 2660436) |
| **BASE_UNDER_ATTACK 误报** | 只在"基地被攻击"时触发 | 建筑 HP 微小波动即触发 | 未设阈值+未检查附近敌军 | **已修** (commit eca213a) |
| **defend_base 延迟** | 设计说 "预注册规则，自动创建 Task" | 原实现等 LLM 5-10s 才行动 | 缺少即时反射层 | **已修** (commit 398902b) |

---

## Part 2: 当前阻断点 (Blockers)

### Active Blockers

| # | 问题 | 影响 | 状态 |
|---|---|---|---|
| B1 | 建筑名称不匹配 (LLM→GameAPI) | 所有建造指令失败 | Yu 已修 (production_names.py) |
| B2 | 建筑 auto_place 缺失 | 建筑造完不放置，queue 卡住 | Yu 已修 (auto_place_building=True) |
| B3 | 阵营检测缺失 | 可能尝试建造对方阵营建筑 | **未修 — 需要检测我方阵营** |

### Potential Blockers (未验证)

| # | 风险 | 验证方法 |
|---|---|---|
| B4 | 多步建造依赖（建完电厂才能建兵营）— LLM 是否能正确序列化 | 连续发 "建电厂" → "建兵营"，看 LLM 是否理解顺序 |
| B5 | 资源不足时 Job 恢复 — waiting→running 自动转换 | 钱不够时发建造命令，等资金回来后检查 |
| B6 | 多 Task 并发资源冲突 — 优先级抢占是否正确 | 同时发侦察+进攻，看高优先级是否拿到单位 |
| B7 | 战斗单位 target 选择 — CombatExpert 是否能找到敌人 | 有单位后发 "攻击敌人"，看是否移动到敌人位置 |

---

## Part 3: 我们在测试什么

### 测试目标
验证 **design.md 定义的全部用户可见行为** 在真实游戏中正常工作。

### 测试矩阵

| ID | 测试场景 | 验证的设计行为 | 涉及组件 | 通过条件 |
|---|---|---|---|---|
| T5 | 部署基地车 | instant task → DeployExpert → GameAPI deploy | Adjutant→Kernel→TaskAgent→DeployExpert→GameAPI | 建造厂出现 |
| T9 | "战况如何" | 查询不进 Kernel，Adjutant 直接 LLM+WorldModel 回答 | Adjutant→WorldModel→LLM | 中文战况简报，含经济/军事/地图 |
| T-BUILD | 建造电厂 | command → EconomyExpert → GameAPI produce | 全链路 | POWR 出现在 query_actor |
| T-PROD | 生产步兵 | EconomyExpert 多单位生产 | 全链路 | N 个步兵出现 |
| T1 | 探索地图 | ReconExpert 自主执行 + 事件驱动 | Kernel→TaskAgent→ReconExpert→GameAPI | 单位开始移动，map 探索率上升 |
| T4 | 攻击敌人 | CombatExpert FSM(approach→engage→pursue) | 全链路 | 单位移向敌人并攻击 |
| T-DEFEND | 被攻击自动防御 | BASE_UNDER_ATTACK → Kernel 即时反射 → CombatJob(HOLD) | WorldModel→Kernel→CombatExpert | 建筑被打时立刻有单位回防 |
| T7 | "别追太远" | create_constraint(do_not_chase) | TaskAgent→Kernel→constraint 传播 | CombatJob 遵守追击距离 |
| T10 | 回复提问 | pending_question → player reply → 路由回 TaskAgent | Adjutant→Kernel→TaskAgent | 回复被正确传递 |
| T-MULTI | 同时侦察+建造 | 多 Task 并发 + 资源互不干扰 | Kernel 资源分配 | 两个任务各自推进 |

### 尚未覆盖的设计场景

| 设计场景 | 原因 | 计划 |
|---|---|---|
| 优先级抢占（高优 Task 夺低优资源） | 需要多 Task + 资源竞争 | Phase E 战斗测试 |
| 侦察兵死亡 → Kernel 自动补充 | 需要单位死亡事件 | 战斗中自然触发 |
| LLM 连续失败 → 自动终止 Task + 通知玩家 | 需要 LLM 故障 | 可手动断 API 测试 |
| GameAPI 断连 → Job pause + 自动重连 | 需要杀 GameAPI | 可手动杀 OpenRA 进程 |
| default_if_timeout 超时自动回复 | 需要玩家不回复问题 | 故意不回复 |
| 约束传播 enforcement=escalate | 需要 Job 违反约束 | 构造场景 |

---

## Part 4: 怎么测 — 全链路调试方案

### 4.1 环境架构

```
┌─────────────────────────────────────────────────┐
│  OpenRA 游戏进程 (OpenCodeAlert)                 │
│  ├── CopilotCommandServer (TCP :7445)           │
│  └── 游戏逻辑 (地图/单位/AI)                     │
└──────────────────┬──────────────────────────────┘
                   │ TCP Socket (JSON-over-newline)
┌──────────────────▼──────────────────────────────┐
│  Python 后端 (main.py)                           │
│  ├── GameAPI ──→ WorldModel ──→ Kernel           │
│  │                  │              │              │
│  │              detect_events   route_events      │
│  │                  │              │              │
│  │              TaskAgent ←── Signals ── Jobs     │
│  │                  │                    │        │
│  │              LLM (Qwen)          GameAPI calls │
│  │                                               │
│  ├── Adjutant (分类 + 查询)                      │
│  ├── RuntimeBridge (WS ↔ Kernel 桥接)           │
│  └── WSServer (aiohttp :8765)                    │
└──────────────────┬──────────────────────────────┘
                   │ WebSocket (JSON)
┌──────────────────▼──────────────────────────────┐
│  前端 (Vue 3, Vite :5173)                        │
│  ├── ChatView (对话主界面)                        │
│  ├── TaskPanel (任务列表)                         │
│  ├── OpsPanel (操作面板)                          │
│  └── DiagPanel (诊断面板)                         │
└─────────────────────────────────────────────────┘
```

### 4.2 调试观测点

#### Layer 1: GameAPI (最底层)
```bash
# 直接测 GameAPI 连通和数据
python3 -c "
from openra_api.game_api import GameAPI
from openra_api.models import TargetsQueryParam
api = GameAPI('localhost', 7445)
print('ping:', api.is_server_running())
actors = api.query_actor(TargetsQueryParam(faction='己方'))
for a in actors:
    print(f'  {a.type} ID={a.actor_id} at ({a.position.x},{a.position.y}) HP={a.hppercent}%')
"
```
**看什么**：连通性、单位列表是否正确、type 名称是什么

#### Layer 2: WorldModel (数据层)
```bash
# 检查 WorldModel 刷新是否正常
grep "world_refresh_failed\|stale" /tmp/backend.log | tail -10
```
**看什么**：是否有 refresh 失败、stale 标记

#### Layer 3: Kernel + TaskAgent (逻辑层)
```bash
# 检查任务/Job 状态
grep "task_created\|job_started\|job_aborted\|signal_routed\|event_routed" /tmp/backend.log | tail -20

# 检查 LLM 调用
grep "llm_succeeded\|llm_failed\|tool_execute" /tmp/backend.log | tail -20
```
**看什么**：
- Task 是否创建成功
- LLM 选了什么 Expert（看 `tool_execute` 的 `expert_type`）
- Job 是否启动并获得资源
- Signal 是否正确路由

#### Layer 4: WS + 前端 (交互层)
```python
# 通过 WS 发命令并监听回复
import asyncio, json, websockets, time
async def cmd(text):
    ws = await websockets.connect('ws://localhost:8765/ws', max_size=10*1024*1024)
    await ws.send(json.dumps({'type':'command_submit','text':text}))
    start = time.time()
    while time.time() - start < 30:
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=1)
        except asyncio.TimeoutError:
            continue
        d = json.loads(raw)
        t = d.get('type','')
        if t == 'query_response':
            print(f'副官: {d.get("data",{}).get("answer","?")}')
        elif t == 'player_notification':
            print(f'通知: {d.get("content","")}')
    await ws.close()
asyncio.run(cmd('你的命令'))
```
**看什么**：是否收到 query_response（命令确认）、是否收到 notification（系统事件）

### 4.3 诊断决策树

```
命令发了但没反应？
├── 检查 WS 连接 → lsof -i :8765
├── 检查后端日志 → grep "player_input\|command_submit" /tmp/backend.log
│   ├── 没有 player_input → WS 消息没到后端
│   ├── 有 player_input 但没有 input_classified → Adjutant LLM 超时
│   ├── 有 input_classified 但没有 task_created → Kernel 创建 Task 失败
│   └── 有 task_created 但没有 tool_execute → TaskAgent LLM 未调用/超时
│       ├── 检查 llm_failed → LLM API 错误
│       └── 检查 llm_succeeded + tool_execute → 看 expert_type 和 config

建筑/单位没造出来？
├── grep "expert_signal.*blocked\|cannot_produce" /tmp/backend.log
│   ├── cannot_produce → 名称不匹配或前置不满足
│   ├── blocked + queue_type → 生产队列被占
│   └── resource_lost → 工厂被摧毁
├── 直接查 GameAPI → api.produce('POWR', 1, True) 看是否成功
└── 查 production queue → api.query_production_queue('Building')

侦察/战斗没动作？
├── grep "job_started\|resource_granted\|job_aborted" /tmp/backend.log
│   ├── 没有 job_started → TaskAgent 没调 start_job
│   ├── 有 job_started 但没有 resource_granted → Kernel 没有可分配的单位
│   └── 有 resource_granted → Job 在执行但可能卡住
├── 查 Job tick → grep "expert.*tick\|move_units\|attack" /tmp/backend.log
└── 直接查单位位置 → api.query_actor() 看是否在移动
```

### 4.4 启动/重启 Checklist

```bash
# 1. 确认游戏运行
lsof -i :7445   # GameAPI port

# 2. 杀旧后端
lsof -i :8765 | awk 'NR>1{print $2}' | xargs kill 2>/dev/null

# 3. 启动新后端
nohup python3 main.py --log-level INFO > /tmp/backend.log 2>&1 &
sleep 4

# 4. 验证
lsof -i :8765                           # 后端在跑
tail -3 /tmp/backend.log                # 无错误
python3 -c "
from openra_api.game_api import GameAPI
api = GameAPI('localhost', 7445)
print('GameAPI:', api.is_server_running())
"

# 5. 前端（如果需要）
cd web-console-v2 && npm run dev &      # :5173
```

### 4.5 日志关键词速查

| 关键词 | 含义 | 在哪找 |
|---|---|---|
| `player_input` | Adjutant 收到用户输入 | adjutant |
| `input_classified` | 输入分类结果 | adjutant |
| `task_created` / `job_started` | 任务/Job 创建 | kernel |
| `llm_succeeded` / `llm_failed` | LLM 调用结果 | task_agent |
| `tool_execute` | LLM 选的 tool + 参数 | task_agent |
| `resource_granted` / `resource_lost` | 资源分配变化 | kernel/expert |
| `expert_signal` | Job 发给 TaskAgent 的 Signal | expert |
| `signal_routed` / `event_routed` | Kernel 路由 Signal/Event | kernel |
| `world_refresh_failed` | WorldModel 刷新失败 | world_model |
| `job_aborted` | Job 被终止 | kernel/expert |
| `cannot_produce` / `blocked` | 生产失败原因 | expert |

---

## Part 5: 系统成熟度评估

### 按 design.md 场景推演覆盖率

| 场景 (design.md §9-10) | Mock 测试 | Live 验证 | 备注 |
|---|---|---|---|
| "探索地图找敌人基地" | ✅ | ⚠️ 逻辑正确但无可用单位 | 需要先有步兵/车辆 |
| "生产5辆坦克" | ✅ | ⚠️ 名称修复后待验证 | Round 6 验证 |
| "包围右边基地" | ✅ | ❌ | 需要战斗单位+敌人位置 |
| "所有部队撤退" | ✅ | ❌ | 需要战斗中场景 |
| "别追太远" | ✅ | ⚠️ LLM 当 managed task | prompt 需优化 |
| "部署基地车" | ✅ | ✅ | Round 4+5 验证 |
| "战况如何" | ✅ | ✅ | Round 5 验证 |
| 侦察兵死亡→自动补充 | ✅ | ❌ | 需要单位死亡场景 |
| 用户取消探索 | ✅ | ❌ | 需要活跃 Task |
| 高优先级抢占资源 | ✅ | ❌ | 需要多 Task 竞争 |

### 整体评估

```
基础架构：  █████████░  90% — 核心组件全部就绪
GameAPI 集成：████████░░  80% — 名称映射是最后一块拼图
LLM 决策质量：███████░░░  70% — Expert 选对了，参数偶尔错
开局到战斗链路：████░░░░░░  40% — 建造链刚修，生产/侦察/战斗未验证
用户体验：  █████░░░░░  50% — 命令回复有了，但缺"思考中"状态
前端：     ████░░░░░░  40% — 功能在但体验粗糙
```

### 当前最高优先级

1. **Round 6 验证完整开局链** — Yu 正在执行
2. **阵营检测** — 避免建错阵营建筑
3. **生产→侦察→战斗全链跑通** — 系统 E2E 闭环
4. **前端"思考中"状态** — 用户感知优化

# System Analysis v1 — Live E2E Test Findings + Architecture Gap Analysis

Date: 2026-04-01
Author: wang (architect / test lead)

---

## 1. Live Testing Summary (Rounds 1-5)

### What Works

| Component | Status | Evidence |
|---|---|---|
| GameAPI 底层 | **Solid** | deploy/produce/query/move 全部直接调用成功 |
| Adjutant 分类 | **Good** | command/query 准确分类，confidence 0.95+，fallback 规则兜底 |
| Kernel Task 生命周期 | **Good** | 创建/运行/完成/取消 全路径正常 |
| Kernel 资源匹配 | **Good** | 排除建筑/static，优先级抢占正确 |
| Task Agent LLM 调用 | **Good** | 正确选择 Expert 类型和参数（修复后） |
| WorldModel 事件检测 | **Good** | UNIT_DIED/ENEMY_DISCOVERED/PRODUCTION_COMPLETE 检测准确 |
| BASE_UNDER_ATTACK 去误报 | **Fixed** | 5% 阈值 + 附近敌军检查有效 |
| defend_base 即时反射 | **Fixed** | Kernel 直接创建 CombatJob(HOLD)，无需等 LLM |
| 命令反馈通道 | **Fixed** | query_response 通道回显副官回复 |
| WS 双向通信 | **Working** | command_submit → 处理 → query_response 链路通畅 |

### What's Broken or Fragile

| Issue | 根因 | 影响 | 修复难度 |
|---|---|---|---|
| **建筑名称不匹配** (Issue 8) | LLM 说 "PowerPlant"，GameAPI 要 "powr" | 所有建造指令失败 | 中 — 需要名称映射表 |
| **production queue 查询失败** (Issue 9) | GameAPI.query_production_queue 返回错误 | EconomyExpert 无法检查建造前提 | 低 — 调研 API 格式 |
| **WS 帧超限** (Issue 10) | world_snapshot > 1MB | WS 连接断开 | 低 — 加 max_size 或压缩 |
| **GameAPI 连接失效** (Issue 11) | 后端重启后旧持久连接不可用 | WorldModel 持续刷错 | 中 — 加连接健康检查 |
| **LLM 响应慢** | 分类~2s + 查询~8s = 总~10s | 用户等待体验差 | 高 — 需要 streaming + 前端状态 |
| **前端缓存残留** | localStorage 跨 session 持久化 | 用户看到旧数据 | 已修 → sessionStorage |

---

## 2. 架构层面的系统性问题

### 2.1 LLM 与游戏世界的语义鸿沟

**问题**：LLM 理解自然语言（"建电厂"），但游戏 API 用内部代号（"powr"）。这不是一个 bug，是一个架构缺陷——系统中没有"语义翻译层"。

**影响面**：
- EconomyExpert: unit_type 名称全部不匹配
- CombatExpert: 目标选择可能用错单位类型
- Task Agent system prompt: 给的 Expert config 示例可能用错名称

**设计思考**：
- **方案 A**：在 EconomyExpert/CombatExpert 内部加映射表 → 每个 Expert 维护自己的映射，重复且脆弱
- **方案 B**：在 WorldModel 中维护全局 `UnitRegistry`（类型名 → 游戏内部名、分类、建造前提、成本），Expert 从 WorldModel 查询 → 单一来源，所有组件共享
- **方案 C**：在 GameAPI 层做名称规范化 → 把 "powr" 翻译成 "PowerPlant" 后暴露给上层

**推荐**：方案 B。UnitRegistry 应该是 WorldModel 的一部分，从游戏 production queue 动态加载（而不是硬编码）。这样：
- Task Agent system prompt 可以用人类可读的名称
- EconomyExpert 在 produce() 前查 registry 做翻译
- 新阵营/新 mod 自动适配

### 2.2 测试环境 vs 真实环境的断层

**Mock E2E 的局限性**：
- 136 个 mock 测试全部通过，但 live 测试发现 15+ 个 mock 检测不到的问题
- Mock 不会暴露：名称不匹配、API 格式错误、连接管理、时序问题
- Mock 的 GameAPI 总是成功，不会返回 `cannot_produce` 或 `COMMAND_EXECUTION_ERROR`

**需要的测试分层**：

```
                    Live E2E (真实游戏)
                   /                    \
           Integration (真实 GameAPI)    Integration (真实 LLM)
                  |                         |
            Unit Tests (Mock 全部)     LLM Benchmark (离线)
```

当前只有最底层和最顶层，缺少中间层。

**改进建议**：
1. **GameAPI Integration Test**：只测 GameAPI ↔ 游戏连接，不走 LLM
   - `test_gameapi_live.py`: ping、query_actor、produce 全量测试
   - 需要游戏在运行但不需要 Kernel/Agent/Adjutant
2. **LLM Decision Test**：只测 LLM 决策质量，不需要真实游戏
   - 给定 WorldModel snapshot + 指令，检查 LLM 是否选了正确的 Expert 和参数
   - 可以离线批量跑，不用启动游戏

### 2.3 开局序列的设计空白

**问题**：RTS 游戏有固定的开局流程（MCV→建造厂→电厂→兵营→…），当前系统没有"开局自动化"能力。

**当前状态**：
- 用户必须手动发送每一步指令
- 每个指令都要 LLM 处理（~5s 延迟 × 5 步 = 25s 才能完成开局）
- 如果任何一步的名称不对（Issue 8），整个开局卡住

**设计思考**：
- **方案 A**：预定义开局脚本（按阵营/地图自动执行前 N 步）→ 简单有效，但不灵活
- **方案 B**：StrategyAgent（design.md §7 提到但未实现）生成开局计划，Kernel 依次执行 → 最终方案
- **方案 C**：用户可以选择一个"开局模板"（"标准开局"/"快攻开局"/"经济开局"），系统自动执行 → 平衡点

**短期建议**：先实现方案 A（硬编码开局序列），作为测试快速通过的脚手架。

### 2.4 Job 间依赖与时序

**问题**：很多 RTS 操作有严格的前后依赖：
- 建电厂 → 等建完 → 建兵营 → 等建完 → 生产步兵
- 侦察 → 发现敌人 → 调度攻击

当前 Task Agent 通过 LLM 记忆来管理这些依赖——收到 Job 完成的 Signal 后再启动下一个 Job。但这依赖 LLM 的上下文记忆，在长对话中可能丢失。

**设计思考**：
- Kernel 加 Job DAG 支持（`start_job(depends_on=["j1", "j2"])`）→ Kernel 自己管理依赖，不依赖 LLM 记忆
- 或者 Task Agent 加 plan 工具（`create_plan(steps=[...])`），生成执行计划后 Kernel 按步推进

### 2.5 实时性与延迟预算

**实测延迟分布**：

| 操作 | 延迟 | 占比 |
|---|---|---|
| LLM 分类 | ~2s | 15% |
| LLM 决策 | ~5s | 38% |
| LLM 查询回答 | ~8s | 62% |
| GameAPI 调用 | <10ms | <1% |
| Kernel/Expert 逻辑 | <1ms | <1% |
| WorldModel 刷新 | <1ms (mock) / ~50ms (live) | 3% |

**结论**：LLM 是唯一瓶颈。所有非 LLM 组件都远低于预算。

**优化路径**：
1. **短期**：前端显示"正在思考..."状态（感知延迟优化）
2. **中期**：LLM streaming 输出（查询回答边生成边显示）
3. **中期**：简单意图用 qwen-turbo（分类 <1s，简单命令 <2s）
4. **长期**：Prompt caching（system prompt 复用，减少 ~50% prompt tokens）

---

## 3. 测试 Workflow 改进方案

### 3.1 当前测试流程的问题

```
现在：手动发 WS 命令 → 手动等 → 手动查 GameAPI → 手动看日志
问题：慢、不可重复、依赖人的判断、容易漏检
```

### 3.2 推荐的测试 Workflow

#### 3.2.1 自动化 Live 测试脚本

```python
# test_live_e2e.py — 自动化 Live E2E 测试

class LiveE2ETestRunner:
    """
    连接真实游戏的自动化测试。
    假设：游戏已启动，后端已运行。
    """

    def __init__(self):
        self.ws = None
        self.api = GameAPI('localhost', 7445)

    async def setup(self):
        self.ws = await websockets.connect(WS_URL, max_size=10*1024*1024)

    async def send_and_wait_response(self, text, timeout=30):
        """发送命令并等待 query_response"""
        await self.ws.send(json.dumps({...}))
        # 等待直到收到 query_response 或超时
        ...

    async def wait_for_game_state(self, predicate, timeout=60):
        """轮询 GameAPI 直到状态满足条件"""
        while time.time() < deadline:
            actors = self.api.query_actor(...)
            if predicate(actors):
                return True
            await asyncio.sleep(2)
        return False

    async def test_deploy_mcv(self):
        """T5: 部署基地车"""
        # 前置：确认 MCV 存在
        actors = self.api.query_actor(TargetsQueryParam(faction='己方'))
        mcv = [a for a in actors if a.type == '基地车']
        assert mcv, "No MCV found"

        # 动作
        resp = await self.send_and_wait_response('部署基地车')
        assert '收到' in resp or '任务' in resp

        # 验证：等待建造厂出现
        ok = await self.wait_for_game_state(
            lambda actors: any(a.type == '建造厂' for a in actors),
            timeout=30
        )
        assert ok, "MCV not deployed within 30s"

    async def test_query_status(self):
        """T9: 查询战况"""
        resp = await self.send_and_wait_response('战况如何')
        assert len(resp) > 50, "Response too short"
        assert '经济' in resp or '军事' in resp or '单位' in resp

    async def test_build_sequence(self):
        """开局建造序列：电厂→兵营→矿场"""
        for building in ['电厂', '兵营', '矿场']:
            resp = await self.send_and_wait_response(f'建造{building}')
            assert '收到' in resp
            # 等待建造完成...
```

#### 3.2.2 测试状态检查工具

```python
# test_check.py — 快速状态检查（不发命令，只读）

def check_all():
    api = GameAPI('localhost', 7445)

    # 1. 连通性
    assert api.is_server_running(), "GameAPI not running"

    # 2. 我方单位
    actors = api.query_actor(TargetsQueryParam(faction='己方'))
    print(f"己方: {len(actors)} units")
    for a in actors:
        print(f"  {a.type} ID={a.actor_id} HP={a.hppercent}%")

    # 3. 敌方
    enemies = api.query_actor(TargetsQueryParam(faction='敌方'))
    print(f"敌方可见: {len(enemies)} units")

    # 4. 后端 WS
    # Quick connect + sync_request + check task_list
    ...
```

#### 3.2.3 测试阶段划分

| 阶段 | 前提 | 测试内容 | 预估时间 |
|---|---|---|---|
| Phase A: 基础链路 | 游戏启动 | ping/query_actor/produce 直接调用 | 1 min |
| Phase B: 开局序列 | Phase A | 部署→电厂→兵营 via WS 命令 | 3 min |
| Phase C: 生产 | 有兵营/工厂 | 生产步兵/坦克 | 2 min |
| Phase D: 侦察 | 有可移动单位 | 侦察命令→ReconJob 执行 | 3 min |
| Phase E: 战斗 | 有战斗单位+敌人 | 进攻/防御/包围 | 5 min |
| Phase F: 查询+约束 | 任意阶段 | 战况查询/设约束 | 2 min |

---

## 4. 系统改进 Roadmap

### P0 — 阻塞测试的问题（本周）
1. **建筑名称映射**：LLM→GameAPI 名称翻译（Issue 8）
2. **production queue 查询修复**（Issue 9）
3. **GameAPI 连接重连鲁棒性**（Issue 11）

### P1 — 用户体验（下周）
4. **前端"正在思考..."状态**：发命令后立刻显示，LLM 回复后消失
5. **LLM streaming 回答**：查询回答边生成边显示
6. **开局序列自动化**：预定义脚本快速过开局
7. **前端用户消息回显**：聊天区显示用户发的命令（已派 Yu）

### P2 — 系统鲁棒性（两周内）
8. **Job 依赖 DAG**：Kernel 管理 Job 执行顺序
9. **UnitRegistry**：WorldModel 维护全局单位数据库
10. **测试自动化**：test_live_e2e.py 自动化测试脚本
11. **GameAPI integration test 层**

### P3 — 性能优化（月内）
12. **简单意图用 qwen-turbo**
13. **Prompt caching**
14. **WorldModel 增量刷新**
15. **Context summarization**（长任务的 token 管理）

---

## 5. Kernel + 系统行为验证清单

以下是 design.md 中定义的核心行为，对照 live 测试验证状态：

| 设计要求 | 验证状态 | 备注 |
|---|---|---|
| Kernel 无 LLM 依赖 | ✅ | 纯确定性逻辑 |
| Task 生命周期 (create→run→complete) | ✅ | Round 4 验证 |
| Job 资源声明式匹配 | ✅ | Round 3 验证 |
| 优先级抢占 | ⚠️ 未 live 验证 | Mock 测试通过 |
| defend_base 自动响应 | ✅ | Round 3 触发，Round 5 即时反射 |
| ExpertSignal → TaskAgent 路由 | ✅ | blocked/resource_lost signal 正确传递 |
| decision_request + default_if_timeout | ⚠️ 未 live 验证 | Mock 测试通过 |
| Adjutant 三路分类 | ✅ | command/query 验证，reply 未测 |
| 全局约束 create_constraint | ⚠️ | LLM 把 "别追太远" 当 managed task |
| GameLoop 10Hz | ✅ | 但 tick 经常超 100ms budget |
| WorldModel 事件检测 | ✅ | ENEMY_DISCOVERED/BASE_UNDER_ATTACK |
| Job 自动恢复（资源恢复后） | ⚠️ 未验证 | WAITING → RUNNING 自动转换 |
| 多 Task 并发 | ⚠️ 未验证 | 需要同时侦察+建造 |

## Current
优化任务文档已完成，等待用户确认后开始执行

## Queue
详见 optimization_tasks.md，建议执行顺序：
1. T1: Task Phase Template — 阶段约束，阻止 LLM 漂移
2. T2: Complete Task Hard Guard — 框架级 success 条件检查
3. T3: Task→Player 通信工具 — 恢复 design.md §6 核心能力
4. T7: DeployExpert 验证 — 消除 fire-and-forget
5. T5: Signal 日志顺序 — 修正 resource_lost < job_started
6. T4: Conversation 压缩 — 控制 token 膨胀
7. T6: Smart Wake — 无增量跳过 LLM
8. T9: OpenRA 知识补全 — 开局模板 + 科技前置
9. T8: Information Expert — BaseState + ThreatAssessor
10. T10: Adjutant 可观测性

## Blocked
- xi 暂停分配（用户要求节省 token）

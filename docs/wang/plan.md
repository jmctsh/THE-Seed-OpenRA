## Current
四项审计任务全部完成，等待用户指示下一步

## Queue
（根据审计报告，建议优先级）
1. Phase Template 注入 — Task model + Adjutant + SYSTEM_PROMPT 动态化
2. Complete Task Hard Guard — 框架级 success 条件检查
3. Task→Player 通信工具 — send_task_message / ask_player
4. Conversation Sliding Window — 控制 token 膨胀
5. Signal 顺序修正 — start_job() 中 log 移到 rebalance 之前
6. Smart Wake — 无增量信息时跳过 LLM 调用

## Blocked
- xi 暂停分配（用户要求节省 token）

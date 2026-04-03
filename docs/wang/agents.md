# Wang — Knowledge Base

- Agent name: **wang**
- Project: THE-Seed-OpenRA

## agent-chat Communication
- MCP server `agent-chat` is connected and working (5 tools: whoami, check_inbox, send_message, post, check_group)
- 优先使用 MCP，不用 curl fallback

## 游戏侧定义（不是黑盒）
- 游戏单位/建筑的完整定义在 `OpenCodeAlert/mods/ra/rules/` 下的 yaml 文件中
- copilot mod 定义在 `OpenCodeAlert/mods/copilot/rules/` 下
- 关键文件：structures.yaml, vehicles.yaml, infantry.yaml, aircraft.yaml, ships.yaml
- 单位 ID 是大写缩写（POWR=电厂, BARR=兵营, WEAP=战车工厂, PROC=矿场, E1=步枪兵, 3TNK=重型坦克）
- 生产名称解析层：`openra_api/production_names.py`（yu 新增），从 Copilot.yaml 读 alias

## GameAPI 协议
- 持久 TCP 连接，端口 7445
- 请求格式需要 apiVersion/requestId/command/params/language 五个字段
- 换行分隔 JSON 帧协议
- CopilotCommandServer.cs 是 C# 侧入口

## Live 测试已知模式
- Mock 测试全通不代表 live 能工作 — 名称、连接、时序问题只在 live 暴露
- LLM 是唯一性能瓶颈（分类~2s + 决策~5s + 查询~8s），其他组件 <1ms
- WS 测试脚本需要 max_size=10MB 防御 world_snapshot 大帧

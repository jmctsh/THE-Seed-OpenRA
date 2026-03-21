# 修复总结 (Fixes Summary)

本次修复解决了以下问题：

## 1. 核心配置问题 (Core Configuration Issues)

### API 端点修复
**文件**: `the-seed/the_seed/config/schema.py`

**问题**:
- base_url 有双重错误：
  1. 拼写错误: `"hhttps://openai.com/api/v1"` (双 h)
  2. URL 错误: OpenAI 的正确 URL 应该是 `https://api.openai.com/v1`

**修复**:
```python
# 修改前
base_url: Optional[str] = "hhttps://openai.com/api/v1"
model: str = "gpt-4o-mini"

# 修改后 (改为 DeepSeek)
base_url: Optional[str] = "https://api.deepseek.com"
model: str = "deepseek-chat"
```

### API Key 环境变量支持
**文件**: `the-seed/the_seed/config/manager.py`

**问题**: API key 硬编码为 `"sk-xxx"`，无法从环境变量加载

**修复**: 添加环境变量支持
```python
# 从环境变量加载 API key
api_key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY")
if api_key:
    cfg.model_templates["default"].api_key = api_key
```

## 2. Dashboard 界面优化 (Dashboard UI Improvements)

### 左侧面板 - Plan 显示
**文件**: `dashboard/src/app.rs`

**新增功能**: 在左侧面板添加 Plan 列表显示，带视觉指示器：
- `▶` 当前步骤
- `✓` 已完成步骤
- `-` 待执行步骤

### 指标显示修改
**文件**:
- `dashboard/src/app.rs` (前端)
- `the-seed/the_seed/utils/dashboard_bridge.py` (后端)

**修改**:
- Token 消耗: 从"每分钟"改为"总计"
- LLM 调用: 从"每分钟"改为"总计"

### 连接状态指示器
**修改**:
- 移除右侧 Connection 面板 (节省 300px 空间)
- 在顶部栏版本号旁边添加紧凑的连接状态指示器
  - 绿点 = 已连接
  - 红点 = 未连接

## 3. FSM 提示词修复 (FSM Prompt Fixes)

### PlanNode 严格目标遵循
**文件**: `the-seed/the_seed/core/prompt.py`

**问题**: 用户目标 "展开基地车" 被扩展为 "建造矿场、建造兵营"

**修复**: 添加 CRITICAL RULES 强调严格遵循用户目标:
```python
"CRITICAL RULES:\n"
"1. Your ONLY job is to plan how to achieve the [Goal] given by the user.\n"
"2. DO NOT expand or interpret the goal - follow it EXACTLY as stated.\n"
"3. DO NOT assume the goal is already completed.\n"
"4. If the goal is simple and direct (e.g., '展开基地车'), your plan should directly address that specific task.\n"
"5. DO NOT add extra steps beyond what the user asked for.\n\n"
```

## 4. 游戏 API 修复 (Game API Fixes)

### ensure_can_produce_unit 建筑支持
**文件**: `openra_api/game_api.py`

**问题**: 该方法只检查 UNIT_DEPENDENCIES，不支持建筑物

**修复**: 先检查 BUILDING_DEPENDENCIES，再检查 UNIT_DEPENDENCIES
```python
# 先检查是否为建筑
if unit_name in self.BUILDING_DEPENDENCIES:
    deps = self.BUILDING_DEPENDENCIES.get(unit_name, [])
    for dep in deps:
        self.ensure_building_wait_buildself(dep)
else:
    # 否则作为单位处理
    needed_buildings = self.UNIT_DEPENDENCIES.get(unit_name, [])
    # ...
```

## 测试 (Testing)

### 运行测试脚本
```bash
# 设置 API key
export DEEPSEEK_API_KEY='your-api-key-here'

# 运行测试
./test_backend.sh
```

### 完整系统测试
```bash
# 1. 确保 OpenRA 游戏服务器运行在 localhost:7445
# 2. 设置 API key
export DEEPSEEK_API_KEY='your-api-key-here'

# 3. 运行系统
./run.sh

# 4. Dashboard 会自动打开
# 5. 在 Dashboard 中测试命令: 展开基地车
```

## 预期效果 (Expected Results)

1. ✅ 后端成功启动，无 "hhttps://" 错误
2. ✅ Dashboard 成功连接到后端 (顶部绿点指示)
3. ✅ 左侧面板显示 Plan 进度和步骤
4. ✅ Token 和 LLM 调用显示总计数
5. ✅ 命令 "展开基地车" 生成正确的单步计划
6. ✅ ActionGen 执行 deploy_mcv_and_wait()

## 配置说明 (Configuration Notes)

### 使用 DeepSeek (推荐，当前配置)
```bash
export DEEPSEEK_API_KEY='sk-...'
# schema.py 已配置为:
# base_url: "https://api.deepseek.com"
# model: "deepseek-chat"
```

### 切换到 OpenAI (如需要)
1. 修改 `the-seed/the_seed/config/schema.py`:
```python
base_url: Optional[str] = "https://api.openai.com/v1"
model: str = "gpt-4o"
```

2. 设置环境变量:
```bash
export OPENAI_API_KEY='sk-...'
```

## 文件修改列表 (Modified Files)

1. `the-seed/the_seed/config/schema.py` - API 配置修复
2. `the-seed/the_seed/config/manager.py` - 环境变量支持
3. `dashboard/src/app.rs` - UI 优化 (Plan 显示、指标、连接状态)
4. `the-seed/the_seed/utils/dashboard_bridge.py` - 总计指标跟踪
5. `the-seed/the_seed/core/prompt.py` - PlanNode 提示词修复
6. `openra_api/game_api.py` - 建筑生产支持 (已在之前修复)
7. `test_backend.sh` - 新增测试脚本

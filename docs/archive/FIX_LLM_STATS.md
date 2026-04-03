# LLM 统计修复说明

## 问题描述

Dashboard 的 LLM 调用统计和 Action 统计一直显示为 0：
- Total Tokens: 0
- Total LLM Calls: 0
- Total Actions: 0
- Failure Rate / Recovery Rate 也都是 0

## 根本原因

虽然后端 `dashboard_bridge.py` 定义了统计追踪方法：
- `track_llm_call(tokens)` - 追踪 LLM 调用
- `track_action(name, success)` - 追踪 Action 执行

但这些方法**从未被实际调用**，导致统计数据始终为 0。

## 修复方案

### 1. LLM 调用追踪 (model_adapter.py)

在 `_OpenAIClient.complete()` 方法中添加：
```python
# Track LLM call for dashboard metrics
usage = data.get("usage", {})
total_tokens = usage.get("total_tokens", 0)
DashboardBridge().track_llm_call(tokens=total_tokens)
```

**位置**：每次 OpenAI API 调用后，提取 token 使用量并追踪。

### 2. Action 执行追踪 (excution.py)

在 `PythonActionExecutor.execute()` 方法的所有退出点添加追踪：

**成功执行**：
```python
# Track successful action for dashboard
DashboardBridge().track_action("python_action", success=True)
```

**失败场景**（3 处）：
- 代码执行异常
- `__result__` 缺失或格式错误
- `__result__` 缺少必需字段

每处都添加：
```python
DashboardBridge().track_action("python_action", success=False)
```

## 修复效果

现在 Dashboard 会正确显示：
- ✅ **Total Tokens**: 显示所有 LLM 调用使用的总 token 数
- ✅ **Total LLM Calls**: 显示 LLM 调用的总次数
- ✅ **Total Actions**: 显示 Action 执行的总次数
- ✅ **Failure Rate**: 显示 Action 失败率（失败次数 / 总次数）
- ✅ **Recovery Rate**: 显示从失败中恢复的比例

## Git 分支

修复已提交到分支：**`fix/llm-stats-display`**

### 提交记录

```
69ac409 fix: 更新 the-seed submodule 添加 Dashboard 统计追踪
  └─ the-seed: 14b0a36 fix: 添加 LLM 调用和 Action 执行的 Dashboard 统计追踪
```

### 修改的文件

**the-seed submodule**:
- `the_seed/model/model_adapter.py` - 添加 LLM 调用追踪
- `the_seed/core/excution.py` - 添加 Action 执行追踪（成功 + 3 个失败分支）

## 测试验证

运行 Dashboard 并执行一些命令：
```bash
./run.sh
```

预期结果：
1. 每次 LLM 调用后，"Total Tokens" 和 "Total LLM Calls" 会增加
2. 每次 Action 执行后，"Total Actions" 会增加
3. 如果有失败的 Action，"Failure Rate" 会更新
4. 数值会实时显示在 Dashboard 的 "Agent Benchmark" 选项卡中

## 注意事项

1. **统计是累积的**：所有计数器都是从 0 开始累加，Dashboard 重启后会重置
2. **字段名称映射**：后端使用 `tokens_per_min` 和 `llm_calls_per_min` 字段名，但实际存储的是总数（total），而非每分钟的速率
3. **未实现的统计**：
   - Active Tasks（当前待定）
   - Execution Volume（目前等同于 Total Actions）

## 下一步建议

如果需要更精确的统计，可以考虑：
1. 实现真正的"每分钟速率"计算（需要时间窗口滑动平均）
2. 追踪活跃任务数量（需要任务队列管理）
3. 区分不同类型的 Action（不仅是 "python_action"）
4. 添加更详细的错误分类统计

---

**修复完成时间**: 2026-01-19
**修复分支**: `fix/llm-stats-display`
**测试状态**: 待用户验证

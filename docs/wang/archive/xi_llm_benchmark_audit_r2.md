# xi Phase 7.2 回归审计（`415849f`）

## 结论

这轮我**没有清成 `zero-gap`**。

上轮我提的 3 个 blocker 里，**2 个已经实质关闭**：

- raw JSON 带时间戳输出、`QWEN_API_KEY` 缺失时不再覆盖主报告，这条已通过
- T6 的正文分析和 optimization/cost 表述已明显收紧，不再把未测项直接写成已验证结论

但还剩 **1 个新的实现 blocker**：CLI 里宣称支持的 `--skip-live` 实际没有接到执行逻辑，仍会跑 live Qwen 并改写报告。另有 2 个 should-fix。

## 已关闭项

### 1. 已关闭 — raw JSON 时间戳输出 + 无 key 不覆盖报告

- [tests/test_llm_benchmark.py](/Users/kamico/work/theseed/THE-Seed-OpenRA/tests/test_llm_benchmark.py#L297)
- [tests/test_llm_benchmark.py](/Users/kamico/work/theseed/THE-Seed-OpenRA/tests/test_llm_benchmark.py#L316)
- [tests/test_llm_benchmark.py](/Users/kamico/work/theseed/THE-Seed-OpenRA/tests/test_llm_benchmark.py#L323)
- [tests/test_llm_benchmark.py](/Users/kamico/work/theseed/THE-Seed-OpenRA/tests/test_llm_benchmark.py#L328)

现在脚本会先导出 `docs/llm_benchmark_YYYYMMDD_HHMMSS.json`，并且只有在存在 real API 结果时才更新 `docs/llm_benchmark_report.md`。

我本地验证了：
- `QWEN_API_KEY='' python3 tests/test_llm_benchmark.py`
- 返回码 `0`
- 主报告 hash 保持不变
- 新 raw JSON 文件会生成

所以“无 API key 不覆盖报告”这条现在是成立的。

### 2. 已关闭 — T6 正文结论已降级成“首轮意图正确，multi-turn 待测”

- [docs/llm_benchmark_report.md](/Users/kamico/work/theseed/THE-Seed-OpenRA/docs/llm_benchmark_report.md#L47)
- [docs/llm_benchmark_report.md](/Users/kamico/work/theseed/THE-Seed-OpenRA/docs/llm_benchmark_report.md#L48)

正文分析现在明确写了：
- 只验证了 first-turn `query_world`
- full multi-turn coordination 需要 agentic loop integration test
- multi-Job coordination quality 是 `untested`

这已经把上轮最严重的 overclaim 主体关掉了。

### 3. 已关闭 — cost / optimization 被重新标成 estimate / untested

- [docs/llm_benchmark_report.md](/Users/kamico/work/theseed/THE-Seed-OpenRA/docs/llm_benchmark_report.md#L55)
- [docs/llm_benchmark_report.md](/Users/kamico/work/theseed/THE-Seed-OpenRA/docs/llm_benchmark_report.md#L59)
- [docs/llm_benchmark_report.md](/Users/kamico/work/theseed/THE-Seed-OpenRA/docs/llm_benchmark_report.md#L69)
- [docs/llm_benchmark_report.md](/Users/kamico/work/theseed/THE-Seed-OpenRA/docs/llm_benchmark_report.md#L72)

成本现在明确标了 `*(estimate)*`，optimization 也标成 `*(untested)*`，这部分不再伪装成实测结果。

### 4. 已关闭 — `dotenv` 现在是优雅降级

- [tests/test_llm_benchmark.py](/Users/kamico/work/theseed/THE-Seed-OpenRA/tests/test_llm_benchmark.py#L23)
- [tests/test_llm_benchmark.py](/Users/kamico/work/theseed/THE-Seed-OpenRA/tests/test_llm_benchmark.py#L340)
- [tests/test_llm_benchmark.py](/Users/kamico/work/theseed/THE-Seed-OpenRA/tests/test_llm_benchmark.py#L344)

`python-dotenv` 不再是硬依赖；缺失时会继续执行，并打印提示。

### 5. 已关闭 — `--help` 现在正常返回

- [tests/test_llm_benchmark.py](/Users/kamico/work/theseed/THE-Seed-OpenRA/tests/test_llm_benchmark.py#L333)
- [tests/test_llm_benchmark.py](/Users/kamico/work/theseed/THE-Seed-OpenRA/tests/test_llm_benchmark.py#L337)

我本地验证：
- `python3 tests/test_llm_benchmark.py --help`
- 立即退出，返回码 `0`
- usage/help 文本正确输出

## Remaining Finding

### 1. Blocker — `--skip-live` 只是被 argparse 解析到了，但没有真正影响执行路径

- [tests/test_llm_benchmark.py](/Users/kamico/work/theseed/THE-Seed-OpenRA/tests/test_llm_benchmark.py#L337)
- [tests/test_llm_benchmark.py](/Users/kamico/work/theseed/THE-Seed-OpenRA/tests/test_llm_benchmark.py#L346)
- [tests/test_llm_benchmark.py](/Users/kamico/work/theseed/THE-Seed-OpenRA/tests/test_llm_benchmark.py#L274)

根因很直接：
- CLI 解析了 `args = parser.parse_args()`
- 但后续 `asyncio.run(main())` 没把 `args` 传进去
- `main()` 内部仍然只看 `QWEN_API_KEY`，完全不看 `args.skip_live`

我本地复现：
- `python3 tests/test_llm_benchmark.py --skip-live`
- 在当前环境有 `QWEN_API_KEY` 的情况下，它仍然执行了 live `Qwen3.5 (qwen-plus)` 路径
- 仍然更新了 `docs/llm_benchmark_report.md`
- stdout 里明确出现了 live Qwen 的三条结果，而不是只跑 mock baseline

这不是纯粹的 nit。因为一旦 reviewer 以为 `--skip-live` 会避免：
- 花费 API 调用时间/费用
- 覆盖当前正式报告

实际都会失效。

## Should-fix

### 2. Should-fix — `--model` 也同样是“解析了但没接线”

- [tests/test_llm_benchmark.py](/Users/kamico/work/theseed/THE-Seed-OpenRA/tests/test_llm_benchmark.py#L336)
- [tests/test_llm_benchmark.py](/Users/kamico/work/theseed/THE-Seed-OpenRA/tests/test_llm_benchmark.py#L277)

`--model` 被 argparse 接住了，但 `main()` 里仍然硬编码 `model="qwen-plus"`。这说明 CLI 的参数面还没真正闭环。

### 3. Should-fix — 表格/推荐摘要仍残留一点比正文更强的措辞

- [docs/llm_benchmark_report.md](/Users/kamico/work/theseed/THE-Seed-OpenRA/docs/llm_benchmark_report.md#L28)
- [docs/llm_benchmark_report.md](/Users/kamico/work/theseed/THE-Seed-OpenRA/docs/llm_benchmark_report.md#L64)

正文已经老实很多了，但：
- T6 结果表仍写 `OK: querying world first (multi-turn expected)`
- 推荐摘要仍写 `Correct tool_use for all tested scenarios`

这两句现在不算 blocker，因为正文已明确写了 `multi-Job coordination quality is untested`；但如果要让报告前后一致，最好把摘要也同步收紧。

## 本地验证

我执行了：

- `python3 -m py_compile tests/test_llm_benchmark.py`
- `python3 tests/test_llm_benchmark.py --help`
- `QWEN_API_KEY='' python3 tests/test_llm_benchmark.py`
- `python3 tests/test_llm_benchmark.py --skip-live`

结果：

- `--help` 正常
- `no-key` 模式下主报告不会被覆盖，且会生成时间戳 raw JSON
- 但 `--skip-live` 仍然跑 live Qwen，并覆盖报告

## 最终判断

当前我的口径是：**还差 1 个 blocker，不能清成 `zero-gap`**。

如果 xi 把 `args.skip_live` / `args.model` 真正接进执行逻辑，这条 7.2 基本就可以收口了。

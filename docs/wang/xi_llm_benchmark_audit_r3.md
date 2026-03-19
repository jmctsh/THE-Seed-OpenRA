# xi Phase 7.2 最终回归审计（`6311e2a`）

## 结论

这轮我把 `7.2` 清成了 **`zero blockers`**。

上轮剩下的两个 CLI 接线问题现在都已经实质关闭：

- `--skip-live` 会真正跳过 live Qwen 路径，不再触发 real API 调用
- `--model` 会真正传到 `QwenProvider(model=...)`

按我的审计口径，`Phase 7.2` 现在可以关闭；如果 Wang 以这条为项目最终回归门槛，那么项目也可以一起收口。

## 已关闭项

### 1. 已关闭 — `--skip-live` 现在真正切断 live Qwen 执行路径

- [tests/test_llm_benchmark.py](/Users/kamico/work/theseed/THE-Seed-OpenRA/tests/test_llm_benchmark.py#L275)
- [tests/test_llm_benchmark.py](/Users/kamico/work/theseed/THE-Seed-OpenRA/tests/test_llm_benchmark.py#L283)
- [tests/test_llm_benchmark.py](/Users/kamico/work/theseed/THE-Seed-OpenRA/tests/test_llm_benchmark.py#L330)
- [tests/test_llm_benchmark.py](/Users/kamico/work/theseed/THE-Seed-OpenRA/tests/test_llm_benchmark.py#L355)

现在脚本的执行逻辑是：

- `skip_live=True` 时直接走 `Qwen3.5: SKIPPED (--skip-live)`
- 不会实例化 `QwenProvider`
- 不会跑 live benchmark
- 因为没有 real result，`docs/llm_benchmark_report.md` 也不会被覆盖

我按 Wang 指定的同一条 repro 做了本地验证：

- `python3 tests/test_llm_benchmark.py --skip-live`

结果：

- 返回码 `0`
- stdout 明确出现 `Qwen3.5: SKIPPED (--skip-live)`
- stdout **没有**出现 live `Qwen3.5 (...)` header
- stdout 明确出现 `Report NOT updated`
- `docs/llm_benchmark_report.md` hash 保持不变
- 只生成了时间戳 raw JSON

所以“`--skip-live` 实际仍会调 real Qwen”这个 blocker 现在已经关掉了。

### 2. 已关闭 — `--model` 现在真正进入 `QwenProvider`

- [tests/test_llm_benchmark.py](/Users/kamico/work/theseed/THE-Seed-OpenRA/tests/test_llm_benchmark.py#L283)
- [tests/test_llm_benchmark.py](/Users/kamico/work/theseed/THE-Seed-OpenRA/tests/test_llm_benchmark.py#L343)
- [tests/test_llm_benchmark.py](/Users/kamico/work/theseed/THE-Seed-OpenRA/tests/test_llm_benchmark.py#L355)

这次不是只停在 argparse 层，而是：

- CLI 解析 `args.model`
- `asyncio.run(main(skip_live=args.skip_live, model=args.model))`
- `main()` 再把这个值传入 `QwenProvider(api_key=qwen_key, model=model)`

我补了一个无网络捕获验证：

- 动态载入 `tests/test_llm_benchmark.py`
- 用 `FakeQwenProvider` 替换真实 provider
- 调用 `main(skip_live=False, model=\"custom-model\")`

捕获结果是：

- provider 类型确实变成 `FakeQwenProvider`
- 实际收到的 `model` 值是 `custom-model`

这说明 `--model` 不再是 parsed-but-unused。

## 本地验证

我执行了：

- `python3 -m py_compile tests/test_llm_benchmark.py`
- `python3 tests/test_llm_benchmark.py --help`
- `python3 tests/test_llm_benchmark.py --skip-live`
- 一个无网络的 provider 捕获验证，确认 `main(skip_live=False, model=\"custom-model\")` 会把 `custom-model` 传进 `QwenProvider`

结果：

- `--help` 正常返回
- `--skip-live` 不再触发 live Qwen，也不会覆盖主报告
- `--model` 已真实接线到 provider 构造

验证过程中产生的临时 raw JSON 已清理，没有把本地 benchmark 试跑产物留在工作区里。

## 最终判断

当前我的口径是：**这条 `7.2` 已经没有剩余 blocker，可以清成 `zero blockers`。**

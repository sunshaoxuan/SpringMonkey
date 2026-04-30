# Runtime Notes

This section is for semi-stable operating facts:

- known good paths
- service shapes
- compatibility constraints
- expected runtime locations

These notes may change over time, but they should remain factual and should not silently expand privileges.

- Discord 手动重跑新闻未走 `cron run`：`discord-news-manual-rerun-intent-override.md`
- 当前宿主机恢复基线：`openclaw-runtime-baseline-2026-04.md`
- 当前环境运行基线：`openclaw-current-environment-baseline-2026-04.md`
- 分层故障模型：`openclaw-failure-layer-model-2026-04.md`
- LINE 运行基线：`line-runtime-baseline-2026-04.md`
- LINE / TimesCar 定时任务根因修复与回归：`line-timescar-cron-repair-2026-04.md`
- Codex 主、Qwen/Ollama 兜底策略：`qwen-timeout-retry-policy-2026-04.md`
- 任务执行从单轮聊天向 Goal / Intent / Task / Step / Agent Society 过渡：`agent-society-runtime-guard-2026-04.md`
- Agent Society 开始记录 capability gap 与 helper tool：`agent-society-self-repair-loop-2026-04.md`
- 自增强计算总册：`../policies/AGENT_SELF_IMPROVEMENT_AND_TOOLSMITH_ARCHITECTURE.md`
- 通用定时任务落地与验收：`generic-cron-task-domain-2026-04.md`
- `memory-lancedb` embeddings 维度漂移修复与启动级自愈：`memory-lancedb-raw-embeddings-fix.md`
- 新闻 cron 自动投递只发执行报告的修复：`news-cron-final-broadcast-delivery-fix.md`
- TimesCar 登录页缓存与自主探查基线：`timescar-site-discovery-baseline-2026-04.md`
- 2026 年度再部署 / 灾备总册：`openclaw-redeployment-runbook-2026.md`
- 灾难恢复蓝图与 recovery bundle：`openclaw-disaster-recovery-blueprint-2026-04.md`
- OpenClaw 路由补丁自测：`../scripts/openclaw/test_manual_news_heuristics.py`、宿主机 `test_cron_run_cli.sh`、`integration_verify_host.py`
- 定时新闻走多阶段流水线：`config/news/broadcast.json` 中 `newsExecution.mode=pipeline` 时，`apply_news_config.py` 会把 cron 的 `agentTurn` 改为「先跑 `scripts/news/run_news_pipeline.py` 再投递 `final_broadcast.md`」；宿主机须 `git pull` 后执行 `python3 scripts/news/apply_news_config.py` 与 `verify_news_config.py`
- 同一 Ollama 端点的多模型请求已加“端点串行、同模型优先”补丁，见 `ollama-endpoint-model-queue-2026-04.md`
- 修复→测试→上线顺序与命令：`news-deploy-checklist.md`；就绪检查 `scripts/news/verify_runtime_readiness.py`；当日 memory `scripts/news/ensure_daily_memory.py`

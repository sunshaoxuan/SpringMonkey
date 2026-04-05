# Runtime Notes

This section is for semi-stable operating facts:

- known good paths
- service shapes
- compatibility constraints
- expected runtime locations

These notes may change over time, but they should remain factual and should not silently expand privileges.

- Discord 手动重跑新闻未走 `cron run`：`discord-news-manual-rerun-intent-override.md`
- OpenClaw 路由补丁自测：`../scripts/openclaw/test_manual_news_heuristics.py`、宿主机 `test_cron_run_cli.sh`、`integration_verify_host.py`
- 定时新闻走多阶段流水线：`config/news/broadcast.json` 中 `newsExecution.mode=pipeline` 时，`apply_news_config.py` 会把 cron 的 `agentTurn` 改为「先跑 `scripts/news/run_news_pipeline.py` 再投递 `final_broadcast.md`」；宿主机须 `git pull` 后执行 `python3 scripts/news/apply_news_config.py` 与 `verify_news_config.py`
- 修复→测试→上线顺序与命令：`news-deploy-checklist.md`；就绪检查 `scripts/news/verify_runtime_readiness.py`；当日 memory `scripts/news/ensure_daily_memory.py`

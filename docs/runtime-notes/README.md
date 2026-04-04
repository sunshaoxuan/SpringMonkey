# Runtime Notes

This section is for semi-stable operating facts:

- known good paths
- service shapes
- compatibility constraints
- expected runtime locations

These notes may change over time, but they should remain factual and should not silently expand privileges.

- Discord 手动重跑新闻未走 `cron run`：`discord-news-manual-rerun-intent-override.md`
- OpenClaw 路由补丁自测：`../scripts/openclaw/test_manual_news_heuristics.py`、宿主机 `test_cron_run_cli.sh`、`integration_verify_host.py`

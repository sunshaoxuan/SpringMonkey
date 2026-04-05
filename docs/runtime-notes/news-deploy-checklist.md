# 新闻任务：修复 → 测试 → 上线流程

面向 `news-digest-jst-0900` / `1700` 与 `newsExecution.mode=pipeline` 的标准闭环。

## 阶段 A — 本地（开发机）

1. `python -m py_compile scripts/news/*.py`
2. `python scripts/news/test_news_pipeline.py -v`（含流水线消息与无 LLM 冒烟）
3. `git status` → 提交 → `git push origin main`

## 阶段 B — 宿主机（网关）

路径以现场为准，默认：`/var/lib/openclaw/repos/SpringMonkey`。

```bash
cd /var/lib/openclaw/repos/SpringMonkey
git pull --ff-only origin main
python3 scripts/news/ensure_daily_memory.py
python3 scripts/news/apply_news_config.py
python3 scripts/news/verify_news_config.py
python3 scripts/news/verify_runtime_readiness.py
systemctl restart openclaw.service
sleep 10
systemctl is-active openclaw.service
```

说明：

- `ensure_daily_memory.py`：避免 `read …/memory/YYYY-MM-DD.md` ENOENT。
- `verify_runtime_readiness.py`：确认 `jobs.json` 中新闻任务 payload 含「流水线模式」且超时与配置一致；`feeds.reuters.com` 不可解析时仅 WARN（可用 `--strict-dns` 改为失败）。
- 若需 **Brave web_search**：在网关环境中配置 `BRAVE_API_KEY`（见 OpenClaw 文档）。

## 阶段 C — 集成验证（可 SSH 的开发机）

在含 `HOST_ACCESS.md` 与 `paramiko` 的环境：

```bash
python scripts/openclaw/_run_integration_with_hostaccess.py
```

默认 `--full-contract --no-pull`：dist 契约、`test_manual_news_heuristics.py`、`openclaw cron run` 冒烟。

## 阶段 D — 事故类根因（2026-04-05 09:00）

- OpenClaw **`web_fetch` 未捕获异常导致整进程退出**：需上游修复或升级；本仓库通过 **pipeline 脚本** 降低对网关内并行 `web_fetch` 的依赖。
- **DNS**：宿主机无法解析 `feeds.reuters.com` 时需修 resolv/网络或换 RSS 源。
- **Brave 未配置**：`web_search` 返回 `missing_brave_api_key`，应配置密钥或依赖 RSS/直链。

## 回滚

将 `broadcast.json` 中 `newsExecution.mode` 改为非 `pipeline`（或删除块），再执行 `apply_news_config.py` + 重启网关。

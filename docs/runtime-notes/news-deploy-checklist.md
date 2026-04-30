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
- 新闻流水线工人阶段：`run_news_pipeline.py` 连 Ollama 的顺序为 **`OLLAMA_HOST` 环境变量** → **`broadcast.json` 的 `model.ollamaBaseUrl`** → 回退本机 `127.0.0.1:11434`。定时任务往往没有交互式 shell 里的 `export`，因此必须在配置里写明远端基址（与 OpenClaw 实际使用的节点一致）。
- `model.newsWorker` 默认应为 `openai-codex/gpt-5.4`；若配置为 `ollama/qwen3:14b`，只能作为 Codex 不可用后的兜底。
- 定时任务 payload 里的 shell 命令使用 **`bash -lc 'cd … && python3 …'`**（由 `apply_news_config` 生成），避免以 `cd` 开头触发网关 **exec allowlist miss**。
- `verify_runtime_readiness.py`：确认 `jobs.json` 中新闻任务 payload 含「流水线模式」且超时与配置一致；`runtimeReadiness.rssReachabilityHosts` 中**任一台**可解析即通过；**全部**不可解析时 WARN（`--strict-dns` 则失败）。
- 若需 **Brave web_search**：在网关环境中配置 `BRAVE_API_KEY`（见 OpenClaw 文档）。

## 阶段 C — 集成验证（可 SSH 的开发机）

在含 `HOST_ACCESS.md` 与 `paramiko` 的环境：

```bash
python scripts/openclaw/_run_integration_with_hostaccess.py
```

默认 `--full-contract --no-pull`：dist 契约、`test_manual_news_heuristics.py`、`openclaw cron run` 冒烟。

**端到端（Discord 上可见新闻任务结果）**：拉最新 `main`、宿主机上 `ensure_daily_memory` + `apply_news_config` + `verify_runtime_readiness` 后，用长跑超时执行 `openclaw cron run`（默认 7200s，可用环境变量 `SPRINGMONKEY_E2E_CRON_TIMEOUT_SEC` 调整）：

```bash
python scripts/openclaw/_run_integration_with_hostaccess.py --full-contract --e2e-news-discord
```

可选：`SPRINGMONKEY_E2E_WAIT_PIPE_SEC=1800` 时轮询 `journalctl` 是否出现 `PIPELINE_OK` / `run_news_pipeline.py`（多数网关**不会**把子进程 stdout 写入 systemd 日志，**以 Discord 频道结果为准**）。

## 模型使用策略

**定位**：Codex（`openai-codex/gpt-5.4`）是默认主模型，覆盖新闻编排、逐条处理和终稿格式化；Qwen（`ollama/qwen3:14b`）只做兜底处理器。

| 允许 | 禁止 |
|------|------|
| 逐条新闻摘要（per-query worker 调用） | Discord 长历史控制命令入口 |
| 单条分类与格式校验 | 新闻任务总控与执行调度 |
| 短对话（history < 8000 chars） | 大任务整包直出 |
| 中间稿压缩与提取 | 多轮复杂工具调用决策 |

**配置要点**：
- `model.workerCallMode: "per-query"` — 每个检索查询独立调用主模型，保持超短上下文
- `model.maxWorkerInputChars: 1500` — 单次 worker 输入上限，超出会截断
- `model.chatEscalateWhenHistoryCharsExceed: 8000` — Discord 会话历史超长时应升级到 chatFallback
- `model.qwenUsagePolicy` — 详细的允许/禁止场景列表，由 `apply_news_config.py` 写入 cron payload

**架构分层**：
```
orchestrate (Codex)  →  per-query worker (Codex×N, Qwen fallback)  →  merge  →  finalize (Codex)  →  verify
   编排检索计划              逐条短上下文处理            机械拼接      合并润色成稿          机械校验
```

## 阶段 D — 事故类根因（2026-04-05 09:00）

- OpenClaw **`web_fetch` 未捕获异常导致整进程退出**：需上游修复或升级；本仓库通过 **pipeline 脚本** 降低对网关内并行 `web_fetch` 的依赖。
- **DNS**：若配置中的 RSS 探测主机**全部**不可解析，需修 resolv/网络；单点 `feeds.reuters.com` 失败时可依赖 `www.reuters.com` 等备用域名（见 `broadcast.json` 的 `rssFeedHints`）。
- **Brave 未配置**：`web_search` 返回 `missing_brave_api_key`，应配置密钥或依赖 RSS/直链。

## 回滚

将 `broadcast.json` 中 `newsExecution.mode` 改为非 `pipeline`（或删除块），再执行 `apply_news_config.py` + 重启网关。

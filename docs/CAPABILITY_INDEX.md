# 能力索引：汤猴 / OpenClaw / SpringMonkey 仓库

**用途**：做任何运维、改配置、写脚本前，**先查本页**，再点进专题文档或脚本路径；避免在仓库里「大海捞针」。

**权威层级**（详见 `docs/policies/DOCS_AUTHORITY_MODEL.md`）：**线上宿主机真实配置 > 本仓库策略与事实类文档 > 仅报告类记录**。

---

## 1. 线上环境与入口（无密钥）

| 能力 | 说明 | 文档 / 位置 |
|------|------|-------------|
| 网关主机名 | `ubuntu-2625` | `docs/ops/HOST_ACCESS_REDACTED.md` |
| 远程方式 | Tailscale SSH、FRP SSH（具体 IP/密码**不在**仓库） | 同上 |
| 持久服务 | `frpc`、`tailscaled`、`ssh`、`docker` 等 | 同上 |
| OpenClaw 运行目录 | `/var/lib/openclaw/.openclaw` | 同上 |
| 仓库现场路径 | 常见 `/var/lib/openclaw/repos/SpringMonkey/` | `README.md` |
| **本机→宿主机 SSH 工具链**（Python、`paramiko`、一次性安装） | 固定 `OPENCLAW_PYTHON`、不重复 `pip install` | `docs/ops/SSH_TOOLCHAIN.md`、`scripts/requirements-ssh.txt` |
| **工具注册表与场景映射** | 何时用哪个脚本、参数约定、分裂 vs 组合 | `docs/ops/TOOLS_REGISTRY.md` |
| **远程统一 CLI** | `openclaw_remote_cli.py`（git-pull / diag / doctor / line-install / line-push / recover） | `scripts/openclaw_remote_cli.py` |
| **宿主机拉取 SpringMonkey** | `git pull` + 可选重启；见 §7 | `scripts/remote_springmonkey_git_pull.py`、`docs/ops/TOOLS_REGISTRY.md` §7 |
| 宿主机密钥 / 私网 IP | **勿写入仓库**；若本地有仅本机 `HOST_ACCESS.md`，与仓库 **脱敏版** 对照使用 | 仓库仅 `HOST_ACCESS_REDACTED.md` |

**红线**：未经明确授权，不执行改变 Tailscale 认证/暴露态的命令（见 `HOST_ACCESS_REDACTED.md` § Tailscale Red Line）。

---

## 2. OpenClaw 运行时（已文档化事实）

| 能力 | 说明 | 文档 |
|------|------|------|
| systemd 形态 | `openclaw.service` → `/usr/local/bin/openclaw-gateway-supervise`，**不要**直接回退为裸 `openclaw gateway run` | `docs/ops/HOST_ACCESS_REDACTED.md`、`docs/ops/OPENCLAW_MONITORING_PLAN.md` |
| 沙箱 | `MemoryDenyWriteExecute=false`（V8 兼容） | `OPENCLAW_MONITORING_PLAN.md` |
| 环境变量 | `HOME=/var/lib/openclaw`；**勿**再设 `OPENCLAW_HOME=/var/lib/openclaw/.openclaw` | 同上 |
| Gateway 绑定 | `--bind loopback`、`gateway.mode=local` | 同上 |
| HTTP 监听 | 默认 **127.0.0.1:18789**（本机 `/line/webhook` 诊断用） | `scripts/remote_diag_openclaw_webhook.py`、运维对话记录 |
| 共享能力入口 | `openclaw.service` 通过 drop-in 加载 `/etc/openclaw/openclaw.env`；Discord / LINE 共用同一套 provider secret 与 `tools.elevated.allowFrom` | `scripts/remote_enable_shared_channel_capabilities.py`、`docs/runtime-notes/openclaw-runtime-baseline-2026-04.md` |
| 聊天主模型 | `ollama/qwen3:14b` 主力，`openai-codex/gpt-5.4` 候补 | `config/news/broadcast.json`、`docs/runtime-notes/openclaw-runtime-baseline-2026-04.md` |
| qwen 超时策略 | `qwen3:14b` 超时先在同模型内重试 3 次，现有 qwen cron 超时基线抬到 `1800s`，耗尽后才允许切 `codex` | `scripts/remote_install_qwen_timeout_retry_policy.py`、`docs/runtime-notes/qwen-timeout-retry-policy-2026-04.md` |
| Browser backend | 常驻 Chrome + raw CDP，默认 `127.0.0.1:18800`，OpenClaw profile `openclaw` | `scripts/remote_enable_persistent_browser_backend.py`、`scripts/remote_install_browser_guardrails.py`、`docs/runtime-notes/openclaw-runtime-baseline-2026-04.md` |
| 长记忆 | `memory-lancedb`、LanceDB 路径、embedding 策略 | `HOST_ACCESS_REDACTED.md`、`docs/ops/OPENCLAW_VECTOR_BACKEND_PLAN.md` |
| 监控与审计 | 日志路径、`openclaw-snapshot.timer` 等 | `docs/ops/OPENCLAW_MONITORING_PLAN.md` |
| 自动更新（root 侧） | `openclaw-update.timer`、脚本路径 | `docs/ops/OPENCLAW_AUTO_UPDATE_2026-03-26.md` |
| Discord 入口 | 服务器 `PKROCOHR001`、频道 `public`、策略要点 | `HOST_ACCESS_REDACTED.md` |
| 新闻播报 | 定时任务、流水线、`broadcast.json` 域；成功分支最终回答必须直接等于 `final_broadcast.md` 正文 | `docs/runtime-notes/news-task-domain.md`、`news-deploy-checklist.md`、`docs/runtime-notes/news-cron-final-broadcast-delivery-fix.md` |
| 年度再部署 / 灾备 | 汇总 2026 已落地运行时改动、宿主机真值与恢复顺序 | `docs/runtime-notes/openclaw-redeployment-runbook-2026.md` |
| 通用定时任务 | 普通 recurring task 的真实落地入口与验收规则；不能只凭对话宣称任务已创建 | `docs/runtime-notes/generic-cron-task-domain-2026-04.md`、`scripts/cron/upsert_generic_cron_job.py` |
| LINE | Webhook 路径默认 `/line/webhook`、插件 `@openclaw/line`、需 HTTPS 公网；`dmPolicy` / pairing / open / frpc 映射见专项基线文档 | `docs/runtime-notes/line-runtime-baseline-2026-04.md`、本仓库 `scripts/remote_*.py`、`remote_line_*.sh` |
| TimesCar 自动化 | 登录入口不再写死为单一 URL；采用“缓存优先，失效后自主探查并回写缓存” | `docs/runtime-notes/timescar-site-discovery-baseline-2026-04.md` |
| LINE TimesCar cron 修复 | 解释为什么 `LINE` 自修复会越修越差、`NO_REPLY` 的 `not-delivered` 应如何解读，以及 `timescar-*` 的当前稳定链路 | `docs/runtime-notes/line-timescar-cron-repair-2026-04.md` |
| 国际渠道预部署 | Telegram / Slack / Signal / Matrix / IRC / Twitch 等插件已预部署，但默认不写 token | `scripts/remote_enable_international_channels.py`、`docs/runtime-notes/openclaw-runtime-baseline-2026-04.md` |

**注意**：`OPENCLAW_MONITORING_PLAN.md` 前段曾有「未下令前不启动」等历史结论，后段与 `docs/ops/*` 中 **已稳定运行** 的描述可能并存；以**当前** `systemctl` 与最新 ops 为准。

---

## 3. 仓库内可执行脚本（按目录）

先读：`scripts/INDEX.md`（脚本入口索引，避免重复写临时脚本）。

### 3.1 远程 SSH（从 Windows/开发机跑，需 `paramiko`）

| 脚本 | 作用 |
|------|------|
| `scripts/remote_diag_openclaw_webhook.py` | 服务状态、`ss`、`curl` 本机 Webhook、`frpc` 片段、日志 |
| `scripts/remote_enable_shared_channel_capabilities.py` | 统一 Discord / LINE 的共享能力入口：加载 `/etc/openclaw/openclaw.env` 并同步 `tools.elevated.allowFrom` |
| `scripts/remote_enable_browser_capabilities.py` | 修复 Node TLS / `web_fetch` 证书链，并安装 `xvfb` + Playwright，固化浏览器能力基线 |
| `scripts/remote_refresh_capability_awareness.py` | 刷新 runtime workspace 的能力基线提示，避免沿用过时的“无联网能力”认知 |
| `scripts/remote_repair_memory_lancedb.py` | 修复 `memory-lancedb` embeddings 路径与维度配置，重启 gateway 并做长记忆回归验证 |
| `scripts/remote_install_memory_lancedb_guard.py` | 为 `memory-lancedb` 安装启动级自愈守护，避免补丁被升级/重装覆盖后静默回退 |
| `scripts/remote_enable_international_channels.py` | 预部署国际向官方渠道插件（Telegram / Slack / Signal / Matrix 等），默认不写密钥 |
| `scripts/push_line_credentials_remote.py` | 将 LINE token/secret 写入宿主机并启用 `channels.line` |
| `scripts/remote_install_line_plugin_fix.py` | 安装 `@openclaw/line` 并重启服务 |
| `scripts/remote_line_openclaw_setup.sh` | 宿主机上 bash：安装插件、合并 `channels.line`（占位密钥） |
| `scripts/remote_line_apply_secrets.sh` | 宿主机上 bash：用环境变量写入密钥并启用 |

### 3.2 新闻与流水线

| 路径 | 作用 |
|------|------|
| `scripts/news/run_news_pipeline.py` | 多阶段新闻流水线 |
| `scripts/news/apply_news_config.py` / `verify_news_config.py` | 配置应用与校验 |
| `scripts/news/verify_runtime_readiness.py` | 运行时就绪 |
| `scripts/news/ensure_daily_memory.py` | 当日 memory |
| `config/news/broadcast.json` | 新闻配置真源（与流水线联动） |

### 3.3 OpenClaw 补丁与集成

| 路径 | 作用 |
|------|------|
| `scripts/openclaw/patch_news_router_v*.py` | 路由补丁（版本递增，以现场为准） |
| `scripts/openclaw/integration_verify_host.py` | 宿主机集成验证（需 `paramiko`） |
| `scripts/openclaw/test_manual_news_heuristics.py` | 路由启发式自测 |
| `scripts/openclaw/test_cron_run_cli.sh` | cron CLI 自测 |

### 3.4 Git hooks

| 路径 | 作用 |
|------|------|
| `scripts/hooks/pre-commit`、`pre-push` | 本地钩子（按需启用） |

---

## 4. 策略与治理（给人看的边界）

| 文档 | 内容 |
|------|------|
| `docs/policies/DOCS_AUTHORITY_MODEL.md` | 文档权威层级 |
| `docs/policies/REPOSITORY_GUARDRAILS.md` | 分支、`bot/openclaw` 可写范围、秘密禁止 |
| `docs/policies/INTENT_TOOL_ROUTING_AND_ACCUMULATION.md` | 意图→工具→任务闭环 |
| `docs/policies/EXECUTION_AND_RECOVERY_LOOP.md` | 执行与恢复 |
| `docs/policies/TASK_DELIVERY_STANDARD.md` | 交付标准 |

---

## 5. 文档重复与选用建议（避免混淆）

| 现象 | 建议 |
|------|------|
| **同名** `OPENCLAW_AUTO_UPDATE_2026-03-26.md`、`OPENCLAW_PERMISSION_CHANGELOG.md` 同时存在于 `docs/ops/` 与 `docs/reports/` | **以 `docs/ops/` 为完整版**（含背景与原因）；`docs/reports/` 多为**精简摘要或快照**，适合历史记录。新增修改优先在 **ops** 落地，reports 可只放指针或简短结论。 |
| `README.md` 称 `docs/ops/` 为「legacy imported pending reclassification」 | 实际 **ops** 仍承担大量**现行真值**；重分类未完成前，**不要**仅因路径名忽略 ops。 |
| 仓库外 `HOST_ACCESS.md`（含敏感） vs 仓库 `HOST_ACCESS_REDACTED.md` | **仓库只保留脱敏版**；敏感内容仅本地或密码管理器。 |

---

## 6. 做事时的推荐顺序

1. **读本页** → 定位能力属于哪一类（入口、OpenClaw、新闻、LINE、策略）。  
2. **打开对应专题文档或脚本**（上表链接）。  
3. **需要动宿主机时**：先 `SSH_TOOLCHAIN` 固定 Python，再跑 `remote_*.py`；**不在**脚本里写死 Token。  
4. **需要改策略/意图路由**：只改 `docs/policies/` 与约定脚本，并遵守 `REPOSITORY_GUARDRAILS.md`。

---

## 7. 本索引未覆盖时

- 在仓库 `rg`/语义搜索前，先扩展本表「**脚本**」与「**docs**」列表（欢迎 PR 补一行）。  
- 外部真源：**OpenClaw 官方文档**、LINE Developers、宿主机 `openclaw.json`（不在 Git）。

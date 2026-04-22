# Scripts 索引（远程运维 / Line / 新闻）

这个索引用于避免重复造轮子。遇到同类任务，先查本页再执行脚本。

**设计原则与场景分裂说明**：`docs/ops/TOOLS_REGISTRY.md`  
**统一 CLI（子命令 → 各脚本）**：`openclaw_remote_cli.py`（例：`python SpringMonkey/scripts/openclaw_remote_cli.py list`）

## 0. 前置（只做一次）

- 安装依赖：`python -m pip install -r SpringMonkey/scripts/requirements-ssh.txt`
- 配置 Python：见 `docs/ops/SSH_TOOLCHAIN.md`
- 远程脚本统一环境变量：
  - `OPENCLAW_SSH_PASSWORD`（或 `SSH_ROOT_PASSWORD`）

## 1. Git 同步（汤猴宿主机拉取 SpringMonkey）

- `remote_springmonkey_git_pull.py`
  - 用途：在 **`/var/lib/openclaw/repos/SpringMonkey`** 执行 `git pull`；可选 `OPENCLAW_RESTART_AFTER_PULL=1` 后重启 `openclaw.service`。
  - 流程约定见：`docs/ops/TOOLS_REGISTRY.md` §7。

- `remote_create_openclaw_recovery_bundle.py`
  - 用途：从宿主机打包当前 OpenClaw 恢复包到本地，包含 `openclaw.json`、`cron/jobs.json`、workspace、state、sessions、memory、systemd drop-in、`/usr/local/lib/openclaw` 与 manifest。
  - 典型用法：`python SpringMonkey/scripts/remote_create_openclaw_recovery_bundle.py`

- `remote_install_openclaw_recovery_timer.py`
  - 用途：在宿主机安装每日 recovery bundle 定时备份与自动清理，默认每日生成恢复包，并保留近 7 日、近 8 周、近 6 月的关键备份。
  - 典型用法：`python SpringMonkey/scripts/remote_install_openclaw_recovery_timer.py`

- `local_sync_openclaw_recovery_bundle.py`
  - 用途：在本地机器调用远程恢复包导出脚本，并按本地保留策略自动清理旧包。
  - 典型用法：`python SpringMonkey/scripts/local_sync_openclaw_recovery_bundle.py`

- `install_local_openclaw_recovery_pull_task.py`
  - 用途：在 Windows 本地安装每日 Scheduled Task，自动执行 `local_sync_openclaw_recovery_bundle.py`。
  - 典型用法：`python SpringMonkey/scripts/install_local_openclaw_recovery_pull_task.py`

## 2. OpenClaw 远程诊断与修复

- `remote_diag_openclaw_webhook.py`
  - 用途：检查 `openclaw.service`、监听端口、`/line/webhook` 本机可达、`frpc` 片段、最近日志。
  - 典型用法：`python SpringMonkey/scripts/remote_diag_openclaw_webhook.py`

- `remote_openclaw_doctor_fix.py`
  - 用途：针对 `Config invalid / legacy key` 类配置问题执行 `openclaw doctor --fix`，并重启服务。
  - 典型用法：`python SpringMonkey/scripts/remote_openclaw_doctor_fix.py`

- `remote_enable_shared_channel_capabilities.py`
  - 用途：为 Discord / LINE 建立同一套共享能力入口；给 `openclaw.service` 加载统一环境文件 `/etc/openclaw/openclaw.env`，并把 `tools.elevated.allowFrom` 同时放行给 `discord` 与 `line`。
  - 典型用法：`python SpringMonkey/scripts/remote_enable_shared_channel_capabilities.py`

- `remote_enable_browser_capabilities.py`
  - 用途：修复 Node HTTPS 证书链、安装 `xvfb` 与 Playwright，并为 OpenClaw 固化可用的浏览器能力基线。
  - 典型用法：`python SpringMonkey/scripts/remote_enable_browser_capabilities.py`

- `remote_install_browser_guardrails.py`
  - 用途：为常驻浏览器安装哨兵标签、标签数阈值与内存阈值清理守护。
  - 典型用法：`python SpringMonkey/scripts/remote_install_browser_guardrails.py`

- `remote_enable_persistent_browser_backend.py`
  - 用途：拉起常驻 Chrome raw CDP backend（默认 `127.0.0.1:18800`），并把 OpenClaw browser 默认 profile 指向该会话。
  - 典型用法：`python SpringMonkey/scripts/remote_enable_persistent_browser_backend.py`

- `remote_refresh_capability_awareness.py`
  - 用途：刷新运行时 workspace 注入文件中的“能力认知基线”，避免 LINE / Discord 沿用过时的“没有上网能力”自我描述。
  - 典型用法：`python SpringMonkey/scripts/remote_refresh_capability_awareness.py`

- `remote_repair_memory_lancedb.py`
  - 用途：修复 `memory-lancedb` 插件的 embeddings 路径与维度配置，重启 gateway 并做长记忆回归验证。
  - 典型用法：`python SpringMonkey/scripts/remote_repair_memory_lancedb.py`

- `remote_install_memory_lancedb_guard.py`
  - 用途：为 `memory-lancedb` 安装启动级自愈守护；每次 `openclaw.service` 启动前自动重打补丁，启动后自动校验 embeddings 必须为 1024 维。
  - 典型用法：`python SpringMonkey/scripts/remote_install_memory_lancedb_guard.py`

- `remote_install_qwen_timeout_retry_policy.py`
  - 用途：给宿主机当前 `pi-embedded` bundle 加上 `qwen3:14b` 超时三次内重试、三次后才允许切 `codex` 的策略，并把现有所有 qwen cron 的 `timeoutSeconds` 统一抬到 `1800`。
  - 典型用法：`python SpringMonkey/scripts/remote_install_qwen_timeout_retry_policy.py`

- `remote_install_three_phase_reply_guard.py`
  - 用途：给 direct chat 安装“三段式可见性”补丁，确保先回执、长任务给进度、空结果时给兜底收尾，而不是石沉大海。
  - 典型用法：`python SpringMonkey/scripts/remote_install_three_phase_reply_guard.py`

- `remote_install_line_direct_visibility_watchdog.py`
  - 用途：给 LINE 直连任务安装非模型回执与长时 watchdog；即使模型卡在首包阶段，也会先发“已收到”的可见文本，而不是只转圈。
  - 典型用法：`python SpringMonkey/scripts/remote_install_line_direct_visibility_watchdog.py`

- `remote_install_operational_execution_guard.py`
  - 用途：给操作型任务安装 plan-execute-observe-replan 执行协议，网站/账号类任务优先走 browser-first，而不是只靠一段长 thinking。
  - 典型用法：`python SpringMonkey/scripts/remote_install_operational_execution_guard.py`

- `remote_install_agent_society_runtime_guard.py`
  - 用途：执行一次性的 agent society runtime 部署；会把仓库中的 `scripts/openclaw/patch_agent_society_runtime_current.py` 同步到宿主机并应用。
  - 典型用法：`python SpringMonkey/scripts/remote_install_agent_society_runtime_guard.py`

- `remote_install_agent_society_startup_guard.py`
  - 用途：为 agent society runtime 安装启动级自愈守护；以后宿主机只要 `git pull` 到新 patch 脚本，`openclaw.service` 启动前就会从 repo 重打补丁，不再依赖手改残留。
  - 典型用法：`python SpringMonkey/scripts/remote_install_agent_society_startup_guard.py`

- `remote_install_agent_society_kernel.py`
  - 用途：安装 agent society 的最小原生内核，把 `goal -> intent -> task -> step` 的持久化状态根落到宿主机 workspace，而不是只靠 runtime prompt 注入。
  - 典型用法：`python SpringMonkey/scripts/remote_install_agent_society_kernel.py`

- `remote_install_agent_society_kernel_bridge.py`
  - 用途：初始化 direct task -> durable kernel 的 bridge 目录与 bootstrap session，并要求 repo 中存在 helper toolsmith 脚本。
  - 典型用法：`python SpringMonkey/scripts/remote_install_agent_society_kernel_bridge.py`

- `remote_enable_international_channels.py`
  - 用途：启用一批国际向官方渠道插件并预注册空配置入口，默认不写入 token、不主动上线。
  - 典型用法：`python SpringMonkey/scripts/remote_enable_international_channels.py`

## 3. LINE 相关（OpenClaw 侧）

- `remote_install_line_plugin_fix.py`
  - 用途：远程安装 `@openclaw/line`（失败自动尝试 `npx`），重启并查看 line 相关日志。

- `push_line_credentials_remote.py`
  - 用途：将 `LINE_CHANNEL_ACCESS_TOKEN` / `LINE_CHANNEL_SECRET` 写入远程 secrets 文件，并启用 `channels.line.enabled=true`。
  - 必需环境变量：`LINE_CHANNEL_ACCESS_TOKEN`、`LINE_CHANNEL_SECRET`。

- `remote_line_openclaw_setup.sh`
  - 用途：在宿主机上一次性准备 LINE 结构（备份配置、写入占位密钥文件、默认 `enabled=false`）。
  - 场景：首次接入 LINE 前。

- `remote_line_apply_secrets.sh`
  - 用途：在宿主机上用环境变量写入真实 LINE 密钥并启用通道。
  - 场景：你已在 LINE Developers 取得 token/secret 后。

- `remote_frpc_line_webhook_map.py`
  - 用途：在汤猴宿主机上备份并追加 **`/etc/frp/frpc.toml`**，将 **`127.0.0.1:<本地网关端口>`** TCP 映射到 frps 公网端口（默认 **18789 → 31879**），重启 **`frpc.service`** 并做本机 curl 探测。
  - 环境变量：`OPENCLAW_SSH_PASSWORD`；可选 `FRPC_LINE_LOCAL_PORT`、`FRPC_LINE_REMOTE_PORT`、`OPENCLAW_SSH_HOST`、`OPENCLAW_SSH_PORT`。
  - 统一入口：`python SpringMonkey/scripts/openclaw_remote_cli.py frpc-line`

- `remote_diag_frpc_tunnel.py`
  - 用途：只读诊断 frpc 配置片段、`journalctl`、本机 `18789` 监听；说明 **remotePort 在 frps/ccnode 上**，不在汤猴。

- `remote_cat_frpc_config.py`
  - 用途：SSH 拉取汤猴 **`/etc/frp/frpc.toml` 全文**（只读），并尝试写入 `var/remote_frpc_frpc.toml.snapshot.txt`。
  - 统一入口：`python SpringMonkey/scripts/openclaw_remote_cli.py frpc-cat`

## 4. 新闻流水线

- `news/run_news_pipeline.py`：多阶段新闻流水线主入口
- `news/apply_news_config.py` / `news/verify_news_config.py`：新闻配置应用与校验
- `news/verify_runtime_readiness.py`：运行时就绪检查
- `news/ensure_daily_memory.py`：当日 memory 保证

## 4.1 通用定时任务

- `cron/upsert_generic_cron_job.py`
  - 用途：为普通 recurring task 创建 / 更新 / 校验 / 删除 OpenClaw cron 任务，不再靠聊天里“已创建”的口头确认。
  - 典型用法：
    - 创建/更新：`python SpringMonkey/scripts/cron/upsert_generic_cron_job.py --name <job> --expr "<cron>" --message-file <prompt.txt> --delivery-channel <channel> --delivery-to <target>`
    - 校验：`python SpringMonkey/scripts/cron/upsert_generic_cron_job.py --name <job> --verify-only`
    - 删除：`python SpringMonkey/scripts/cron/upsert_generic_cron_job.py --name <job> --delete`

## 5. OpenClaw 补丁与验证

- `openclaw/patch_news_router_v*.py`：新闻路由补丁（按版本增量）
- `openclaw/patch_news_manual_rerun_current.py`：面向当前 `pi-embedded` bundle 的手动新闻重跑修复；自动定位当前活跃 `runEmbeddedAttempt` 文件，强制 Discord 手动重跑走正式 `cron run`，并禁止主会话自由发挥
- `openclaw/patch_memory_lancedb_raw_embeddings_current.py`：修复当前 `memory-lancedb` 插件，强制 `baseUrl` 场景改走原始 HTTP `/v1/embeddings`，避免 SDK 兼容性导致向量维度漂移
- `openclaw/agent_society_runtime_record_gap.py`：把真实 direct-task 失败写进 durable kernel，并在可复用时自动落 helper scaffold 到 `scripts/openclaw/helpers/`；当前已接通 LINE direct `no-response`、`auto-reply failed` 与 watchdog `timeout`
- `openclaw/integration_verify_host.py`：宿主机集成验证
- `openclaw/test_manual_news_heuristics.py`：启发式路由测试

## 6. 执行顺序建议（避免影响主流程）

0. **策略/脚本已改并 push**：先跑 `remote_springmonkey_git_pull.py`（宿主机 `git pull`），再按需 `apply_news_config` / 补丁 / 重启。
1. 先跑 `remote_diag_openclaw_webhook.py` 获取证据
2. 若日志指向配置 schema 问题，跑 `remote_openclaw_doctor_fix.py`
3. 若 Discord / LINE 能力不一致，跑 `remote_enable_shared_channel_capabilities.py`
4. 若联网能力报“没有上网能力”或 `web_fetch` TLS 失败，跑 `remote_enable_browser_capabilities.py`
5. 若需要 OpenClaw 真正可用的 `browser` 自动化，再跑 `remote_enable_persistent_browser_backend.py` 与 `remote_install_browser_guardrails.py`
6. 若模型仍沿用旧认知，再跑 `remote_refresh_capability_awareness.py`
7. 若日志指向 line 插件问题，跑 `remote_install_line_plugin_fix.py`
8. 稳定后再执行 `push_line_credentials_remote.py` 或 `remote_line_apply_secrets.sh`

## 7. Ollama（拉取与同一提示词对比）

- `remote_install_ollama_endpoint_queue.py`
- 用途：给宿主机 OpenClaw 的 Ollama 统一流入口打“同一端点串行、同模型优先”补丁，减少不同模型在同一 Ollama 端点上的频繁切换与超时。

- `ollama_pull_and_benchmark.py`
- 用途：在能访问 Ollama HTTP 的机器上对 **`qwen3:14b` / `gemma3:12b`** 等做固定中文译名提示词对比；可选先 **`/api/pull`** 拉取缺失模型（适合约 **16GB VRAM**，如 RTX 5070 Ti）。
  - 环境变量：`OLLAMA_BASE`（默认 `http://127.0.0.1:11434`），例如 `http://ccnode.briconbric.com:22545`。
  - 仅对比、不下载：`python SpringMonkey/scripts/ollama_pull_and_benchmark.py --chat-only --base <URL>`
  - 拉取并对比：同上去掉 `--chat-only`（pull 耗时较长）。
  - Windows 建议在脚本内已做 UTF-8 控制台修复；另可用 `--output 路径.txt` 将结果以 UTF-8 落盘。

- `ollama_multi_axis_benchmark.py`
  - 用途：多维度（逻辑、数理、翻译、专名、代码、标题压缩、信息边界、JSON 结构化、指令格式、歧义）多轮对比，供 **`newsWorker`** 等主语义选型；输出 Markdown + 可选 JSON。
  - 示例：`python SpringMonkey/scripts/ollama_multi_axis_benchmark.py --base <URL> --rounds 2 --output-md var/ollama_axis_report.md --output-json var/ollama_axis_report.json`

## 8. 约束

- 不在脚本里写死任何 token/secret/password。
- 先保主流程（openclaw.service 稳定）再切换 LINE 到 `enabled=true`。

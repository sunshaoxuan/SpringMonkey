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

强规则：所有会约束或提示 OpenClaw 行为的规则、prompt、路由、任务、投递、guardrail、自修复策略和补丁源，都必须先进入 Git，并能由宿主机通过自动 pull / 受控 pull 获取；不允许把手工上传到宿主机当作 durable 部署。

- `openclaw_behavior_rule_gate.py`
  - 用途：OpenClaw 行为规则机械门禁；若行为规则相关文件未提交、未推送到 `origin/main`，或远端未 pull 到同一 HEAD，则失败。
  - 本地门禁：`python scripts/openclaw_behavior_rule_gate.py`
  - 远端 pull 验证：`python scripts/openclaw_behavior_rule_gate.py --verify-remote-pull`

- `openclaw_release_preflight.py`
  - 用途：发布/回复“已部署”前的本地机械预检；检查 Python 语法与缩进、远程安装脚本内嵌 bash 语法、未加引号 heredoc 中的 `$()` 展开风险，并运行关键定向测试。
  - 典型用法：`python scripts/openclaw_release_preflight.py`
  - 约定：涉及 cron、远程安装器、任务投递、新闻/天气等可执行路径改动时，必须先通过该预检，再提交、推送、远端 pull 和远端状态验证。

- `remote_springmonkey_git_pull.py`
  - 用途：在 **`/var/lib/openclaw/repos/SpringMonkey`** 执行 `git pull`；可选 `OPENCLAW_RESTART_AFTER_PULL=1` 后重启 `openclaw.service`。
  - 流程约定见：`docs/ops/TOOLS_REGISTRY.md` §7。

- `remote_install_repo_sync_timer.py`
  - 用途：在宿主机安装 `openclaw-repo-sync.timer`，每 10 分钟自动同步 SpringMonkey（`fetch`、**仅 fast-forward** 的 `origin/main`、非 `main` 时 `checkout main`、脏工作区先 `stash`）；不重启 `openclaw.service`。升级内嵌脚本时在本机重跑本安装器。详见 `docs/runtime-notes/repo-sync-timer-baseline-2026-04.md`。
  - 注意：这只同步 repo，不自动重打 `dist` 补丁；涉及 runtime patch 的改动仍要靠 installer 或重启时 startup guard 生效。

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

- `remote_install_browser_human_control_helper.py`
  - 用途：部署并 promotion `scripts/openclaw/helpers/browser_cdp_human.py`，让汤猴在 `browser` 工具 targetId/tab/ref 漂移时，能直接通过宿主机常驻 Chrome CDP 做打开、检查、点击、输入与等待文本等人类式动作。
  - 典型用法：`python SpringMonkey/scripts/remote_install_browser_human_control_helper.py`
  - 统一入口：`python SpringMonkey/scripts/openclaw_remote_cli.py browser-human-helper`

- `remote_repair_reply_media_images.py`
  - 用途：修复 OpenClaw 回复图片/浏览器截图发送链路；当日志出现 `dropping blocked reply media`、`Failed to optimize image` 或 `Optional dependency sharp is required` 时，安装/验证 `sharp` 并重启 OpenClaw。
  - 典型用法：`python SpringMonkey/scripts/remote_repair_reply_media_images.py`
  - 只验证：`python SpringMonkey/scripts/remote_repair_reply_media_images.py --check-only`
  - 统一入口：`python SpringMonkey/scripts/openclaw_remote_cli.py reply-media-repair`

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
  - 用途：历史 qwen-first 超时策略安装器；当前默认模型策略已改为 Codex 主、Qwen/Ollama 兜底，除非在迁移旧任务时需要，不应作为新默认策略入口。
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
  - 新建任务会自动做 `execution_depth` 判定；非 `atomic` 任务会被写入 staged/agentic runtime policy wrapper，避免把多步任务藏进黑盒 exec。

- `cron/verify_timescar_delivery_channels.py`：校驗拷出的 `cron/jobs.json` 中，所有 `timescar-*` 的 `delivery.to` 必为私聊频道（见 `docs/runtime-notes/discord-timescar-public-channel-leak.md`），防止租车内容误投公共 Discord。

## 5. OpenClaw 补丁与验证

- `openclaw/patch_news_router_v*.py`：新闻路由补丁（按版本增量）
- `openclaw/patch_news_manual_rerun_current.py`：面向当前 `pi-embedded` bundle 的手动新闻重跑修复；自动定位当前活跃 `runEmbeddedAttempt` 文件，强制 Discord 手动重跑走正式 `cron run`，并禁止主会话自由发挥
- `openclaw/patch_memory_lancedb_raw_embeddings_current.py`：修复当前 `memory-lancedb` 插件，强制 `baseUrl` 场景改走原始 HTTP `/v1/embeddings`，避免 SDK 兼容性导致向量维度漂移
- `openclaw/agent_society_runtime_record_gap.py`：把真实 direct-task 失败写进 durable kernel，并在可复用时自动落 bounded executable helper 到 `scripts/openclaw/helpers/`；当前已接通 LINE direct `no-response`、`auto-reply failed` 与 watchdog `timeout`，并已对齐 `execution_blocked`、`runtime_timeout`、`tool_missing` 这三类失败的 helper 产出、即时验证与自动 promotion 路径
- `openclaw/cron_failure_self_heal.py`：扫描宿主机 journal 里的 cron failure，去重后写入 durable kernel；同样走 `gap -> helper -> pattern -> promotion` 闭环，而不是只给用户发一条失败通知
- `openclaw/job_orchestrator.py`：cron/pipeline job 的通用执行包装器；把脚本命令作为 kernel step 的 action/tool 执行，成功保持 stdout 契约，失败写 gap、触发 helper、自修复后 bounded retry
- `openclaw/agent_society_kernel.py`：durable `goal -> intent -> task -> step` 内核；记录 order/dependency/parallel/shared-context 元数据，并可通过 `tree-report` 输出长流程树状报告
- `openclaw/test_agent_society_tree_report.py`：验证 orchestrated job 不再被拆成 metadata 平铺项，而是保留 intent/task/step 树、依赖和共享上下文
- `openclaw/test_framework_domain_purity.py`：框架纯度回归测试；禁止 kernel / orchestrator 这类通用框架文件硬编码业务域内容
- `openclaw/test_job_orchestrator_success.py`：验证 orchestrator 成功路径保持 stdout 并写 completed observation
- `openclaw/test_job_orchestrator_failure_self_repair.py`：验证 orchestrator 失败路径写 gap、生成 helper，并在一次 bounded retry 后完成
- `openclaw/test_helper_retirement.py`：验证 helper 被 drift gate 连续拒绝后会 deprecated，且不会再进入 future tool candidates
- `openclaw/agent_society_kernel.py`：durable `goal -> intent -> task -> step` 内核，现已包含 `failure_pattern` 累积与 `candidate -> emerging -> learned` 生命周期
- `openclaw/agent_society_helper_toolsmith.py`：生成 bounded business repairer；输出 helper contract、repair workflow 与 drift guard，而不再只是薄 scaffold
- `openclaw/helpers/browser_cdp_human.py`：真实浏览器 CDP fallback helper；当 OpenClaw `browser` 工具 targetId/tab/ref 漂移或误判为 headless/profile=user 时，直接连接宿主机常驻 Chrome CDP，并输出结构化证据
- `openclaw/test_browser_control_helper.py`：验证浏览器控制漂移会被分类为 `browser_control`，并优先选择 `browser_cdp_human.py`
- `openclaw/test_agent_society_composed_repairer_plan.py`：验证 planner 会把多个 promoted business repairer 组合成 bounded repair pipeline，而不是只挑一个 helper
- `openclaw/test_agent_society_step_drift_guard.py`：验证 planner 会在 step 选择时重新做 drift gate，把已经不匹配当前 failure surface 的 promoted repairer 过滤掉
- `openclaw/test_agent_society_repair_graph_budget.py`：验证组合 repair pipeline 会带每步预算上限与 rollback policy，而不是无限扩展 repair graph
- `remote_install_timescar_task_runtime.py`：把 repo 中的 TimesCar 任务脚本同步到宿主机 workspace；不改 cron job 定义，但把“外部单步、内部多步”的订车/续订/查询任务升级为阶段可观察脚本
- `timescar/task_runtime.py`：TimesCar 任务运行时；把阶段、步骤、依赖、共享上下文和最终结果写入 `workspace/state/timescar_traces/*.latest.json`
- `timescar/timescar_fetch_reservations.py`：TimesCar 查询脚本的 repo 基线版；保留现有输出契约，但把登录、打开列表、解析预约等步骤显式写进 trace
- `timescar/timescar_next24h_notice.py`：24 小时取消提醒；保留现有用户消息格式，但把读取预约、解析、筛选候选变成可观察步骤
- `timescar/timescar_book_sat_3weeks.py`：周六订车任务；把“检查现有预约、登录、打开表单、校验确认、提交、回查验证”拆成显式阶段
- `timescar/timescar_extend_sun_3weeks.py`：周日续订任务；把“选择目标预约、定位修改入口、校验确认、提交、回查验证”拆成显式阶段
- `timescar/timescar_daily_report_render.py`：日报渲染仍保持单步输出，但内部改为复用带 trace 的预约查询路径
- `timescar/test_timescar_task_runtime.py`：验证 TimesCar 任务运行时会落 trace 文件并记录阶段状态
- `timescar/test_timescar_next24h_notice.py`：验证 next24h 提醒的解析路径保持兼容
- `staged_jobs/task_trace.py`：轻量 staged task trace 运行时；把多步任务的阶段、步骤、产物和最终结果写进 `workspace/state/task_traces/`
- `staged_jobs/test_task_trace.py`：验证 staged task trace 会落 latest trace 并记录步骤与产物
- `weather/test_discord_weather_report.py`：验证天气任务在假数据下保持输出契约，同时可接受 staged trace 接入
- `news/test_run_news_pipeline_trace.py`：验证新闻流水线在 dry-run / skip-finalize 下仍会写出 staged trace，而不是继续做黑盒 exec
- `openclaw/agent_society_entry_policy.py`：direct task 自动接入策略；把“未来你直接给汤猴布置的真实任务”自动识别成 agent-society / self-improvement 入口，而不是只靠登录类关键词
- `openclaw/test_agent_society_entry_policy.py`：回归验证 direct task 入口策略不会漏掉真实委托，也不会把寒暄和简单闲聊误接入
- `cron/test_upsert_generic_cron_job_policy.py`：验证通用 cron 创建器会自动把天气、新闻、登录、搜索、翻译、投递、自增强等任务判成 staged/agentic，而不是黑盒单步。
- `cron/migrate_existing_cron_to_orchestrator.py`：按审计清单迁移现有多步 cron payload，给 staged 任务补 orchestrator policy wrapper
- `cron/test_migrate_existing_cron_to_orchestrator.py`：验证现有 cron 迁移脚本 dry-run 会命中需要迁移的任务
- `openclaw/test_agent_society_runtime_record_gap.py`：回归验证当前三类已对齐失败会产出并 promotion helper
- `openclaw/test_agent_society_failure_patterns.py`：验证重复失败可聚合成 durable `failure_pattern`
- `openclaw/test_agent_society_pattern_influenced_promotion.py`：验证 `learned failure_pattern` 会反过来影响后续 helper promotion
- `openclaw/test_agent_society_pattern_routing.py`：验证 `learned failure_pattern` 会影响后续 step 的 `tool_candidates / chosen_tool / next_decision`
- `openclaw/test_cron_failure_self_heal.py`：验证 cron failure 会被 watcher 自动写入 durable kernel，并且同一失败会被去重
- `openclaw/test_agent_society_promoted_helper_registry.py`：验证 promoted helper 会进入正式 durable registry，并在后续新 session 中被默认选中
- `openclaw/test_agent_society_business_repairer.py`：验证生成的 helper 已是 business repairer，包含 contract、repair workflow 与 drift guard
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

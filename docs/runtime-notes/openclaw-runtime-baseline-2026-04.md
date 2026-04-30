# 汤猴当前运行基线（2026-04）

用途：把 2026-04-08 到 2026-04-09 实际落到宿主机的关键运行时事实收敛成一份恢复基线，避免只靠聊天记录回忆。

权威说明：

- 本文记录的是“当前已验证可运行”的宿主机基线。
- 若与旧报告冲突，以宿主机当前配置与本文件为准。
- 若宿主机被升级或覆盖，先按本文恢复，再做增量排障。

## 1. 共享能力入口

目标：Discord 与 LINE 共用同一套全局能力与 provider secret，不再按 channel 各配一份。

当前宿主机事实：

- `openclaw.service` 通过 systemd drop-in 加载：`/etc/systemd/system/openclaw.service.d/10-shared-capabilities.conf`
- 该 drop-in 引入统一环境文件：`/etc/openclaw/openclaw.env`
- `BRAVE_API_KEY` 等全局 provider secret 放在 `/etc/openclaw/openclaw.env`
- `openclaw.json` 中：
  - `tools.elevated.allowFrom.discord = ["*"]`
  - `tools.elevated.allowFrom.line = ["*"]`

恢复脚本：

- `python SpringMonkey/scripts/openclaw_remote_cli.py shared-capabilities`

## 2. 聊天主模型

当前宿主机基线：

- 主力聊天模型：`openai-codex/gpt-5.4`
- 候补模型：`ollama/qwen3:14b`
- 新闻总控：`openai-codex/gpt-5.4`
- 新闻 worker：`openai-codex/gpt-5.4`
- Ollama 基址：`http://ccnode.briconbric.com:22545`

仓库真源：

- `config/news/broadcast.json`

说明：

- 新闻、聊天与任务总控基线已统一到 `codex -> qwen fallback`
- `ollama/qwen3:14b` 只应在 Codex 主链路不可用时作为最后兜底
- 若宿主机 `openclaw.json` 漂回 `qwen2.5:14b-instruct`，应视为偏离当前基线

## 2.1 会话压缩基线

当前宿主机基线：

- `agents.defaults.compaction.mode = "safeguard"`
- `agents.defaults.compaction.reserveTokens = 12000`
- `agents.defaults.compaction.keepRecentTokens = 8000`
- `agents.defaults.compaction.reserveTokensFloor = 12000`
- `agents.defaults.compaction.recentTurnsPreserve = 6`

说明：

- 这条基线必须与当前主模型 `openai-codex/gpt-5.4` 的真实上下文窗匹配；若降级到 Qwen/Ollama，再按 `qwen3:14b` 的较小上下文窗保守处理。
- 当前值的目标是降低 Discord / LINE 长会话在高日志、高工具结果场景下突然触发 `Context limit exceeded` 的概率，同时避免把 qwen 路径的 prompt budget 直接压坏。
- 该项是全局 `agents.defaults` 配置，Discord 与 LINE 共用，不是单独 channel 配置。
- 当前宿主机还启用了“任务前预压缩守卫”：当估算 prompt 已达到预算约 `90%`，且会话已进入长任务区间时，会在运行前先 compact，并保留最近若干轮原文，而不是等到中途溢出。

## 3. 联网与浏览器能力

当前宿主机事实：

- Node TLS 已通过共享环境修复：
  - `NODE_OPTIONS=--use-openssl-ca`
  - `NODE_EXTRA_CA_CERTS=/etc/ssl/certs/ca-certificates.crt`
- 普通联网能力应可用：
  - `web_search`
  - `web_fetch`
- 图形浏览器自动化已改为“长时挂载 + raw CDP”：
  - Chrome 可执行文件：`/usr/bin/google-chrome`
  - CDP 端口：`127.0.0.1:18800`
  - OpenClaw browser profile：`openclaw`
- 常驻 browser backend 服务：
  - `openclaw-browser-backend.service`

恢复顺序：

1. `python SpringMonkey/scripts/openclaw_remote_cli.py browser-capabilities`
2. `python SpringMonkey/scripts/openclaw_remote_cli.py browser-backend`
3. `python SpringMonkey/scripts/openclaw_remote_cli.py browser-guardrails`
4. `python SpringMonkey/scripts/openclaw_remote_cli.py capability-awareness`

验证口径：

- `openclaw browser status`
- `openclaw browser profiles`
- `openclaw browser open https://example.com`
- `openclaw browser snapshot`

## 4. 浏览器守护规则

长时挂载不是“普通人工浏览器”，而是受控浏览器服务。

当前约束：

- 常驻只保留 1 个哨兵标签页
- 每轮任务结束后应收敛无关标签
- 由宿主机守护脚本做阈值清理，不依赖模型自觉
- `OPENCLAW_BROWSER_CDP=http://127.0.0.1:18800`

恢复脚本：

- `python SpringMonkey/scripts/openclaw_remote_cli.py browser-guardrails`

## 5. 能力认知基线

问题背景：LINE / Discord 会沿用旧会话认知，把“本轮工具失败”说成“我没有上网能力”。

当前处理：

- runtime workspace 的 `TOOLS.md` 已刷新
- 明确声明：
  - 有 `web_search`
  - 有 `web_fetch`
  - 有 `browser`
  - 如果 browser 本轮失败，只能说“本轮 browser backend 不可用”或“本轮网页访问失败”
  - 不得笼统说“我没有上网能力”
  - 对管理员已授权、且宿主机已具备凭据的既有业务，不要求每次在聊天里重新显式给出密码或 token
  - 直连 LINE 的 TimesCar 业务是这条通用规则的一个已知实例

恢复脚本：

- `python SpringMonkey/scripts/openclaw_remote_cli.py capability-awareness`

## 6. 长记忆

当前基线：

- 默认长记忆插件：`memory-lancedb`
- `plugins.slots.memory = "memory-lancedb"`
- embedding 后端：
  - `model = "bge-m3:latest"`
  - `baseUrl = "http://ccnode.briconbric.com:22545/v1"`
  - `dimensions = 1024`
- 数据路径：`/var/lib/openclaw/.openclaw/memory/lancedb`
- `autoCapture = true`
- `autoRecall = true`

特殊补丁：

- 当前 OpenClaw 版本下，`memory-lancedb` 查询 embeddings 需强制走 raw HTTP `/v1/embeddings`
- 否则会出现 `query vector dimension: 256`

恢复脚本：

- `python SpringMonkey/scripts/openclaw_remote_cli.py memory-repair`

专项说明：

- 见：`memory-lancedb-raw-embeddings-fix.md`

## 7. 国际渠道预部署

当前已预部署、可继续接入的国际向渠道插件：

- `telegram`
- `slack`
- `whatsapp`
- `signal`
- `msteams`
- `mattermost`
- `googlechat`
- `matrix`
- `irc`
- `twitch`
- `synology-chat`

说明：

- 这里的“预部署”是插件已加载、配置入口已建，不代表已经写入 token 或真正上线
- `nextcloud-talk`、`nostr` 当前版本不稳，保持禁用

恢复脚本：

- `python SpringMonkey/scripts/openclaw_remote_cli.py intl-channels`

## 8. 新闻任务域

当前真源：

- `config/news/broadcast.json`

关键值：

- `timezone = "Asia/Tokyo"`
- 09:00 / 17:00 JST 两档 cron
- `delivery.channel = "discord"`
- `delivery.to = "1483636573235843072"`
- `newsExecution.mode = "pipeline"`
- `cronTimeoutSeconds = 7200`

当前恢复动作：

1. 宿主机 `git pull`
2. `python3 scripts/news/ensure_daily_memory.py`
3. `python3 scripts/news/apply_news_config.py`
4. `python3 scripts/news/verify_news_config.py`
5. `python3 scripts/news/verify_runtime_readiness.py`
6. `systemctl restart openclaw.service`

专项说明：

- 见：`news-deploy-checklist.md`
- 见：`news-cron-final-broadcast-delivery-fix.md`

## 9. 最小恢复顺序

如果宿主机被覆盖，优先按这个顺序恢复：

1. `git pull` 仓库到宿主机现场路径
2. 恢复 direct task runtime bridge：`agent-society-runtime` → `agent-society-guard`
3. 恢复共享能力入口：`shared-capabilities`
4. 恢复联网与浏览器基线：`browser-capabilities` → `browser-backend` → `browser-guardrails`
5. 刷新能力认知：`capability-awareness`
6. 恢复长记忆：`memory-repair`
7. 预部署国际渠道：`intl-channels`
8. 应用新闻配置并重启服务

## 10. 相关脚本入口

- `scripts/openclaw_remote_cli.py`
- `scripts/remote_enable_shared_channel_capabilities.py`
- `scripts/remote_enable_browser_capabilities.py`
- `scripts/remote_enable_persistent_browser_backend.py`
- `scripts/remote_install_browser_guardrails.py`
- `scripts/remote_refresh_capability_awareness.py`
- `scripts/remote_repair_memory_lancedb.py`
- `scripts/remote_install_agent_society_runtime_guard.py`
- `scripts/remote_install_agent_society_startup_guard.py`
- `scripts/openclaw/patch_agent_society_runtime_current.py`
- `scripts/remote_enable_international_channels.py`
- `scripts/news/apply_news_config.py`

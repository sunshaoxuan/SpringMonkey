# Discord：手动重跑新闻未走 `openclaw cron run` 的修复（v3）

## 现象

用户明确要求「按正式规则手动重跑 17:00 / 09:00 新闻播报」时，`汤猴` 仍像普通对话一样由模型自由生成摘要，未执行 `openclaw cron run <jobId>`。

## 根因（与 v2 补丁的关系）

`pi-embedded` 中 v2 逻辑仅在 `classifyDiscordIntent(promptText) === "news_task"` 时才会调用 `queueFormalNewsJobRun`。  
当分类器将长指令、元说明较多的消息判为 **`chat`** 或 **`task_control`** 时，会在 `if (intent === "chat") return ...` 处提前返回，**永远不会进入** `news_task` 分支，因此不会触发正式 cron。

## 修复（v3）

在宿主机已应用 **v2**（含 `queueFormalNewsJobRun`）的前提下，再应用 v3：

- 脚本：`scripts/openclaw/patch_news_router_v3.py`（仓库内）或工作区根目录同名副本。
- 行为：若 `(chat | task_control)` 且满足启发式（手动重跑类用语 + 明确 09/17 时段 + 新闻/播报/正式任务等语义），则 **强制 `intent = news_task`**，再走 v2 的 `cron run` 与固定一句回复。

应用后需 **重启 gateway**（如 `openclaw.service`）。

## v8（必打）：`messageOverride` 无效导致主 session 自由发挥

现象：`formal-payload=1` 日志正常输出，但主 chat session 仍然调 `web_fetch` 抓 RSS 并生成自由摘要；用户看到两条消息（一条自由摘要 + 一条流水线正确结果）。

原因：`params.message = intentRoute.messageOverride` 实际上是**死代码**。`runEmbeddedAttempt` 从不读取 `params.message`（只读 `params.sessionFile`）。用户原始消息已写入 session JSONL，模型直接读文件看到的仍是 "手动重跑 17:00 新闻播报"。

修复（`scripts/openclaw/patch_news_router_v8.py`）：
- `manualNewsRun=true` 时设 `params.disableTools = true`：阻止模型调用任何工具（web_fetch/exec 等）。
- 重写 session JSONL 最后一条 user 消息的 content 为 override 指令："你已成功触发正式任务…只回复这一句确认"。
- 模型策略保持 Codex-first：`openai-codex/gpt-5.5` 为主，`ollama/qwen3:14b` 仅作兜底。
- 效果：主 session 秒回确认文本，不生成任何新闻内容；cron session 独立完成流水线并投递。

## v7（必打）：网关内 `spawnSync openclaw cron run` 自死锁

现象：日志已有 `bypass classifier: news_task`，随后 `spawnSync openclaw ETIMEDOUT`，`codex fallback` 仍 `spawnSync` 同样超时；频道里仍像「自由发挥」。

原因：在 **openclaw-gateway 进程内** `spawnSync` 会 **阻塞 Node 事件循环**。子 CLI 需 **WebSocket 连回同一网关** 才能完成 `cron run`，网关却无法处理 → **自死锁**。

修复：`scripts/openclaw/patch_news_router_v7.py` 将 `queueFormalNewsJobRun` 改为 **`spawn` + `await new Promise`**，不阻塞事件循环。

## v6（必打）：Ollama 异常时自动切 Codex + 分类器超时

- `classifyDiscordIntent` 对 22545 的 `fetch` 增加 **12s** 超时，避免无限挂死。
- `maybeRouteDiscordIntent` 的 `catch`：**不再 `return null`**；优先按启发式恢复 `news_task`（含 `cron run`），否则 **强制 reroute 到 `openai-codex/gpt-5.5`**（`task_control`）。
- `runEmbeddedAttempt`：Discord 且本轮仍为 **ollama** 时，做一次 **极短 generate 探针**（`num_predict:1`，12s 超时）；失败则 **embedded 主调用切到 Codex**（日志 `[model-fallback]`）。

脚本：`scripts/openclaw/patch_news_router_v6.py`（在 v5 已应用的前提下执行）。

## v5（必打）：手动重跑不得依赖 Ollama 意图分类

`classifyDiscordIntent()` 会向 Ollama 发 HTTP；若 Ollama 卡住，整段 `maybeRouteDiscordIntent` 在分类器处失败并 `return null`，网关退回默认 ollama 链路，表现为「自由发挥」且无 `[intent-router] reroute` 日志。

**处理：**`scripts/openclaw/patch_news_router_v5.py` — 当 `shouldOverrideToNewsTask` 为真时 **跳过分类器**，直接 `intent=news_task` 再 `queueFormalNewsJobRun`。

## v4（必打）：网关非 root 时禁止用 `runuser`

若 `openclaw.service` 的 `User=` 为 `openclaw`（常见），进程内调用 `runuser -u openclaw ...` 会失败：`runuser: may not be used by non-root users`。  
此时 `maybeRouteDiscordIntent` 会 catch 并 `return null`，汤猴退回默认链路并**自由发挥**。

**处理：**在 v3 之后执行 `scripts/openclaw/patch_news_router_v4.py`：非 root 时直接 `spawnSync("openclaw", ["cron","run",jobId], { env: { ...process.env, HOME: "/var/lib/openclaw" } })`；仅当 `getuid()===0` 时保留 `runuser`。

## 部署顺序

1. 若 `dist/pi-embedded-*.js` 尚无 v2 块：先在工作区使用 `patch_news_router_v2.py`（或宿主上已备份的等价补丁）。
2. 再执行 v3 脚本。
3. 再执行 **v4** 脚本（systemd 以非 root 跑网关时必需）。
4. 再执行 **v5** 脚本（避免 Ollama 分类器阻塞手动重跑路径）。
5. 再执行 **v6** 脚本（Ollama 超时 / 失败时自动 Codex）。
6. 再执行 **v7** 脚本（async `spawn` 修复网关内 cron CLI 死锁）。
7. 再执行 **v8** 脚本（阻止主 session 自由发挥，强制只输出确认）。
8. 自动化验证：`test_manual_news_heuristics.py`、`test_cron_run_cli.sh`、`integration_verify_host.py --apply-v6 --apply-v7`。
9. 验证：`journalctl` 可出现 `manual-news-run=1 tools-disabled=1` 且主 session 不再输出新闻摘要。

## 当前 bundle 修复（2026-04-08）

若 OpenClaw 升级后 `dist/pi-embedded-*.js` 文件名与旧补丁脚本写死的目标不一致，`v3`–`v8` 可能**根本没有打到当前运行文件**，表现为 Discord 手动重跑再次自由发挥。

当前仓库新增：

- `scripts/openclaw/patch_news_manual_rerun_current.py`

行为：

- 自动定位当前包含 `runEmbeddedAttempt` 的活跃 `pi-embedded` bundle
- 对 Discord 手动新闻重跑请求直接执行正式 `openclaw cron run`
- 主会话禁用工具，只允许回复固定确认句
- 避免再次出现“主会话自由生成摘要，正式任务没有真正接管”的回归

## 策略对齐

见 `docs/policies/INTENT_TOOL_ROUTING_AND_ACCUMULATION.md` 中 `news_rerun` 与 `openclaw.cron.run`。

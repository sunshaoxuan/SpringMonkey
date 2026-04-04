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

## v4（必打）：网关非 root 时禁止用 `runuser`

若 `openclaw.service` 的 `User=` 为 `openclaw`（常见），进程内调用 `runuser -u openclaw ...` 会失败：`runuser: may not be used by non-root users`。  
此时 `maybeRouteDiscordIntent` 会 catch 并 `return null`，汤猴退回默认链路并**自由发挥**。

**处理：**在 v3 之后执行 `scripts/openclaw/patch_news_router_v4.py`：非 root 时直接 `spawnSync("openclaw", ["cron","run",jobId], { env: { ...process.env, HOME: "/var/lib/openclaw" } })`；仅当 `getuid()===0` 时保留 `runuser`。

## 部署顺序

1. 若 `dist/pi-embedded-*.js` 尚无 v2 块：先在工作区使用 `patch_news_router_v2.py`（或宿主上已备份的等价补丁）。
2. 再执行 v3 脚本。
3. 再执行 **v4** 脚本（systemd 以非 root 跑网关时必需）。
4. 验证：`journalctl` 中不再出现 `classify failed: cron run failed ... runuser`；可出现 `manual-cron-run=1` 或 `override ... -> news_task`。

## 策略对齐

见 `docs/policies/INTENT_TOOL_ROUTING_AND_ACCUMULATION.md` 中 `news_rerun` 与 `openclaw.cron.run`。

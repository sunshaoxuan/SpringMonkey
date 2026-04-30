# LINE TimesCar 定时任务根因修复（2026-04）

## 结论

2026-04-10 这轮 `LINE` 侧 `TimesCar` 任务反复失败，不是单一故障，也不是 `LINE webhook` 本身坏了。根因是多层问题叠加：

1. `LINE webhook` 与 gateway 入口正常，但任务执行链被别的问题击穿。
2. `timescar-*` 定时任务一度被改成复杂的 `bash -lc 'python3 ... 2>>log'` 形式；OpenClaw `exec` preflight 会拒绝这类“复杂解释器调用”，导致任务在脚本真正启动前就失败。
3. 旧的 cron session 污染仍在生效。即使任务 prompt 已改，旧 session 仍会延续过时行为，表现为“越修越差”。
4. `timescar-daily-report-2200` 的脚本本身可以成功，但 Playwright/Node 的 `DEP0169` warning 曾混进 `stderr`，再被 `exec` 一起返回给模型，导致 `qwen3:14b` 在“原样回传长文本”阶段明显变慢。

## 为什么它自己修不好

`LINE` 会话中的“自修复”之前不是沿着单一权威路径进行，而是临时修改 prompt、脚本权限、命令包装，甚至尝试做 `git commit`。这类修法的问题是：

- 它没有统一的“先改任务定义，再验证任务真实执行”的闭环。
- 它会在聊天上下文中继续继承旧错误结论。
- 它容易用到不被当前 runtime 接受的调用方式，例如复杂 `exec` 包装。

因此，`LINE` 任务故障的权威修法必须是：

1. 修正宿主机 `cron/jobs.json` 中对应 job 的 payload。
2. 清理污染的 cron session 与悬空 `runningAtMs`。
3. 重启 `openclaw.service`。
4. 再用正式 `openclaw cron run <jobId>` 做回归。

## 当前稳定基线

以下任务现在都已统一到同一条执行链：

- `timescar-daily-report-2200`
- `timescar-ask-cancel-next24h-2300`
- `timescar-ask-cancel-next24h-0000`
- `timescar-ask-cancel-next24h-0100`
- `timescar-ask-cancel-next24h-0700`
- `timescar-ask-cancel-next24h-0800`

它们的共同约束是：

- 主模型使用 `openai-codex/gpt-5.5`；`ollama/qwen3:14b` 仅作兜底
- `thinking = off`
- 不允许在 cron 中直接用 `browser` / `web_search` / `web_fetch`
- 必须先走 `exec`
- 由脚本负责访问 TimesCar，agent 只负责接收并原样返回结果

其中：

- `timescar_daily_report_render.py`：输出完整预约日报
- `timescar_next24h_notice.py`：若未来 24 小时内没有命中的取消预约提醒，返回精确文本 `NO_REPLY`

## `not-delivered` 的含义

对 `timescar-ask-cancel-next24h-*` 这组任务而言：

- `lastRunStatus = ok`
- `lastDeliveryStatus = not-delivered`

并不表示失败。

这类任务的语义是：

- 如果脚本结果为 `NO_REPLY`，则任务成功结束，但不需要向 `LINE` 再额外发一条提示
- 因此可以出现“执行成功，但无投递”的状态

只有当 `lastRunStatus != ok`，或者任务长期残留 `runningAtMs` 时，才应视为异常。

## `stderr` warning 的处理

`timescar_fetch_reservations.py` 已加进程级 `stderr` 重定向：

- 用户可见正文只保留业务结果
- Playwright/Node 的 warning 改写入：
  - `/var/lib/openclaw/.openclaw/logs/timescar_browser.stderr.log`

这一步是为避免 warning 混入 `exec` 结果，拖慢或干扰模型收尾。

## 2026-04-10 回归结果

正式回归确认如下：

- `timescar-ask-cancel-next24h-2300`：`ok`
- `timescar-ask-cancel-next24h-0000`：`ok`
- `timescar-ask-cancel-next24h-0100`：`ok`
- `timescar-ask-cancel-next24h-0700`：`ok`
- `timescar-ask-cancel-next24h-0800`：`ok`
- `timescar-daily-report-2200`：`ok` + `delivered`

其中 `next24h` 这组任务在新 session 中的实际执行证据是：

- 先调用 `exec`
- 精确执行 `python3 /var/lib/openclaw/.openclaw/workspace/scripts/timescar_next24h_notice.py`
- 工具结果返回 `NO_REPLY`
- 最终 assistant 原样返回 `NO_REPLY`

`22:00` 日报任务在 warning 隔离后也已重新跑成：

- `lastRunStatus = ok`
- `lastDeliveryStatus = delivered`

## 以后再出问题时的排查顺序

1. 看 `healthz` 与 `/line/webhook` 是否 `200`
2. 看 `cron/jobs.json` 对应 job 的 `payload.message` 是否仍是“直接 `exec` 跑脚本”
3. 看 job `state` 是否存在悬空 `runningAtMs`
4. 看对应 session 是否又被旧上下文污染
5. 看 `timescar_browser.stderr.log`

不要再用“在 LINE 聊天里让它自己反复改 prompt/脚本”的方式救火。

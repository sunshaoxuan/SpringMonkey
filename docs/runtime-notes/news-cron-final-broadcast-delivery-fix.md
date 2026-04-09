# 新闻 cron 正文投递修复

问题日期：2026-04-08 17:00 JST 的 Discord 新闻播报。

## 现象

流水线本身成功，`final_broadcast.md` 已生成，但 Discord 频道里只出现了执行报告，例如：

- `流水线成功，退出码 0`
- `PIPELINE_OK 运行目录：...`
- `按任务要求，应向当前 Discord 频道原样发送该文件正文：.../final_broadcast.md`

而不是新闻正文。

## 根因

OpenClaw cron 会把 agent 的“最终回答”自动投递到任务的 `delivery` 目标。

旧版 `scripts/news/apply_news_config.py` 为 pipeline 模式生成的 cron 提示词虽然要求：

- 执行 job wrapper
- 成功后读取 `final_broadcast.md`
- 再“投递到 Discord”

但系统尾注同时告诉 agent：

- 若任务要求给外部对象发消息，只需说明要发到哪里，不要自己发送

结果 2026-04-08 17:00 那轮 session 里 agent 实际行为变成：

1. 成功执行流水线
2. 成功读取 `final_broadcast.md`
3. 最终回答返回了一段“应发送该文件正文”的执行报告
4. cron 自动投递了这段执行报告

所以频道里只看到执行报告。

## 修复

已修改：

- `scripts/news/apply_news_config.py`

新规则：

- 成功分支时，最终回答必须且只能是 `final_broadcast.md` 正文本身
- 禁止返回：
  - `已成功`
  - `应发送`
  - `运行目录`
  - `文件路径`
  - `执行报告`
- 明确写死：
  - 系统会自动把最终回答投递到 Discord
  - agent 不得再调用 `message.send`

失败分支：

- 最终回答只允许是一条简短失败说明
- 禁止补写新闻内容

## 生效方式

仅改本地仓库文件不够，必须在宿主机执行：

1. 宿主机 `git pull`
2. `python3 scripts/news/apply_news_config.py`
3. `python3 scripts/news/verify_news_config.py`
4. `systemctl restart openclaw.service`

## 验证方式

检查 `/var/lib/openclaw/.openclaw/cron/jobs.json` 中 `news-digest-jst-0900` / `news-digest-jst-1700` 的 `payload.message`，应包含以下语义：

- `你的最终回答必须且只能是该文件正文本身`
- `系统会把你的最终回答自动投递到该任务的 Discord 目标`
- `禁止返回“已成功/应发送/运行目录/文件路径/执行报告”之类说明文字`

## 结论

2026-04-08 17:00 的问题不是新闻没生成，而是“成功分支最终回答格式错误”，导致自动投递把执行报告发了出去。当前修复已经把行为收紧为“成功时只能回正文”。

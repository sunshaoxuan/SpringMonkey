# Discord：TimesCar 定时任务误投公共频道

## 严重性

租车相关输出（预约、取消提醒、日报正文）属于 **私密**，若 delivery.to 指向新闻/天气用的公共频道，即为公私不分。

## 权威频道 ID（与 docs/ops/CRON_TASKS_SUMMARY.md 一致）

| 用途 | Discord channel id |
|------|---------------------|
| 新闻摘要、weather-report-jst-0700（公共播报） | 1483636573235843072 |
| 全部 timescar-* 任务（私聊/DM） | 1497009159940608020 |

## 根因模式（常见）

1. openclaw cron edit --to 复制粘贴错误。
2. 从新闻任务克隆 job 时未改 delivery.to。
3. 批量脚本仅更新部分 job。
4. direct cron 与 OpenClaw cron 并存时须同时核对 jobs.json 与宿主 /etc/cron.d/。

## 机读校验

python3 scripts/cron/verify_timescar_delivery_channels.py /path/to/jobs.json

退出码 0 = 全部 timescar-* 指向私聊频道。

## 修正示例

HOME=/var/lib/openclaw openclaw cron edit "<jobId>" --to 1497009159940608020 --announce

详见脚本内注释。
# 湯猴 (OpenClaw) 定時任務彙總表 (完整版)

最後更新：2026-04-28（補充投遞校驗）

> **投遞隱私校驗**：將宿主 `cron/jobs.json` 拷出後執行  
> `python3 scripts/cron/verify_timescar_delivery_channels.py jobs.json`。  
> 若 `timescar-*` 的 `delivery.to` 誤為公共頻道 `1483636573235843072`，會導致租車內容誤投公開頻道；修復與根因說明見 `docs/runtime-notes/discord-timescar-public-channel-leak.md`。

最後更新（任務表）：2026-04-27 19:14 JST

| 任務 ID | 名稱 | 表達式 (JST) | 核心內容 / 腳本 | 發送目標 | 狀態 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `549d02c7-1797-4331-899f-46e35829b150` | `news-digest-jst-0900` | `0 9 * * *` | 新聞摘要 Pipeline | Discord Public (`1483636573235843072`) | ✅ 已啟用 |
| `856980f1-1a45-41e5-b1b8-e6fa547742a6` | `news-digest-jst-1700` | `0 17 * * *` | 新聞摘要 Pipeline | Discord Public (`1483636573235843072`) | ✅ 已啟用 |
| `08f27ede-5f70-44e0-9d92-1ce774ea2178` | `weather-report-jst-0700` | `0 7 * * *` | 每日天氣預報 (3地點) | Discord Public (`1483636573235843072`) | ✅ 已啟用 |
| `0ecec719-e2fb-4eb2-ae02-a192e596083a` | `timescar-ask-cancel-next24h-0700` | `0 7 * * *` | TimesCar 取消詢問 | Discord Private (`1497009159940608020`) | ✅ 已啟用 |
| `8521657d-527d-4125-b17b-791e4ca84493` | `timescar-ask-cancel-next24h-0800` | `0 8 * * *` | TimesCar 取消詢問 | Discord Private (`1497009159940608020`) | ✅ 已啟用 |
| `d8e801bd-0f12-4b8b-a2f5-b716ca319aac` | `timescar-daily-report-2200` | `0 22 * * *` | TimesCar 每日報告 | Discord Private (`1497009159940608020`) | ✅ 已啟用 |
| `8f2a2a43-cf35-451f-a7a6-815562f3631c` | `timescar-book-sat-3weeks` | `15 0 * * 6` | TimesCar 自動預約 | Discord Private (`1497009159940608020`) | ✅ 已啟用 |
| `97a41705-7ee3-44f3-8ebb-19a3a0064afd` | `timescar-extend-sun-3weeks` | `15 0 * * 0` | TimesCar 自動續約 | Discord Private (`1497009159940608020`) | ✅ 已啟用 |
| `c157fe27-91fd-4bf0-b3bc-5d667c09f298` | `timescar-ask-cancel-next24h-2300` | `0 23 * * *` | TimesCar 取消詢問 | Discord Private (`1497009159940608020`) | ✅ 已啟用 |
| `728831a9-30c4-42cc-bcd0-b925c63dccb8` | `timescar-ask-cancel-next24h-0000` | `0 0 * * *` | TimesCar 取消詢問 | Discord Private (`1497009159940608020`) | ✅ 已啟用 |
| `6c613335-3012-417f-8143-c0e83248af36` | `timescar-ask-cancel-next24h-0100` | `0 1 * * *` | TimesCar 取消詢問 | Discord Private (`1497009159940608020`) | ✅ 已啟用 |

## 關鍵配置說明

- **全量啟用**：應用戶要求，目前系統中所有 11 個定時任務均已進入「已啟用 (Enabled)」狀態。
- **天氣預報**：投遞至公共頻道，報告 3 個地點的天氣情況。
- **TimesCar 監控**：涵蓋早間、深夜及自動訂單/續約邏輯。**務必**與宿主 `cron/jobs.json` 對照：`timescar-*` 只允許 `delivery.to = 1497009159940608020`；若發現任一誤為公共頻道 ID（例如曾出現在快照中的 ``timescar-ask-cancel-next24h-2300``），先做 `cron edit` 修正再跑上方校驗腳本。

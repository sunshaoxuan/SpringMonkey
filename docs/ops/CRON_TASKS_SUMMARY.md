# 湯猴 (OpenClaw) 定時任務匯總表

本表記錄了當前宿主機上所有註冊的定時任務及其詳細配置。

| 任務 ID | 任務名稱 | 表達式 (Asia/Tokyo) | 主要工作內容 | 投遞目標 | 狀態 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `549d02c7-1797-4331-899f-46e35829b150` | `news-digest-jst-0900` | `0 9 * * *` | 早間新聞摘要 (Pipeline 模式) | Discord Public Channel | **Enabled** |
| `856980f1-1a45-41e5-b1b8-e6fa547742a6` | `news-digest-jst-1700` | `0 17 * * *` | 晚間新聞摘要 (Pipeline 模式) | Discord Public Channel | **Enabled** |
| `0ecec719-e2fb-4eb2-ae02-a192e596083a` | `timescar-ask-cancel-next24h-0700` | `0 7 * * *` | TimesCar 24h 內訂單取消通知 | Discord Private Channel | Disabled |
| `8521657d-527d-4125-b17b-791e4ca84493` | `timescar-ask-cancel-next24h-0800` | `0 8 * * *` | TimesCar 24h 內訂單取消通知 | Discord Private Channel | Disabled |
| `08f27ede-5f70-44e0-9d92-1ce774ea2178` | `weather-report-jst-0700` | `0 7 * * *` | 天氣預報 (調用 discord_weather_report.py) | Discord Private Channel | Disabled |

## 關鍵配置說明

### 1. 新聞摘要任務 (News Digest)
- **ID 引用**：日誌中出現 `unknown cron job id: news-digest-jst-0900` 是因為調用方錯誤地使用了**名稱**而非 **UUID**。
- **解決方案**：使用 `scripts/openclaw/run_job_by_name.py` 進行動態解析。

### 2. 啟動加固
- **Autostart**：已通過 `systemctl enable` 固化，並移除了啟動頻率限制。

---

> [!NOTE]
> 以上數據實時提取自宿主機 `/var/lib/openclaw/.openclaw/cron/jobs.json`。

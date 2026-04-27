import json
import os

JOBS_FILE = "/var/lib/openclaw/.openclaw/cron/jobs.json"

def main():
    if not os.path.exists(JOBS_FILE):
        print("Error: jobs.json not found.")
        return
        
    with open(JOBS_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    jobs = data.get("jobs", [])
    
    print("# 湯猴 (OpenClaw) 定時任務彙總表")
    print("")
    print("| 任務 ID | 名稱 | 表達式 (JST) | 核心內容 / 腳本 | 發送目標 | 狀態 |")
    print("| :--- | :--- | :--- | :--- | :--- | :--- |")
    
    for job in jobs:
        jid = job.get("id", "N/A")
        name = job.get("name", "N/A")
        enabled = job.get("enabled", False)
        status = "✅ 已啟用" if enabled else "❌ 禁用"
        
        schedule = job.get("schedule", {})
        expr = schedule.get("expr", "N/A")
        
        delivery = job.get("delivery", {})
        target = f"{delivery.get('channel', 'N/A')} ({delivery.get('to', 'N/A')})"
        
        # Extract content
        payload = job.get("payload", {})
        msg = payload.get("message", "")
        
        content = "未知"
        if "news-digest" in name:
            content = "新聞摘要 Pipeline"
        elif "timescar" in name:
            if "daily-report" in name:
                content = "TimesCar 每日報告"
            elif "book" in name:
                content = "TimesCar 自動預約"
            elif "extend" in name:
                content = "TimesCar 自動續約"
            elif "ask-cancel" in name:
                content = "TimesCar 取消詢問"
            else:
                content = "TimesCar 相關任務"
        elif "weather" in name:
            content = "每日天氣預報 (3地點)"
            
        print(f"| `{jid}` | `{name}` | `{expr}` | {content} | {target} | {status} |")

if __name__ == "__main__":
    main()

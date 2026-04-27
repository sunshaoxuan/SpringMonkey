import paramiko
import sys
import time
from pathlib import Path

# Set up paths for local imports if needed
sys.path.append(str(Path(__file__).resolve().parents[1]))
from openclaw_ssh_password import load_openclaw_ssh_password

HOST = "ccnode.briconbric.com"
PORT = 8822
USER = "root"
PRIVATE_CHANNEL = "1497009159940608020"
PUBLIC_CHANNEL = "1483636573235843072"

TASKS = [
    {"id": "08f27ede-5f70-44e0-9d92-1ce774ea2178", "name": "weather-report-jst-0700", "should_be_public": True},
    {"id": "0ecec719-e2fb-4eb2-ae02-a192e596083a", "name": "timescar-ask-cancel-next24h-0700", "should_be_public": False},
    {"id": "8521657d-527d-4125-b17b-791e4ca84493", "name": "timescar-ask-cancel-next24h-0800", "should_be_public": False},
    {"id": "d8e801bd-0f12-4b8b-a2f5-b716ca319aac", "name": "timescar-daily-report-2200", "should_be_public": False},
    {"id": "8f2a2a43-cf35-451f-a7a6-815562f3631c", "name": "timescar-book-sat-3weeks", "should_be_public": False},
    {"id": "97a41705-7ee3-44f3-8ebb-19a3a0064afd", "name": "timescar-extend-sun-3weeks", "should_be_public": False},
    {"id": "c157fe27-91fd-4bf0-b3bc-5d667c09f298", "name": "timescar-ask-cancel-next24h-2300", "should_be_public": False},
    {"id": "728831a9-30c4-42cc-bcd0-b925c63dccb8", "name": "timescar-ask-cancel-next24h-0000", "should_be_public": False},
    {"id": "6c613335-3012-417f-8143-c0e83248af36", "name": "timescar-ask-cancel-next24h-0100", "should_be_public": False},
]

def run_cmd(client, cmd):
    stdin, stdout, stderr = client.exec_command(cmd)
    out = stdout.read().decode('utf-8', errors='replace')
    err = stderr.read().decode('utf-8', errors='replace')
    return out, err

def main():
    pw = load_openclaw_ssh_password()
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        client.connect(HOST, port=PORT, username=USER, password=pw, timeout=30)
        
        results = []
        for task in TASKS:
            tid = task["id"]
            name = task["name"]
            print(f"--- Testing Task: {name} ({tid}) ---")
            
            # 1. Set to Private
            print(f"Setting to Private Channel...")
            run_cmd(client, f"HOME=/var/lib/openclaw openclaw cron edit {tid} --to {PRIVATE_CHANNEL} --announce")
            
            # 2. Run Task
            print(f"Triggering Run...")
            out, err = run_cmd(client, f"HOME=/var/lib/openclaw openclaw cron run {tid}")
            print(f"Run Output: {out}")
            
            # Wait for completion (poll session status or just wait)
            # Since some take minutes, we might want to check the session
            # For simplicity in this script, we'll wait 30s and check logs later
            time.sleep(30)
            
            # 3. If success and should be public, set back to Public
            if task["should_be_public"]:
                print(f"Setting back to Public Channel...")
                run_cmd(client, f"HOME=/var/lib/openclaw openclaw cron edit {tid} --to {PUBLIC_CHANNEL} --announce")
            
            results.append({"name": name, "status": "Triggered"})
            
        print("\nSummary:")
        for r in results:
            print(f"{r['name']}: {r['status']}")
            
        client.close()
    except Exception as e:
        print(f"Failed: {e}")

if __name__ == "__main__":
    main()

import paramiko
import os
from pathlib import Path

# SSH Credentials
HOST = "ccnode.briconbric.com"
PORT = 8822
USER = "root"
PASSWORD = "Nho#123456"

def run_remote_cmd(client, cmd):
    print(f"Executing: {cmd}")
    stdin, stdout, stderr = client.exec_command(cmd)
    out = stdout.read().decode('utf-8', 'ignore').strip()
    err = stderr.read().decode('utf-8', 'ignore').strip()
    return out, err

def main():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print(f"Connecting to {HOST}:{PORT}...")
    try:
        client.connect(HOST, port=PORT, username=USER, password=PASSWORD)
    except Exception as e:
        print(f"Connection failed: {e}")
        return

    # 1. Upload broadcast.json
    print("Uploading broadcast.json...")
    local_config = Path(r"c:\tmp\default\SpringMonkey\config\news\broadcast.json")
    remote_config = "/var/lib/openclaw/repos/SpringMonkey/config/news/broadcast.json"
    
    sftp = client.open_sftp()
    try:
        sftp.put(str(local_config), remote_config)
        print("Config uploaded.")
    except Exception as e:
        print(f"Config upload failed: {e}")
    sftp.close()

    # 2. Upload and Run v8 Patch
    print("Uploading and running patch_news_router_v8.py...")
    local_patch = Path(r"c:\tmp\default\SpringMonkey\scripts\openclaw\patch_news_router_v8.py")
    remote_patch = "/tmp/patch_v8.py"
    
    sftp = client.open_sftp()
    sftp.put(str(local_patch), remote_patch)
    sftp.close()
    
    run_remote_cmd(client, f"chmod +x {remote_patch}")
    out, err = run_remote_cmd(client, f"python3 {remote_patch}")
    print(f"Patch Output:\n{out}")
    if err:
        print(f"Patch Error:\n{err}")

    # 3. Apply News Config (updates jobs.json)
    print("Applying news configuration...")
    run_remote_cmd(client, "python3 /var/lib/openclaw/repos/SpringMonkey/scripts/news/apply_news_config.py")
    
    # 4. Restart Service
    print("Restarting openclaw.service...")
    run_remote_cmd(client, "systemctl restart openclaw.service")
    
    status, _ = run_remote_cmd(client, "systemctl is-active openclaw.service")
    print(f"Service status: {status}")

    client.close()
    print("\nMission Accomplished.")

if __name__ == "__main__":
    main()

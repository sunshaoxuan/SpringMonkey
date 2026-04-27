import paramiko
import sys
import os
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))
from openclaw_ssh_password import load_openclaw_ssh_password

HOST = "ccnode.briconbric.com"
PORT = 8822
USER = "root"

def main():
    pw = load_openclaw_ssh_password()
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        client.connect(HOST, port=PORT, username=USER, password=pw, timeout=30)
        
        # We need to change the channel and ensure enabled=true
        # Target job: weather-report-jst-0700 (ID 08f27ede-5f70-44e0-9d92-1ce774ea2178)
        
        job_id = "08f27ede-5f70-44e0-9d92-1ce774ea2178"
        public_channel = "1483636573235843072"
        
        print(f"Updating weather job {job_id} to channel {public_channel} and enabling...")
        
        # openclaw cron edit supports --to and --enable
        cmd = f"HOME=/var/lib/openclaw openclaw cron edit {job_id} --to {public_channel} --enable --announce"
        
        stdin, stdout, stderr = client.exec_command(cmd)
        print(stdout.read().decode())
        print(stderr.read().decode())
        
        client.close()
    except Exception as e:
        print(f"Failed: {e}")

if __name__ == "__main__":
    main()

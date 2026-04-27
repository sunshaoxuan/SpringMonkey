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
    if len(sys.argv) < 2:
        print("Usage: remote_cron_run_by_name.py <job_name>")
        sys.exit(1)
        
    name = sys.argv[1]
    pw = load_openclaw_ssh_password()
    if not pw:
        print("Error: OPENCLAW_SSH_PASSWORD not set.")
        sys.exit(1)

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        client.connect(HOST, port=PORT, username=USER, password=pw, timeout=30)
        print(f"Connected. Requesting run for job: {name}")
        
        remote_path = "/var/lib/openclaw/repos/SpringMonkey/scripts/openclaw/run_job_by_name.py"
        stdin, stdout, stderr = client.exec_command(f"python3 {remote_path} {name}", get_pty=True)
        
        for line in stdout:
            print(line, end="")
            
        err = stderr.read().decode()
        if err:
            print(f"STDERR: {err}", file=sys.stderr)
            
        client.close()
    except Exception as e:
        print(f"Failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

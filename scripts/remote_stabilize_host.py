import paramiko
import sys
import os
from pathlib import Path

# Add parent dir to path for shared modules if any
sys.path.append(str(Path(__file__).resolve().parents[1]))
from openclaw_ssh_password import load_openclaw_ssh_password

HOST = "ccnode.briconbric.com"
PORT = 8822
USER = "root"

def main():
    pw = load_openclaw_ssh_password()
    if not pw:
        print("Error: OPENCLAW_SSH_PASSWORD not set.")
        sys.exit(1)

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        client.connect(HOST, port=PORT, username=USER, password=pw, timeout=30)
        print("Connected to host. Running stabilization script...")
        
        # Run the script that was just pulled via git
        remote_path = "/var/lib/openclaw/repos/SpringMonkey/scripts/ops/ensure_host_stability.py"
        stdin, stdout, stderr = client.exec_command(f"python3 {remote_path}", get_pty=True)
        
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

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
        print("Usage: remote_enable_cron_jobs.py <job_name_1> [job_name_2] ...")
        sys.exit(1)
        
    names = sys.argv[1:]
    pw = load_openclaw_ssh_password()
    if not pw:
        print("Error: OPENCLAW_SSH_PASSWORD not set.")
        sys.exit(1)

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        client.connect(HOST, port=PORT, username=USER, password=pw, timeout=30)
        
        for name in names:
            print(f"Enabling job: {name}")
            # Use upsert_generic_cron_job.py on the host if it supports simple enable
            # Actually, we can just run `openclaw cron edit <ID> --enable`
            
            # 1. Get ID
            get_id_cmd = f"python3 /var/lib/openclaw/repos/SpringMonkey/scripts/openclaw/run_job_by_name.py {name}"
            # Wait, run_job_by_name.py runs the job. I need just the ID.
            # I'll use a one-liner to get the ID.
            find_id_cmd = f"python3 -c \"import json; d=json.load(open('/var/lib/openclaw/.openclaw/cron/jobs.json')); print([j['id'] for j in d['jobs'] if j['name']=='{name}'][0])\""
            
            stdin, stdout, stderr = client.exec_command(find_id_cmd)
            job_id = stdout.read().decode().strip()
            
            if not job_id:
                print(f"Could not find ID for {name}")
                continue
                
            print(f"Found ID: {job_id}. Enabling...")
            enable_cmd = f"HOME=/var/lib/openclaw openclaw cron edit {job_id} --enable --announce"
            stdin, stdout, stderr = client.exec_command(enable_cmd)
            print(stdout.read().decode())
            print(stderr.read().decode())
            
        client.close()
    except Exception as e:
        print(f"Failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

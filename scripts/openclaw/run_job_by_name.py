#!/usr/bin/env python3
import json
import subprocess
import sys
import os
from pathlib import Path

JOBS_PATH = Path("/var/lib/openclaw/.openclaw/cron/jobs.json")

def find_id_by_name(name):
    if not JOBS_PATH.exists():
        return None
    with open(JOBS_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)
        for job in data.get('jobs', []):
            if job.get('name') == name:
                return job.get('id')
    return None

def main():
    if len(sys.argv) < 2:
        print("Usage: run_job_by_name.py <job_name>")
        sys.exit(1)

    name = sys.argv[1]
    job_id = find_id_by_name(name)
    
    if not job_id:
        print(f"Error: Unknown cron job name: {name}")
        sys.exit(1)

    print(f"Resolved '{name}' to ID '{job_id}'. Running...")
    
    cmd = ["openclaw", "cron", "run", job_id]
    
    # Set HOME if needed
    os.environ["HOME"] = "/var/lib/openclaw"
    
    if os.geteuid() == 0:
        cmd = ["runuser", "-u", "openclaw", "--", "env", "HOME=/var/lib/openclaw", "openclaw", "cron", "run", job_id]
        
    subprocess.run(cmd, check=True)

if __name__ == "__main__":
    main()

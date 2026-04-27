#!/usr/bin/env python3
import subprocess
import os
import sys
from pathlib import Path

def run(cmd, check=True):
    print(f"Running: {' '.join(cmd)}")
    return subprocess.run(cmd, check=check, capture_output=True, text=True)

def main():
    if os.geteuid() != 0:
        print("This script must be run as root.")
        sys.exit(1)

    print("=== OpenClaw Host Stabilization ===")

    # 1. Ensure openclaw.service is enabled and robust
    service_file = Path("/etc/systemd/system/openclaw.service")
    if not service_file.exists():
        print(f"Error: {service_file} not found.")
        sys.exit(1)

    # Enable autostart
    run(["systemctl", "enable", "openclaw.service"])
    
    # Remove start limits to ensure it always retries
    dropin_dir = Path("/etc/systemd/system/openclaw.service.d")
    dropin_dir.mkdir(exist_ok=True)
    limit_conf = dropin_dir / "99-start-limit.conf"
    limit_conf.write_text("[Service]\nStartLimitIntervalSec=0\n")
    
    run(["systemctl", "daemon-reload"])
    
    # Check current status
    status = run(["systemctl", "is-active", "openclaw.service"], check=False).stdout.strip()
    if status != "active":
        print("Service not active, starting now...")
        run(["systemctl", "start", "openclaw.service"])
    else:
        print("Service is already active.")

    # 2. Fix Permissions
    print("Fixing permissions for /var/lib/openclaw/.openclaw...")
    run(["chown", "-R", "openclaw:openclaw", "/var/lib/openclaw/.openclaw"])
    run(["chmod", "600", "/var/lib/openclaw/.openclaw/openclaw.json"])
    run(["chmod", "700", "/var/lib/openclaw/.openclaw/cron"])
    run(["chmod", "644", "/var/lib/openclaw/.openclaw/cron/jobs.json"])

    # 3. Verify FRP and Tailscale
    print("Checking network tunnels...")
    run(["systemctl", "is-active", "frpc.service"], check=False)
    run(["systemctl", "is-active", "tailscaled.service"], check=False)

    print("=== Stabilization Complete ===")

if __name__ == "__main__":
    main()

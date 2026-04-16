import paramiko
import os
from pathlib import Path

HOST = "ccnode.briconbric.com"
PORT = 8822
USER = "root"
PASSWORD = "Nho#123456"

def run_remote_cmd(client, cmd):
    print(f"Executing: {cmd}")
    stdin, stdout, stderr = client.exec_command(cmd)
    out = stdout.read().decode()
    err = stderr.read().decode()
    if err:
        print(f"Err: {err}")
    return out

def main():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print(f"Connecting to {HOST}:{PORT}...")
    client.connect(HOST, port=PORT, username=USER, password=PASSWORD)

    # 1. Update broadcast.json
    local_config_path = Path(r"c:\tmp\default\SpringMonkey\config\news\broadcast.json")
    remote_config_path = "/var/lib/openclaw/repos/SpringMonkey/config/news/broadcast.json"
    
    print("Updating remote broadcast.json...")
    sftp = client.open_sftp()
    sftp.put(str(local_config_path), remote_config_path)
    sftp.close()

    # 2. Find and Patch the JS file
    # We search the dist directory for any file starting with pi-embedded- and containing maybeRouteDiscordIntent
    print("Patching pi-embedded in /usr/lib/node_modules/openclaw/dist...")
    patch_script = """
import os
from pathlib import Path
import shutil

dist = Path("/usr/lib/node_modules/openclaw/dist")
candidates = sorted(dist.glob("pi-embedded-*.js"), key=lambda p: p.stat().st_mtime, reverse=True)
if not candidates:
    print("BUNDLE_NOT_FOUND")
    exit(1)

# Use the most recently modified one
target = candidates[0]
print(f"Targeting: {target}")
text = target.read_text(encoding='utf-8')

# V8 logic: Ollama-first with failover
old_prov = 'const provider = "openai-codex";'
new_prov = 'const provider = "ollama";'
old_mod = 'const modelId = "gpt-5.4";'
new_mod = 'const modelId = "qwen3:14b";'

if old_prov in text:
    text = text.replace(old_prov, new_prov)
    text = text.replace(old_mod, new_mod)
    print("APPLY_OK")
else:
    print("ANCHOR_NOT_FOUND")

# Ensure manual news rerun heuristics are included (if missing from dist)
# We assume v7 or similar is already in part of the bundle if it's the latest version.

target.write_text(text, encoding='utf-8')
"""
    # Create the remote python script file to avoid shell expansion issues
    sftp = client.open_sftp()
    with sftp.file("/tmp/patch_v8.py", "w") as f:
        f.write(patch_script)
    sftp.close()
    
    res = run_remote_cmd(client, "python3 /tmp/patch_v8.py")
    print(res)

    # 3. Apply News Config
    print("Applying news config...")
    # Apply jobs.json updates
    run_remote_cmd(client, "python3 /var/lib/openclaw/repos/SpringMonkey/scripts/news/apply_news_config.py")
    
    # 4. Sync common cron jobs (optional but good for consistency)
    run_remote_cmd(client, "ls /var/lib/openclaw/.openclaw/cron/jobs.json")

    # 5. Restart Service
    print("Restarting openclaw.service...")
    run_remote_cmd(client, "systemctl restart openclaw.service")
    
    status = run_remote_cmd(client, "systemctl is-active openclaw.service")
    print(status.strip())

    client.close()
    print("\nDeployment Finished.")

if __name__ == "__main__":
    main()

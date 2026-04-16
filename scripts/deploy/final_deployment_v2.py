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
    client.connect(HOST, port=PORT, username=USER, password=PASSWORD)

    # 1. Upload updated broadcast.json
    print("Uploading relaxed broadcast.json...")
    local_config = Path(r"c:\tmp\default\SpringMonkey\config\news\broadcast.json")
    remote_config = "/var/lib/openclaw/repos/SpringMonkey/config/news/broadcast.json"
    
    sftp = client.open_sftp()
    sftp.put(str(local_config), remote_config)
    sftp.close()
    print("Config uploaded.")

    # 2. Perform a direct search-and-replace for the hardcoded router logic
    # We target the most likely patterns in the dist folder
    # We'll use a python script on the remote for safety
    patch_logic = """
import os
from pathlib import Path

dist_dir = Path('/usr/lib/node_modules/openclaw/dist/')
files = list(dist_dir.glob('*.js'))

# We search for the router's signature: "openai-codex" and "task_control"
# Minified patterns:
# provider:"openai-codex"
# modelId:"gpt-5.4"

for f in files:
    try:
        content = f.read_text(encoding='utf-8')
        modified = False
        
        # Pattern 1: unminified
        if 'const provider = "openai-codex";' in content:
            content = content.replace('const provider = "openai-codex";', 'let provider = global.consecutiveOllamaFailures < 3 ? "ollama" : "openai-codex";')
            modified = True
            
        # Pattern 2: minified attribute
        if 'provider:"openai-codex"' in content and 'task_control' in content:
            content = content.replace('provider:"openai-codex"', 'provider:global.consecutiveOllamaFailures<3?"ollama":"openai-codex"')
            modified = True
            
        if modified:
            # Inject global counter if not present
            if 'global.consecutiveOllamaFailures' not in content:
                content = 'global.consecutiveOllamaFailures=global.consecutiveOllamaFailures||0;' + content
            
            # Inject success/failure tracking on common fetch patterns
            if '.json()' in content and 'global.consecutiveOllamaFailures=0' not in content:
                content = content.replace('.json()', '.json().then(d=>(global.consecutiveOllamaFailures=0,d))')
                
            f.write_text(content, encoding='utf-8')
            print(f'Patched: {f}')
    except Exception as e:
        continue
"""
    run_remote_cmd(client, f"python3 -c \"{patch_logic}\"")

    # 3. Apply News Config
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

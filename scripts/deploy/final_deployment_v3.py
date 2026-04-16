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

    # 2. Resilient Regex Patching
    patch_logic = r"""
import os
import re
from pathlib import Path

dist_dir = Path('/usr/lib/node_modules/openclaw/dist/')
files = list(dist_dir.glob('*.js'))

# Regex to match provider assignment for codex
# Matches: provider: "openai-codex", provider:'openai-codex', provider:"openai-codex" etc.
p_regex = re.compile(r'provider\s*:\s*["\']openai-codex["\']')
m_regex = re.compile(r'modelId\s*:\s*["\']gpt-5\.4["\']')

# Success/Failure injection targets
# We look for where the response is handled
success_anchor = re.compile(r'\.json\(\)')

for f in files:
    try:
        content = f.read_text(encoding='utf-8')
        modified = False
        
        # We only want to patch the file that likely contains the router logic
        # That's typically the one containing BOTH task_control and openai-codex
        if 'task_control' in content and 'openai-codex' in content:
            print(f"Found candidate router file: {f}")
            
            if p_regex.search(content):
                content = p_regex.sub('provider:(global.consecutiveOllamaFailures<3?"ollama":"openai-codex")', content)
                modified = True
            
            if m_regex.search(content):
                content = m_regex.sub('modelId:(global.consecutiveOllamaFailures<3?"qwen3:14b":"gpt-5.4")', content)
                modified = True
                
        if modified:
            # Inject global counter if not present
            if 'global.consecutiveOllamaFailures' not in content:
                content = 'global.consecutiveOllamaFailures=global.consecutiveOllamaFailures||0;' + content
            
            # Inject success/failure tracking
            content = success_anchor.sub('.json().then(d=>(global.consecutiveOllamaFailures=0,d))', content)
            
            # Since we can't easily find every catch block, we'll try to find common error handlers
            content = content.replace('catch(error){', 'catch(error){global.consecutiveOllamaFailures++;')
            content = content.replace('catch(e){', 'catch(e){global.consecutiveOllamaFailures++;')

            f.write_text(content, encoding='utf-8')
            print(f'PATCHED: {f}')
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

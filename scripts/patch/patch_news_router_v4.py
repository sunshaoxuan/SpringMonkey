#!/usr/bin/env python3
"""
OpenClaw Discord 意图路由 / 模型降级补丁 v8
- 默认为 Ollama (Ollama-First)
- 连续 3 次失败后降级到 Codex
- 包含 Ollama generate 探针
"""
from pathlib import Path
import shutil
import sys
from datetime import datetime

# 自动寻找 dist 目录下的 pi-embedded bundle
dist = Path("/usr/lib/node_modules/openclaw/dist")
candidates = sorted(dist.glob("pi-embedded-*.js"), key=lambda p: p.stat().st_mtime, reverse=True)

if not candidates:
    print("Error: pi-embedded bundle not found in /usr/lib/node_modules/openclaw/dist")
    sys.exit(1)

# 我们取最新的那个，或者如果有多个，可能需要更精确的逻辑
# 通常 OpenClaw 只会有一个主 bundle。
TARGET = candidates[0]
BACKUP = TARGET.with_name(f"{TARGET.name}.bak-v8-{datetime.now().strftime('%Y%m%d%H%M%S')}")

print(f"Targeting: {TARGET}")

# 1. 注入全局变量 (在文件开头附近)
VAR_INJECTION = "let consecutiveOllamaFailures = 0;\n"

# 2. 修改 classifyDiscordIntent (增加失败计数和超时)
NEW_CLASSIFY = """async function classifyDiscordIntent(promptText) {
\tif (consecutiveOllamaFailures >= 3) {
\t\tlog$16.warn(`[intent-router] Ollama consecutive failures >= 3; bypassing classifier to force codex fallback`);
\t\treturn "task_control"; // 强制走任务路径
\t}
\tconst ac = new AbortController();
\tconst tid = setTimeout(() => ac.abort(), 12000);
\ttry {
\t\tconst response = await fetch("http://ccnode.briconbric.com:22545/api/generate", {
\t\t\tmethod: "POST",
\t\t\theaders: { "content-type": "application/json" },
\t\t\tsignal: ac.signal,
\t\t\tbody: JSON.stringify({
\t\t\t\tmodel: "qwen3:14b",
\t\t\t\tprompt: ["Classify...","Allowed labels: chat, task_control, news_task, repo_sync.",promptText].join("\\n"),
\t\t\t\tstream: false,
\t\t\t\tkeep_alive: "8h",
\t\t\t\toptions: { temperature: 0 }
\t\t\t})
\t\t});
\t\tif (!response.ok) throw new Error(`http ${response.status}`);
\t\tconst data = await response.json();
\t\tconsecutiveOllamaFailures = 0; // 成功则清零
\t\tconst raw = String(data?.response ?? "").trim();
\t\t// ... 简化逻辑，假设 parsed 已处理 ...
\t\treturn "news_task"; // 示例简化
\t} catch (err) {
\t\tconsecutiveOllamaFailures++;
\t\tthrow err;
\t} finally {
\t\tclearTimeout(tid);
\t}
}"""

# 这里的 replace 逻辑需要非常精确，因为是生产环境。
#鉴于 JS 文件是混淆或打包过的，直接 replace 字符串很危险。
# 最安全的方法是寻找 'maybeRouteDiscordIntent(params)' 这种确定的函数名。

def main():
    text = TARGET.read_text(encoding="utf-8")
    
    # 我们寻找 maybeRouteDiscordIntent 的开始位置
    # 在 v7 中，它包含 provider = "openai-codex"
    
    if 'const provider = "openai-codex";' not in text:
        print("Error: Could not find anchor for codex provider in target file.")
        sys.exit(1)
        
    print("Found codex provider anchor. Patching to ollama...")
    
    # 简单的全局替换 (小心！) 实际上我们应该只替换 maybeRouteDiscordIntent 里的那两个。
    # 更安全的方法是定位到新闻路由分支。
    
    # 我们尝试定位 maybeRouteDiscordIntent 内部的 codex 设置
    v3_block = 'const provider = "openai-codex";\n\t\tconst modelId = "gpt-5.4";'
    # 注意：在混淆的代码中，空白字符可能不同。
    
    # 我们改用 patch_news_router_current_to_v7.py 的逻辑：
    # 寻找 START_MARKER 和 END_MARKER (如果有的话)
    
    # 既然我不知道当前远程的确切内容，我先写一个探测脚本跑一下。
    pass

if __name__ == "__main__":
    main()

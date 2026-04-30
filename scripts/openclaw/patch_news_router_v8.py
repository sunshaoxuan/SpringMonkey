#!/usr/bin/env python3
"""
OpenClaw Discord 意图路由 / 模型降级补丁 v8
- 默认为 Codex (Codex-First)
- Codex 连续失败后才降级到 Qwen/Ollama
- 通过在 process 全局作用域注入失败计数器实现
"""
from __future__ import annotations
from pathlib import Path
import shutil
import sys
from datetime import datetime

DIST_DIR = Path("/usr/lib/node_modules/openclaw/dist")

def detect_target() -> Path:
    # 寻找包含可能路由逻辑的文件
    # 我们寻找包含 "maybeRouteDiscordIntent" 或类似特征码的文件
    candidates = sorted(DIST_DIR.glob("pi-embedded-*.js"), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in candidates:
        try:
            text = path.read_text(encoding="utf-8")
            if "maybeRouteDiscordIntent" in text or "classifyDiscordIntent" in text:
                return path
        except Exception:
            continue
    raise SystemExit("Intent router target file not found on host.")

def main():
    target = detect_target()
    print(f"Targeting bundle: {target}")
    
    backup = target.with_name(f"{target.name}.bak-v8-{datetime.now().strftime('%Y%m%d%H%M%S')}")
    shutil.copy2(target, backup)
    print(f"Backup created: {backup}")
    
    content = target.read_text(encoding="utf-8")

    # 1. 注入全局计数器 (如果尚未注入)
    # 我们在文件开头注入，确保所有函数都能访问
    if "global.consecutiveCodexFailures" not in content:
        content = "global.consecutiveCodexFailures = global.consecutiveCodexFailures || 0;\n" + content

    # 2. 修改 maybeRouteDiscordIntent 逻辑
    # 我们寻找 v7 或原始逻辑中的 codex 硬编码部分并改写为动态逻辑
    
    # 原始或 v7 逻辑通常是:
    # const provider = "openai-codex";
    # const modelId = "gpt-5.5";
    
    # 我们替换为:
    # let provider = global.consecutiveCodexFailures < 3 ? "openai-codex" : "ollama";
    # let modelId = global.consecutiveCodexFailures < 3 ? "gpt-5.5" : "qwen3:14b";

    old_prov = 'const provider = "openai-codex";'
    new_prov = 'let provider = global.consecutiveCodexFailures < 3 ? "openai-codex" : "ollama";'
    old_model = 'const modelId = "gpt-5.5";'
    new_model = 'let modelId = global.consecutiveCodexFailures < 3 ? "gpt-5.5" : "qwen3:14b";'

    if old_prov in content:
        content = content.replace(old_prov, new_prov)
        content = content.replace(old_model, new_model)
        print("Updated provider/model selection to Codex-first with Qwen fallback.")
    else:
        # 如果已经是 let 或者被混淆了，可能需要更精确的正则。
        # 这里假设之前是 v7，所以应该是确定的。
        print("Warning: Standard provider anchor not found. Checking if already patched.")
        if "global.consecutiveCodexFailures < 3" in content:
            print("Already patched or newer logic detected.")
        else:
            print("Error: Could not find patch anchors.")
            sys.exit(1)

    # 3. 注入成功/失败的处理逻辑
    # 我们需要在 classifyDiscordIntent 成功时清零，失败时增加。
    
    # 寻找 classifyDiscordIntent 的 fetch 调用
    # const response = await fetch("http://ccnode.briconbric.com:22545/api/generate", ...
    
    success_injection = "\n\t\tglobal.consecutiveCodexFailures = 0;"
    fail_injection = "\n\t\tglobal.consecutiveCodexFailures++;"

    # 寻找成功读取 JSON 的位置
    if "const data = await response.json();" in content:
        content = content.replace("const data = await response.json();", "const data = await response.json();" + success_injection)
        print("Injected success counter reset.")
        
    # 寻找 catch 块
    if "} catch (error) {" in content:
        content = content.replace("} catch (error) {", "} catch (error) {" + fail_injection)
        print("Injected failure counter increment.")

    target.write_text(content, encoding="utf-8")
    print("PATCH_V8_SUCCESS")

if __name__ == "__main__":
    main()

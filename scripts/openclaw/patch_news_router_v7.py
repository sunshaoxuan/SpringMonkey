"""
OpenClaw Discord 新闻手动重跑补丁 v7（在 v6 已部署的基础上）

根因：queueFormalNewsJobRun 使用 spawnSync("openclaw", ["cron","run", jobId]) 在 **gateway 进程内**
同步阻塞 Node 事件循环。子进程 openclaw CLI 需通过 WebSocket 回调 **同一网关** 才能完成
cron run，结果形成自死锁 → 120s ETIMEDOUT → catch 再次 spawnSync 仍死锁 → 最终 codex fallback
也失败 → 路由整体失败，退回默认 ollama「自由发挥」。

日志典型序列：
  [intent-router] bypass classifier: news_task
  primary route failed: spawnSync openclaw ETIMEDOUT
  codex fallback failed: spawnSync openclaw ETIMEDOUT

修复：queueFormalNewsJobRun 改为 **async + spawn + Promise**，不阻塞事件循环，子进程可与网关并发。

前置：dist 中 queueFormalNewsJobRun 仍为 spawnSync 版本（v4–v6）。

用法：
  python3 scripts/openclaw/patch_news_router_v7.py && systemctl restart openclaw.service
"""
from pathlib import Path
import shutil


TARGET = Path("/usr/lib/node_modules/openclaw/dist/pi-embedded-BYdcxQ5A.js")
BACKUP = Path(
    "/usr/lib/node_modules/openclaw/dist/pi-embedded-BYdcxQ5A.js.bak-20260405-cron-run-async-spawn"
)


OLD_QUEUE = """async function queueFormalNewsJobRun(promptText) {
\tconst jobName = selectFormalNewsJobName(promptText);
\tconst { jobId } = await loadFormalNewsJob(jobName);
\tconst env = { ...process.env, HOME: "/var/lib/openclaw" };
\tlet result;
\tif (typeof process.getuid === \"function\" && process.getuid() === 0) {
\t\tresult = spawnSync(\"runuser\", [\"-u\", \"openclaw\", \"--\", \"env\", \"HOME=/var/lib/openclaw\", \"openclaw\", \"cron\", \"run\", jobId], { encoding: \"utf8\", timeout: 120000, env });
\t} else {
\t\tresult = spawnSync(\"openclaw\", [\"cron\", \"run\", jobId], { encoding: \"utf8\", timeout: 120000, env });
\t}
\tif (result.error) throw result.error;
\tif (result.status !== 0) {
\t\tthrow new Error(`cron run failed (${result.status}): ${(result.stderr || result.stdout || \"\").trim()}`);
\t}
\tlet runId = \"\";
\tconst raw = String(result.stdout || \"\").trim();
\ttry {
\t\tconst parsed = JSON.parse(raw);
\t\tif (parsed && typeof parsed.runId === \"string\") runId = parsed.runId;
\t} catch {}
\treturn { jobName, jobId, runId };
}"""


NEW_QUEUE = """async function queueFormalNewsJobRun(promptText) {
\tconst jobName = selectFormalNewsJobName(promptText);
\tconst { jobId } = await loadFormalNewsJob(jobName);
\tconst env = { ...process.env, HOME: "/var/lib/openclaw" };
\tconst timeoutMs = 120000;
\tconst command = typeof process.getuid === \"function\" && process.getuid() === 0 ? \"runuser\" : \"openclaw\";
\tconst args = typeof process.getuid === \"function\" && process.getuid() === 0
\t\t? [\"-u\", \"openclaw\", \"--\", \"env\", \"HOME=/var/lib/openclaw\", \"openclaw\", \"cron\", \"run\", jobId]
\t\t: [\"cron\", \"run\", jobId];
\tconst execResult = await new Promise((resolve, reject) => {
\t\tconst child = spawn(command, args, { env });
\t\tlet stdout = \"\";
\t\tlet stderr = \"\";
\t\tconst tid = setTimeout(() => {
\t\t\ttry {
\t\t\t\tchild.kill(\"SIGKILL\");
\t\t\t} catch {}
\t\t\treject(new Error(`cron run timed out after ${timeoutMs}ms`));
\t\t}, timeoutMs);
\t\tchild.stdout?.on(\"data\", (chunk) => {
\t\t\tstdout += chunk.toString();
\t\t});
\t\tchild.stderr?.on(\"data\", (chunk) => {
\t\t\tstderr += chunk.toString();
\t\t});
\t\tchild.on(\"error\", (err) => {
\t\t\tclearTimeout(tid);
\t\t\treject(err);
\t\t});
\t\tchild.on(\"close\", (code) => {
\t\t\tclearTimeout(tid);
\t\t\tresolve({ status: code, stdout, stderr });
\t\t});
\t});
\tif (execResult.status !== 0) {
\t\tthrow new Error(`cron run failed (${execResult.status}): ${(execResult.stderr || execResult.stdout || \"\").trim()}`);
\t}
\tlet runId = \"\";
\tconst raw = String(execResult.stdout || \"\").trim();
\ttry {
\t\tconst parsed = JSON.parse(raw);
\t\tif (parsed && typeof parsed.runId === \"string\") runId = parsed.runId;
\t} catch {}
\treturn { jobName, jobId, runId };
}"""


def main():
    text = TARGET.read_text(encoding="utf-8")
    if not BACKUP.exists():
        shutil.copy2(TARGET, BACKUP)
    if OLD_QUEUE not in text:
        raise SystemExit(
            "spawnSync queueFormalNewsJobRun not found — dist may already be patched or layout changed"
        )
    text = text.replace(OLD_QUEUE, NEW_QUEUE, 1)
    TARGET.write_text(text, encoding="utf-8")
    print("PATCH_V7_OK")


if __name__ == "__main__":
    main()

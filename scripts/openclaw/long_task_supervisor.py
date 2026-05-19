#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

try:
    import grp
    import pwd
except ImportError:  # Windows test environment.
    grp = None
    pwd = None


WORKSPACE = Path("/var/lib/openclaw/.openclaw/workspace")
DEFAULT_STATE_PATH = WORKSPACE / "state" / "long_task_supervisor" / "tasks.json"
DEFAULT_EVENTS_PATH = WORKSPACE / "state" / "long_task_supervisor" / "events.jsonl"
DEFAULT_SESSIONS_DIR = Path("/var/lib/openclaw/.openclaw/agents/main/sessions")
DEFAULT_CONFIG_PATH = Path("/var/lib/openclaw/.openclaw/openclaw.json")
DEFAULT_DELIVERY_QUEUE_DIR = Path("/var/lib/openclaw/.openclaw/delivery-queue")
DEFAULT_OWNER_DM_CHANNEL = "1497009159940608020"
DEFAULT_OWNER_USER_ID = "999666719356354610"
DEFAULT_TIMEOUT_SECONDS = 3600
DEFAULT_REPO_ROOT = Path("/var/lib/openclaw/repos/SpringMonkey")

ACTIVE_STATUSES = {"running", "final_detected", "delivery_failed", "delivery_queued"}
OWNER_QUEUE_TARGET = f"user:{DEFAULT_OWNER_USER_ID}"
LEGACY_OWNER_CHANNEL_TARGET = f"channel:{DEFAULT_OWNER_USER_ID}"

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_iso(value: str) -> float:
    if not value:
        return 0.0
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def stable_task_id(run_id: str, job_id: str = "") -> str:
    seed = run_id or job_id or str(time.time())
    return "long_" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]


def read_state(path: Path = DEFAULT_STATE_PATH) -> dict[str, Any]:
    if not path.is_file():
        return {"schema_version": 1, "tasks": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"schema_version": 1, "tasks": []}
    if not isinstance(data, dict):
        return {"schema_version": 1, "tasks": []}
    tasks = data.get("tasks")
    if not isinstance(tasks, list):
        data["tasks"] = []
    data.setdefault("schema_version", 1)
    return data


def write_state(data: dict[str, Any], path: Path = DEFAULT_STATE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def append_event(event: dict[str, Any], path: Path = DEFAULT_EVENTS_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"created_at": utc_now(), **event}
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def upsert_task(task: dict[str, Any], *, state_path: Path = DEFAULT_STATE_PATH) -> dict[str, Any]:
    data = read_state(state_path)
    tasks = data.setdefault("tasks", [])
    run_id = str(task.get("run_id") or "")
    existing = next((item for item in tasks if run_id and str(item.get("run_id") or "") == run_id), None)
    if existing:
        existing.update({key: value for key, value in task.items() if value not in (None, "")})
        existing["last_seen"] = utc_now()
        write_state(data, state_path)
        return existing
    tasks.append(task)
    write_state(data, state_path)
    append_event({"event": "registered", "task_id": task.get("task_id"), "run_id": run_id, "job_id": task.get("job_id")})
    return task


def register_task(
    *,
    source: str,
    job_id: str,
    run_id: str,
    job_name: str = "",
    reply_target: str = "owner_dm",
    reply_channel_id: str = "",
    original_text: str = "",
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    state_path: Path = DEFAULT_STATE_PATH,
) -> dict[str, Any]:
    now = utc_now()
    task = {
        "task_id": stable_task_id(run_id, job_id),
        "run_id": run_id,
        "job_id": job_id,
        "job_name": job_name,
        "source": source,
        "status": "running",
        "stage": "running",
        "started_at": now,
        "last_seen": now,
        "session_file": "",
        "final_report": "",
        "delivery_state": "pending",
        "reply_target": reply_target,
        "reply_channel_id": reply_channel_id,
        "original_text": original_text,
        "timeout_seconds": int(timeout_seconds or DEFAULT_TIMEOUT_SECONDS),
    }
    return upsert_task(task, state_path=state_path)


def message_text(message: dict[str, Any]) -> str:
    content = message.get("content")
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "text" and str(item.get("text") or "").strip():
            parts.append(str(item.get("text") or "").strip())
    return "\n".join(parts).strip()


def is_final_answer(message: dict[str, Any]) -> bool:
    if message.get("role") != "assistant":
        return False
    content = message.get("content")
    if not isinstance(content, list):
        return bool(message_text(message))
    for item in content:
        if not isinstance(item, dict):
            continue
        signature = item.get("textSignature")
        if isinstance(signature, str) and '"phase":"final_answer"' in signature:
            return True
    return False


def parse_session_final_answer(path: Path) -> str:
    final = ""
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        message = row.get("message") if isinstance(row.get("message"), dict) else {}
        if is_final_answer(message):
            text = message_text(message)
            if text:
                final = text
    return final


def find_final_report(task: dict[str, Any], sessions_dir: Path = DEFAULT_SESSIONS_DIR) -> dict[str, Any]:
    if not sessions_dir.is_dir():
        return {"found": False, "reason": "sessions directory missing"}
    needles = [str(task.get("run_id") or ""), str(task.get("job_id") or "")]
    needles = [item for item in needles if item]
    if not needles:
        return {"found": False, "reason": "missing run_id and job_id"}
    started_ts = parse_iso(str(task.get("started_at") or ""))
    candidates: list[Path] = []
    for path in sessions_dir.glob("*.jsonl"):
        try:
            if started_ts and path.stat().st_mtime + 2 < started_ts:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if any(needle in text for needle in needles):
            candidates.append(path)
    candidates.sort(key=lambda item: (0 if ".trajectory." in item.name else 1, item.stat().st_mtime), reverse=True)
    for path in candidates:
        final = parse_session_final_answer(path)
        if final:
            return {"found": True, "session_file": str(path), "text": final}
    return {"found": False, "reason": "matching session has no final answer"}


def discord_token(config_path: Path = DEFAULT_CONFIG_PATH) -> str:
    token = os.environ.get("OPENCLAW_DISCORD_TOKEN", "").strip()
    if token:
        return token
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return ""
    discord = (data.get("channels") or {}).get("discord") if isinstance(data.get("channels"), dict) else {}
    return str((discord or {}).get("token") or "")


def discord_request(token: str, path: str, payload: dict[str, Any]) -> tuple[bool, str, dict[str, Any]]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"https://discord.com/api/v10{path}",
        data=body,
        headers={"Authorization": f"Bot {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            data = json.loads(raw) if raw.strip() else {}
            return 200 <= resp.status < 300, f"discord_http_{resp.status}", data if isinstance(data, dict) else {}
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}", {}


def create_owner_dm_channel(token: str, *, owner_user_id: str = DEFAULT_OWNER_USER_ID) -> tuple[str, str]:
    ok, evidence, data = discord_request(token, "/users/@me/channels", {"recipient_id": owner_user_id})
    if not ok:
        return "", evidence
    channel_id = str(data.get("id") or "")
    return channel_id, evidence if channel_id else "discord_dm_channel_missing_id"


def deliver_to_channel(token: str, channel_id: str, text: str) -> tuple[bool, str]:
    payload = {"content": text[:1900], "allowed_mentions": {"parse": []}}
    ok, evidence, _data = discord_request(token, f"/channels/{channel_id}/messages", payload)
    return ok, evidence


def deliver_owner_dm(task: dict[str, Any], text: str, *, config_path: Path = DEFAULT_CONFIG_PATH) -> tuple[bool, str]:
    token = discord_token(config_path)
    if not token:
        return False, "missing Discord token"
    preferred_channel = str(task.get("reply_channel_id") or os.environ.get("OPENCLAW_OWNER_DM_CHANNEL") or "").strip()
    if preferred_channel:
        ok, evidence = deliver_to_channel(token, preferred_channel, text)
        if ok:
            return True, evidence
        queued, queue_evidence = enqueue_openclaw_delivery(task, text, destination=f"channel:{preferred_channel}")
        if queued:
            return False, f"{queue_evidence}; preferred_channel_failed={evidence}"
        channel_id, dm_evidence = create_owner_dm_channel(token)
        if not channel_id:
            queued, queue_evidence = enqueue_openclaw_delivery(task, text)
            if queued:
                return False, queue_evidence
            return False, f"{evidence}; create_dm_failed={dm_evidence}"
        retry_ok, retry_evidence = deliver_to_channel(token, channel_id, text)
        if not retry_ok:
                queued, queue_evidence = enqueue_openclaw_delivery(task, text)
                if queued:
                    return False, queue_evidence
        return retry_ok, f"{evidence}; create_dm={dm_evidence}; retry={retry_evidence}"
    fallback_channel = os.environ.get("OPENCLAW_OWNER_DM_CHANNEL") or DEFAULT_OWNER_DM_CHANNEL
    if fallback_channel:
        ok, evidence = deliver_to_channel(token, fallback_channel, text)
        if ok:
            return True, f"owner_channel={evidence}"
    channel_id, dm_evidence = create_owner_dm_channel(token)
    if not channel_id:
        ok, evidence = deliver_to_channel(token, fallback_channel, text)
        if not ok:
            queued, queue_evidence = enqueue_openclaw_delivery(task, text)
            if queued:
                return False, queue_evidence
        return ok, f"create_dm_failed={dm_evidence}; fallback={evidence}"
    ok, evidence = deliver_to_channel(token, channel_id, text)
    if not ok:
        queued, queue_evidence = enqueue_openclaw_delivery(task, text)
        if queued:
            return False, queue_evidence
    return ok, f"create_dm={dm_evidence}; send={evidence}"


def enqueue_openclaw_delivery(
    task: dict[str, Any],
    text: str,
    *,
    queue_dir: Path = DEFAULT_DELIVERY_QUEUE_DIR,
    owner_user_id: str = DEFAULT_OWNER_USER_ID,
    destination: str = "",
) -> tuple[bool, str]:
    queue_dir.mkdir(parents=True, exist_ok=True)
    entry_id = str(uuid.uuid4())
    to = destination.strip()
    if not to:
        reply_channel_id = str(task.get("reply_channel_id") or "").strip()
        fallback_channel = os.environ.get("OPENCLAW_OWNER_DM_CHANNEL") or DEFAULT_OWNER_DM_CHANNEL
        to = f"channel:{reply_channel_id or fallback_channel}" if (reply_channel_id or fallback_channel) else f"user:{owner_user_id}"
    payload = {
        "id": entry_id,
        "enqueuedAt": int(time.time() * 1000),
        "channel": "discord",
        "to": to,
        "accountId": "default",
        "payloads": [{"text": text[:1900]}],
        "bestEffort": False,
        "session": {
            "key": f"long-task-supervisor:{task.get('run_id') or task.get('task_id') or entry_id}",
            "agentId": "main",
        },
        "retryCount": 0,
    }
    path = queue_dir / f"{entry_id}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        path.chmod(0o660)
        if pwd is not None and grp is not None and hasattr(os, "chown"):
            uid = pwd.getpwnam("openclaw").pw_uid
            gid = grp.getgrnam("openclaw").gr_gid
            os.chown(path, uid, gid)
    except OSError:
        pass
    except KeyError:
        pass
    return True, f"delivery_queued:{entry_id}"


def delivery_queue_state(entry_id: str, *, queue_dir: Path = DEFAULT_DELIVERY_QUEUE_DIR) -> str:
    if not entry_id:
        return "missing"
    if (queue_dir / f"{entry_id}.json").exists():
        return "pending"
    if (queue_dir / "failed" / f"{entry_id}.json").exists():
        return "failed"
    return "acked"


def read_delivery_queue_entry(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def queue_payload_text(entry: dict[str, Any]) -> str:
    payloads = entry.get("payloads")
    if not isinstance(payloads, list):
        return ""
    parts: list[str] = []
    for payload in payloads:
        if isinstance(payload, dict) and str(payload.get("text") or "").strip():
            parts.append(str(payload.get("text") or "").strip())
    return "\n".join(parts).strip()


def repair_owner_queue_target(path: Path, entry: dict[str, Any]) -> bool:
    if str(entry.get("to") or "") != LEGACY_OWNER_CHANNEL_TARGET:
        return False
    repaired = dict(entry)
    repaired["to"] = OWNER_QUEUE_TARGET
    repaired["retryCount"] = 0
    repaired.pop("lastError", None)
    repaired.pop("lastAttemptAt", None)
    path.write_text(json.dumps(repaired, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return True


def find_cron_failure_delivery(
    task: dict[str, Any],
    *,
    queue_dir: Path = DEFAULT_DELIVERY_QUEUE_DIR,
) -> dict[str, Any]:
    if str(task.get("source") or "") != "cron":
        return {"found": False}
    if not queue_dir.is_dir():
        return {"found": False, "reason": "delivery queue missing"}
    needles = [str(task.get("job_id") or ""), str(task.get("job_name") or ""), str(task.get("run_id") or "")]
    needles = [item for item in needles if item]
    for path in sorted(queue_dir.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
        entry = read_delivery_queue_entry(path)
        if not entry:
            continue
        session = entry.get("session") if isinstance(entry.get("session"), dict) else {}
        session_key = str((session or {}).get("key") or "")
        text = queue_payload_text(entry)
        haystack = "\n".join([session_key, text])
        if "cron" not in haystack.lower() or "failed" not in haystack.lower():
            continue
        if needles and not any(needle in haystack for needle in needles):
            continue
        repaired = repair_owner_queue_target(path, entry)
        return {
            "found": True,
            "delivery_queue_id": str(entry.get("id") or path.stem),
            "delivery_queue_path": str(path),
            "delivery_queue_target_repaired": repaired,
            "text": text or "Cron job failed before final report.",
        }
    return {"found": False}


def process_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except PermissionError:
        return True
    except OSError:
        return False


def read_text_tail(path_value: str, limit: int = 4000) -> str:
    if not path_value:
        return ""
    path = Path(path_value)
    if not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    return text[-limit:] if len(text) > limit else text


def read_text_limited(path_value: str, limit: int = 200000) -> str:
    if not path_value:
        return ""
    path = Path(path_value)
    if not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    return text[-limit:] if len(text) > limit else text


def domain_implementation_visible_text(stdout: str) -> str:
    if not stdout.strip():
        return ""
    try:
        data = json.loads(stdout)
    except Exception:
        return stdout.strip()
    result = data.get("result") if isinstance(data, dict) else None
    result = result if isinstance(result, dict) else data
    payloads = result.get("payloads") if isinstance(result, dict) else None
    if isinstance(payloads, list):
        parts = [str(item.get("text") or "").strip() for item in payloads if isinstance(item, dict) and str(item.get("text") or "").strip()]
        if parts:
            return "\n".join(parts).strip()
    meta = result.get("meta") if isinstance(result, dict) else None
    if isinstance(meta, dict):
        text = str(meta.get("finalAssistantVisibleText") or meta.get("finalAssistantRawText") or "").strip()
        if text:
            return text
    return stdout.strip()


def domain_report_claims_repo_change(visible: str) -> bool:
    if not visible.strip():
        return False
    markers = (
        "修改内容",
        "新增",
        "更新",
        "注册",
        "改动",
        "代码改动",
        "changed",
        "created",
        "updated",
        "registered",
    )
    if any(marker in visible for marker in markers):
        return True
    return bool(re.search(r"(scripts|config|packages)/[A-Za-z0-9_./-]+\.(py|json|md|toml|js|ts)", visible))


def extract_claimed_commit_hashes(visible: str) -> list[str]:
    if not visible.strip():
        return []
    return re.findall(r"\b[0-9a-f]{7,40}\b", visible, re.IGNORECASE)


def git_commit_exists(repo_root: Path, commit: str) -> tuple[bool, str]:
    if not repo_root.is_dir():
        return False, f"repo root not found: {repo_root}"
    try:
        proc = subprocess.run(
            ["git", "cat-file", "-e", f"{commit}^{{commit}}"],
            cwd=repo_root,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=20,
        )
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"
    output = (proc.stdout or "").strip()
    return proc.returncode == 0, output or f"git cat-file {commit} -> {proc.returncode}"


def domain_report_claims_committed_changes(visible: str, *, repo_root: Path | None = None) -> tuple[bool, str]:
    if not visible.strip():
        return False, "empty report"
    commits = extract_claimed_commit_hashes(visible)
    commit_markers = (
        "commit:",
        "已成功 push",
        "已成功推送",
        "已推送",
        "pushed",
        "origin/main",
        "工作区干净",
        "工作树干净",
        "worktree clean",
    )
    if not any(marker in visible for marker in commit_markers):
        return False, "report has no commit/push marker"
    if not commits:
        return False, "report mentions commit/push but includes no commit hash"
    root = repo_root or DEFAULT_REPO_ROOT
    missing: list[str] = []
    for commit in commits:
        exists, evidence = git_commit_exists(root, commit)
        if exists:
            return True, f"verified commit exists: {commit}"
        missing.append(f"{commit}: {evidence}")
    return False, "claimed commit hashes not found in repo: " + "; ".join(missing)


def git_has_worktree_changes(repo_root: Path) -> tuple[bool, str]:
    if not repo_root.is_dir():
        return False, f"repo root not found: {repo_root}"
    try:
        proc = subprocess.run(
            ["git", "status", "--short"],
            cwd=repo_root,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=20,
        )
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"
    output = (proc.stdout or "").strip()
    if proc.returncode != 0:
        return False, output or f"git status failed: {proc.returncode}"
    return bool(output), output


def domain_implementation_report_status(stdout: str, *, repo_root: Path | None = None) -> tuple[str, str]:
    visible = domain_implementation_visible_text(stdout)
    lowered = visible.lower()
    has_run_id = "implementation_run_id" in visible
    has_verification = any(
        marker in visible
        for marker in (
            "pytest",
            "verify_intent_tool_registry",
            "verify_harness_registry",
            "verify_capability_baseline",
            "验证通过",
            "测试通过",
        )
    )
    has_explicit_verified_success = has_run_id and has_verification and any(
        marker in visible
        for marker in (
            "self-evolution run：`passed`",
            "self-evolution run：passed",
            "stage：`verified`",
            "stage：verified",
            "验证已运行",
            "验证通过",
            "可以重试",
        )
    )
    generic_completion = any(
        marker in lowered
        for marker in (
            "let me know if",
            "successfully written",
            "file has been successfully written",
            "issue creating or binding",
            "session mode is unavailable",
            "subagent spawns are disabled",
        )
    )
    failed_tool = ('"failures": 1' in stdout or '"replayInvalid": true' in stdout) and not has_explicit_verified_success
    if generic_completion or not has_run_id or not has_verification:
        evidence = visible or "no visible implementation report"
        return "failed", "内部能力实现未通过验收：缺少实现 run id 或验证证据。\n" + evidence
    if failed_tool:
        evidence = visible or "tool failure without verified implementation report"
        return "failed", "内部能力实现未通过验收：执行器工具失败或 replay invalid。\n" + evidence
    if domain_report_claims_repo_change(visible):
        root = repo_root or DEFAULT_REPO_ROOT
        has_changes, git_evidence = git_has_worktree_changes(root)
        has_commit, commit_evidence = domain_report_claims_committed_changes(visible, repo_root=root)
        if not has_changes and not has_commit:
            evidence = "; ".join(item for item in (git_evidence or "git status --short returned no changes", commit_evidence) if item)
            return (
                "failed",
                "内部能力实现未通过验收：报告声称修改了仓库/注册表/测试，但真实 Git 工作树没有对应变更，也没有可验证 commit。\n"
                f"Git 证据：{evidence}\n"
                + visible,
            )
    return "success", visible


def find_domain_implementation_result(task: dict[str, Any]) -> dict[str, Any]:
    if str(task.get("source") or "") != "domain_implementation":
        return {"found": False}
    pid = int(task.get("pid") or 0)
    if pid > 0 and process_running(pid):
        return {"found": False, "reason": "implementation process still running"}
    stdout = read_text_limited(str(task.get("stdout_file") or ""))
    stderr = read_text_tail(str(task.get("stderr_file") or ""))
    if stdout:
        repo_root = Path(str(task.get("repo_root") or DEFAULT_REPO_ROOT))
        result_status, text = domain_implementation_report_status(stdout, repo_root=repo_root)
        return {"found": True, "result_status": result_status, "text": text}
    if stderr:
        return {"found": True, "result_status": "failed", "text": f"内部能力实现失败：\n{stderr}"}
    if pid > 0:
        return {"found": True, "result_status": "failed", "text": "内部能力实现进程已退出，但没有产生最终输出。"}
    return {"found": False, "reason": "implementation run registered but no process output yet"}


def final_delivery_text(task: dict[str, Any]) -> str:
    title = str(task.get("job_name") or task.get("job_id") or "long task")
    heading = "长任务失败" if str(task.get("result_status") or "") == "failed" else "长任务完成"
    return "\n".join([heading, f"任务：{title}", "", str(task.get("final_report") or "").strip()]).strip()


def record_timeout_gap(task: dict[str, Any], *, repair: bool) -> str:
    append_event(
        {
            "event": "timed_out",
            "task_id": task.get("task_id"),
            "run_id": task.get("run_id"),
            "job_id": task.get("job_id"),
            "status": "timed_out",
            "stage": "timeout_waiting_final_report",
        }
    )
    if not repair:
        return "repair_skipped"
    try:
        from capability_repair_runner import run_repair

        result = run_repair(
            text=str(task.get("original_text") or task.get("job_name") or task.get("job_id") or "long task"),
            channel="long_task_supervisor",
            user_id="long_task_supervisor",
            stage="long_task_timeout",
            reason="long task timed out before final report was detected or delivered",
            execution_output=json.dumps(task, ensure_ascii=False, sort_keys=True),
            kernel_root=WORKSPACE / "agent_society_kernel",
            context="long_task_supervisor",
        )
        return result.status
    except Exception as exc:
        return f"repair_failed:{type(exc).__name__}:{exc}"


def poll_tasks(
    *,
    state_path: Path = DEFAULT_STATE_PATH,
    sessions_dir: Path = DEFAULT_SESSIONS_DIR,
    deliver: bool = False,
    repair: bool = True,
    now_ts: float | None = None,
    deliverer: Callable[[dict[str, Any], str], tuple[bool, str]] | None = None,
    queue_dir: Path = DEFAULT_DELIVERY_QUEUE_DIR,
) -> list[dict[str, Any]]:
    now_ts = time.time() if now_ts is None else now_ts
    data = read_state(state_path)
    changed = False
    results: list[dict[str, Any]] = []
    for task in data.get("tasks", []):
        if not isinstance(task, dict):
            continue
        status = str(task.get("status") or "")
        delivery_state = str(task.get("delivery_state") or "")
        final_report = str(task.get("final_report") or "").strip()
        result_summary = str(task.get("result_summary") or "").strip()
        if status == "delivered" and delivery_state != "delivered":
            task["status"] = "final_detected"
            task["stage"] = "final_detected"
            task["delivery_state"] = "pending"
            if result_summary and not final_report:
                task["final_report"] = "长任务已完成内部验证，但此前投递状态未收口。\n\n验证摘要：\n" + result_summary
            elif not final_report:
                task["result_status"] = "failed"
                task["final_report"] = "长任务状态不一致：任务被标记为已完成，但没有可投递的最终报告。已阻止假成功并要求重新收口。"
            append_event(
                {
                    "event": "inconsistent_delivered_state_recovered",
                    "task_id": task.get("task_id"),
                    "run_id": task.get("run_id"),
                    "previous_delivery_state": delivery_state,
                    "had_result_summary": bool(result_summary),
                }
            )
            changed = True
        if str(task.get("status") or "") not in ACTIVE_STATUSES:
            continue
        task["last_seen"] = utc_now()
        if task.get("status") == "delivery_queued":
            queue_status = delivery_queue_state(str(task.get("delivery_queue_id") or ""), queue_dir=queue_dir)
            task["delivery_queue_state"] = queue_status
            if queue_status == "acked":
                result_status = str(task.get("result_status") or "success")
                task["status"] = "failed" if result_status == "failed" else "delivered"
                task["stage"] = "cron_failed_delivered" if result_status == "failed" else "delivered"
                task["delivery_state"] = "delivered"
                task["delivered_at"] = utc_now()
                append_event({"event": "delivered", "task_id": task.get("task_id"), "run_id": task.get("run_id"), "via": "openclaw_delivery_queue"})
                changed = True
            elif queue_status == "failed":
                task["status"] = "delivery_failed"
                task["stage"] = "delivery_failed"
                task["delivery_state"] = "failed"
                append_event({"event": "delivery_failed", "task_id": task.get("task_id"), "run_id": task.get("run_id"), "evidence": "openclaw_delivery_queue_failed"})
                changed = True
            results.append(dict(task))
            continue
        if not task.get("final_report") and task.get("status") == "running":
            implementation_result = find_domain_implementation_result(task)
            if implementation_result.get("found"):
                task["status"] = "final_detected"
                task["stage"] = "final_detected"
                task["result_status"] = str(implementation_result.get("result_status") or "success")
                task["final_report"] = str(implementation_result.get("text") or "").strip()
                task["delivery_state"] = "pending"
                append_event(
                    {
                        "event": "domain_implementation_final_detected",
                        "task_id": task.get("task_id"),
                        "run_id": task.get("run_id"),
                        "result_status": task.get("result_status"),
                    }
                )
                changed = True
            if task.get("final_report"):
                results.append(dict(task))
                continue
            cron_failure = find_cron_failure_delivery(task, queue_dir=queue_dir)
            if cron_failure.get("found"):
                task["status"] = "delivery_queued"
                task["stage"] = "cron_failed_delivery_queued"
                task["result_status"] = "failed"
                task["final_report"] = str(cron_failure.get("text") or "Cron job failed before final report.").strip()
                task["delivery_state"] = "queued"
                task["delivery_queue_id"] = str(cron_failure.get("delivery_queue_id") or "")
                task["delivery_queue_path"] = str(cron_failure.get("delivery_queue_path") or "")
                task["delivery_queue_state"] = "pending"
                task["delivery_queue_target_repaired"] = bool(cron_failure.get("delivery_queue_target_repaired"))
                append_event(
                    {
                        "event": "cron_failure_detected",
                        "task_id": task.get("task_id"),
                        "run_id": task.get("run_id"),
                        "delivery_queue_id": task.get("delivery_queue_id"),
                        "target_repaired": task.get("delivery_queue_target_repaired"),
                    }
                )
                changed = True
                results.append(dict(task))
                continue
            report = find_final_report(task, sessions_dir=sessions_dir)
            if report.get("found"):
                task["status"] = "final_detected"
                task["stage"] = "final_detected"
                task["session_file"] = str(report.get("session_file") or "")
                task["final_report"] = str(report.get("text") or "")
                task["delivery_state"] = "pending"
                append_event({"event": "final_detected", "task_id": task.get("task_id"), "run_id": task.get("run_id")})
                changed = True
            else:
                started_raw = str(task.get("started_at") or "")
                started_ts = parse_iso(started_raw)
                timeout = int(task.get("timeout_seconds") or DEFAULT_TIMEOUT_SECONDS)
                if started_raw and now_ts - started_ts > timeout:
                    task["status"] = "timed_out"
                    task["stage"] = "timeout_waiting_final_report"
                    task["delivery_state"] = "not_applicable"
                    task["repair_status"] = record_timeout_gap(task, repair=repair)
                    changed = True
        if deliver and task.get("status") in {"final_detected", "delivery_failed"} and task.get("final_report"):
            send = deliverer or (lambda item, body: deliver_owner_dm(item, body))
            ok, evidence = send(task, final_delivery_text(task))
            task["delivery_evidence"] = evidence
            if ok:
                result_status = str(task.get("result_status") or "success")
                task["status"] = "failed" if result_status == "failed" else "delivered"
                task["stage"] = "long_task_failed_delivered" if result_status == "failed" else "delivered"
                task["delivery_state"] = "delivered"
                task["delivered_at"] = utc_now()
                append_event({"event": "delivered", "task_id": task.get("task_id"), "run_id": task.get("run_id")})
            elif evidence.startswith("delivery_queued:"):
                queue_id = evidence.split(":", 1)[1]
                task["status"] = "delivery_queued"
                task["stage"] = "delivery_queued"
                task["delivery_state"] = "queued"
                task["delivery_queue_id"] = queue_id
                task["delivery_queue_state"] = "pending"
                append_event({"event": "delivery_queued", "task_id": task.get("task_id"), "run_id": task.get("run_id"), "delivery_queue_id": queue_id})
            else:
                task["status"] = "delivery_failed"
                task["stage"] = "delivery_failed"
                task["delivery_state"] = "failed"
                append_event({"event": "delivery_failed", "task_id": task.get("task_id"), "run_id": task.get("run_id"), "evidence": evidence})
            changed = True
        results.append(dict(task))
    if changed:
        write_state(data, state_path)
    return results


def status_text(*, state_path: Path = DEFAULT_STATE_PATH, limit: int = 10) -> str:
    tasks = [item for item in read_state(state_path).get("tasks", []) if isinstance(item, dict)]
    tasks = list(reversed(tasks[-limit:]))
    lines = ["长任务状态", f"最近任务：{len(tasks)}"]
    running = [item for item in tasks if str(item.get("status") or "") in ACTIVE_STATUSES]
    lines.append(f"进行中/待投递：{len(running)}")
    for index, task in enumerate(tasks, start=1):
        title = str(task.get("job_name") or task.get("job_id") or task.get("run_id") or "long task")
        status = str(task.get("status") or "unknown")
        result_status = str(task.get("result_status") or "")
        if status == "delivery_queued":
            conclusion = "最终结果已进入投递队列，等待 Discord/OpenClaw 投递确认。"
        elif status == "delivery_failed":
            conclusion = "最终结果投递失败，后续会重试或报告投递故障。"
        elif status == "final_detected":
            conclusion = "已检测到最终结果，等待投递。"
        elif status == "running":
            conclusion = "正在进行，尚未最终收口。"
        elif status == "delivered" and result_status != "failed":
            conclusion = "已完成，最终结果已投递。"
        elif status == "failed" or result_status == "failed":
            conclusion = "已失败，失败报告已投递。"
        elif status == "timed_out":
            conclusion = "已超时，未检测到最终结果。"
        else:
            conclusion = f"状态：{status}"

        lines.extend(
            [
                "---",
                f"{index}. {title}",
                f"结论：{conclusion}",
                f"阶段：{task.get('stage') or 'unknown'}",
                f"投递：{task.get('delivery_state') or 'unknown'}",
                f"开始：{task.get('started_at') or 'unknown'}",
            ]
        )
        delivered_at = str(task.get("delivered_at") or "").strip()
        if delivered_at:
            lines.append(f"投递时间：{delivered_at}")
        queue_id = str(task.get("delivery_queue_id") or "").strip()
        if queue_id:
            lines.append(f"投递记录：{queue_id}")
        final_report = str(task.get("final_report") or "").strip()
        if final_report:
            preview = " ".join(final_report.split())
            if len(preview) > 180:
                preview = preview[:177].rstrip() + "..."
            label = "失败摘要" if status == "failed" or result_status == "failed" else "结果摘要"
            lines.append(f"{label}：{preview}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Track and close OpenClaw long-running tasks.")
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE_PATH)
    parser.add_argument("--sessions-dir", type=Path, default=DEFAULT_SESSIONS_DIR)
    sub = parser.add_subparsers(dest="command", required=True)

    reg = sub.add_parser("register")
    reg.add_argument("--source", required=True)
    reg.add_argument("--job-id", required=True)
    reg.add_argument("--run-id", required=True)
    reg.add_argument("--job-name", default="")
    reg.add_argument("--reply-target", default="owner_dm")
    reg.add_argument("--reply-channel-id", default="")
    reg.add_argument("--original-text", default="")
    reg.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)

    poll = sub.add_parser("poll")
    poll.add_argument("--deliver", action="store_true")
    poll.add_argument("--no-repair", action="store_true")

    stat = sub.add_parser("status")
    stat.add_argument("--limit", type=int, default=10)

    args = parser.parse_args()
    if args.command == "register":
        task = register_task(
            source=args.source,
            job_id=args.job_id,
            run_id=args.run_id,
            job_name=args.job_name,
            reply_target=args.reply_target,
            reply_channel_id=args.reply_channel_id,
            original_text=args.original_text,
            timeout_seconds=args.timeout_seconds,
            state_path=args.state,
        )
        print(json.dumps(task, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.command == "poll":
        tasks = poll_tasks(state_path=args.state, sessions_dir=args.sessions_dir, deliver=args.deliver, repair=not args.no_repair)
        print(json.dumps({"status": "ok", "tasks": tasks}, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.command == "status":
        print(status_text(state_path=args.state, limit=args.limit))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

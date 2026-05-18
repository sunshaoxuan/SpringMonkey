from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import long_task_supervisor as supervisor


def final_session(path: Path, *, run_id: str, text: str) -> None:
    path.write_text(
        "\n".join(
            [
                json.dumps({"sessionKey": f"agent:main:cron:job_1:run:{run_id}"}),
                json.dumps(
                    {
                        "message": {
                            "role": "assistant",
                            "content": [{"type": "text", "text": text, "textSignature": '{"phase":"final_answer"}'}],
                        }
                    },
                    ensure_ascii=False,
                ),
            ]
        ),
        encoding="utf-8",
    )


def test_register_long_task_is_idempotent(tmp_path: Path) -> None:
    state = tmp_path / "tasks.json"

    first = supervisor.register_task(source="cron", job_id="job_1", run_id="run_1", job_name="job", state_path=state)
    second = supervisor.register_task(source="cron", job_id="job_1", run_id="run_1", job_name="job", state_path=state)

    data = supervisor.read_state(state)
    assert first["task_id"] == second["task_id"]
    assert len(data["tasks"]) == 1
    assert data["tasks"][0]["status"] == "running"


def test_poll_detects_final_and_delivers(tmp_path: Path) -> None:
    state = tmp_path / "tasks.json"
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    supervisor.register_task(source="cron", job_id="job_1", run_id="run_1", job_name="job", state_path=state)
    final_session(sessions / "run.jsonl", run_id="run_1", text="最终结果")
    delivered: list[str] = []

    tasks = supervisor.poll_tasks(
        state_path=state,
        sessions_dir=sessions,
        deliver=True,
        repair=False,
        deliverer=lambda _task, body: (delivered.append(body) is None, "sent"),
    )

    assert tasks[0]["status"] == "delivered"
    assert tasks[0]["delivery_state"] == "delivered"
    assert "最终结果" in delivered[0]


def test_delivery_failure_keeps_final_for_retry(tmp_path: Path) -> None:
    state = tmp_path / "tasks.json"
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    supervisor.register_task(source="cron", job_id="job_1", run_id="run_1", job_name="job", state_path=state)
    final_session(sessions / "run.jsonl", run_id="run_1", text="最终结果")

    tasks = supervisor.poll_tasks(
        state_path=state,
        sessions_dir=sessions,
        deliver=True,
        repair=False,
        deliverer=lambda _task, _body: (False, "discord failed"),
    )

    assert tasks[0]["status"] == "delivery_failed"
    assert tasks[0]["final_report"] == "最终结果"
    retry = supervisor.poll_tasks(
        state_path=state,
        sessions_dir=sessions,
        deliver=True,
        repair=False,
        deliverer=lambda _task, _body: (True, "sent"),
    )
    assert retry[0]["status"] == "delivered"


def test_deliver_owner_dm_queues_origin_channel_before_created_dm(monkeypatch, tmp_path: Path) -> None:
    calls: list[tuple[str, str]] = []
    queue = tmp_path / "delivery-queue"

    monkeypatch.setattr(supervisor, "discord_token", lambda _config_path=supervisor.DEFAULT_CONFIG_PATH: "token")
    monkeypatch.setattr(supervisor, "create_owner_dm_channel", lambda _token: ("dm_channel", "discord_http_200"))
    original_enqueue = supervisor.enqueue_openclaw_delivery
    monkeypatch.setattr(
        supervisor,
        "enqueue_openclaw_delivery",
        lambda task, text, **kwargs: original_enqueue(task, text, queue_dir=queue, **kwargs),
    )

    def fake_deliver(_token: str, channel_id: str, text: str) -> tuple[bool, str]:
        calls.append((channel_id, text))
        if channel_id == "stale_channel":
            return False, "HTTPError: HTTP Error 403: Forbidden"
        return True, "discord_http_200"

    monkeypatch.setattr(supervisor, "deliver_to_channel", fake_deliver)

    ok, evidence = supervisor.deliver_owner_dm({"reply_channel_id": "stale_channel", "run_id": "run_1"}, "最终结果")

    assert ok is False
    assert calls == [("stale_channel", "最终结果")]
    assert "preferred_channel_failed=HTTPError" in evidence
    entry_id = evidence.split("delivery_queued:", 1)[1].split(";", 1)[0]
    entry = json.loads((queue / f"{entry_id}.json").read_text(encoding="utf-8"))
    assert entry["to"] == "channel:stale_channel"


def test_delivery_queue_fallback_tracks_ack(tmp_path: Path) -> None:
    state = tmp_path / "tasks.json"
    sessions = tmp_path / "sessions"
    queue = tmp_path / "delivery-queue"
    sessions.mkdir()
    supervisor.register_task(source="cron", job_id="job_1", run_id="run_1", job_name="job", state_path=state)
    final_session(sessions / "run.jsonl", run_id="run_1", text="最终结果")

    def fake_queue(task: dict, body: str) -> tuple[bool, str]:
        _ok, evidence = supervisor.enqueue_openclaw_delivery(task, body, queue_dir=queue, owner_user_id="owner")
        return False, evidence

    queued = supervisor.poll_tasks(state_path=state, sessions_dir=sessions, deliver=True, repair=False, deliverer=fake_queue)

    assert queued[0]["status"] == "delivery_queued"
    queue_id = queued[0]["delivery_queue_id"]
    assert supervisor.delivery_queue_state(queue_id, queue_dir=queue) == "pending"
    (queue / f"{queue_id}.json").unlink()

    delivered = supervisor.poll_tasks(state_path=state, sessions_dir=sessions, deliver=True, repair=False)

    assert delivered[0]["status"] == "delivered"
    assert delivered[0]["delivery_state"] == "delivered"


def test_delivery_queue_uses_origin_channel_when_available(tmp_path: Path) -> None:
    queue = tmp_path / "delivery-queue"
    task = {"run_id": "run_1", "reply_channel_id": "origin_channel"}

    _ok, evidence = supervisor.enqueue_openclaw_delivery(task, "最终结果", queue_dir=queue)

    entry_id = evidence.split(":", 1)[1]
    entry = json.loads((queue / f"{entry_id}.json").read_text(encoding="utf-8"))
    assert entry["to"] == "channel:origin_channel"


def test_deliver_owner_dm_queues_origin_channel_before_dm_fallback(monkeypatch, tmp_path: Path) -> None:
    queue = tmp_path / "delivery-queue"
    monkeypatch.setattr(supervisor, "discord_token", lambda _config_path=supervisor.DEFAULT_CONFIG_PATH: "token")
    monkeypatch.setattr(supervisor, "deliver_to_channel", lambda _token, _channel_id, _text: (False, "HTTPError: 403"))
    original_enqueue = supervisor.enqueue_openclaw_delivery
    monkeypatch.setattr(
        supervisor,
        "enqueue_openclaw_delivery",
        lambda task, text, **kwargs: original_enqueue(task, text, queue_dir=queue, **kwargs),
    )

    ok, evidence = supervisor.deliver_owner_dm({"reply_channel_id": "origin_channel", "run_id": "run_1"}, "最终结果")

    assert ok is False
    assert "preferred_channel_failed=HTTPError: 403" in evidence
    entry_id = evidence.split("delivery_queued:", 1)[1].split(";", 1)[0]
    entry = json.loads((queue / f"{entry_id}.json").read_text(encoding="utf-8"))
    assert entry["to"] == "channel:origin_channel"


def test_cron_failure_delivery_marks_task_failed_and_repairs_owner_target(tmp_path: Path) -> None:
    state = tmp_path / "tasks.json"
    sessions = tmp_path / "sessions"
    queue = tmp_path / "delivery-queue"
    sessions.mkdir()
    queue.mkdir()
    supervisor.register_task(source="cron", job_id="job_1", run_id="run_1", job_name="job", state_path=state)
    entry = {
        "id": "queue_1",
        "channel": "discord",
        "to": supervisor.LEGACY_OWNER_CHANNEL_TARGET,
        "payloads": [{"text": 'Cron job "job" failed: cron: job interrupted by gateway restart'}],
        "retryCount": 3,
        "lastError": "Unknown Channel",
        "session": {"key": "cron:job_1:failure"},
    }
    (queue / "queue_1.json").write_text(json.dumps(entry), encoding="utf-8")

    tasks = supervisor.poll_tasks(state_path=state, sessions_dir=sessions, deliver=True, repair=False, queue_dir=queue)

    assert tasks[0]["status"] == "delivery_queued"
    assert tasks[0]["stage"] == "cron_failed_delivery_queued"
    assert tasks[0]["result_status"] == "failed"
    assert tasks[0]["delivery_queue_target_repaired"] is True
    repaired = json.loads((queue / "queue_1.json").read_text(encoding="utf-8"))
    assert repaired["to"] == supervisor.OWNER_QUEUE_TARGET
    assert repaired["retryCount"] == 0
    assert "lastError" not in repaired

    (queue / "queue_1.json").unlink()
    delivered = supervisor.poll_tasks(state_path=state, sessions_dir=sessions, deliver=True, repair=False, queue_dir=queue)

    assert delivered[0]["status"] == "failed"
    assert delivered[0]["stage"] == "cron_failed_delivered"
    assert delivered[0]["delivery_state"] == "delivered"


def test_timeout_marks_task_and_records_no_fake_success(tmp_path: Path) -> None:
    state = tmp_path / "tasks.json"
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    task = supervisor.register_task(
        source="cron",
        job_id="job_1",
        run_id="run_1",
        job_name="job",
        timeout_seconds=1,
        state_path=state,
    )
    task["started_at"] = datetime.fromtimestamp(0, timezone.utc).isoformat()
    supervisor.write_state({"schema_version": 1, "tasks": [task]}, state)

    tasks = supervisor.poll_tasks(state_path=state, sessions_dir=sessions, deliver=True, repair=False, now_ts=10)

    assert tasks[0]["status"] == "timed_out"
    assert tasks[0]["stage"] == "timeout_waiting_final_report"
    assert not tasks[0].get("final_report")


def test_inconsistent_delivered_without_final_report_is_recovered_and_delivered(tmp_path: Path) -> None:
    state = tmp_path / "tasks.json"
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    task = supervisor.register_task(
        source="domain_implementation",
        job_id="repair_1",
        run_id="impl_1",
        job_name="自增益实现",
        state_path=state,
    )
    task.update(
        {
            "status": "delivered",
            "stage": "verified",
            "delivery_state": "ready_for_reply",
            "final_report": "",
            "result_summary": "verify registry -> 0; verify baseline -> 0",
        }
    )
    supervisor.write_state({"schema_version": 1, "tasks": [task]}, state)
    delivered: list[str] = []

    tasks = supervisor.poll_tasks(
        state_path=state,
        sessions_dir=sessions,
        deliver=True,
        repair=False,
        deliverer=lambda _task, body: (delivered.append(body) is None, "sent"),
    )

    assert tasks[0]["status"] == "delivered"
    assert tasks[0]["delivery_state"] == "delivered"
    assert "此前投递状态未收口" in tasks[0]["final_report"]
    assert "verify baseline" in delivered[0]


def test_inconsistent_delivered_without_any_report_becomes_failure_report(tmp_path: Path) -> None:
    state = tmp_path / "tasks.json"
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    task = supervisor.register_task(
        source="domain_implementation",
        job_id="repair_1",
        run_id="impl_1",
        job_name="自增益实现",
        state_path=state,
    )
    task.update({"status": "delivered", "stage": "verified", "delivery_state": "ready_for_reply", "final_report": ""})
    supervisor.write_state({"schema_version": 1, "tasks": [task]}, state)

    tasks = supervisor.poll_tasks(
        state_path=state,
        sessions_dir=sessions,
        deliver=True,
        repair=False,
        deliverer=lambda _task, _body: (True, "sent"),
    )

    assert tasks[0]["status"] == "failed"
    assert tasks[0]["delivery_state"] == "delivered"
    assert "没有可投递的最终报告" in tasks[0]["final_report"]


def test_domain_implementation_process_output_becomes_final_report(monkeypatch, tmp_path: Path) -> None:
    state = tmp_path / "tasks.json"
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    stdout = tmp_path / "impl.out"
    stderr = tmp_path / "impl.err"
    stdout.write_text("implementation_run_id=impl_1\npython -m pytest -q scripts/openclaw\n验证通过。", encoding="utf-8")
    stderr.write_text("", encoding="utf-8")
    task = supervisor.register_task(
        source="domain_implementation",
        job_id="repair_1",
        run_id="impl_1",
        job_name="自增益实现",
        state_path=state,
    )
    task.update({"pid": 12345, "stdout_file": str(stdout), "stderr_file": str(stderr)})
    supervisor.write_state({"schema_version": 1, "tasks": [task]}, state)
    monkeypatch.setattr(supervisor, "process_running", lambda _pid: False)

    tasks = supervisor.poll_tasks(state_path=state, sessions_dir=sessions, deliver=False, repair=False)

    assert tasks[0]["status"] == "final_detected"
    assert tasks[0]["result_status"] == "success"
    assert "验证通过" in tasks[0]["final_report"]


def test_domain_implementation_generic_file_written_report_fails_validation(monkeypatch, tmp_path: Path) -> None:
    state = tmp_path / "tasks.json"
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    stdout = tmp_path / "impl.out"
    stderr = tmp_path / "impl.err"
    stdout.write_text(
        json.dumps({"result": {"payloads": [{"text": "The file has been successfully written. Let me know if you need anything else."}]}}),
        encoding="utf-8",
    )
    stderr.write_text("", encoding="utf-8")
    task = supervisor.register_task(
        source="domain_implementation",
        job_id="repair_1",
        run_id="impl_1",
        job_name="自增益实现",
        state_path=state,
    )
    task.update({"pid": 12345, "stdout_file": str(stdout), "stderr_file": str(stderr)})
    supervisor.write_state({"schema_version": 1, "tasks": [task]}, state)
    monkeypatch.setattr(supervisor, "process_running", lambda _pid: False)

    tasks = supervisor.poll_tasks(state_path=state, sessions_dir=sessions, deliver=False, repair=False)

    assert tasks[0]["status"] == "final_detected"
    assert tasks[0]["result_status"] == "failed"
    assert "未通过验收" in tasks[0]["final_report"]


def test_domain_implementation_claimed_repo_changes_require_git_diff(monkeypatch, tmp_path: Path) -> None:
    state = tmp_path / "tasks.json"
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    repo = tmp_path / "repo"
    repo.mkdir()
    stdout = tmp_path / "impl.out"
    stderr = tmp_path / "impl.err"
    stdout.write_text(
        "\n".join(
            [
                "implementation_run_id: impl_1",
                "修改内容",
                "- 新增 scripts/openclaw/new_helper.py",
                "python scripts/openclaw/verify_intent_tool_registry.py",
                "验证通过。",
            ]
        ),
        encoding="utf-8",
    )
    stderr.write_text("", encoding="utf-8")
    task = supervisor.register_task(
        source="domain_implementation",
        job_id="repair_1",
        run_id="impl_1",
        job_name="自增益实现",
        state_path=state,
    )
    task.update({"pid": 12345, "stdout_file": str(stdout), "stderr_file": str(stderr), "repo_root": str(repo)})
    supervisor.write_state({"schema_version": 1, "tasks": [task]}, state)
    monkeypatch.setattr(supervisor, "process_running", lambda _pid: False)
    monkeypatch.setattr(supervisor, "git_has_worktree_changes", lambda _repo: (False, ""))

    tasks = supervisor.poll_tasks(state_path=state, sessions_dir=sessions, deliver=False, repair=False)

    assert tasks[0]["status"] == "final_detected"
    assert tasks[0]["result_status"] == "failed"
    assert "真实 Git 工作树没有对应变更" in tasks[0]["final_report"]


def test_status_text_lists_recent_tasks(tmp_path: Path) -> None:
    state = tmp_path / "tasks.json"
    supervisor.register_task(source="cron", job_id="job_1", run_id="run_1", job_name="job", state_path=state)

    text = supervisor.status_text(state_path=state)

    assert "长任务状态" in text
    assert "1. job" in text
    assert "结论：正在进行，尚未最终收口。" in text
    assert "阶段：running" in text


def test_status_text_distinguishes_delivery_queue_from_running(tmp_path: Path) -> None:
    state = tmp_path / "tasks.json"
    task = supervisor.register_task(source="cron", job_id="job_1", run_id="run_1", job_name="job", state_path=state)
    task.update({"status": "delivery_queued", "stage": "delivery_queued", "delivery_state": "queued", "delivery_queue_id": "queue_1"})
    supervisor.write_state({"schema_version": 1, "tasks": [task]}, state)

    text = supervisor.status_text(state_path=state)

    assert "结论：最终结果已进入投递队列" in text
    assert "结论：正在进行，尚未最终收口。" not in text

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


def test_deliver_owner_dm_falls_back_to_created_dm_channel(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []

    monkeypatch.setattr(supervisor, "discord_token", lambda _config_path=supervisor.DEFAULT_CONFIG_PATH: "token")
    monkeypatch.setattr(supervisor, "create_owner_dm_channel", lambda _token: ("dm_channel", "discord_http_200"))

    def fake_deliver(_token: str, channel_id: str, text: str) -> tuple[bool, str]:
        calls.append((channel_id, text))
        if channel_id == "stale_channel":
            return False, "HTTPError: HTTP Error 403: Forbidden"
        return True, "discord_http_200"

    monkeypatch.setattr(supervisor, "deliver_to_channel", fake_deliver)

    ok, evidence = supervisor.deliver_owner_dm({"reply_channel_id": "stale_channel"}, "最终结果")

    assert ok is True
    assert calls == [("stale_channel", "最终结果"), ("dm_channel", "最终结果")]
    assert "retry=discord_http_200" in evidence


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


def test_status_text_lists_recent_tasks(tmp_path: Path) -> None:
    state = tmp_path / "tasks.json"
    supervisor.register_task(source="cron", job_id="job_1", run_id="run_1", job_name="job", state_path=state)

    text = supervisor.status_text(state_path=state)

    assert "长任务状态" in text
    assert "job status=running" in text

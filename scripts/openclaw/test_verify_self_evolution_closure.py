from __future__ import annotations

import json
from pathlib import Path

import verify_self_evolution_closure as closure


def write_state(path: Path, tasks: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schema_version": 1, "tasks": tasks}, ensure_ascii=False), encoding="utf-8")


def test_closure_flags_active_tasks(tmp_path: Path) -> None:
    state = tmp_path / "tasks.json"
    write_state(state, [{"task_id": "long_1", "run_id": "run_1", "status": "running"}])

    results = closure.check_long_tasks(state, allow_active=False)

    by_name = {item.name: item for item in results}
    assert by_name["long_tasks_no_active_or_pending"].ok is False
    assert "active=1" in by_name["long_tasks_no_active_or_pending"].detail


def test_closure_allows_active_when_requested(tmp_path: Path) -> None:
    state = tmp_path / "tasks.json"
    write_state(state, [{"task_id": "long_1", "run_id": "run_1", "status": "running"}])

    results = closure.check_long_tasks(state, allow_active=True)

    by_name = {item.name: item for item in results}
    assert by_name["long_tasks_no_active_or_pending"].ok is True


def test_closure_flags_success_report_misclassified_as_failed(monkeypatch, tmp_path: Path) -> None:
    state = tmp_path / "tasks.json"
    stdout = tmp_path / "impl.out"
    stdout.write_text("implementation_run_id: impl_1\n验证通过\nCommit:\nabc1234", encoding="utf-8")
    write_state(
        state,
        [
            {
                "task_id": "long_1",
                "run_id": "impl_1",
                "source": "domain_implementation",
                "status": "delivered",
                "result_status": "failed",
                "stdout_file": str(stdout),
                "repo_root": str(tmp_path),
            }
        ],
    )
    monkeypatch.setattr(closure, "recompute_domain_task", lambda _task: ("success", "verified"))

    results = closure.check_long_tasks(state, allow_active=False)

    by_name = {item.name: item for item in results}
    assert by_name["long_tasks_no_success_misclassified_as_failed"].ok is False
    assert "impl_1" in by_name["long_tasks_no_success_misclassified_as_failed"].detail


def test_closure_passes_clean_delivered_tasks(tmp_path: Path) -> None:
    state = tmp_path / "tasks.json"
    write_state(
        state,
        [
            {
                "task_id": "long_1",
                "run_id": "run_1",
                "source": "domain_implementation",
                "status": "delivered",
                "result_status": "success",
                "delivery_state": "delivered",
                "final_report": "ok",
            }
        ],
    )

    results = closure.check_long_tasks(state, allow_active=False)

    assert all(item.ok for item in results), results


def test_resolve_repo_root_falls_back_to_cwd(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    monkeypatch.chdir(tmp_path)

    assert closure.resolve_repo_root(Path("/not/a/local/repo")) == tmp_path

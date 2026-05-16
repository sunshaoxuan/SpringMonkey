from __future__ import annotations

import json
from pathlib import Path

import harness_eval_suite


def test_eval_suite_checks_baseline_and_trial_outcomes(tmp_path: Path) -> None:
    trial_log = tmp_path / "trials.jsonl"
    trial_log.write_text(
        json.dumps(
            {
                "trace_id": "trace_1",
                "task_id": "task_1",
                "status": "ok",
                "stage": "report",
                "outcome": "completed",
                "route_kind": "registered_task",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    result = harness_eval_suite.run_eval_suite(trial_log=trial_log, require_trials=True)

    assert result.passed
    assert result.baseline_passed
    assert result.trial_count == 1
    assert result.outcome_summary["completed"] == 1


def test_eval_suite_rejects_failed_trial_without_failure_type(tmp_path: Path) -> None:
    trial_log = tmp_path / "trials.jsonl"
    trial_log.write_text(
        json.dumps(
            {
                "trace_id": "trace_bad",
                "task_id": "task_bad",
                "status": "failed",
                "stage": "execute",
                "outcome": "failed",
                "route_kind": "registered_tool_failed",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    result = harness_eval_suite.run_eval_suite(trial_log=trial_log, require_trials=True)

    assert not result.passed
    assert result.bad_trials[0]["reason"] == "failed/unsupported trial missing failure_type"

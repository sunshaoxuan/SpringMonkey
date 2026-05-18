from __future__ import annotations

import json
import subprocess

import run_job_by_name as runner


def test_manual_script_job_runs_directly_without_openclaw_cron(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run(command, **kwargs):
        calls.append(list(command))
        return subprocess.CompletedProcess(command, 0, stdout="天气预报\n- ok\n", stderr="")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    rc = runner.run_direct_script_job("weather-report-jst-0700")

    assert rc == 0
    assert calls == [runner.DIRECT_SCRIPT_JOBS["weather-report-jst-0700"]]
    assert calls[0][:1] != ["openclaw"]


def test_manual_script_job_emits_contract_json(monkeypatch, capsys) -> None:
    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(command, 0, stdout="天气预报\n- ok\n", stderr="hidden detail")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    assert runner.run_direct_script_job("weather-report-jst-0700") == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["status"] == "success"
    assert payload["job_name"] == "weather-report-jst-0700"
    assert payload["delivery"] == "manual_owner_reply"
    assert payload["final_report"] == "天气预报\n- ok"
    assert payload["stderr_hidden"] is True

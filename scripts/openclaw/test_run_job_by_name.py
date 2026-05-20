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


def test_manual_media_job_sends_attachment_to_reply_channel(monkeypatch, tmp_path, capsys) -> None:
    image = tmp_path / "weather.svg"
    image.write_text("<svg/>", encoding="utf-8")

    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(command, 0, stdout=f"MEDIA:{image}\n天气预报图片", stderr="")

    sent = {}

    def fake_send(channel_id, content):
        sent["channel_id"] = channel_id
        sent["content"] = content
        return 1, f"media:{image}"

    monkeypatch.setenv("OPENCLAW_REPLY_CHANNEL_ID", "dm_channel")
    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    monkeypatch.setattr(runner, "send_discord_message", fake_send)

    assert runner.run_direct_script_job("weather-report-jst-0700") == 0
    payload = json.loads(capsys.readouterr().out)

    assert sent["channel_id"] == "dm_channel"
    assert sent["content"].startswith("MEDIA:")
    assert payload["delivery"] == "manual_media_sent"
    assert payload["final_report"] == ""


def test_manual_media_job_preserves_multiple_media_delivery_evidence(monkeypatch, tmp_path, capsys) -> None:
    first = tmp_path / "tokyo.png"
    second = tmp_path / "beijing.png"
    first.write_bytes(b"png1")
    second.write_bytes(b"png2")

    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(command, 0, stdout=f"MEDIA:{first}\nMEDIA:{second}", stderr="")

    def fake_send(channel_id, content):
        return 2, f"media:{first},{second}"

    monkeypatch.setenv("OPENCLAW_REPLY_CHANNEL_ID", "dm_channel")
    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    monkeypatch.setattr(runner, "send_discord_message", fake_send)

    assert runner.run_direct_script_job("weather-report-jst-0700") == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["delivery"] == "manual_media_sent"
    assert str(first) in payload["media_delivery"]
    assert str(second) in payload["media_delivery"]


def test_composite_news_job_runs_both_formal_slots(monkeypatch, capsys) -> None:
    calls: list[list[str]] = []

    def fake_run(command, **kwargs):
        calls.append(list(command))
        text = "morning report" if "0900" in " ".join(command) else "evening report"
        return subprocess.CompletedProcess(command, 0, stdout=text, stderr="")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    assert runner.run_composite_script_job("news-digest-jst-today") == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["status"] == "success"
    assert payload["job_name"] == "news-digest-jst-today"
    assert "news-digest-jst-0900" in payload["final_report"]
    assert "morning report" in payload["final_report"]
    assert "news-digest-jst-1700" in payload["final_report"]
    assert "evening report" in payload["final_report"]
    assert len(calls) == 2

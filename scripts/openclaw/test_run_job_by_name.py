from __future__ import annotations

import json
import subprocess
from pathlib import Path

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
    calls: list[str] = []

    def fake_news_job(name):
        calls.append(name)
        text = "morning report" if name.endswith("0900") else "evening report"
        return 0, text, f"/tmp/{name}", ""

    monkeypatch.setattr(runner, "run_news_pipeline_job", fake_news_job)

    assert runner.run_composite_script_job("news-digest-jst-today") == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["status"] == "success"
    assert payload["job_name"] == "news-digest-jst-today"
    assert "news-digest-jst-0900" in payload["final_report"]
    assert "morning report" in payload["final_report"]
    assert "news-digest-jst-1700" in payload["final_report"]
    assert "evening report" in payload["final_report"]
    assert calls == ["news-digest-jst-0900", "news-digest-jst-1700"]


def test_composite_news_public_delivery_sends_and_marks_each_slot(monkeypatch, capsys) -> None:
    sent: list[tuple[str, str]] = []
    marked: list[tuple[str, str]] = []

    def fake_news_job(name):
        text = "morning report" if name.endswith("0900") else "evening report"
        return 0, text, f"/tmp/{name}", ""

    def fake_send(channel_id, content):
        sent.append((channel_id, content))
        return 1, "text"

    def fake_mark(name, run_dir):
        marked.append((name, run_dir))
        return "MARK_PUBLISHED_OK"

    monkeypatch.setenv("OPENCLAW_NEWS_DELIVERY_CHANNEL_ID", "public_channel")
    monkeypatch.setattr(runner, "run_news_pipeline_job", fake_news_job)
    monkeypatch.setattr(runner, "send_discord_message", fake_send)
    monkeypatch.setattr(runner, "mark_news_published", fake_mark)

    assert runner.run_composite_script_job("news-digest-jst-today") == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["status"] == "success"
    assert payload["delivery"] == "manual_owner_reply"
    assert "已补发到公共频道" in payload["final_report"]
    assert "morning report" not in payload["final_report"]
    assert "evening report" not in payload["final_report"]
    assert sent == [("public_channel", "morning report"), ("public_channel", "evening report")]
    assert marked == [("news-digest-jst-0900", "/tmp/news-digest-jst-0900"), ("news-digest-jst-1700", "/tmp/news-digest-jst-1700")]


def test_news_pipeline_job_uses_window_override_and_reads_final_report(monkeypatch, tmp_path) -> None:
    run_dir = tmp_path / "news-run"
    run_dir.mkdir()
    (run_dir / "final_broadcast.md").write_text("补发正文", encoding="utf-8")
    captured: dict[str, list[str]] = {}

    def fake_run(command, **kwargs):
        captured["command"] = list(command)
        return subprocess.CompletedProcess(command, 0, stdout=f"PIPELINE_OK {run_dir}\n", stderr="")

    monkeypatch.setenv("OPENCLAW_NEWS_WINDOW_START_TS", "1779033600")
    monkeypatch.setenv("OPENCLAW_NEWS_WINDOW_END_TS", "1779062400")
    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    code, final_report, found_run_dir, detail = runner.run_news_pipeline_job("news-digest-jst-1700")

    assert code == 0
    assert final_report == "补发正文"
    assert Path(found_run_dir) == run_dir
    assert "--window-start" in captured["command"]
    assert "--window-end" in captured["command"]
    assert "--reset-published-window-start" in captured["command"]
    assert "--ignore-recent" in captured["command"]
    assert detail.startswith("PIPELINE_OK")


def test_composite_news_job_fails_when_pipeline_returns_no_final_content(monkeypatch, capsys) -> None:
    def fake_news_job(name):
        return 0, "", f"/tmp/{name}", "PIPELINE_OK without final content"

    monkeypatch.setattr(runner, "run_news_pipeline_job", fake_news_job)

    assert runner.run_composite_script_job("news-digest-jst-today") == 1
    payload = json.loads(capsys.readouterr().out)

    assert payload["status"] == "failed"
    assert payload["failures"][0]["returncode"] == 4
    assert "did not produce final_broadcast.md content" in payload["failures"][0]["stderr"]

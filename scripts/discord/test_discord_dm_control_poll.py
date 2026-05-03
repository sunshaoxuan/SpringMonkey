#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path


def load_module():
    path = Path(__file__).with_name("discord_dm_control_poll.py")
    spec = importlib.util.spec_from_file_location("discord_dm_control_poll", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_classify_timescar():
    module = load_module()
    assert module.classify("保留这单") == "timescar_keep"
    assert module.classify("今天的订车时间整体往后延15分钟") == "timescar_change"
    assert module.classify("请把明天开始的订车取消明天的时间，让开始时间从后天早上9点开始，结束时间不变。") == "timescar_change"
    assert module.classify("取消这单") == "timescar_cancel"


def test_remember_keep_records_booking():
    module = load_module()
    with tempfile.TemporaryDirectory() as tmp:
        module.DECISIONS_PATH = Path(tmp) / "decisions.json"
        msg = module.remember_keep("保留预约 214525110", "1500")
        assert "214525110" in msg
        data = module.read_json(module.DECISIONS_PATH, {})
        assert data["keepBookingNumbers"]["214525110"]["status"] == "keep"


if __name__ == "__main__":
    test_classify_timescar()
    test_remember_keep_records_booking()
    print("discord_dm_control_poll_ok")

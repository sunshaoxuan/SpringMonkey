#!/usr/bin/env python3
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
CFG = REPO / "config" / "news" / "broadcast.json"
NEWS_DIR = Path(__file__).resolve().parent


def _load_run_news_pipeline():
    import importlib.util

    p = NEWS_DIR / "run_news_pipeline.py"
    spec = importlib.util.spec_from_file_location("run_news_pipeline", p)
    assert spec and spec.loader
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _load_verify():
    import importlib.util

    p = NEWS_DIR / "verify_broadcast_draft.py"
    spec = importlib.util.spec_from_file_location("verify_broadcast_draft", p)
    assert spec and spec.loader
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class TestPlanAndTemplate(unittest.TestCase):
    def setUp(self):
        self.cfg = json.loads(CFG.read_text(encoding="utf-8"))
        self.m = _load_run_news_pipeline()

    def test_build_plan_batches(self):
        job = self.m.job_spec(self.cfg, "news-digest-jst-1700")
        plan = self.m.build_plan(self.cfg, job)
        self.assertEqual(len(plan["batches"]), 4)
        self.assertEqual(plan["batches"][0]["id"], "japan")
        self.assertIn("Reuters", " ".join(plan["batches"][0]["source_pool"]))

    def test_template_orchestration(self):
        job = self.m.job_spec(self.cfg, "news-digest-jst-1700")
        plan = self.m.build_plan(self.cfg, job)
        orch = self.m.template_orchestration(plan)
        self.assertEqual(len(orch["batches"]), 4)
        self.assertIn("queries", orch["batches"][0])


class TestVerifyDraft(unittest.TestCase):
    def setUp(self):
        self.cfg = json.loads(CFG.read_text(encoding="utf-8"))
        self.v = _load_verify()

    def test_good_sample(self):
        text = """新闻简报
当日 09:00 到当日 17:00（亚洲/东京，JST）
1. 日本
- a
2. 中国
- b
3. 国际
- c
4. 市场或风险提示
- d
"""
        ok, err = self.v.verify_text(text, self.cfg)
        self.assertTrue(ok, err)

    def test_bad_numbering(self):
        text = """新闻简报
窗口
1. 日本
2. 中国
3. 国际
5. 错
"""
        ok, err = self.v.verify_text(text, self.cfg)
        self.assertFalse(ok)
        self.assertTrue(any("bad_top_level" in e for e in err))


class TestCliSmoke(unittest.TestCase):
    def test_pipeline_no_llm(self):
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td) / "r1"
            r = subprocess.run(
                [
                    sys.executable,
                    str(NEWS_DIR / "run_news_pipeline.py"),
                    "--job",
                    "news-digest-jst-1700",
                    "--run-dir",
                    str(run_dir),
                    "--template-orchestrate",
                    "--skip-worker",
                    "--skip-finalize",
                    "--skip-verify",
                ],
                cwd=str(REPO),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertTrue((run_dir / "plan.json").is_file())
            self.assertTrue((run_dir / "orchestration.json").is_file())
            self.assertTrue((run_dir / "draft_merged.md").is_file())


if __name__ == "__main__":
    unittest.main()

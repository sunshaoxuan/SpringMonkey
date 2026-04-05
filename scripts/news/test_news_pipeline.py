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


class TestPipelineCronMessage(unittest.TestCase):
    def test_build_pipeline_message_has_job_and_script(self):
        m = _load_apply_news_config()
        cfg = json.loads(CFG.read_text(encoding="utf-8"))
        spec = cfg["jobs"][0]
        text = m.build_pipeline_cron_message(cfg, spec)
        self.assertIn("run_news_pipeline.py", text)
        self.assertIn(spec["name"], text)
        self.assertIn("PIPELINE_OK", text)
        self.assertIn("final_broadcast.md", text)


def _load_apply_news_config():
    import importlib.util

    p = NEWS_DIR / "apply_news_config.py"
    spec = importlib.util.spec_from_file_location("apply_news_config", p)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


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


class TestEnsureDailyMemory(unittest.TestCase):
    def test_creates_file(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            r = subprocess.run(
                [
                    sys.executable,
                    str(NEWS_DIR / "ensure_daily_memory.py"),
                    "--workspace-root",
                    str(root),
                    "--date",
                    "2030-06-01",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(r.returncode, 0, r.stderr)
            p = root / "memory" / "2030-06-01.md"
            self.assertTrue(p.is_file())
            self.assertIn("2030-06-01", p.read_text(encoding="utf-8"))


class TestVerifyRuntimeReadiness(unittest.TestCase):
    def test_pipeline_jobs_ok(self):
        cfg = json.loads(CFG.read_text(encoding="utf-8"))
        if (cfg.get("newsExecution") or {}).get("mode") != "pipeline":
            self.skipTest("not pipeline mode")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            tok = "【新闻定时任务 · 流水线模式】"
            jobs = {
                "version": 1,
                "jobs": [
                    {
                        "name": spec["name"],
                        "payload": {
                            "message": tok + "\n" + spec["name"],
                            "timeoutSeconds": 7200,
                        },
                    }
                    for spec in cfg["jobs"]
                ],
            }
            jp = root / "jobs.json"
            jp.write_text(json.dumps(jobs, ensure_ascii=False), encoding="utf-8")
            mem = root / "memory"
            mem.mkdir()
            (mem / "2030-01-01.md").write_text("#\n", encoding="utf-8")
            r = subprocess.run(
                [
                    sys.executable,
                    str(NEWS_DIR / "verify_runtime_readiness.py"),
                    "--config",
                    str(CFG),
                    "--jobs",
                    str(jp),
                    "--workspace-root",
                    str(root),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("RUNTIME_VERIFY_OK", r.stdout)

    def test_pipeline_jobs_missing_token_fails(self):
        cfg = json.loads(CFG.read_text(encoding="utf-8"))
        if (cfg.get("newsExecution") or {}).get("mode") != "pipeline":
            self.skipTest("not pipeline mode")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            jobs = {
                "version": 1,
                "jobs": [
                    {
                        "name": spec["name"],
                        "payload": {"message": "旧文案无流水线", "timeoutSeconds": 7200},
                    }
                    for spec in cfg["jobs"]
                ],
            }
            jp = root / "jobs.json"
            jp.write_text(json.dumps(jobs, ensure_ascii=False), encoding="utf-8")
            (root / "memory").mkdir()
            r = subprocess.run(
                [
                    sys.executable,
                    str(NEWS_DIR / "verify_runtime_readiness.py"),
                    "--config",
                    str(CFG),
                    "--jobs",
                    str(jp),
                    "--workspace-root",
                    str(root),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("RUNTIME_VERIFY_FAIL", r.stderr)


if __name__ == "__main__":
    unittest.main()

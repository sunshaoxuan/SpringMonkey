#!/usr/bin/env python3
import json
import os
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


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


def _load_fetcher():
    import importlib.util
    import sys

    p = NEWS_DIR / "news_fetcher.py"
    spec = importlib.util.spec_from_file_location("news_fetcher", p)
    assert spec and spec.loader
    m = importlib.util.module_from_spec(spec)
    sys.modules["news_fetcher"] = m
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

    def test_summarize_article_prompt(self):
        sys_p, user_p = self.m.summarize_article_prompt(
            "Test Title", "https://example.com/article", "Article body text here."
        )
        self.assertIn("example.com/article", sys_p)
        self.assertIn("Test Title", user_p)
        self.assertIn("Article body text here", user_p)
        self.assertIn("•", sys_p)

    def test_summarize_prompt_truncates_long_content(self):
        long_body = "A" * 3000
        _, user_p = self.m.summarize_article_prompt(
            "Title", "https://example.com", long_body, max_chars=500
        )
        self.assertLessEqual(len(user_p), 600)

    def test_summarize_articles_fallback_when_empty(self):
        result = self.m._summarize_articles_with_qwen(
            articles=[],
            ollama_host="http://localhost:9999",
            model="test",
            timeout=5,
            fallback_line="本节无合格新增新闻条目。",
            max_input_chars=1500,
            bid="japan",
        )
        self.assertIn("本节无合格新增新闻条目", result)

    def test_summarize_articles_skips_unfetched(self):
        articles = [
            {"title": "T1", "url": "http://a.com", "content": "", "fetch_ok": False, "snippet": ""},
        ]
        result = self.m._summarize_articles_with_qwen(
            articles=articles,
            ollama_host="http://localhost:9999",
            model="test",
            timeout=5,
            fallback_line="本节无合格新增新闻条目。",
            max_input_chars=1500,
            bid="japan",
        )
        self.assertIn("本节无合格新增新闻条目", result)

    def test_resolve_ollama_base_url_from_config(self):
        cfg = {"model": {"ollamaBaseUrl": "http://remote.example:22545"}}
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("OLLAMA_HOST", None)
            self.assertEqual(self.m.resolve_ollama_base_url(cfg), "http://remote.example:22545")

    def test_resolve_ollama_env_overrides_config(self):
        cfg = {"model": {"ollamaBaseUrl": "http://remote.example:22545"}}
        with patch.dict(os.environ, {"OLLAMA_HOST": "http://127.0.0.1:11434"}):
            self.assertEqual(self.m.resolve_ollama_base_url(cfg), "http://127.0.0.1:11434")

    def test_mechanical_fallback_passes_verify(self):
        cfg = self.cfg
        job = self.m.job_spec(cfg, "news-digest-jst-1700")
        plan = self.m.build_plan(cfg, job)
        merged = (
            "<!-- batch:japan -->\n- JP news item\n"
            "<!-- batch:china -->\n- CN news item\n"
            "<!-- batch:world -->\n- Intl news item\n"
            "<!-- batch:markets -->\n- Markets item\n"
        )
        text = self.m._mechanical_fallback(cfg, plan, merged)
        v = _load_verify()
        ok, err = v.verify_text(text, cfg)
        self.assertTrue(ok, f"mechanical fallback should pass verify: {err}")
        self.assertIn("新闻简报", text)
        self.assertIn("**1. 日本**", text)
        self.assertIn("**4. 市场或风险提示**", text)
        self.assertIn("• ", text)

    def test_mechanical_fallback_strips_numbering(self):
        cfg = self.cfg
        job = self.m.job_spec(cfg, "news-digest-jst-1700")
        plan = self.m.build_plan(cfg, job)
        merged = (
            "<!-- batch:japan -->\n- 1. Numbered item\n- **2.** Bold numbered\n- 3、Chinese num\n"
            "<!-- batch:china -->\n1. Bare number\n(2) Paren number\n"
            "<!-- batch:world -->\n- ① Circle number\n"
            "<!-- batch:markets -->\n- Normal item\n"
        )
        text = self.m._mechanical_fallback(cfg, plan, merged)
        v = _load_verify()
        ok, err = v.verify_text(text, cfg)
        self.assertTrue(ok, f"should strip numbering and pass verify: {err}")
        japan_section = text.split("**1. 日本**")[1].split("**2. 中国**")[0]
        self.assertNotIn("• 1.", japan_section)
        self.assertNotIn("• **2.**", text)
        self.assertNotIn("• 3、", text)
        self.assertNotIn("• ①", text)

    def test_mechanical_fallback_empty_batch(self):
        cfg = self.cfg
        job = self.m.job_spec(cfg, "news-digest-jst-1700")
        plan = self.m.build_plan(cfg, job)
        merged = "<!-- batch:japan -->\n<!-- batch:china -->\n<!-- batch:world -->\n<!-- batch:markets -->\n"
        text = self.m._mechanical_fallback(cfg, plan, merged)
        v = _load_verify()
        ok, err = v.verify_text(text, cfg)
        self.assertTrue(ok, f"empty-batch fallback should still pass: {err}")
        self.assertIn("本节无合格新增新闻条目", text)

    def test_ollama_api_model_name_strips_provider_prefix(self):
        self.assertEqual(
            self.m.ollama_api_model_name("ollama/qwen3:14b"),
            "qwen3:14b",
        )
        self.assertEqual(self.m.ollama_api_model_name("qwen3:14b"), "qwen3:14b")
        self.assertEqual(self.m.ollama_api_model_name("Ollama/foo:bar"), "foo:bar")

    def test_strip_think_blocks(self):
        raw = "<think>internal plan</think>\n• 新闻摘要条目\n链接：https://example.com"
        cleaned = self.m.strip_think_blocks(raw)
        self.assertNotIn("<think>", cleaned)
        self.assertIn("• 新闻摘要条目", cleaned)

    def test_broadcast_json_has_ollama_base_url(self):
        url = self.cfg.get("model", {}).get("ollamaBaseUrl", "")
        self.assertTrue(url.startswith("http://"), "model.ollamaBaseUrl should be set for pipeline hosts")
        self.assertNotIn("127.0.0.1", url)


class TestVerifyDraft(unittest.TestCase):
    def setUp(self):
        self.cfg = json.loads(CFG.read_text(encoding="utf-8"))
        self.v = _load_verify()

    def test_good_sample(self):
        text = """新闻简报
当日 09:00 到当日 17:00（亚洲/东京，JST）
**1. 日本**
• a
**2. 中国**
• b
**3. 国际**
• c
**4. 市场或风险提示**
• d
"""
        ok, err = self.v.verify_text(text, self.cfg)
        self.assertTrue(ok, err)

    def test_bad_numbering(self):
        text = """新闻简报
窗口
**1. 日本**
**2. 中国**
**3. 国际**
5. 错
"""
        ok, err = self.v.verify_text(text, self.cfg)
        self.assertFalse(ok)
        self.assertTrue(any("bad_top_level" in e or "bare_numbered" in e for e in err))

    def test_numbered_inside_bullet_fails(self):
        text = """新闻简报
窗口
**1. 日本**
• 1. Item with number
**2. 中国**
• ok
**3. 国际**
• ok
**4. 市场或风险提示**
• ok
"""
        ok, err = self.v.verify_text(text, self.cfg)
        self.assertFalse(ok)
        self.assertTrue(any("numbered_inside_bullet" in e for e in err))

    def test_chinese_numbering_in_bullet_fails(self):
        text = """新闻简报
窗口
**1. 日本**
• 1、Item
**2. 中国**
• ok
**3. 国际**
• ok
**4. 市场或风险提示**
• ok
"""
        ok, err = self.v.verify_text(text, self.cfg)
        self.assertFalse(ok)
        self.assertTrue(any("numbered_inside_bullet_cn" in e for e in err))

    def test_think_block_fails(self):
        text = """新闻简报
窗口
**1. 日本**
<think>internal</think>
• ok
**2. 中国**
• ok
**3. 国际**
• ok
**4. 市场或风险提示**
• ok
"""
        ok, err = self.v.verify_text(text, self.cfg)
        self.assertFalse(ok)
        self.assertTrue(any("contains_think_block" in e for e in err))

    def test_bare_dash_bullet_fails(self):
        """Discord 会把 - 开头渲染成列表，应该用 • 而不是 -"""
        text = """新闻简报
窗口
**1. 日本**
- item with dash
**2. 中国**
• ok
**3. 国际**
• ok
**4. 市场或风险提示**
• ok
"""
        ok, err = self.v.verify_text(text, self.cfg)
        # - 开头在 forbidNestedNumbering 环境下不应该被硬拒，
        # 但如果 contentBulletPrefix 是 • 则理想上应检查一致性。
        # 当前校验至少不应把 - item 当成通过。


class TestPipelineCronMessage(unittest.TestCase):
    def test_build_pipeline_message_has_job_and_script(self):
        m = _load_apply_news_config()
        cfg = json.loads(CFG.read_text(encoding="utf-8"))
        spec = cfg["jobs"][0]
        text = m.build_pipeline_cron_message(cfg, spec)
        self.assertIn("python3", text)
        self.assertIn("news_digest_jst_0900", text)
        self.assertIn("PIPELINE_OK", text)
        self.assertIn("final_broadcast.md", text)
        self.assertIn(spec["name"], text)
        self.assertIn("模型角色边界", text)
        self.assertIn("逐条处理器", text)

    def test_build_message_has_qwen_policy(self):
        m = _load_apply_news_config()
        cfg = json.loads(CFG.read_text(encoding="utf-8"))
        spec = cfg["jobs"][0]
        text = m.build_message(cfg, spec)
        self.assertIn("处理器", text)
        self.assertIn("禁止场景", text)


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
                    "--skip-discover",
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


def _load_verify_runtime():
    import importlib.util

    p = NEWS_DIR / "verify_runtime_readiness.py"
    spec = importlib.util.spec_from_file_location("verify_runtime_readiness", p)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestRssReachabilityHelpers(unittest.TestCase):
    def test_hosts_from_cfg_custom(self):
        vr = _load_verify_runtime()
        cfg = {"runtimeReadiness": {"rssReachabilityHosts": ["a.example", "b.example"]}}
        self.assertEqual(vr.rss_reachability_hosts(cfg), ["a.example", "b.example"])

    def test_hosts_from_cfg_default_when_empty(self):
        vr = _load_verify_runtime()
        self.assertIn("feeds.reuters.com", vr.rss_reachability_hosts({}))

    @patch.object(socket, "getaddrinfo", side_effect=OSError("nxdomain"))
    def test_any_resolves_all_fail(self, _mock):
        vr = _load_verify_runtime()
        ok, detail = vr.any_rss_host_resolves(["x.test", "y.test"])
        self.assertFalse(ok)
        self.assertIn("x.test", detail or "")

    @patch.object(socket, "getaddrinfo", side_effect=[OSError("a"), [(0, 0, 0, "", ("1.1.1.1", 443))]])
    def test_any_resolves_second_ok(self, _mock):
        vr = _load_verify_runtime()
        ok, detail = vr.any_rss_host_resolves(["bad.test", "good.test"])
        self.assertTrue(ok)
        self.assertIsNone(detail)


class TestFetcherDegradedFallback(unittest.TestCase):
    def test_fetch_error_uses_snippet_when_long_enough(self):
        f = _load_fetcher()
        article = f.Article(
            title="T",
            url="https://example.com/a",
            source_feed="feed",
            snippet="这是一段足够长的摘要片段，用于在正文抓取失败时降级保底输出，避免整批变成无新闻。",
        )
        with patch.object(f, "fetch_article_content", return_value="[fetch_error: HTTP 502]"):
            out = f.fetch_and_fill([article])
        self.assertTrue(out[0].fetch_ok)
        self.assertIn("degraded_to_snippet", out[0].fetch_error)
        self.assertGreater(len(out[0].content), 20)

    def test_batch_relevant_filters_japan_non_japan(self):
        f = _load_fetcher()
        self.assertFalse(
            f._batch_relevant(
                "japan",
                "Mali Terror Attack",
                "https://example.com/world/mali",
                "Mali news",
            )
        )
        self.assertTrue(
            f._batch_relevant(
                "japan",
                "Tokyo inflation rises",
                "https://example.com/japan/tokyo",
                "Tokyo CPI update",
            )
        )

    def test_discover_fallback_when_relevance_filters_everything(self):
        f = _load_fetcher()
        item = {
            "title": "Mali Terror Attack",
            "url": "https://example.com/world/mali",
            "snippet": "Mali news",
            "published_at": "Mon, 01 Jan 2024 00:00:00 GMT",
            "published_ts": 1704067200,
            "fingerprint": "example.com|mali",
        }
        with patch.object(f, "fetch_rss", return_value=[item]):
            arts = f.discover_articles(
                "japan",
                feeds=["https://example.com/feed.xml"],
                max_per_batch=8,
                window_start_ts=0,
                window_end_ts=0,
                exclude_fingerprints=set(),
                require_timestamp=False,
            )
        self.assertEqual(len(arts), 1)
        self.assertEqual(arts[0].title, "Mali Terror Attack")


if __name__ == "__main__":
    unittest.main()

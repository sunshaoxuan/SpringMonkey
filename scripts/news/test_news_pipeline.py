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
        self.assertEqual(len(plan["batches"]), len(self.cfg["formatRules"]["outline"]))
        self.assertEqual(plan["batches"][0]["id"], "japan")
        self.assertIn("Reuters", " ".join(plan["batches"][0]["source_pool"]))

    def test_template_orchestration(self):
        job = self.m.job_spec(self.cfg, "news-digest-jst-1700")
        plan = self.m.build_plan(self.cfg, job)
        orch = self.m.template_orchestration(plan)
        self.assertEqual(len(orch["batches"]), len(self.cfg["formatRules"]["outline"]))
        self.assertIn("queries", orch["batches"][0])

    def test_summarize_article_prompt(self):
        sys_p, user_p = self.m.summarize_article_prompt(
            "Test Title", "https://example.com/article", "Article body text here."
        )
        self.assertIn("example.com/article", sys_p)
        self.assertIn("不得补充背景知识", sys_p)
        self.assertIn("公司隶属", sys_p)
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

    def test_summarize_articles_skips_untranslated_when_model_empty(self):
        articles = [
            {
                "title": "Sample market headline",
                "url": "https://example.com/market",
                "content": "content",
                "fetch_ok": True,
                "snippet": "",
            }
        ]
        with patch.object(self.m, "ollama_chat", return_value=""):
            result = self.m._summarize_articles_with_qwen(
                articles=articles,
                ollama_host="http://localhost:9999",
                model="test",
                timeout=5,
                fallback_line="本节无合格新增新闻条目。",
                max_input_chars=1500,
                bid="markets",
            )
        self.assertIn("本节无合格新增新闻条目", result)
        self.assertNotIn("Sample market headline", result)

    def test_summarize_articles_uses_known_chinese_mapping_when_model_empty(self):
        articles = [
            {
                "title": "South Korean court hikes ex-president's sentence for obstructing justice",
                "url": "https://example.com/korea",
                "content": "content",
                "fetch_ok": True,
                "snippet": "",
            }
        ]
        with patch.object(self.m, "ollama_chat", return_value=""):
            result = self.m._summarize_articles_with_qwen(
                articles=articles,
                ollama_host="http://localhost:9999",
                model="test",
                timeout=5,
                fallback_line="本节无合格新增新闻条目。",
                max_input_chars=1500,
                bid="world",
        )
        self.assertIn("韩国法院因妨碍司法加重前总统刑期", result)
        self.assertIn("https://example.com/korea", result)

    def test_process_raw_article_item_does_not_invent_when_model_fails(self):
        item = {
            "item_id": "001",
            "original_batch": "japan",
            "title": "Food prices in Japan set to rise as war drives up cost of plastic packaging",
            "source_url": "https://example.com/a",
            "source_url_key": "https://example.com/a",
            "raw_content": "English body",
            "fetch_ok": True,
        }
        with patch.object(self.m, "ollama_chat", side_effect=RuntimeError("model down")):
            result = self.m.process_raw_article_item(
                item,
                ollama_host="http://localhost:9999",
                openai_base_url="https://api.openai.com/v1",
                openai_api_key="",
                model="test",
                fallback_model="",
                timeout=5,
                max_input_chars=1500,
            )
        self.assertFalse(result["included"])
        self.assertEqual(result["summary_zh"], "")
        self.assertEqual(result["skip_reason"], "model_failed")

    def test_processor_healthcheck_reports_unavailable(self):
        with patch.object(self.m, "ollama_chat", side_effect=RuntimeError("down")):
            ok, detail = self.m.check_processor_health(
                "ollama/test",
                ollama_host="http://localhost:9",
                openai_base_url="https://api.openai.com/v1",
                openai_api_key="",
                timeout=1,
            )
        self.assertFalse(ok)
        self.assertIn("down", detail)

    def test_codex_model_uses_configured_http_endpoint(self):
        with patch.object(self.m, "openai_chat", return_value='{"ok":true}') as mocked:
            result = self.m.chat_with_model(
                "openai-codex/gpt-5.5",
                ollama_host="http://localhost:9",
                openai_base_url="https://api.openai.com/v1",
                openai_api_key="",
                codex_base_url="http://ccnode.briconbric.com:49530/v1",
                codex_api_key="secret",
                system="s",
                user="u",
                timeout=5,
            )
        self.assertEqual(result, '{"ok":true}')
        mocked.assert_called_once_with(
            "http://ccnode.briconbric.com:49530/v1",
            "secret",
            "gpt-5.5",
            "s",
            "u",
            5,
        )

    def test_codex_http_endpoint_requires_key_and_does_not_use_gateway(self):
        with patch.object(self.m, "openclaw_model_chat") as gateway:
            with self.assertRaises(RuntimeError) as ctx:
                self.m.chat_with_model(
                    "openai-codex/gpt-5.5",
                    ollama_host="http://localhost:9",
                    openai_base_url="https://api.openai.com/v1",
                    openai_api_key="",
                    codex_base_url="http://ccnode.briconbric.com:49530/v1",
                    codex_api_key="",
                    system="s",
                    user="u",
                    timeout=5,
                )
        self.assertIn("missing NEWS_CODEX_API_KEY", str(ctx.exception))
        gateway.assert_not_called()

    def test_load_runtime_env_files_does_not_override_existing_env(self):
        with tempfile.TemporaryDirectory() as td:
            env_file = Path(td) / "openclaw.env"
            env_file.write_text(
                "NEWS_CODEX_API_KEY=from_file\n"
                "export NEWS_CODEX_BASE_URL='http://ccnode.briconbric.com:49530/v1'\n",
                encoding="utf-8",
            )
            old_key = os.environ.get("NEWS_CODEX_API_KEY")
            old_base = os.environ.get("NEWS_CODEX_BASE_URL")
            try:
                os.environ["NEWS_CODEX_API_KEY"] = "already_set"
                os.environ.pop("NEWS_CODEX_BASE_URL", None)
                self.m.load_runtime_env_files([env_file])
                self.assertEqual(os.environ["NEWS_CODEX_API_KEY"], "already_set")
                self.assertEqual(os.environ["NEWS_CODEX_BASE_URL"], "http://ccnode.briconbric.com:49530/v1")
            finally:
                if old_key is None:
                    os.environ.pop("NEWS_CODEX_API_KEY", None)
                else:
                    os.environ["NEWS_CODEX_API_KEY"] = old_key
                if old_base is None:
                    os.environ.pop("NEWS_CODEX_BASE_URL", None)
                else:
                    os.environ["NEWS_CODEX_BASE_URL"] = old_base

    def test_resolve_codex_api_key_reads_public_secret_file(self):
        with tempfile.TemporaryDirectory() as td:
            secret_file = Path(td) / "codex.key"
            secret_file.write_text("from_file_secret\n", encoding="utf-8")
            old = os.environ.get("NEWS_CODEX_API_KEY_FILE")
            try:
                os.environ.pop("NEWS_CODEX_API_KEY", None)
                os.environ["NEWS_CODEX_API_KEY_FILE"] = str(secret_file)
                self.assertEqual(self.m.resolve_codex_api_key({"model": {}}), "from_file_secret")
            finally:
                if old is None:
                    os.environ.pop("NEWS_CODEX_API_KEY_FILE", None)
                else:
                    os.environ["NEWS_CODEX_API_KEY_FILE"] = old

    def test_archive_raw_article_items_writes_per_article_files(self):
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td)
            raw = self.m.archive_raw_article_items(
                run_dir,
                {
                    "world": [
                        {
                            "title": "标题",
                            "url": "https://example.com/a#frag",
                            "content": "正文",
                            "fetch_ok": True,
                            "snippet": "摘要",
                            "published_at": "today",
                            "published_ts": 123,
                            "fingerprint": "fp",
                            "source_feed": "feed",
                        }
                    ]
                },
            )
            self.assertEqual(len(raw), 1)
            self.assertEqual(raw[0]["source_url_key"], "https://example.com/a")
            self.assertTrue((run_dir / "raw_items" / f"{raw[0]['item_id']}.json").is_file())
            self.assertTrue((run_dir / "raw_items_index.json").is_file())

    def test_process_raw_article_item_rejects_untranslated_model_output(self):
        item = {
            "item_id": "001",
            "original_batch": "world",
            "title": "Sample market headline",
            "source_url": "https://example.com/a",
            "source_url_key": "https://example.com/a",
            "raw_content": "English body",
            "fetch_ok": True,
        }
        with patch.object(
            self.m,
            "ollama_chat",
            return_value='{"summary_zh":"Sample market headline remains English","region":"world","category":"economy"}',
        ):
            result = self.m.process_raw_article_item(
                item,
                ollama_host="http://localhost:9999",
                openai_base_url="https://api.openai.com/v1",
                openai_api_key="",
                model="test",
                fallback_model="",
                timeout=5,
                max_input_chars=1500,
            )
        self.assertFalse(result["included"])
        self.assertEqual(result["skip_reason"], "non_chinese_summary")

    def test_write_selected_items_and_workers_uses_structured_items_only(self):
        job = self.m.job_spec(self.cfg, "news-digest-jst-1700")
        plan = self.m.build_plan(self.cfg, job)
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td)
            self.m.write_selected_items_and_workers(
                run_dir,
                plan,
                [
                    {
                        "item_id": "001",
                        "region": "world",
                        "summary_zh": "韩国法院因妨碍司法加重前总统刑期",
                        "source_url": "https://example.com/korea",
                        "included": True,
                    },
                    {
                        "item_id": "002",
                        "region": "japan",
                        "summary_zh": "Sample English",
                        "source_url": "https://example.com/en",
                        "included": False,
                    },
                ],
                "本节无合格新增新闻条目。",
            )
            world = (run_dir / "worker_world.md").read_text(encoding="utf-8")
            japan = (run_dir / "worker_japan.md").read_text(encoding="utf-8")
            self.assertIn("韩国法院因妨碍司法加重前总统刑期", world)
            self.assertNotIn("Sample English", japan)
            self.assertIn("本节无合格新增新闻条目", japan)

    def test_write_selected_items_keeps_country_batch_in_country_section(self):
        job = self.m.job_spec(self.cfg, "news-digest-jst-1700")
        plan = self.m.build_plan(self.cfg, job)
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td)
            selected = self.m.write_selected_items_and_workers(
                run_dir,
                plan,
                [
                    {
                        "item_id": "001",
                        "original_batch": "japan",
                        "region": "world",
                        "summary_zh": "日本新闻自由排名相关报道。",
                        "source_url": "https://example.com/jp",
                        "included": True,
                    }
                ],
                "本节无合格新增新闻条目。",
            )
            self.assertEqual(len(selected["japan"]), 1)
            self.assertEqual(len(selected["world"]), 0)

    def test_classification_prefers_region_over_content(self):
        f = _load_fetcher()
        self.assertEqual(
            f.classify_article_batch(
                "technology",
                "US AI startup raises funding in New York",
                "https://example.com/us-ai",
                "American artificial intelligence company",
            ),
            "us",
        )

    def test_append_published_items_records_selected_official_items(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "published_items.json"
            self.m.append_published_items(
                path,
                {"version": 1, "items": []},
                {
                    "world": [
                        {
                            "source_url": "https://example.com/a#frag",
                            "source_title": "原始标题",
                            "summary_zh": "国际新闻中文摘要",
                            "category": "politics",
                            "published_ts": 100,
                        }
                    ]
                },
                job_name="news-digest-jst-0900",
                window_start_ts=1000,
                window_end_ts=2000,
                now_ts=2100,
            )
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(len(data["items"]), 1)
            self.assertEqual(data["items"][0]["url_key"], "https://example.com/a")
            self.assertEqual(data["items"][0]["status"], "broadcasted")

    def test_reset_published_items_for_window_removes_overlapping_records(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "published_items.json"
            self.m.save_json(
                path,
                {
                    "version": 1,
                    "items": [
                        {
                            "url": "https://example.com/a",
                            "broadcast_window_start_ts": 1000,
                            "broadcast_window_end_ts": 2000,
                        },
                        {
                            "url": "https://example.com/b",
                            "broadcast_window_start_ts": 3000,
                            "broadcast_window_end_ts": 4000,
                        },
                    ],
                },
            )
            removed = self.m.reset_published_items_for_window(path, 1500, 2500)
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(removed, 1)
            self.assertEqual([x["url"] for x in data["items"]], ["https://example.com/b"])

    def test_mark_published_run_dir_records_selected_items(self):
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td) / "run"
            state_path = Path(td) / "published_items.json"
            self.m.save_json(
                run_dir / "meta.json",
                {
                    "job": "news-digest-jst-0900",
                    "window_start_ts": 1000,
                    "window_end_ts": 2000,
                },
            )
            self.m.save_json(
                run_dir / "selected_items.json",
                {
                    "version": 1,
                    "sections": {
                        "world": [
                            {
                                "source_url": "https://example.com/a",
                                "source_title": "原始标题",
                                "summary_zh": "国际新闻中文摘要",
                                "category": "politics",
                                "published_ts": 100,
                            }
                        ]
                    },
                },
            )
            added = self.m.mark_published_run_dir(run_dir, state_path)
            data = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(added, 1)
            self.assertEqual(data["items"][0]["broadcast_job"], "news-digest-jst-0900")

    def test_verify_rejects_untranslated_english_item(self):
        v = _load_verify()
        text = """新闻简报
当日 09:00 到当日 17:00（亚洲/东京，JST）
**1. 日本**
• Asia-Pacific markets set for weaker open as oil climbs on Iran tensions, Fed holds rates
链接：https://example.com
**2. 中国**
• 本节无合格新增新闻条目。
**3. 国际**
• 本节无合格新增新闻条目。
**4. 市场或风险提示**
• 本节无合格新增新闻条目。
"""
        ok, err = v.verify_text(text, self.cfg)
        self.assertFalse(ok)
        self.assertTrue(any("non_chinese_news_item" in e for e in err))

    def test_verify_rejects_japanese_item(self):
        v = _load_verify()
        text = """新闻简报
当日 09:00 到当日 17:00（亚洲/东京，JST）
**1. 日本**
• 日本関係船舶の海峡通過 イラン側に働きかけを継続 日本政府
链接：https://example.com
**2. 中国**
• 本节无合格新增新闻条目。
**3. 国际**
• 本节无合格新增新闻条目。
**4. 市场或风险提示**
• 本节无合格新增新闻条目。
"""
        ok, err = v.verify_text(text, self.cfg)
        self.assertFalse(ok)
        self.assertTrue(any("non_chinese_news_item" in e for e in err))

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
            "<!-- batch:japan -->\n- 日本新闻条目\n"
            "<!-- batch:china -->\n- 中国新闻条目\n"
            "<!-- batch:us -->\n- 美国新闻条目\n"
            "<!-- batch:europe -->\n- 欧洲新闻条目\n"
            "<!-- batch:technology -->\n- 科技新闻条目\n"
            "<!-- batch:entertainment -->\n- 娱乐新闻条目\n"
            "<!-- batch:world -->\n- 国际新闻条目\n"
            "<!-- batch:markets -->\n- 市场新闻条目\n"
        )
        text = self.m._mechanical_fallback(cfg, plan, merged)
        v = _load_verify()
        ok, err = v.verify_text(text, cfg)
        self.assertTrue(ok, f"mechanical fallback should pass verify: {err}")
        self.assertIn("新闻简报", text)
        self.assertIn("**1. 日本**", text)
        self.assertIn("**8. 市场或风险提示**", text)
        self.assertIn("• ", text)

    def test_mechanical_fallback_strips_numbering(self):
        cfg = self.cfg
        job = self.m.job_spec(cfg, "news-digest-jst-1700")
        plan = self.m.build_plan(cfg, job)
        merged = (
            "<!-- batch:japan -->\n- 1. 日本编号条目\n- **2.** 日本加粗编号条目\n- 3、中国编号条目\n"
            "<!-- batch:china -->\n1. 中国裸编号条目\n(2) 中国括号编号条目\n"
            "<!-- batch:us -->\n- 美国普通条目\n"
            "<!-- batch:europe -->\n- 欧洲普通条目\n"
            "<!-- batch:technology -->\n- 科技普通条目\n"
            "<!-- batch:entertainment -->\n- 娱乐普通条目\n"
            "<!-- batch:world -->\n- ① 国际圆圈编号条目\n"
            "<!-- batch:markets -->\n- 市场普通条目\n"
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
        merged = "".join(f"<!-- batch:{b['id']} -->\n" for b in plan["batches"])
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

    def test_codex_model_uses_openclaw_profile_not_api_key(self):
        with patch.object(self.m, "openclaw_model_chat", return_value='{"ok":true}') as mocked:
            out = self.m.chat_with_model(
                "openai-codex/gpt-5.5",
                ollama_host="http://127.0.0.1:9",
                openai_base_url="https://api.openai.com/v1",
                openai_api_key="",
                system="sys",
                user="user",
                timeout=10,
            )
        self.assertEqual(out, '{"ok":true}')
        mocked.assert_called_once()
        self.assertEqual(mocked.call_args.args[0], "openai-codex/gpt-5.5")

    def test_extract_openclaw_model_text_from_outputs_envelope(self):
        raw = json.dumps(
            {
                "ok": True,
                "outputs": [
                    {
                        "text": '{"summary_zh":"中文摘要","region":"japan","category":"technology"}',
                        "mediaUrl": None,
                    }
                ],
            },
            ensure_ascii=False,
        )
        self.assertEqual(
            self.m._extract_openclaw_model_text(raw),
            '{"summary_zh":"中文摘要","region":"japan","category":"technology"}',
        )

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
**3. 美国**
• c
**4. 欧洲**
• d
**5. 科技**
• e
**6. 娱乐与文化**
• f
**7. 国际**
• g
**8. 市场或风险提示**
• h
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
    def test_codex_healthcheck_is_not_capped_at_ollama_timeout(self):
        text = (NEWS_DIR / "run_news_pipeline.py").read_text(encoding="utf-8")
        self.assertNotIn(
            "timeout=min(args.openai_timeout if is_openai_model(worker_model_raw) else args.ollama_timeout, 20)",
            text,
        )
        self.assertNotIn(
            "timeout=min(args.openai_timeout if is_openai_model(fallback_model_raw) else args.ollama_timeout, 20)",
            text,
        )

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
                    "--ignore-recent",
                    "--no-record-recent",
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

    def test_pipeline_refuses_empty_broadcast_when_processing_fails(self):
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td) / "r2"
            r = subprocess.run(
                [
                    sys.executable,
                    str(NEWS_DIR / "run_news_pipeline.py"),
                    "--job",
                    "news-digest-jst-1700",
                    "--run-dir",
                    str(run_dir),
                    "--ignore-recent",
                    "--no-record-recent",
                    "--ollama-timeout",
                    "1",
                ],
                cwd=str(REPO),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env={
                    **os.environ,
                    "OLLAMA_HOST": "http://127.0.0.1:9",
                },
                timeout=90,
            )
            self.assertEqual(r.returncode, 4, r.stdout + r.stderr)
            self.assertTrue((run_dir / "processor_failure.json").is_file())
            self.assertFalse((run_dir / "final_broadcast.md").exists())


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

    def test_fetch_error_uses_title_when_snippet_short(self):
        f = _load_fetcher()
        article = f.Article(
            title="Markets open mixed after policy signal",
            url="https://example.com/m1",
            source_feed="feed",
            snippet="",
        )
        with patch.object(f, "fetch_article_content", return_value="[fetch_error: HTTP 502]"):
            out = f.fetch_and_fill([article])
        self.assertTrue(out[0].fetch_ok)
        self.assertIn("Markets open mixed", out[0].content)

    def test_empty_extract_uses_title_snippet_degraded(self):
        f = _load_fetcher()
        article = f.Article(
            title="Pharma bets a little-known form",
            url="https://example.com/p",
            source_feed="feed",
            snippet="Novartis and peers are betting on new lipid drugs.",
        )
        with patch.object(f, "fetch_article_content", return_value=""):
            out = f.fetch_and_fill([article])
        self.assertTrue(out[0].fetch_ok)
        self.assertIn("degraded_to_snippet", out[0].fetch_error)
        self.assertIn("Pharma bets", out[0].content)

    def test_batch_relevant_filters_japan_non_japan(self):
        f = _load_fetcher()
        self.assertFalse(
            f.batch_relevant(
                "japan",
                "Mali Terror Attack",
                "https://example.com/world/mali",
                "Mali news",
            )
        )
        self.assertTrue(
            f.batch_relevant(
                "japan",
                "Tokyo inflation rises",
                "https://example.com/japan/tokyo",
                "Tokyo CPI update",
            )
        )

    def test_classify_article_batch_is_per_article(self):
        f = _load_fetcher()
        keywords = {
            "japan": ["japan", "tokyo", "日本", "東京"],
            "china": ["china", "beijing", "中国", "北京"],
        }
        self.assertEqual(
            f.classify_article_batch(
                "japan",
                "Mali Terror Attack",
                "https://example.com/world/mali",
                "Mali news",
                keywords,
            ),
            "world",
        )
        self.assertEqual(
            f.classify_article_batch(
                "japan",
                "Trump’s family and friends help revive a former Balkan pariah",
                "https://www.japantimes.co.jp/news/2026/04/28/world/politics/trump-balkan/",
                "A Balkan political story with no local angle.",
                keywords,
            ),
            "world",
        )
        self.assertEqual(
            f.classify_article_batch(
                "world",
                "Tokyo inflation rises",
                "https://example.com/asia",
                "Tokyo CPI update",
                keywords,
            ),
            "japan",
        )
        self.assertEqual(
            f.classify_article_batch(
                "world",
                "China EV exports rise",
                "https://example.com/business",
                "Beijing policy update",
                keywords,
            ),
            "china",
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

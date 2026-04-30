from openclaw_behavior_rule_gate import is_behavior_rule_path


def assert_true(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def assert_false(value: bool, message: str) -> None:
    if value:
        raise AssertionError(message)


def main() -> int:
    behavior_paths = [
        "docs/policies/REPOSITORY_GUARDRAILS.md",
        "docs/runtime-notes/news-task-domain.md",
        "config/news/broadcast.json",
        "scripts/news/run_news_pipeline.py",
        "scripts/openclaw/patch_agent_society_runtime_current.py",
        "scripts/cron/upsert_generic_cron_job.py",
        "scripts/remote_install_direct_discord_cron.py",
        "scripts/remote_install_browser_guardrails.py",
        "scripts/remote_refresh_capability_awareness.py",
        "scripts/deploy/deployment_master.py",
        "scripts/patch/final_patch_deploy.py",
        "docs/ops/TOOLS_REGISTRY.md",
        "scripts/INDEX.md",
    ]
    non_behavior_paths = [
        "docs/reports/some-observation.md",
        "var/tmp.json",
        "README.md",
        "scripts/ollama_pull_and_benchmark.py",
    ]
    for path in behavior_paths:
        assert_true(is_behavior_rule_path(path), f"expected behavior path: {path}")
    for path in non_behavior_paths:
        assert_false(is_behavior_rule_path(path), f"expected non-behavior path: {path}")
    print("openclaw_behavior_rule_gate_tests_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

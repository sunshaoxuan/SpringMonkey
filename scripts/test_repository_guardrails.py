from pathlib import Path


REPO = Path(__file__).resolve().parents[1]


def require_text(path: str, snippets: list[str]) -> None:
    text = (REPO / path).read_text(encoding="utf-8")
    missing = [snippet for snippet in snippets if snippet not in text]
    if missing:
        raise AssertionError(f"{path} missing required guardrail text: {missing}")


def main() -> int:
    require_text(
        "docs/policies/REPOSITORY_GUARDRAILS.md",
        [
            "Strong OpenClaw behavior-rule rule",
            "must be transmitted through Git",
            "Hand-uploading such rules or patch sources to the host is not",
            "python scripts/openclaw_behavior_rule_gate.py --verify-remote-pull",
        ],
    )
    require_text(
        "docs/policies/INTENT_TOOL_ROUTING_AND_ACCUMULATION.md",
        [
            "所有会约束或提示 OpenClaw 行为的规则",
            "必须通过 Git 传递",
            "不允许把这类规则只手工上传到宿主机后当作已部署能力",
        ],
    )
    require_text(
        "scripts/INDEX.md",
        [
            "强规则：所有会约束或提示 OpenClaw 行为的规则",
            "必须先进入 Git",
            "不允许把手工上传到宿主机当作 durable 部署",
            "openclaw_behavior_rule_gate.py",
        ],
    )
    print("repository_guardrails_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

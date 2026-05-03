from verify_intent_tool_registry import main


def test_registry_valid() -> None:
    assert main() == 0


if __name__ == "__main__":
    raise SystemExit(main())

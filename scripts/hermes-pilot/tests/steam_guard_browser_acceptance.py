"""Verify Steam Guard's field selection and native vault prompt in isolated Chromium."""
import json
import sys
from pathlib import Path
from unittest.mock import patch

from playwright.sync_api import sync_playwright

sys.path.insert(0, "/opt/hermes")
sys.path.extend(str(p) for p in Path("/opt/hermes/.venv/lib").glob("python*/site-packages"))
from agent.vault_backends import unlock
from agent.vault_login_classifier import LoginControl, build_inspection_js, classify_otp_controls
from tools import browser_vault_tool as vault

STEAM = "https://partner.steamgames.com"
REPORT = "https://partner.steampowered.com"
FAKE_CODE = "Q8M2K"


def document(count, heading="Enter the code sent to your email", extra=""):
    boxes = '<input type="text" maxlength="1">' * count
    return f"<input><main><div><h1>{heading}</h1><section><div>{boxes}{extra}</div></section></div></main>"


def main():
    with sync_playwright() as playwright:
        chromium = playwright.chromium.launch(executable_path="/usr/bin/chromium", args=["--no-sandbox"])
        page = chromium.new_page()

        def load(origin, html):
            page.unroute_all()
            page.route("**/*", lambda route: route.fulfill(status=200, content_type="text/html", body=html))
            page.goto(origin + "/")

        for origin, html in [
            ("https://example.net", document(5)),
            (STEAM, document(4)),
            (STEAM, document(5, heading="Your account")),
            (STEAM, document(5, extra="<input>")),
        ]:
            load(origin, html)
            controls = json.loads(page.evaluate(build_inspection_js("negative")))
            assert not classify_otp_controls([LoginControl.from_dict(item) for item in controls])

        load("https://example.net", '<input autocomplete="one-time-code">')
        controls = json.loads(page.evaluate(build_inspection_js("standard")))
        assert len(classify_otp_controls([LoginControl.from_dict(item) for item in controls])) == 1

        def evaluate(task_id, expression):
            return {"success": True, "result": page.evaluate(expression)}

        def invoke(user_input, navigation=False, origin=STEAM):
            load(origin, document(5))
            requested = []

            def prompt(site, hint):
                requested.append(site)
                if navigation:
                    load("https://example.net", document(5))
                return user_input

            with (
                patch.object(vault, "_focus_bound_origin", return_value=None),
                patch.object(vault, "_current_page_origin", return_value=origin),
                patch.object(vault, "_eval_js", evaluate),
                patch.object(vault, "_eval_js_secret", evaluate),
                patch.object(unlock, "can_prompt_here", return_value=True),
                patch.object(unlock, "get_code_prompt_callback", return_value=prompt),
            ):
                result = json.loads(vault.browser_vault_enter_code())
            assert requested == [origin.split("://")[1]]
            assert FAKE_CODE not in json.dumps(result)
            return result, page.locator("input").evaluate_all("(inputs) => inputs.map(x => x.value)")

        for origin in (STEAM, REPORT):
            result, values = invoke(FAKE_CODE, origin=origin)
            assert result["success"] and result["filled_fields"] == 5 and values == ["", *FAKE_CODE]
        result, values = invoke("TOOLONG")
        assert result["success"] is False and not any(values)
        result, values = invoke(FAKE_CODE, navigation=True)
        assert result["error_type"] == "origin_changed" and not any(values)
        chromium.close()
    print("PASS: native private-prompt callback, 5-field fill, malformed code, origin change, 5 classifier controls")


if __name__ == "__main__":
    main()

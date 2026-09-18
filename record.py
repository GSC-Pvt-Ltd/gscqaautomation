"""Record mode — drive Odoo by hand, get Python out.

Signs in first, then opens Playwright's recorder attached to an already
logged-in browser, so you start inside Odoo rather than at the login page.
Everything you click is written to /reports/recordings/<id>.py as you go.

What comes out is a DRAFT, not a test. It records what you did, not what
should be true. See docs/rewrite-prompt.md for turning it into a real test.
"""
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

REPORT_DIR = Path(os.environ.get("REPORT_DIR", "/reports"))
OUT_DIR = REPORT_DIR / "recordings"
STATE = Path("/tmp/qa-record-state.json")


def cfg(key, required=True):
    val = os.environ.get(key)
    if required and not val:
        raise RuntimeError(f"Missing required environment variable: {key}")
    return val


def sign_in(url, user, password):
    """Log in headlessly and keep the session, so recording starts inside Odoo."""
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(base_url=url, ignore_https_errors=True)
        page = ctx.new_page()
        page.goto("/web/login")
        form = page.locator("form:has(input[name='login'])")
        form.locator("input[name='login']").fill(user)
        form.locator("input[name='password']").fill(password)
        form.locator("button[type='submit']").click()
        try:
            page.wait_for_selector(".o_main_navbar", timeout=30000)
        except Exception:
            raise RuntimeError(
                "could not sign in — check ODOO_USER / ODOO_PASSWORD / ODOO_DB")
        ctx.storage_state(path=str(STATE))
        ctx.close()
        browser.close()


def main():
    url = cfg("ODOO_URL").rstrip("/")
    user = cfg("ODOO_USER")
    password = cfg("ODOO_PASSWORD")
    env_name = os.environ.get("QA_ENV_NAME", "sit")
    host = os.environ.get("QA_PUBLIC_HOST", "localhost")
    note = os.environ.get("QA_RECORD_NOTE", "")

    if os.environ.get("QA_READ_ONLY", "true").lower() == "true":
        print("!! QA_READ_ONLY is true on this target.")
        print("!! Recording a flow that creates data will not be reproducible here.")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rec_id = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
    draft = OUT_DIR / f"{rec_id}.py"

    print(">> signing in so the recorder starts inside Odoo")
    sign_in(url, user, password)

    print("")
    print("================================================================")
    print("  RECORDING — open this now:")
    print(f"  http://{host}:6080/vnc.html")
    print("")
    print("  Two windows appear: Odoo, and the Playwright Inspector.")
    print("  Click through your flow in Odoo. Use the Inspector's assert")
    print("  buttons where a value matters. Close the browser to finish.")
    print("")
    print(f"  Draft will be saved to  recordings/{rec_id}.py")
    print("================================================================")
    print("")

    cmd = [
        sys.executable, "-m", "playwright", "codegen",
        "--target", "python-pytest",
        "--load-storage", str(STATE),
        "--viewport-size", "1440,900",
        "-o", str(draft),
        f"{url}/odoo",
    ]
    result = subprocess.run(cmd)

    meta = {
        "id": rec_id,
        "env": env_name,
        "target": url,
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "recorded_by": os.environ.get("QA_RECORDED_BY", "unknown"),
        "note": note,
        "draft": f"recordings/{rec_id}.py",
        "status": "draft",          # draft -> rewritten -> committed
        "exit_code": result.returncode,
    }
    (OUT_DIR / f"{rec_id}.json").write_text(json.dumps(meta, indent=2))

    if draft.exists():
        print("")
        print(f">> draft saved: {draft}")
        print(">> it is a recording, not a test — rewrite it before committing.")
        print(">> rules: docs/rewrite-prompt.md")
    else:
        print("!! no draft written — the recorder was closed before anything was recorded")

    return 0


if __name__ == "__main__":
    sys.exit(main())

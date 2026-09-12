import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

from odoo_rpc import OdooRPC
from reporting import write_report

REPORT_DIR = Path(os.environ.get("REPORT_DIR", "/reports"))
ENV_NAME = os.environ.get("QA_ENV_NAME", "unknown")

# Every run writes into its own folder so history is never overwritten.
# entrypoint.sh exports QA_RUN_ID so the shell and python agree on the name.
RUN_ID = os.environ.get("QA_RUN_ID") or datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
RUN_DIR = REPORT_DIR / ENV_NAME / "runs" / RUN_ID

# When to keep the screen recording of a test:
#   always    every test, passing or not  (useful while learning the tool)
#   failures  only when a test fails      (the default once you trust it)
#   never     no recording at all
KEEP_VIDEO = os.environ.get("QA_KEEP_VIDEO", "failures").strip().lower()

# Watching the run live:
#   QA_HEADLESS=false   drive a real visible browser (needs a display — see
#                       the VNC stack in the panel; DISPLAY must be set)
#   QA_SLOWMO=500       pause 500ms between actions so a human can follow
HEADLESS = os.environ.get("QA_HEADLESS", "true").strip().lower() != "false"
SLOWMO = float(os.environ.get("QA_SLOWMO", "0") or 0)


def env(key, default=None, required=False):
    val = os.environ.get(key, default)
    if required and not val:
        raise RuntimeError(f"Missing required environment variable: {key}")
    return val


# --------------------------------------------------------------------------
# configuration
# --------------------------------------------------------------------------

@pytest.fixture(scope="session")
def config():
    return {
        "name": env("QA_ENV_NAME", "unknown"),
        "url": env("ODOO_URL", required=True).rstrip("/"),
        "db": env("ODOO_DB", required=True),
        "user": env("ODOO_USER", required=True),
        "password": env("ODOO_PASSWORD", required=True),
        "read_only": env("QA_READ_ONLY", "true").lower() == "true",
    }


@pytest.fixture(scope="session", autouse=True)
def announce(config):
    print(f"\n>> target: {config['name']}  {config['url']}  db={config['db']}  "
          f"read_only={config['read_only']}\n")


def pytest_collection_modifyitems(config, items):
    """Refuse to run data-mutating tests against a read-only environment."""
    if os.environ.get("QA_READ_ONLY", "true").lower() != "true":
        return
    skip = pytest.mark.skip(reason="QA_READ_ONLY=true - writes forbidden here")
    for item in items:
        if "write" in item.keywords:
            item.add_marker(skip)


# --------------------------------------------------------------------------
# odoo
# --------------------------------------------------------------------------

@pytest.fixture(scope="session")
def run_tag():
    """Prefix for every record a test creates, so stray data is identifiable.

    Deliberately the same id as the report folder: a leftover record in Odoo
    names the run that created it.
    """
    return f"QA-{RUN_ID}"


@pytest.fixture(scope="session")
def rpc(config):
    client = OdooRPC(config["url"], config["db"], config["user"], config["password"])
    client.authenticate()
    return client


@pytest.fixture(scope="session")
def browser():
    with sync_playwright() as pw:
        b = pw.chromium.launch(
            headless=HEADLESS,
            slow_mo=SLOWMO,
            args=["--start-maximized"] if not HEADLESS else [],
        )
        if not HEADLESS:
            print(f">> headed mode on DISPLAY={os.environ.get('DISPLAY', '(unset)')}, "
                  f"slow_mo={SLOWMO}ms")
        yield b
        b.close()


@pytest.fixture(scope="session")
def auth_state(browser, config, tmp_path_factory):
    """Log in once for the whole session; every test reuses the cookie."""
    path = tmp_path_factory.mktemp("auth") / "state.json"
    ctx = browser.new_context(base_url=config["url"], ignore_https_errors=True)
    page = ctx.new_page()
    page.goto("/web/login")

    # Scope to the form holding the login field. The website module adds a
    # header with its own submit button, so a bare button[type=submit] is
    # ambiguous and matches the wrong one.
    form = page.locator("form:has(input[name='login'])")
    form.locator("input[name='login']").fill(config["user"])
    form.locator("input[name='password']").fill(config["password"])
    form.locator("button[type='submit']").click()

    try:
        page.wait_for_selector(".o_main_navbar", timeout=30000)
    except Exception:
        alert = page.locator(".alert-danger")
        detail = alert.first.inner_text().strip() if alert.count() else f"still at {page.url}"
        raise RuntimeError(f"login did not reach the backend: {detail}")

    ctx.storage_state(path=str(path))
    ctx.close()
    return str(path)


def _slug(nodeid):
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", nodeid).strip("_")[:120]


@pytest.fixture
def page(request, browser, config, auth_state):
    """A logged-in page. On failure it leaves a screenshot, video and trace."""
    slug = _slug(request.node.nodeid)
    artifacts = RUN_DIR / "artifacts"
    video_tmp = artifacts / "_video_tmp" / slug

    ctx = browser.new_context(
        base_url=config["url"],
        storage_state=auth_state,
        ignore_https_errors=True,
        viewport={"width": 1440, "height": 900},
        record_video_dir=None if KEEP_VIDEO == "never" else str(video_tmp),
    )
    ctx.tracing.start(screenshots=True, snapshots=True, sources=True)

    pg = ctx.new_page()
    pg.set_default_timeout(15000)
    video = pg.video          # grab the handle while the page still exists
    yield pg

    report = getattr(request.node, "rep_call", None) or getattr(request.node, "rep_setup", None)
    failed = bool(report and report.failed)
    evidence = []

    if failed:
        artifacts.mkdir(parents=True, exist_ok=True)
        shot = artifacts / f"{slug}.png"
        try:
            pg.screenshot(path=str(shot), full_page=True)
            evidence.append(shot.name)
        except Exception:
            pass
        trace = artifacts / f"{slug}.trace.zip"
        ctx.tracing.stop(path=str(trace))
        evidence.append(trace.name)
    else:
        ctx.tracing.stop()

    ctx.close()               # the video is finalised during close

    # video.save_as() blocks until the file is actually written, which
    # ctx.close() alone does not guarantee. video.delete() then removes the
    # original, so passing tests leave nothing behind.
    keep_video = KEEP_VIDEO == "always" or (failed and KEEP_VIDEO != "never")
    if video is not None:
        try:
            if keep_video:
                artifacts.mkdir(parents=True, exist_ok=True)
                dest = artifacts / f"{slug}.webm"
                video.save_as(str(dest))
                evidence.append(dest.name)
            video.delete()
        except Exception:
            pass

    try:
        video_tmp.rmdir()
        video_tmp.parent.rmdir()      # removes _video_tmp once it is empty
    except OSError:
        pass                          # not empty, or already gone

    request.node._qa_evidence = ", ".join(evidence)


# --------------------------------------------------------------------------
# result collection -> results.json + report.xlsx
# --------------------------------------------------------------------------

@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    setattr(item, f"rep_{rep.when}", rep)


def _marker_arg(item, name, default=""):
    m = item.get_closest_marker(name)
    return m.args[0] if m and m.args else default


def _title(item):
    doc = (item.function.__doc__ or "").strip().splitlines()
    if doc:
        return doc[0].strip()
    return item.name.replace("test_", "").replace("_", " ").capitalize()


def pytest_sessionstart(session):
    session._qa_started = time.time()
    session._qa_results = []


def _collect(item, results):
    setup = getattr(item, "rep_setup", None)
    call = getattr(item, "rep_call", None)

    if setup is not None and setup.skipped:
        reason = ""
        if isinstance(setup.longrepr, tuple) and len(setup.longrepr) == 3:
            reason = str(setup.longrepr[2]).replace("Skipped: ", "")
        status, duration, error = "SKIP", 0.0, reason[:300]
    elif setup is not None and setup.failed:
        status = "ERROR"
        duration = setup.duration
        error = (setup.longreprtext or "").strip().splitlines()[-1][:300] if setup.longreprtext else ""
    elif call is None:
        return
    elif call.passed:
        status, duration, error = "PASS", call.duration, ""
    elif call.skipped:
        status, duration, error = "SKIP", call.duration, ""
    else:
        status = "FAIL"
        duration = call.duration
        lines = [l for l in (call.longreprtext or "").strip().splitlines() if l.strip()]
        error = next((l.strip() for l in lines if l.strip().startswith("E ")), lines[-1] if lines else "")[:300]

    suites = [m for m in ("smoke", "regression") if item.get_closest_marker(m)]
    results.append({
        "case_id": _marker_arg(item, "case", item.name),
        "suite": ",".join(suites) or "unmarked",
        "module": Path(str(item.fspath)).stem,
        "title": _title(item),
        "priority": _marker_arg(item, "priority", "P2"),
        "status": status,
        "duration": duration,
        "error": error.replace("E   ", "").strip(),
        "evidence": getattr(item, "_qa_evidence", ""),
        "jira": "",
    })


def pytest_sessionfinish(session, exitstatus):
    results = []
    for item in getattr(session, "items", []):
        _collect(item, results)

    started = getattr(session, "_qa_started", time.time())
    finished = time.time()
    meta = {
        "run_id": RUN_ID,
        "env": ENV_NAME,
        "url": os.environ.get("ODOO_URL", ""),
        "db": os.environ.get("ODOO_DB", ""),
        "build": os.environ.get("QA_BUILD", datetime.now(timezone.utc).strftime("%Y.%m.%d-%H%M")),
        "started": datetime.fromtimestamp(started, timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "finished": datetime.fromtimestamp(finished, timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "duration": finished - started,
        "exit_status": exitstatus,
    }

    name = f"report-{ENV_NAME}-{RUN_ID}.xlsx"
    try:
        RUN_DIR.mkdir(parents=True, exist_ok=True)
        (RUN_DIR / "results.json").write_text(
            json.dumps({"meta": meta, "results": results}, indent=2))
        write_report(results, meta, str(RUN_DIR / name))
        print(f"\n>> report written to {RUN_DIR}/{name}")
    except Exception as exc:          # never fail a run because reporting broke
        print(f"\n!! could not write report: {exc}")

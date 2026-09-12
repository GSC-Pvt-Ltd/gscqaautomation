import os
import pytest
from playwright.sync_api import sync_playwright

from odoo_rpc import OdooRPC


def env(key, default=None, required=False):
    val = os.environ.get(key, default)
    if required and not val:
        raise RuntimeError(f"Missing required environment variable: {key}")
    return val


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


@pytest.fixture(scope="session")
def rpc(config):
    client = OdooRPC(config["url"], config["db"], config["user"], config["password"])
    client.authenticate()
    return client


@pytest.fixture(scope="session")
def browser():
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        yield b
        b.close()


@pytest.fixture(scope="session")
def auth_state(browser, config, tmp_path_factory):
    """Log in once for the whole session; every test reuses the cookie."""
    path = tmp_path_factory.mktemp("auth") / "state.json"
    ctx = browser.new_context(base_url=config["url"], ignore_https_errors=True)
    page = ctx.new_page()
    page.goto("/web/login")
    page.fill("input[name='login']", config["user"])
    page.fill("input[name='password']", config["password"])
    page.click("button[type='submit']")
    page.wait_for_url("**/odoo**", timeout=30000)
    ctx.storage_state(path=str(path))
    ctx.close()
    return str(path)


@pytest.fixture
def page(browser, config, auth_state):
    ctx = browser.new_context(base_url=config["url"], storage_state=auth_state,
                              ignore_https_errors=True,
                              viewport={"width": 1440, "height": 900})
    pg = ctx.new_page()
    pg.set_default_timeout(15000)
    yield pg
    ctx.close()

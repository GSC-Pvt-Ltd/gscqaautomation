"""Phase 0 and the start of Phase 1. Keep these boring and always green."""
import pytest

pytestmark = pytest.mark.smoke


def test_rpc_reachable(rpc):
    """Proves the network path and the credentials before any browser starts."""
    assert rpc.uid, "authentication returned no uid"


def test_odoo_version(rpc):
    info = rpc.version()
    assert info["server_version"].startswith("19"), info["server_version"]


def test_login_lands_on_backend(page):
    page.goto("/odoo")
    assert "/web/login" not in page.url, "session was not carried over"


def test_partners_list_loads(page):
    page.goto("/odoo/contacts")
    page.wait_for_selector(".o_list_view, .o_kanban_view")
    assert page.locator(".o_breadcrumb, .o_last_breadcrumb_item").count() > 0

"""Small helpers shared by tests."""
import time


def wait_for_record(rpc, model, domain, fields=None, timeout=15, interval=0.5):
    """Poll Odoo over RPC until a record matching `domain` exists.

    Waiting on the database rather than on a DOM element is deliberate: the
    saved state is what the test actually cares about, and Odoo's save
    indicator markup changes between versions.
    """
    deadline = time.time() + timeout
    last = []
    while time.time() < deadline:
        last = rpc.search_read(model, domain, fields or ["id"])
        if last:
            return last
        time.sleep(interval)
    return last


def fill_field(form, name, value):
    """Fill an Odoo form field by its field name, whatever widget it uses."""
    field = form.locator(f"div[name='{name}'], td[name='{name}']").first
    box = field.locator("input, textarea").first
    box.click()
    box.fill(str(value))
    return box


def select_dropdown(page, form, name, value):
    """Type into a many2one and pick the first matching suggestion."""
    box = fill_field(form, name, value)
    page.wait_for_selector(".o-autocomplete--dropdown-menu", timeout=10000)
    page.locator(".o-autocomplete--dropdown-item").first.click()
    return box

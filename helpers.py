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


def odoo_message(page):
    """Return any visible Odoo notification or validation text, or ''.

    A failed save in Odoo is usually announced in a toast or an inline
    invalid-field marker. Without this, a test that does not save reports
    "no record found" — the symptom — instead of what Odoo actually said.
    """
    parts = []
    for sel in (".o_notification_content", ".o_notification .o_notification_body",
                ".alert-danger", ".o_form_status_indicator_buttons",
                ".o_field_invalid", ".o_error_dialog .modal-body"):
        loc = page.locator(sel)
        try:
            for i in range(min(loc.count(), 3)):
                text = loc.nth(i).inner_text().strip()
                if text:
                    parts.append(text.replace("\n", " ")[:200])
        except Exception:
            continue
    # which fields Odoo marked invalid, if any
    try:
        invalid = page.locator("[name].o_field_invalid, .o_field_invalid[name]")
        names = [invalid.nth(i).get_attribute("name") for i in range(min(invalid.count(), 5))]
        names = [n for n in names if n]
        if names:
            parts.append("invalid fields: " + ", ".join(names))
    except Exception:
        pass
    return " | ".join(dict.fromkeys(parts))

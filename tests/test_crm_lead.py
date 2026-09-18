"""CRM lead creation — the first test that writes data.

Marked `write`, so it is skipped automatically whenever QA_READ_ONLY=true.
That is what keeps it from ever running against production.
"""
import pytest

from helpers import fill_field, odoo_message, wait_for_record

pytestmark = [pytest.mark.smoke, pytest.mark.write]

MODEL = "crm.lead"


@pytest.fixture
def crm_installed(rpc):
    """Skip cleanly instead of failing if the CRM app is not installed."""
    try:
        rpc.search_read(MODEL, [], ["id"], limit=1)
    except Exception:
        pytest.skip("CRM app is not installed on this database")


@pytest.fixture
def lead_cleanup(rpc):
    """Every test removes the records it created, pass or fail."""
    created = []
    yield created
    if created:
        try:
            rpc.unlink(MODEL, created)
        except Exception as exc:
            print(f"!! could not clean up {MODEL} {created}: {exc}")


@pytest.mark.case("TC-0010")
@pytest.mark.priority("P1")
def test_create_lead_through_the_form(page, rpc, run_tag, crm_installed, lead_cleanup):
    """Creating a lead in the CRM form saves it with the values entered."""
    name = f"{run_tag} Automation lead"
    revenue = 25000

    page.goto("/odoo/crm/new")
    form = page.locator(".o_form_view")
    form.wait_for(timeout=20000)

    fill_field(form, "name", name)
    fill_field(form, "expected_revenue", revenue)
    fill_field(form, "email_from", "qa.lead@example.com")

    page.locator(".o_form_button_save").click()

    # Assert against the database, not the save indicator. The record either
    # exists with the right values or the feature is broken.
    rows = wait_for_record(
        rpc, MODEL, [("name", "=", name)],
        fields=["id", "name", "expected_revenue", "email_from", "type"],
    )
    if not rows:
        # say what Odoo said, not just that nothing turned up
        said = odoo_message(page)
        near = rpc.search_read(MODEL, [("name", "like", run_tag)], ["id", "name"], limit=5)
        raise AssertionError(
            f"no {MODEL} named {name!r} was saved.\n"
            f"  odoo said: {said or '(nothing visible)'}\n"
            f"  url now:   {page.url}\n"
            f"  leads with this run tag: {near or 'none'}"
        )
    lead_cleanup.extend(r["id"] for r in rows)

    assert len(rows) == 1, f"expected one lead, found {len(rows)}"
    lead = rows[0]
    assert lead["expected_revenue"] == float(revenue), lead["expected_revenue"]
    assert lead["email_from"] == "qa.lead@example.com", lead["email_from"]


@pytest.mark.case("TC-0011")
@pytest.mark.priority("P2")
def test_new_lead_appears_in_the_pipeline(page, rpc, run_tag, crm_installed, lead_cleanup):
    """A lead created over the API shows up on the CRM pipeline screen."""
    name = f"{run_tag} Pipeline lead"
    lead_id = rpc.create(MODEL, {"name": name, "type": "opportunity"})
    lead_cleanup.append(lead_id)

    page.goto("/odoo/crm")
    page.wait_for_selector(".o_kanban_view, .o_list_view", timeout=20000)

    search = page.locator(".o_searchview_input")
    search.fill(name)
    search.press("Enter")

    page.wait_for_selector(f"text={name}", timeout=15000)
    assert page.locator(f"text={name}").count() >= 1

# gscqaautomation

Playwright + pytest regression suite for Odoo 19, run as a standalone Docker
container deployed from the VPS panel. The container clones this repo on start,
runs the suite against the target Odoo, writes reports, and exits.

## Files

| | |
|---|---|
| `conftest.py` | fixtures (config, rpc, browser, logged-in page) + result collection |
| `odoo_rpc.py` | XML-RPC client — all data setup goes through this, never browser clicks |
| `reporting.py` | writes the two-sheet Excel report from collected results |
| `pytest.ini` | markers and defaults |
| `tests/` | the suite |

## Configuration

All from environment variables set in the VPS panel — nothing secret lives here.

| Variable | SIT | Production |
|---|---|---|
| `QA_ENV_NAME` | `sit` | `prod` |
| `ODOO_URL` | `http://odoo19:8069` | prod container name, port 8069 |
| `ODOO_DB` | `gscodoodev` | prod database |
| `ODOO_USER` | `qa_automation` | `qa_readonly` |
| `ODOO_PASSWORD` | set in panel | set in panel |
| `QA_READ_ONLY` | `false` | `true` |
| `QA_BUILD` | optional build tag | optional build tag |
| `REPORT_DIR` | `/reports` | `/reports` |

`QA_READ_ONLY=true` makes `conftest.py` skip every test marked
`@pytest.mark.write`, so production never gets a test that changes data.

## Output

Written to `$REPORT_DIR/$QA_ENV_NAME/`:

- `report-<env>.xlsx` — Summary sheet and Detail sheet
- `results.json` — the same data, for the Jira push later
- `artifacts/` — screenshot, video and Playwright trace, **failures only**

Open a `.trace.zip` at https://trace.playwright.dev — it replays the run frame by
frame with the DOM at each step. That is how you "watch" a headless test.

## Writing a test

```python
@pytest.mark.smoke
@pytest.mark.case("TC-0007")
@pytest.mark.priority("P1")
def test_invoice_posts(page, rpc):
    """Posting a customer invoice creates the journal entry."""
    ...
```

The docstring becomes the report title, so write it for whoever reads the
spreadsheet, not for the developer.

## Rules

- No `time.sleep`. Wait for a condition — a toast, a row count, a URL.
- No shared state. Each test sets up and tears down its own data.
- Seed over RPC, assert through the browser.
- Anchor selectors on Odoo's `[name='field_id']` or a `data-qa` hook the dev team
  adds. Never CSS paths through generated DOM — `/web/login` already proved why.

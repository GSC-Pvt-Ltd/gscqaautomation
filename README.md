# gscqaautomation

Playwright + pytest regression suite for Odoo 19, run as a standalone Docker
container deployed from the VPS panel. The container clones this repo on start,
runs the suite against the target Odoo, and exits.

Configuration comes entirely from environment variables set in the panel:

| Variable | SIT | Production |
|---|---|---|
| `QA_ENV_NAME` | `sit` | `prod` |
| `ODOO_URL` | `http://odoo19:8069` | prod container name, port 8069 |
| `ODOO_DB` | `gscodoodev` | prod database |
| `ODOO_USER` | `qa_automation` | `qa_readonly` |
| `ODOO_PASSWORD` | set in panel | set in panel |
| `QA_READ_ONLY` | `false` | `true` |

`QA_READ_ONLY=true` makes conftest.py skip every test marked
`@pytest.mark.write`, so production never gets a test that changes data.

Data setup belongs in `odoo_rpc.py`, not in browser clicks. A test that clicks
through six screens to reach its starting state will break next release for
reasons that have nothing to do with what it tests.

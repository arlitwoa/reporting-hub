# Dev Done risk (GitHub Pages)

Static HTML snapshot for GitHub Pages at a **stable URL**:

- Path: `index.html`
- URL: https://arlitwoa.github.io/reporting-hub/dev-done-risk/

The report always reflects the **in-cycle engine** from `smart-engine-in-cycle` (active release). The fixVersion name appears in the report body, not the URL.

## Publish locally

```powershell
C:/development/artifact/.venv/Scripts/python.exe scripts/publish_delivery_health_pages.py --write
```

Dev Done only:

```powershell
C:/development/artifact/.venv/Scripts/python.exe scripts/publish_delivery_health_pages.py --write --dev-done-only
```

Then commit `docs/dev-done-risk/index.html`, push to `develop`.

## Confluence (DTRAIN)

Template page: **Current Engine | Dev Done Risk** under **Deliver → Lines | Deliver → In Cycle | Deliver**.

Create or reset the stub:

```powershell
C:/development/artifact/.venv/Scripts/python.exe scripts/create_delivery_health_confluence_pages.py --dev-done-only
```

Config: `config/delivery-health.json` → `confluence`.

## Automation

Same pipeline as the quarterly dashboard — see [sprint-health/README.md](../sprint-health/README.md#automation).

For a **named** engine (local review only, gitignored output):

```powershell
C:/development/artifact/.venv/Scripts/python.exe scripts/dev_done_risk.py --fixversion 20260611-engine
```

See [dev-done-risk how-to](../how-to/dev-done-risk.md).

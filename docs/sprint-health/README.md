# Sprint Health (GitHub Pages)

Static HTML snapshots for GitHub Pages. Each squad has a **stable URL** that is overwritten when data refreshes.

| Squad | Path | URL |
| --- | --- | --- |
| Landing | `index.html` | https://arlitwoa.github.io/reporting-hub/sprint-health/ |
| Kākāriki | `kakariki/index.html` | https://arlitwoa.github.io/reporting-hub/sprint-health/kakariki/ |
| Kikorangi | `kikorangi/index.html` | https://arlitwoa.github.io/reporting-hub/sprint-health/kikorangi/ |
| Waiporoporo | `waiporoporo/index.html` | https://arlitwoa.github.io/reporting-hub/sprint-health/waiporoporo/ |

Reports use each squad board's **active sprint** and the **in-cycle engine fixVersion** for impediment rules.

## Publish locally

```powershell
C:/development/artifact/.venv/Scripts/python.exe scripts/publish_delivery_health_pages.py --write
```

Sprint Health only:

```powershell
C:/development/artifact/.venv/Scripts/python.exe scripts/publish_delivery_health_pages.py --write --sprint-health-only
```

Then commit `docs/sprint-health/`, push to `develop`.

## Confluence (DTRAIN)

One-time template pages (placeholder until Confluence publish is wired):

```powershell
C:/development/artifact/.venv/Scripts/python.exe scripts/create_delivery_health_confluence_pages.py
```

| Page | Location |
| --- | --- |
| Sprint Health \| Deliver (hub) | Deliver → Reports \| Deliver |
| Current Sprint \| Kākāriki / Kikorangi / Waiporoporo | Under Sprint Health hub |
| Current Engine \| Dev Done Risk | Deliver → Lines \| Deliver → In Cycle \| Deliver |

Config: `config/delivery-health.json` → `confluence`.

## Automation

Workflow: `.github/workflows/github-pages-reports.yml` on **`main`** — hourly (UTC) with the quarterly dashboard, or **Actions → Refresh GitHub Pages reports → Run workflow**.

Local refresh (all GitHub Pages reports):

```bash
bash scripts/refresh_github_pages_reports.sh
```

Same repository secrets as the quarterly dashboard: `ARTIFACT_CREDENTIALS_JSON`, `ARTIFACT_USER_EMAIL`, `REPO_PAT`.

Enable Pages: **Settings → Pages → branch `develop` → folder `/docs`**.

See [execution-notes](../execution-notes.md#sprint-health-delivery-health) and [data-classification](../data-classification.md).

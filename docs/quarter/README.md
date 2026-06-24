# Quarterly dashboard (GitHub Pages)

Static HTML snapshot for GitHub Pages lives here as `index.html`.

Generate and publish:

```powershell
C:/development/artifact/.venv/Scripts/python.exe scripts/quarterly/quarter_dashboard.py --write
C:/development/artifact/.venv/Scripts/python.exe scripts/quarterly/publish_dashboard_pages.py --write
git add docs/quarter/index.html
git commit -m "Refresh quarterly dashboard snapshot."
git push
```

Or rebuild from artifacts in one step:

```powershell
C:/development/artifact/.venv/Scripts/python.exe scripts/quarterly/publish_dashboard_pages.py --write --build
```

Enable Pages: **Settings → Pages → branch `develop` → folder `/docs`**.

See [quarterly-reporting.md](../how-to/quarterly-reporting.md#github-pages-static-report) for hourly automation via `.github/workflows/github-pages-reports.yml` (quarterly + Sprint Health + Dev Done together).

## Visibility audit (June 2026)

Audit date: 2026-06-10. Auditor: improvement-plan Phase 4 (SMART-69).

| Setting | Value | Notes |
| --- | --- | --- |
| Repository visibility | **Private** (`barlconz/artifact-consumer-twoa`) | Source and credentials are not public |
| GitHub Pages source | Branch `develop`, folder `/docs` | Builds `docs/quarter/index.html` |
| Pages site URL | https://arlitwoa.github.io/reporting-hub/quarter/ | |
| Pages `public` flag | **true** | On private repos, the published site is **world-readable** without repo access |

**Classification:** Dashboard HTML contains aggregated EPCE delivery metrics (story points, lane totals, epic keys, fixVersion names). It does **not** include assignee names, comment text, or Salesforce data.

**Action:** Accept public delivery metrics under [data-classification.md](../data-classification.md), or change Pages visibility to private (GitHub Enterprise / org policy) if metrics must be login-gated. Review this table when repository or Pages settings change.

# SEF integrated project plan (GitHub Pages)

Static snapshot of the PDE Block hierarchy Gantt for **SEF | Integrated Project Plan**.

| Path | Description |
| --- | --- |
| [project-plan.html](./project-plan.html) | Block Level One chapter bars with Level Zero stream sub-rows and optional Level Minus One detail rows |

## Refresh locally

Requires `PDE` in `config/profiles/atlassian.json` and Artifact credentials.

```powershell
$env:PYTHONPATH = "C:\development\reporting-hub"
$env:ARTIFACT_PROFILES_DIR = "C:\development\reporting-hub\config\profiles"
$env:ARTIFACT_PROGRAMME_REGISTRY = "C:\development\reporting-hub\config\programme-registry.json"
$env:ARTIFACT_ROLE_REGISTRY = "C:\development\reporting-hub\config\role-registry.json"
$env:ARTIFACT_LOCAL_CREDENTIALS = "C:\development\artifact\config\credentials.local.json"

python scripts/sef/fetch_sef_project_plan_timeline.py --write
python scripts/sef/sef_project_plan_report.py --write
```

Hub keys and chart window: `config/sef-project-plan-reporting.json`. PDE keys: `config/sef-project-plan-blocks.json`.

Or run the full Pages pipeline:

```bash
bash scripts/refresh_github_pages_reports.sh
```

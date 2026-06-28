# reporting-hub

TWoA **reporting hub** for GitHub Pages: programme-scoped delivery snapshots (EPC, SEF, enterprise) refreshed from Jira.

Runs on **`barlconz-artifact-core`** (Artifact core wheel from [barlconz/artifact](https://github.com/barlconz/artifact) GitHub Releases) with the TWoA programme extension from this repo. Published HTML lives under `docs/` on **TWoA GitHub** (`arlitwoa`).

## Live site

After Pages is enabled: **https://arlitwoa.github.io/reporting-hub/**

| Area | Path | Reports |
|------|------|---------|
| Site hub | `/` | Links to programme areas below |
| EPC delivery | `/epc/` | Quarter dashboard, milestone scope, Sprint Health, Dev Done risk |
| SEF | `/sef/` | Integrated project plan Gantt |
| Enterprise reporting | `/enterprise/` | Placeholder for cross-programme reports |

Report URLs are unchanged for stability (e.g. `/quarter/`, `/sprint-health/`, `/sef/project-plan.html`). Programme hubs group navigation only.

## Setup (local refresh)

**Option A — editable core (development):**

```powershell
pip install -e C:\development\artifact
pip install -e C:\development\reporting-hub
```

**Option B — pinned wheel (matches CI):**

```powershell
$env:GH_TOKEN = "<PAT with repo read on barlconz/artifact>"
gh release download v0.2.1 --repo barlconz/artifact --pattern "barlconz_artifact_core-0.2.1-py3-none-any.whl" --dir $env:TEMP
pip install "$env:TEMP\barlconz_artifact_core-0.2.1-py3-none-any.whl"
pip install -e C:\development\reporting-hub
```

Environment (PowerShell):

```powershell
$env:PYTHONPATH = "C:\development\reporting-hub"
$env:ARTIFACT_PROFILES_DIR = "C:\development\reporting-hub\config\profiles"
$env:ARTIFACT_PROGRAMME_REGISTRY = "C:\development\reporting-hub\config\programme-registry.json"
$env:ARTIFACT_ROLE_REGISTRY = "C:\development\reporting-hub\config\role-registry.json"
$env:ARTIFACT_LOCAL_CREDENTIALS = "C:\development\artifact\config\credentials.local.json"
```

Copy profile templates before first run:

```powershell
Copy-Item config\profiles\atlassian.template.json config\profiles\atlassian.json
Copy-Item config\profiles\twoa-programme.template.json config\profiles\twoa-programme.json
```

Refresh all GitHub Pages snapshots:

```powershell
# Git Bash
bash scripts/refresh_github_pages_reports.sh

# Or run the Python steps from that script in PowerShell (see consumer docs/execution-notes.md)
```

Commit changed files under `docs/` when snapshots update.

## Push to GitHub (TWoA / arlitwoa)

Local `gh` may be logged in as a personal account (`barlconz`). Use a **TWoA org PAT** for programmatic push.

### 1. Create a fine-grained PAT

On the TWoA GitHub account that can access `arlitwoa/reporting-hub`:

1. [Fine-grained tokens](https://github.com/settings/tokens?type=beta) → **Generate new token**
2. **Resource owner:** `arlitwoa` (or your TWoA user if the org delegates)
3. **Repository access:** Only `reporting-hub`
4. **Permissions:** Contents → **Read and write**
5. Copy the token once (it is not shown again)

### 2. Push from this machine

```powershell
cd C:\development\reporting-hub

# One-time: save PAT to Windows user profile (prompts securely)
powershell -ExecutionPolicy Bypass -File .\scripts\setup_twoa_github_pat.ps1
# Restart Cursor after this

# Or one session only:
# $env:TWOA_GITHUB_PAT = "<paste token>"

powershell -ExecutionPolicy Bypass -File .\scripts\push_to_github.ps1
```

The script commits staged files if needed, pushes to `main`, and does **not** store the token in `.git/config` (only used for the push URL).

### 3. GitHub Actions secrets (on arlitwoa/reporting-hub)

| Secret | Purpose |
|--------|---------|
| `ARTIFACT_CREDENTIALS_JSON` | Atlassian credentials for Jira refresh |
| `ARTIFACT_CORE_PAT` | Read **repo** on `barlconz/artifact` (download release wheel) |
| `ARTIFACT_USER_EMAIL` | Optional attribution |

CI installs the **v0.2.1 release wheel** from `barlconz/artifact` — no git checkout.

## GitHub Actions

Workflow: `.github/workflows/github-pages-reports.yml` — hourly (UTC) or manual dispatch.

**Repository secrets**

| Secret | Purpose |
|--------|---------|
| `ARTIFACT_CREDENTIALS_JSON` | Full contents of `credentials.local.json` (Atlassian) |
| `ARTIFACT_CORE_PAT` | PAT with **repo read** on `barlconz/artifact` (download release wheel) |
| `ARTIFACT_USER_EMAIL` | Optional attribution for generated content |

Push from the workflow uses the built-in **`GITHUB_TOKEN`** on `arlitwoa/reporting-hub`.

**GitHub Pages:** Settings → Pages → deploy from branch **`main`** → folder **`/docs`**.

## Config

| File | Role |
|------|------|
| `config/github-pages-site.json` | Site hub structure — programmes (EPC, SEF, enterprise) and report links |
| `config/quarterly-reporting.json` | Three-lane quarter model, burn tracking, milestone scope |
| `config/delivery-health.json` | Sprint Health + Dev Done risk |
| `config/sef-project-plan-reporting.json` | SEF Block Gantt hub keys, chart window, artifact names |
| `config/sef-project-plan-blocks.json` | PDE issue keys for Phase 1 and Phase 2 Block hierarchy |
| `config/jira-binding.json` | D-Train status → phase map |
| `config/programme-registry.json` | Wires `extensions.twoa_programme` into Artifact core |

Update `githubPages.githubUser` / `repoName` in both reporting configs if the repo is renamed or moved.

## Sync from consumer

When reporting code changes in `artifact-consumer-twoa`, re-export:

```powershell
C:\development\artifact-consumer-twoa\scripts\export_reporting_hub.ps1
```

Then patch `githubUser` / `repoName` in `config/quarterly-reporting.json` and `config/delivery-health.json` if the export script overwrote them.

## Tests

```powershell
$env:ARTIFACT_PROGRAMME_REGISTRY = "C:\development\reporting-hub\config\programme-registry.json"
python -m unittest discover -s tests -v
```

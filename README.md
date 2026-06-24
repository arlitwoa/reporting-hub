# reporting-hub

TWoA EPCE **delivery report snapshots** for GitHub Pages: quarterly dashboard, milestone scope, Sprint Health, and Dev Done risk.

Runs on [Artifact core](https://github.com/arlitwoa/artifact) with the TWoA programme extension from this repo. Published HTML lives under `docs/` on **TWoA GitHub** (`arlitwoa`), not the personal `barlconz` org.

## Live site

After Pages is enabled: **https://arlitwoa.github.io/reporting-hub/**

| Report | Path |
|--------|------|
| Site hub | `/` |
| Current quarter dashboard | `/quarter/` |
| Milestone scope | `/quarter/milestone.html` |
| Sprint Health (per squad) | `/sprint-health/` |
| Dev Done risk (in-cycle engine) | `/dev-done-risk/` |

## Setup (local refresh)

Install **Artifact core first**, then this repo (same venv):

```powershell
pip install -e C:\development\artifact
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

# One session
$env:TWOA_GITHUB_PAT = "<paste token>"

# Or persist for your Windows user (optional)
# [Environment]::SetUserEnvironmentVariable("TWOA_GITHUB_PAT", "<token>", "User")

.\scripts\push_to_github.ps1
```

The script commits staged files if needed, pushes to `main`, and does **not** store the token in `.git/config` (only used for the push URL).

### 3. GitHub Actions secrets (on arlitwoa/reporting-hub)

| Secret | Purpose |
|--------|---------|
| `ARTIFACT_CREDENTIALS_JSON` | Atlassian credentials for Jira refresh |
| `ARTIFACT_CORE_PAT` | Read access to `arlitwoa/artifact` (CI checkout of Artifact core) |
| `ARTIFACT_USER_EMAIL` | Optional attribution |

Report snapshot commits use the workflow **`GITHUB_TOKEN`** (same repo) — no PAT needed for push inside Actions.

## GitHub Actions

Workflow: `.github/workflows/github-pages-reports.yml` — hourly (UTC) or manual dispatch.

**Repository secrets**

| Secret | Purpose |
|--------|---------|
| `ARTIFACT_CREDENTIALS_JSON` | Full contents of `credentials.local.json` (Atlassian) |
| `ARTIFACT_CORE_PAT` | PAT with **read** on `arlitwoa/artifact` (checkout core in CI) |
| `ARTIFACT_USER_EMAIL` | Optional attribution for generated content |

Push from the workflow uses the built-in **`GITHUB_TOKEN`** on `arlitwoa/reporting-hub` (no extra push PAT).

**GitHub Pages:** Settings → Pages → deploy from branch **`main`** → folder **`/docs`**.

## Config

| File | Role |
|------|------|
| `config/quarterly-reporting.json` | Three-lane quarter model, burn tracking, milestone scope |
| `config/delivery-health.json` | Sprint Health + Dev Done risk |
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

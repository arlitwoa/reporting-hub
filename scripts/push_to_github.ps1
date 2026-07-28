# Push reporting-hub to GitHub (arlitwoa) using a TWoA PAT.
# Token resolution order:
#   1. TWOA_GITHUB_PAT environment variable
#   2. config/credentials.local.json -> github.pat  (git-ignored, local only)
#
# Usage:
#   .\scripts\push_to_github.ps1
#   .\scripts\push_to_github.ps1 -CommitMessage "Initial reporting-hub slice"

param(
    [string]$CommitMessage = "Initial reporting-hub slice from artifact-consumer-twoa",
    [string]$Remote = "https://github.com/arlitwoa/reporting-hub.git",
    [string]$Branch = "main"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
Set-Location $Root

$token = $env:TWOA_GITHUB_PAT

if ([string]::IsNullOrWhiteSpace($token)) {
    $credsPath = Join-Path $Root "config\credentials.local.json"
    if (Test-Path $credsPath) {
        $creds = Get-Content $credsPath -Raw | ConvertFrom-Json
        $token = $creds.github.pat
    }
}

if ([string]::IsNullOrWhiteSpace($token)) {
    throw @"
No GitHub PAT found.

Set one via either:
  1. config/credentials.local.json -> github.pat  (preferred, git-ignored)
  2. `$env:TWOA_GITHUB_PAT = '<token>'

Create a fine-grained PAT (log in as arlitwoa):
  https://github.com/settings/tokens?type=beta
  Repository: arlitwoa/reporting-hub
  Permissions: Contents (Read and write)
"@
}

$authRemote = $Remote -replace "^https://", "https://x-access-token:${token}@"

if (-not (git remote get-url origin 2>$null)) {
    git remote add origin $Remote
} else {
    git remote set-url origin $Remote
}

$status = git status --porcelain
if ($status) {
    git add -A
    git commit -m $CommitMessage
} elseif (-not (git rev-parse HEAD 2>$null)) {
    throw "No commits and nothing staged. Run from a prepared reporting-hub tree."
}

Write-Host "Pushing $Branch to arlitwoa/reporting-hub ..."
git push $authRemote "HEAD:${Branch}"
git remote set-url origin $Remote
git fetch origin $Branch 2>$null
git branch --set-upstream-to=origin/$Branch $Branch 2>$null
Write-Host "Done."

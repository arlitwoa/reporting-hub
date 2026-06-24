# Push reporting-hub to GitHub (arlitwoa) using a TWoA PAT.
# Requires: TWOA_GITHUB_PAT user env var (run scripts/setup_twoa_github_pat.ps1 once)
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
    throw @"
TWOA_GITHUB_PAT is not set.

Create a fine-grained PAT on the TWoA GitHub account/org (arlitwoa):
  https://github.com/settings/tokens?type=beta
  Repository access: arlitwoa/reporting-hub
  Permissions: Contents (Read and write)

Then in PowerShell:
  `$env:TWOA_GITHUB_PAT = '<token>'
  .\scripts\push_to_github.ps1

To persist for your user profile (optional):
  [Environment]::SetEnvironmentVariable('TWOA_GITHUB_PAT', '<token>', 'User')
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
git push $authRemote "HEAD:${Branch}" -u
git remote set-url origin $Remote
Write-Host "Done."

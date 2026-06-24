# Save TWoA GitHub PAT as a Windows user environment variable (for arlitwoa pushes).
# Run once in PowerShell — token is prompted securely and never echoed.
#
#   powershell -ExecutionPolicy Bypass -File .\scripts\setup_twoa_github_pat.ps1
#
# Restart Cursor (or open a new terminal) so agent shells inherit TWOA_GITHUB_PAT.

$ErrorActionPreference = "Stop"

Write-Host "TWoA GitHub PAT setup for arlitwoa/reporting-hub"
Write-Host ""
Write-Host "Create a fine-grained token with:"
Write-Host "  - Repository: arlitwoa/reporting-hub"
Write-Host "  - Contents: Read and write"
Write-Host "  - Workflows: Read and write (only if pushing workflow files)"
Write-Host ""

$secure = Read-Host "Paste TWoA PAT (input hidden)" -AsSecureString
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try {
    $token = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
}

if ([string]::IsNullOrWhiteSpace($token)) {
    throw "No token entered."
}

[Environment]::SetEnvironmentVariable("TWOA_GITHUB_PAT", $token, [EnvironmentVariableTarget]::User)
$env:TWOA_GITHUB_PAT = $token

Write-Host ""
Write-Host "Saved TWOA_GITHUB_PAT for your Windows user profile."
Write-Host "Restart Cursor so agent terminals pick up the variable."
Write-Host ""
Write-Host "Then push from reporting-hub:"
Write-Host "  powershell -ExecutionPolicy Bypass -File .\scripts\push_to_github.ps1"

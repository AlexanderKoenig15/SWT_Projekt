[CmdletBinding()]
param(
    [switch]$Validate,
    [string]$CheckoutParent
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$docsDirectory = Join-Path $repoRoot ".local-preview/virtual-docs"
$assemblyStatusFile = Join-Path $repoRoot ".local-preview/content-assembly-status.json"
if ([string]::IsNullOrWhiteSpace($CheckoutParent)) {
    $CheckoutParent = Split-Path -Parent $repoRoot
}

# Local-only secrets. The .local-preview/ directory is gitignored; never commit it.
$localEnvironmentFile = Join-Path $repoRoot ".local-preview/env"
if (Test-Path -LiteralPath $localEnvironmentFile -PathType Leaf) {
    foreach ($line in Get-Content -LiteralPath $localEnvironmentFile) {
        if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$') {
            Set-Item -Path "Env:$($Matches[1])" -Value $Matches[2].Trim('"''')
        }
    }
}

if ($Validate) {
    $agentsRepository = Join-Path $CheckoutParent "Modul-Agents"
    $skillValidator = Join-Path $agentsRepository "scripts/validate_skills.py"
    if (-not (Test-Path -LiteralPath $skillValidator -PathType Leaf)) {
        Write-Error "Required Modul-Agents skill repository is not available at '$agentsRepository'. Run Workspace: Configure and repeat Docs: Validate (Strict)."
        exit 1
    }
    & uv run --locked python $skillValidator
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

Push-Location $repoRoot
try {
    & uv run --locked python scripts/content_assembly.py `
        --output $docsDirectory `
        --checkout-parent $CheckoutParent `
        --status-output $assemblyStatusFile
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }

    $env:LOCAL_PREVIEW_NOTICE = "This local preview may be incomplete. Categories and features from content repositories that are not checked out locally are omitted. Central CI validates the complete site."
    $env:MODUL_DASHBOARD_ASSEMBLY_STATUS_FILE = $assemblyStatusFile
    $env:MODUL_DASHBOARD_DOCS_DIR = $docsDirectory
    $env:PAGES_URL = "http://127.0.0.1:8000/AS-IO/Modul-Dashboard"
    if ($Validate) {
        & uv run --locked python scripts/validate.py
    }
    else {
        & uv run --locked mkdocs serve --config-file "$repoRoot/mkdocs.yml" --dev-addr 127.0.0.1:8000
    }
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
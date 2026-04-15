[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot

$requiredFiles = @(
    "README.md",
    "SECURITY.md",
    "LICENSE",
    "SKILL.md",
    ".codex-plugin\plugin.json",
    ".claude-plugin\plugin.json",
    ".claude-plugin\marketplace.json",
    "agents\openai.yaml",
    "references\prompt-templates.md",
    "references\windows-linux-ssh-playbook.md",
    "references\hpc-slurm-playbook.md",
    "scripts\sshops.ps1",
    "scripts\remote_run.ps1",
    "scripts\server_preflight.ps1",
    "scripts\configure_ssh_host.ps1",
    "scripts\bootstrap_ssh_key.py",
    "scripts\paramiko_copy_tree.py"
)

$missing = @()
foreach ($relativePath in $requiredFiles) {
    $fullPath = Join-Path $root $relativePath
    if (-not (Test-Path -LiteralPath $fullPath)) {
        $missing += $relativePath
    }
}

if ($missing.Count -gt 0) {
    throw ("Missing required files: " + ($missing -join ", "))
}

$psFiles = Get-ChildItem -Path (Join-Path $root "scripts") -Filter *.ps1 -File
$parseFailures = New-Object System.Collections.Generic.List[string]
foreach ($file in $psFiles) {
    $tokens = $null
    $errors = $null
    [void][System.Management.Automation.Language.Parser]::ParseFile($file.FullName, [ref]$tokens, [ref]$errors)
    if ($errors.Count -gt 0) {
        $parseFailures.Add("$($file.Name): $($errors[0].Message)")
    }
}

if ($parseFailures.Count -gt 0) {
    throw ("PowerShell parse failures: " + ($parseFailures -join " | "))
}

$jsonFiles = @(
    ".codex-plugin\plugin.json",
    ".claude-plugin\plugin.json",
    ".claude-plugin\marketplace.json"
)
foreach ($relativePath in $jsonFiles) {
    $fullPath = Join-Path $root $relativePath
    $null = Get-Content -Path $fullPath -Raw | ConvertFrom-Json
}

$python = Get-Command python -ErrorAction SilentlyContinue
$pythonChecks = @()
if ($python) {
    $pyFiles = Get-ChildItem -Path (Join-Path $root "scripts") -Filter *.py -File
    foreach ($file in $pyFiles) {
        & $python.Source -m py_compile $file.FullName
        if ($LASTEXITCODE -ne 0) {
            throw "Python syntax check failed for $($file.Name)"
        }
        $pythonChecks += $file.Name
    }
}

[ordered]@{
    root                     = $root
    required_file_count      = $requiredFiles.Count
    powershell_files_checked = $psFiles.Count
    json_files_checked       = $jsonFiles.Count
    python_files_checked     = $pythonChecks.Count
    python_tool_available    = [bool]$python
} | ConvertTo-Json -Depth 3

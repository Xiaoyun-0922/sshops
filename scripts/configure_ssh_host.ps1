[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Alias,

    [Parameter(Mandatory = $true)]
    [string]$HostName,

    [Parameter(Mandatory = $true)]
    [int]$Port,

    [Parameter(Mandatory = $true)]
    [string]$User,

    [string]$IdentityFile,

    [string]$PreferredAuthentications,

    [string]$ConfigPath = (Join-Path $HOME ".ssh\config")
)

$ErrorActionPreference = "Stop"

function Convert-ToSshPath {
    param([string]$PathValue)

    if (-not $PathValue) {
        return $null
    }

    $candidate = $PathValue
    if (Test-Path -LiteralPath $PathValue) {
        $candidate = (Resolve-Path -LiteralPath $PathValue).Path
    }

    return ($candidate -replace "\\", "/")
}

function Split-SshConfig {
    param([string]$Text)

    $segments = @()
    if (-not $Text) {
        return $segments
    }

    $lines = $Text -split "`n", -1
    $currentLines = New-Object System.Collections.Generic.List[string]
    $currentIsHost = $false

    foreach ($line in $lines) {
        if ($line -match "^\s*Host\s+") {
            if ($currentLines.Count -gt 0) {
                $segments += [pscustomobject]@{
                    IsHost = $currentIsHost
                    Lines  = @($currentLines)
                }
                $currentLines = New-Object System.Collections.Generic.List[string]
            }
            $currentIsHost = $true
        }
        elseif ($currentLines.Count -eq 0) {
            $currentIsHost = $false
        }

        $currentLines.Add($line)
    }

    if ($currentLines.Count -gt 0) {
        $segments += [pscustomobject]@{
            IsHost = $currentIsHost
            Lines  = @($currentLines)
        }
    }

    return $segments
}

function Get-HostDeclaration {
    param([string[]]$Lines)

    foreach ($line in $Lines) {
        if ($line -match "^\s*Host\s+(.+?)\s*$") {
            return $Matches[1].Trim()
        }
    }

    return $null
}

function Set-OpenSshAcl {
    param([string]$Path)

    if ($env:OS -ne "Windows_NT") {
        return
    }

    $currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    $null = & icacls $Path /inheritance:r /grant:r "${currentUser}:(F)" "SYSTEM:(F)" "Administrators:(F)"
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to set OpenSSH ACLs on $Path"
    }
}

$configDir = Split-Path -Parent $ConfigPath
if (-not (Test-Path -LiteralPath $configDir)) {
    New-Item -ItemType Directory -Path $configDir -Force | Out-Null
}

$rawConfig = ""
if (Test-Path -LiteralPath $ConfigPath) {
    $rawConfig = [System.IO.File]::ReadAllText($ConfigPath)
    $rawConfig = $rawConfig -replace "`r`n", "`n"
}

$segments = Split-SshConfig -Text $rawConfig
$managedBlock = @(
    "Host $Alias",
    "  HostName $HostName",
    "  Port $Port",
    "  User $User"
)

$normalizedIdentity = Convert-ToSshPath -PathValue $IdentityFile
if ($normalizedIdentity) {
    if ($normalizedIdentity -match "\s") {
        $normalizedIdentity = '"' + $normalizedIdentity + '"'
    }
    $managedBlock += "  IdentityFile $normalizedIdentity"
    $managedBlock += "  IdentitiesOnly yes"
}

if ($PreferredAuthentications) {
    $managedBlock += "  PreferredAuthentications $PreferredAuthentications"
}

$updatedSegments = New-Object System.Collections.Generic.List[string]
$matched = $false

foreach ($segment in $segments) {
    if ($segment.IsHost -and (Get-HostDeclaration -Lines $segment.Lines) -eq $Alias) {
        $updatedSegments.Add(($managedBlock -join "`n"))
        $matched = $true
    }
    else {
        $updatedSegments.Add(($segment.Lines -join "`n"))
    }
}

if (-not $matched) {
    $updatedSegments.Add(($managedBlock -join "`n"))
}

$cleanSegments = @()
foreach ($segmentText in $updatedSegments) {
    $trimmed = $segmentText.Trim("`n")
    if ($trimmed -ne "") {
        $cleanSegments += $trimmed
    }
}

$newContent = ""
if ($cleanSegments.Count -gt 0) {
    $newContent = ($cleanSegments -join "`n`n") + "`n"
}

$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($ConfigPath, $newContent, $utf8NoBom)
Set-OpenSshAcl -Path $ConfigPath

[pscustomobject]@{
    Alias                    = $Alias
    HostName                 = $HostName
    Port                     = $Port
    User                     = $User
    IdentityFile             = $normalizedIdentity
    PreferredAuthentications = $PreferredAuthentications
    ConfigPath               = (Resolve-Path -LiteralPath $ConfigPath).Path
} | Format-List

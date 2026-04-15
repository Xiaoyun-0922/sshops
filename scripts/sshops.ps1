[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet("doctor", "configure", "bootstrap-key", "transfer", "run")]
    [string]$Subcommand,

    [string]$CondaEnv = "sshops",

    [string]$Alias,

    [string]$HostName,

    [int]$Port = 22,

    [string]$User,

    [string]$IdentityFile,

    [string]$PreferredAuthentications,

    [string]$ConfigPath,

    [switch]$SkipAuthTest,

    [string]$PublicKey,

    [string]$PrivateKey,

    [string]$PasswordEnv = "SSH_SERVER_PASSWORD",

    [string]$VerifyCommand = "whoami && pwd",

    [switch]$NoVerifyPublickey,

    [switch]$AllowPublickeyVerifyFailure,

    [ValidateSet("upload", "download")]
    [string]$Direction,

    [string]$RemotePath,

    [string]$LocalPath,

    [string]$Command,

    [string]$RemoteDir,

    [switch]$Bash,

    [switch]$BatchMode,

    [int]$ConnectTimeout = 15,

    [string]$ConfigFile,

    [switch]$IdentitiesOnly
)

$ErrorActionPreference = "Stop"

function Test-CondaEnvExists {
    param(
        [Parameter(Mandatory = $true)]
        [string]$EnvironmentName
    )

    $envList = & conda env list 2>$null
    if ($LASTEXITCODE -ne 0) {
        return $false
    }

    $pattern = "(?m)^\s*" + [regex]::Escape($EnvironmentName) + "\s+"
    return [regex]::IsMatch(($envList | Out-String), $pattern)
}

function Resolve-CondaEnvName {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RequestedName
    )

    if (-not (Get-Command conda -ErrorAction SilentlyContinue)) {
        return $RequestedName
    }

    if (Test-CondaEnvExists -EnvironmentName $RequestedName) {
        return $RequestedName
    }

    return $RequestedName
}

function Invoke-PythonScript {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ScriptPath,

        [Parameter(Mandatory = $true)]
        [string]$RequestedCondaEnv,

        [Parameter()]
        [string[]]$ForwardArguments = @()
    )

    $effectiveEnv = Resolve-CondaEnvName -RequestedName $RequestedCondaEnv
    if (-not (Get-Command conda -ErrorAction SilentlyContinue)) {
        throw "conda is required to run $ScriptPath"
    }

    & conda run -n $effectiveEnv python $ScriptPath @ForwardArguments
    exit $LASTEXITCODE
}

function Require-Value {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,

        [Parameter(Mandatory = $true)]
        $Value
    )

    if ($null -eq $Value -or ([string]::IsNullOrWhiteSpace([string]$Value))) {
        throw "$Name is required for subcommand '$Subcommand'."
    }
}

$scriptRoot = $PSScriptRoot

switch ($Subcommand) {
    "doctor" {
        $targetScript = Join-Path $scriptRoot "server_preflight.ps1"
        $invokeArgs = @{
            CondaEnv = (Resolve-CondaEnvName -RequestedName $CondaEnv)
        }

        if ($Alias) {
            $invokeArgs["Alias"] = $Alias
        }
        else {
            Require-Value -Name "HostName" -Value $HostName
            $invokeArgs["HostName"] = $HostName
            $invokeArgs["Port"] = $Port
            if ($User) {
                $invokeArgs["User"] = $User
            }
        }
        if ($SkipAuthTest) {
            $invokeArgs["SkipAuthTest"] = $true
        }

        & $targetScript @invokeArgs
        exit $LASTEXITCODE
    }
    "configure" {
        Require-Value -Name "Alias" -Value $Alias
        Require-Value -Name "HostName" -Value $HostName
        Require-Value -Name "User" -Value $User

        $targetScript = Join-Path $scriptRoot "configure_ssh_host.ps1"
        $invokeArgs = @{
            Alias    = $Alias
            HostName = $HostName
            Port     = $Port
            User     = $User
        }
        if ($IdentityFile) {
            $invokeArgs["IdentityFile"] = $IdentityFile
        }
        if ($PreferredAuthentications) {
            $invokeArgs["PreferredAuthentications"] = $PreferredAuthentications
        }
        if ($ConfigPath) {
            $invokeArgs["ConfigPath"] = $ConfigPath
        }

        & $targetScript @invokeArgs
        exit $LASTEXITCODE
    }
    "bootstrap-key" {
        Require-Value -Name "HostName" -Value $HostName
        Require-Value -Name "User" -Value $User
        Require-Value -Name "PublicKey" -Value $PublicKey

        $targetScript = Join-Path $scriptRoot "bootstrap_ssh_key.py"
        $invokeArgs = @(
            "--host", $HostName,
            "--port", "$Port",
            "--user", $User,
            "--public-key", $PublicKey,
            "--password-env", $PasswordEnv,
            "--verify-command", $VerifyCommand
        )
        if ($PrivateKey) {
            $invokeArgs += @("--private-key", $PrivateKey)
        }
        if ($NoVerifyPublickey) {
            $invokeArgs += "--no-verify-publickey"
        }
        if ($AllowPublickeyVerifyFailure) {
            $invokeArgs += "--allow-publickey-verify-failure"
        }

        Invoke-PythonScript -ScriptPath $targetScript -RequestedCondaEnv $CondaEnv -ForwardArguments $invokeArgs
    }
    "transfer" {
        Require-Value -Name "HostName" -Value $HostName
        Require-Value -Name "User" -Value $User
        Require-Value -Name "Direction" -Value $Direction
        Require-Value -Name "RemotePath" -Value $RemotePath
        Require-Value -Name "LocalPath" -Value $LocalPath

        $targetScript = Join-Path $scriptRoot "paramiko_copy_tree.py"
        $invokeArgs = @(
            "--host", $HostName,
            "--port", "$Port",
            "--user", $User,
            "--password-env", $PasswordEnv,
            "--direction", $Direction,
            "--remote-path", $RemotePath,
            "--local-path", $LocalPath
        )

        Invoke-PythonScript -ScriptPath $targetScript -RequestedCondaEnv $CondaEnv -ForwardArguments $invokeArgs
    }
    "run" {
        Require-Value -Name "Command" -Value $Command

        $targetScript = Join-Path $scriptRoot "remote_run.ps1"
        $invokeArgs = @{
            Command        = $Command
            ConnectTimeout = $ConnectTimeout
        }
        if ($Alias) {
            $invokeArgs["Alias"] = $Alias
        }
        else {
            Require-Value -Name "HostName" -Value $HostName
            $invokeArgs["HostName"] = $HostName
            $invokeArgs["Port"] = $Port
            if ($User) {
                $invokeArgs["User"] = $User
            }
        }
        if ($RemoteDir) {
            $invokeArgs["RemoteDir"] = $RemoteDir
        }
        if ($Bash) {
            $invokeArgs["Bash"] = $true
        }
        if ($BatchMode) {
            $invokeArgs["BatchMode"] = $true
        }
        if ($ConfigFile) {
            $invokeArgs["ConfigFile"] = $ConfigFile
        }
        if ($IdentityFile) {
            $invokeArgs["IdentityFile"] = $IdentityFile
        }
        if ($IdentitiesOnly) {
            $invokeArgs["IdentitiesOnly"] = $true
        }

        & $targetScript @invokeArgs
        exit $LASTEXITCODE
    }
}

[CmdletBinding(DefaultParameterSetName = "Alias")]
param(
    [Parameter(Mandatory = $true, ParameterSetName = "Alias")]
    [string]$Alias,

    [Parameter(Mandatory = $true, ParameterSetName = "Direct")]
    [string]$HostName,

    [Parameter(ParameterSetName = "Direct")]
    [int]$Port = 22,

    [Parameter(ParameterSetName = "Direct")]
    [string]$User,

    [string]$CondaEnv = "sshops",

    [switch]$SkipAuthTest
)

$ErrorActionPreference = "Stop"

function Invoke-NativeCapture {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,

        [Parameter()]
        [string[]]$Arguments = @()
    )

    $stdoutPath = Join-Path $env:TEMP ([System.IO.Path]::GetRandomFileName())
    $stderrPath = Join-Path $env:TEMP ([System.IO.Path]::GetRandomFileName())
    try {
        $process = Start-Process -FilePath $FilePath -ArgumentList $Arguments -NoNewWindow -Wait -PassThru `
            -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath
        $stdout = if (Test-Path $stdoutPath) { Get-Content -Path $stdoutPath -Raw } else { "" }
        $stderr = if (Test-Path $stderrPath) { Get-Content -Path $stderrPath -Raw } else { "" }
        return [ordered]@{
            exit_code = $process.ExitCode
            stdout    = $stdout
            stderr    = $stderr
            combined  = (($stdout + $stderr).Trim())
        }
    }
    finally {
        Remove-Item -LiteralPath $stdoutPath, $stderrPath -Force -ErrorAction SilentlyContinue
    }
}

function Get-ToolInfo {
    param([string]$Name)

    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if ($null -eq $command) {
        return [ordered]@{
            available = $false
            source    = $null
            version   = $null
        }
    }

    $version = $null
    if ($command.Version) {
        $version = $command.Version.ToString()
    }

    return [ordered]@{
        available = $true
        source    = $command.Source
        version   = $version
    }
}

function Parse-SshConfig {
    param([string[]]$Lines)

    $selectedKeys = @(
        "hostname",
        "user",
        "port",
        "identityfile",
        "identitiesonly",
        "preferredauthentications"
    )

    $config = [ordered]@{}
    foreach ($key in $selectedKeys) {
        $config[$key] = $null
    }

    foreach ($line in $Lines) {
        if ($line -match "^(?<key>\S+)\s+(?<value>.+)$") {
            $key = $Matches["key"].ToLowerInvariant()
            if ($selectedKeys -contains $key) {
                $config[$key] = $Matches["value"].Trim()
            }
        }
    }

    return $config
}

function Test-CondaEnvExists {
    param([string]$EnvironmentName)

    $envList = & conda env list 2>$null
    if ($LASTEXITCODE -ne 0) {
        return $false
    }

    $pattern = "(?m)^\s*" + [regex]::Escape($EnvironmentName) + "\s+"
    return [regex]::IsMatch(($envList | Out-String), $pattern)
}

function Get-CondaEnvInfo {
    param([string]$EnvironmentName)

    $info = [ordered]@{
        conda_available    = $false
        requested_name     = $EnvironmentName
        effective_name     = $EnvironmentName
        fallback_used      = $false
        env_exists         = $false
        paramiko_available = $false
        paramiko_version   = $null
    }

    $conda = Get-Command conda -ErrorAction SilentlyContinue
    if ($null -eq $conda) {
        return $info
    }

    $info.conda_available = $true
    if (Test-CondaEnvExists -EnvironmentName $EnvironmentName) {
        $info.effective_name = $EnvironmentName
        $info.env_exists = $true
    }

    if ($info.env_exists) {
        $paramiko = & conda run -n $info.effective_name python -c "import paramiko; print(paramiko.__version__)" 2>&1
        if ($LASTEXITCODE -eq 0) {
            $info.paramiko_available = $true
            $info.paramiko_version = (($paramiko | Out-String).Trim())
        }
    }

    return $info
}

$toolNames = @("ssh", "scp", "sftp", "tar", "conda")
$tools = [ordered]@{}
foreach ($toolName in $toolNames) {
    $tools[$toolName] = Get-ToolInfo -Name $toolName
}

$target = $null
$sshConfig = $null
$resolvedHost = $HostName
$resolvedPort = $Port
$resolvedUser = $User

if ($PSCmdlet.ParameterSetName -eq "Alias") {
    $target = $Alias
}
else {
    $target = if ($User) { "$User@$HostName" } else { $HostName }
}

if ($tools["ssh"].available) {
    $sshConfigResult = Invoke-NativeCapture -FilePath $tools["ssh"].source -Arguments @("-G", $target)
    if ($sshConfigResult.exit_code -eq 0) {
        $sshConfigLines = ($sshConfigResult.stdout -split "\r?\n")
        $sshConfig = Parse-SshConfig -Lines $sshConfigLines
        if ($sshConfig.hostname) {
            $resolvedHost = $sshConfig.hostname
        }
        if ($sshConfig.port) {
            $resolvedPort = [int]$sshConfig.port
        }
        if ($sshConfig.user) {
            $resolvedUser = $sshConfig.user
        }
    }
}

$tcp = [ordered]@{
    host      = $resolvedHost
    port      = $resolvedPort
    reachable = $null
}
if ($resolvedHost -and $resolvedPort) {
    $tcpResult = Test-NetConnection $resolvedHost -Port $resolvedPort -WarningAction SilentlyContinue
    $tcp.reachable = [bool]$tcpResult.TcpTestSucceeded
}

$auth = [ordered]@{
    tested      = (-not $SkipAuthTest.IsPresent)
    success     = $null
    exit_code   = $null
    output      = $null
}

if (-not $SkipAuthTest.IsPresent -and $tools["ssh"].available) {
    if ($PSCmdlet.ParameterSetName -eq "Alias") {
        $authArgs = @("-o", "BatchMode=yes", "-o", "ConnectTimeout=8", $Alias, "whoami")
    }
    else {
        $directTarget = if ($resolvedUser) { "$resolvedUser@$resolvedHost" } else { $resolvedHost }
        $authArgs = @("-o", "BatchMode=yes", "-o", "ConnectTimeout=8", "-p", "$resolvedPort", $directTarget, "whoami")
    }

    $authOutput = Invoke-NativeCapture -FilePath $tools["ssh"].source -Arguments $authArgs
    $auth.exit_code = $authOutput.exit_code
    $auth.success = ($authOutput.exit_code -eq 0)
    $auth.output = $authOutput.combined
}

$condaInfo = Get-CondaEnvInfo -EnvironmentName $CondaEnv

$notes = New-Object System.Collections.Generic.List[string]
if (-not $tools["ssh"].available) {
    $notes.Add("OpenSSH client is not available locally.")
}
if (
    $tools["ssh"].available -and
    $PSCmdlet.ParameterSetName -eq "Alias" -and
    (
        (-not $sshConfig) -or
        (($resolvedHost -eq $Alias) -and ($tcp.reachable -eq $false))
    )
) {
    $notes.Add("SSH alias may be unresolved or missing from ~/.ssh/config; run preflight in Direct mode or configure the host entry first.")
}
if (-not $condaInfo.conda_available) {
    $notes.Add("Conda is unavailable; password bootstrap via Paramiko will not work.")
}
elseif (-not $condaInfo.env_exists) {
    $notes.Add("The requested Python environment is missing; password bootstrap via Paramiko is not ready.")
}
elseif (-not $condaInfo.paramiko_available) {
    $notes.Add("The selected Python environment exists but Paramiko is not installed.")
}
if ($auth.tested -and $auth.success -eq $false) {
    $notes.Add("Key-based non-interactive SSH is not ready yet.")
}

$bootstrapReady = (
    $tools["ssh"].available -and
    $condaInfo.conda_available -and
    $condaInfo.env_exists -and
    $condaInfo.paramiko_available -and
    [bool]$resolvedHost -and
    [bool]$resolvedUser
)

$localTools = $tools
$network = [ordered]@{
    target_host   = $resolvedHost
    target_port   = $resolvedPort
    tcp_reachable = $tcp.reachable
}
$transfer = [ordered]@{
    openssh_scp_available   = $tools["scp"].available
    openssh_sftp_available  = $tools["sftp"].available
    password_fallback_ready = $bootstrapReady
    preferred_order         = @(
        "openssh-publickey",
        "openssh-password",
        "sftp",
        "paramiko-sftp",
        "tar-over-ssh"
    )
}
$remoteShell = [ordered]@{
    probe_command            = if ($auth.tested) { "whoami" } else { $null }
    non_interactive_probe_ok = $auth.success
}

$likelyRootCause = $null
$recommendedNextStep = $null

if (-not $tools["ssh"].available) {
    $likelyRootCause = "openssh_missing"
    $recommendedNextStep = "Install or expose the OpenSSH client on PATH, then rerun doctor."
}
elseif (
    $PSCmdlet.ParameterSetName -eq "Alias" -and
    (
        (-not $sshConfig) -or
        (($resolvedHost -eq $Alias) -and ($tcp.reachable -eq $false))
    )
) {
    $likelyRootCause = "ssh_alias_unresolved"
    $recommendedNextStep = "Repair or create the host block with configure, or rerun doctor in direct mode."
}
elseif ($tcp.reachable -eq $false) {
    $likelyRootCause = "tcp_unreachable"
    $recommendedNextStep = "Verify host, port, VPN, firewall, or gateway routing before trying auth fixes."
}
elseif ($auth.tested -and $auth.success -eq $false) {
    $likelyRootCause = "non_interactive_publickey_unavailable"
    if ($bootstrapReady) {
        $recommendedNextStep = "Either bootstrap public-key access with bootstrap-key or fix the SSH identity selection, then rerun doctor."
    }
    else {
        $recommendedNextStep = "Prepare the Python environment for Paramiko fallback or fix the SSH identity selection, then rerun doctor."
    }
}
elseif ($auth.tested -and $auth.success) {
    $likelyRootCause = "none"
    $recommendedNextStep = "Proceed with run, direct OpenSSH transfer, or the narrowest server task needed."
}
else {
    $likelyRootCause = "auth_not_tested"
    $recommendedNextStep = "Rerun doctor without SkipAuthTest when you are ready to validate non-interactive SSH."
}

$result = [ordered]@{
    target               = $target
    resolved             = [ordered]@{
        host = $resolvedHost
        port = $resolvedPort
        user = $resolvedUser
    }
    ssh_config           = $sshConfig
    local_tools          = $localTools
    network              = $network
    auth                 = [ordered]@{
        batchmode_publickey_tested = $auth.tested
        batchmode_publickey_ok     = $auth.success
        batchmode_exit_code        = $auth.exit_code
        batchmode_output           = $auth.output
    }
    transfer             = $transfer
    remote_shell         = $remoteShell
    python_env           = $condaInfo
    likely_root_cause    = $likelyRootCause
    recommended_next_step = $recommendedNextStep
    risk_level           = "read-only"
    tools                = $tools
    tcp                  = $tcp
    bootstrap_ready      = $bootstrapReady
    notes                = @($notes)
}

$result | ConvertTo-Json -Depth 6

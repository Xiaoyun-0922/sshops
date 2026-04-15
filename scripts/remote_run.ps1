[CmdletBinding(DefaultParameterSetName = "Alias")]
param(
    [Parameter(Mandatory = $true, Position = 0, ParameterSetName = "Alias")]
    [string]$Alias,

    [Parameter(Mandatory = $true, ParameterSetName = "Direct")]
    [string]$HostName,

    [Parameter(ParameterSetName = "Direct")]
    [int]$Port = 22,

    [Parameter(ParameterSetName = "Direct")]
    [string]$User,

    [Parameter(Mandatory = $true, Position = 1)]
    [string]$Command,

    [string]$RemoteDir,

    [switch]$Bash,

    [switch]$BatchMode,

    [int]$ConnectTimeout = 15,

    [string]$ConfigFile,

    [string]$IdentityFile,

    [switch]$IdentitiesOnly
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
        $stdout = if (Test-Path $stdoutPath) { [string](Get-Content -Path $stdoutPath -Raw) } else { "" }
        $stderr = if (Test-Path $stderrPath) { [string](Get-Content -Path $stderrPath -Raw) } else { "" }
        return [ordered]@{
            exit_code = $process.ExitCode
            stdout    = [string]$stdout
            stderr    = [string]$stderr
        }
    }
    finally {
        Remove-Item -LiteralPath $stdoutPath, $stderrPath -Force -ErrorAction SilentlyContinue
    }
}

function Convert-ToDoubleQuotedLiteral {
    param([string]$Value)

    if ($null -eq $Value) {
        return ""
    }

    return ($Value -replace "\\", "\\\\" -replace '"', '\"')
}

$ssh = Get-Command ssh -ErrorAction SilentlyContinue
if ($null -eq $ssh) {
    throw "OpenSSH client 'ssh' is not available on PATH."
}

$target = if ($PSCmdlet.ParameterSetName -eq "Alias") {
    $Alias
}
else {
    if ($User) { "$User@$HostName" } else { $HostName }
}

$remoteCommand = $Command
if ($RemoteDir) {
    $escapedDir = Convert-ToDoubleQuotedLiteral -Value $RemoteDir
    $remoteCommand = "cd `"$escapedDir`" && $remoteCommand"
}
if ($Bash -or $RemoteDir) {
    $escapedCommand = Convert-ToDoubleQuotedLiteral -Value $remoteCommand
    $remoteCommand = "bash -lc `"$escapedCommand`""
}

$sshArgs = @("-o", "ConnectTimeout=$ConnectTimeout")
if ($BatchMode) {
    $sshArgs += @("-o", "BatchMode=yes")
}
if ($ConfigFile) {
    $sshArgs += @("-F", $ConfigFile)
}
if ($IdentityFile) {
    $sshArgs += @("-i", $IdentityFile)
}
if ($IdentitiesOnly) {
    $sshArgs += @("-o", "IdentitiesOnly=yes")
}
if ($PSCmdlet.ParameterSetName -eq "Direct") {
    $sshArgs += @("-p", "$Port")
}
$sshArgs += @($target, $remoteCommand)

$result = Invoke-NativeCapture -FilePath $ssh.Source -Arguments $sshArgs

[ordered]@{
    target         = $target
    mode           = $PSCmdlet.ParameterSetName.ToLowerInvariant()
    command        = $Command
    remote_dir     = $RemoteDir
    bash_wrapped   = [bool]($Bash -or $RemoteDir)
    batch_mode     = [bool]$BatchMode
    exit_code      = $result.exit_code
    success        = ($result.exit_code -eq 0)
    stdout         = $result.stdout
    stderr         = $result.stderr
    ssh_arguments  = $sshArgs
} | ConvertTo-Json -Depth 5

exit $result.exit_code

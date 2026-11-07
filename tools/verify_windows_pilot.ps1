param(
    [Parameter(Mandatory = $true)][string]$OutputPath,
    [int]$MinimumFreeDiskGiB = 10
)
# Read-only preflight. No startup task, sleep, firewall, WSL or Docker setting changes.
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$systemState = Get-CimInstance Win32_OperatingSystem
$projectDrive = [IO.Path]::GetPathRoot($repoRoot).TrimEnd('\')
$driveState = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='$projectDrive'"
$dockerReady = $false
$dockerMemory = $null
$dockerCpus = $null
if (Get-Command docker -ErrorAction SilentlyContinue) {
    $daemon = & docker info --format '{{json .}}' 2>$null
    if ($LASTEXITCODE -eq 0) {
        $dockerState = $daemon | ConvertFrom-Json
        $dockerReady = $true
        $dockerMemory = [math]::Round($dockerState.MemTotal / 1GB, 2)
        $dockerCpus = $dockerState.NCPU
    }
}
$startupEntries = @(Get-CimInstance Win32_StartupCommand | Where-Object { $_.Name -match 'Docker' })
$sleepPolicy = & powercfg /query SCHEME_CURRENT SUB_SLEEP STANDBYIDLE 2>$null
$acMatch = [regex]::Match(($sleepPolicy -join "`n"), 'Current AC Power Setting Index:\s*0x([0-9a-fA-F]+)')
$acSleepSeconds = if ($acMatch.Success) { [Convert]::ToInt64($acMatch.Groups[1].Value, 16) } else { $null }
$receipt = [ordered]@{
    checked_at = [DateTime]::UtcNow.ToString('o')
    scope = 'Read-only Windows/Docker pilot preflight; no configuration changes'
    docker_daemon_available = $dockerReady
    docker_memory_gib = $dockerMemory
    docker_logical_cpus = $dockerCpus
    host_total_memory_gib = [math]::Round(($systemState.TotalVisibleMemorySize * 1KB) / 1GB, 2)
    host_available_memory_gib = [math]::Round(($systemState.FreePhysicalMemory * 1KB) / 1GB, 2)
    project_drive_free_gib = [math]::Round($driveState.FreeSpace / 1GB, 2)
    minimum_free_disk_gib = $MinimumFreeDiskGiB
    disk_threshold_met = $driveState.FreeSpace -ge ($MinimumFreeDiskGiB * 1GB)
    docker_startup_entry_present = $startupEntries.Count -gt 0
    ac_idle_sleep_seconds = $acSleepSeconds
    boot_recovery_verified = $false
    off_machine_backup_verified = $false
    external_host_verified = $false
    settings_changed = $false
    limitations = @(
        'A startup entry does not prove Docker Desktop starts without an interactive login.'
        'AC idle sleep does not cover manual sleep, modern standby, display lid actions, updates or power loss.'
        'No machine restart, route change, workload tuning or GOOL operation was performed.'
    )
}
$resolvedOutput = [IO.Path]::GetFullPath($OutputPath)
[IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($resolvedOutput)) | Out-Null
$serialized = $receipt | ConvertTo-Json -Depth 5
[IO.File]::WriteAllText($resolvedOutput, $serialized + "`n", [Text.UTF8Encoding]::new($false))
$serialized

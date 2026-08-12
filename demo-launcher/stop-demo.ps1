$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$RuntimeFile = Join-Path $RepoRoot ".room-harmony-demo\runtime.json"

function Test-TrackedProcess($Entry, $Process) {
    $ExpectedCreation = ([datetime]$Entry.createdAt).ToUniversalTime()
    $ActualCreation = ([datetime]$Process.CreationDate).ToUniversalTime()
    if ([math]::Abs(($ExpectedCreation - $ActualCreation).TotalSeconds) -gt 2) {
        return $false
    }

    $CommandLine = [string]$Process.CommandLine
    switch -Wildcard ($Entry.role) {
        "backend-*" {
            return $CommandLine -match "uvicorn" -and $CommandLine -match "8000"
        }
        "frontend-launcher" {
            return $CommandLine -match "vite" -and $CommandLine -match "5173"
        }
        "frontend-listener" {
            return $CommandLine -match "vite" -and $CommandLine -match "5173"
        }
        default {
            return $false
        }
    }
}

try {
    Write-Host "========================================" -ForegroundColor DarkGray
    Write-Host " Room Harmony デモ停止" -ForegroundColor Yellow
    Write-Host "========================================" -ForegroundColor DarkGray

    if (-not (Test-Path $RuntimeFile)) {
        Write-Host "この起動器が管理するサービスはありません。" -ForegroundColor DarkGreen
        exit 0
    }

    $Runtime = Get-Content -Raw -Encoding UTF8 -LiteralPath $RuntimeFile | ConvertFrom-Json
    if ((Resolve-Path $Runtime.repoRoot).Path -ne $RepoRoot) {
        throw "実行記録のリポジトリパスが一致しないため、安全のため停止しませんでした。"
    }

    $Entries = @($Runtime.processes) | Sort-Object {
        if ($_.role -eq "frontend-launcher") { 0 }
        elseif ($_.role -eq "backend-launcher") { 1 }
        else { 2 }
    }
    $StoppedPids = [System.Collections.Generic.HashSet[int]]::new()
    foreach ($entry in $Entries) {
        $ProcessId = [int]$entry.pid
        if ($StoppedPids.Contains($ProcessId)) {
            continue
        }
        $process = Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction SilentlyContinue
        if ($null -eq $process) {
            continue
        }
        if (-not (Test-TrackedProcess $entry $process)) {
            Write-Host "PID $ProcessId は記録時と異なるため停止対象から除外しました。" -ForegroundColor Yellow
            continue
        }
        & taskkill.exe /PID $ProcessId /T /F 2>$null | Out-Null
        [void]$StoppedPids.Add($ProcessId)
    }

    Remove-Item -LiteralPath $RuntimeFile -Force
    Write-Host "Room Harmonyのバックエンドとフロントエンドを停止しました。" -ForegroundColor Green
}
catch {
    Write-Host "`n[エラー] $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

param(
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$BackendDir = Join-Path $RepoRoot "backend"
$FrontendDir = Join-Path $RepoRoot "frontend"
$RuntimeDir = Join-Path $RepoRoot ".room-harmony-demo"
$RuntimeFile = Join-Path $RuntimeDir "runtime.json"
$LauncherErrorFile = Join-Path $RuntimeDir "launcher.err.log"
$DemoUrl = "http://localhost:5173/s/QR-PRODUCT-01-02-01-0799"
$BackendHealthUrl = "http://127.0.0.1:8000/health"
$FrontendHealthUrl = "http://127.0.0.1:5173"
$StartedProcesses = [System.Collections.Generic.List[object]]::new()

function Write-Step([string]$Message) {
    Write-Host "`n>> $Message" -ForegroundColor Cyan
}

function Test-Command([string]$Name) {
    return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

function Test-BackendReady {
    try {
        $result = Invoke-RestMethod -Uri $BackendHealthUrl -TimeoutSec 2
        return $result.status -eq "ok"
    }
    catch {
        return $false
    }
}

function Test-FrontendReady {
    try {
        $result = Invoke-WebRequest -Uri $FrontendHealthUrl -UseBasicParsing -TimeoutSec 2
        return $result.StatusCode -eq 200 -and $result.Content -match "Room Harmony"
    }
    catch {
        return $false
    }
}

function Get-PortOwner([int]$Port) {
    return Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
}

function Get-TrackedProcess([int]$ProcessId, [string]$Role) {
    $process = Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction SilentlyContinue
    if ($null -eq $process) {
        return $null
    }
    return [ordered]@{
        role = $Role
        pid = [int]$process.ProcessId
        createdAt = ([datetime]$process.CreationDate).ToUniversalTime().ToString("o")
        commandLine = [string]$process.CommandLine
    }
}

function Test-TrackedRuntimeEntry($Entry, $Process) {
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
        "frontend-*" {
            return $CommandLine -match "vite" -and $CommandLine -match "5173"
        }
        default {
            return $false
        }
    }
}

function Stop-StartedProcesses {
    foreach ($entry in ($StartedProcesses | Sort-Object pid -Unique)) {
        $ProcessId = [int]$entry.pid
        Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
    }
}

function Register-PortListener([int]$Port, [string]$Role, [switch]$StartedThisRun) {
    $owner = Get-PortOwner $Port
    if ($null -eq $owner) {
        return
    }

    $process = Get-CimInstance Win32_Process -Filter "ProcessId=$($owner.OwningProcess)" -ErrorAction SilentlyContinue
    $entry = Get-TrackedProcess $owner.OwningProcess $Role
    if ($null -eq $process -or $null -eq $entry -or -not (Test-TrackedRuntimeEntry $entry $process)) {
        return
    }

    if (-not ($RuntimeEntries | Where-Object { $_.pid -eq $entry.pid })) {
        $RuntimeEntries.Add($entry)
    }
    if ($StartedThisRun -and -not ($StartedProcesses | Where-Object { $_.pid -eq $entry.pid })) {
        $StartedProcesses.Add($entry)
    }
}

try {
    Write-Host "========================================" -ForegroundColor DarkGray
    Write-Host " Room Harmony ワンクリックデモ起動" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor DarkGray

    Write-Step "実行環境を確認しています"
    if (-not (Test-Path (Join-Path $BackendDir "requirements.txt"))) {
        throw "backend/requirements.txt が見つかりません。リポジトリのルートから実行してください。"
    }
    if (-not (Test-Path (Join-Path $FrontendDir "package.json"))) {
        throw "frontend/package.json が見つかりません。リポジトリのルートから実行してください。"
    }
    if (-not (Test-Command "npm.cmd")) {
        throw "Node.js / npm が見つかりません。Node.js 22系をインストールしてください。"
    }

    $VenvPython = Join-Path $BackendDir ".venv\Scripts\python.exe"
    if (-not (Test-Path $VenvPython)) {
        if (-not (Test-Command "py.exe")) {
            throw "Python の py ランチャーが見つかりません。Python 3.13系をインストールしてください。"
        }
        Write-Step "初回セットアップ: Python仮想環境を作成しています"
        & py.exe -m venv (Join-Path $BackendDir ".venv")
        if ($LASTEXITCODE -ne 0) {
            throw "Python仮想環境の作成に失敗しました。"
        }

        Write-Step "初回セットアップ: Python依存関係をインストールしています"
        & $VenvPython -m pip install --upgrade pip
        if ($LASTEXITCODE -ne 0) {
            throw "pip の更新に失敗しました。"
        }
        & $VenvPython -m pip install -r (Join-Path $BackendDir "requirements.txt")
        if ($LASTEXITCODE -ne 0) {
            throw "Python依存関係のインストールに失敗しました。"
        }
    }
    else {
        Write-Host "Python依存関係: 準備済み" -ForegroundColor DarkGreen
    }

    $ViteCommand = Join-Path $FrontendDir "node_modules\.bin\vite.cmd"
    if (-not (Test-Path $ViteCommand)) {
        Write-Step "初回セットアップ: フロントエンド依存関係をインストールしています"
        & npm.cmd install --prefix $FrontendDir
        if ($LASTEXITCODE -ne 0) {
            throw "フロントエンド依存関係のインストールに失敗しました。"
        }
    }
    else {
        Write-Host "フロントエンド依存関係: 準備済み" -ForegroundColor DarkGreen
    }

    New-Item -ItemType Directory -Force -Path $RuntimeDir | Out-Null
    Remove-Item -LiteralPath $LauncherErrorFile -Force -ErrorAction SilentlyContinue
    $RuntimeEntries = [System.Collections.Generic.List[object]]::new()
    if (Test-Path $RuntimeFile) {
        try {
            $PreviousRuntime = Get-Content -Raw -Encoding UTF8 -LiteralPath $RuntimeFile | ConvertFrom-Json
            if ((Resolve-Path $PreviousRuntime.repoRoot).Path -eq $RepoRoot) {
                foreach ($entry in @($PreviousRuntime.processes)) {
                    $process = Get-CimInstance Win32_Process -Filter "ProcessId=$([int]$entry.pid)" -ErrorAction SilentlyContinue
                    if ($null -ne $process -and (Test-TrackedRuntimeEntry $entry $process)) {
                        $RuntimeEntries.Add($entry)
                    }
                }
            }
        }
        catch {
            # 壊れた／古い記録は後で正常な実行記録へ上書きする。外部プロセスは下の照合で拒否する。
        }
    }

    $BackendPortOwner = Get-PortOwner 8000
    if ($null -ne $BackendPortOwner) {
        $managed = $RuntimeEntries | Where-Object {
            $_.pid -eq $BackendPortOwner.OwningProcess -and $_.role -like "backend-*"
        }
        if ($null -eq $managed -or -not (Test-BackendReady)) {
            throw "ポート8000はこの起動器が管理していないプロセスで使用されています。該当プロセスを終了してから再実行してください。"
        }
    }
    $FrontendPortOwner = Get-PortOwner 5173
    if ($null -ne $FrontendPortOwner) {
        $managed = $RuntimeEntries | Where-Object {
            $_.pid -eq $FrontendPortOwner.OwningProcess -and $_.role -like "frontend-*"
        }
        if ($null -eq $managed -or -not (Test-FrontendReady)) {
            throw "ポート5173はこの起動器が管理していないプロセスで使用されています。該当プロセスを終了してから再実行してください。"
        }
    }

    if (-not (Test-BackendReady)) {
        Write-Step "FastAPIバックエンドを起動しています（treatment 100%）"
        $PreviousRatio = $env:EXPERIMENT_GROUP_RATIO
        $env:EXPERIMENT_GROUP_RATIO = "1.0"
        try {
            $backend = Start-Process -FilePath $VenvPython `
                -ArgumentList @("-m", "uvicorn", "app.main:app", "--app-dir", "backend", "--host", "127.0.0.1", "--port", "8000") `
                -WorkingDirectory $RepoRoot `
                -WindowStyle Hidden `
                -RedirectStandardOutput (Join-Path $RuntimeDir "backend.out.log") `
                -RedirectStandardError (Join-Path $RuntimeDir "backend.err.log") `
                -PassThru
        }
        finally {
            $env:EXPERIMENT_GROUP_RATIO = $PreviousRatio
        }
        $backendEntry = Get-TrackedProcess $backend.Id "backend-launcher"
        if ($null -ne $backendEntry) {
            $StartedProcesses.Add($backendEntry)
            $RuntimeEntries.Add($backendEntry)
        }
        $BackendListenerDeadline = (Get-Date).AddSeconds(15)
        while ((Get-Date) -lt $BackendListenerDeadline -and $null -eq (Get-PortOwner 8000)) {
            Start-Sleep -Milliseconds 100
        }
        Register-PortListener 8000 "backend-listener" -StartedThisRun
    }
    else {
        Write-Host "FastAPIバックエンド: 既に起動しています" -ForegroundColor DarkGreen
    }

    if (-not (Test-FrontendReady)) {
        Write-Step "React/Viteフロントエンドを起動しています"
        $NodeCommand = (Get-Command "node.exe").Source
        $ViteScript = Join-Path $FrontendDir "node_modules\vite\bin\vite.js"
        $QuotedViteScript = '"' + $ViteScript.Replace('"', '\"') + '"'
        $frontend = Start-Process -FilePath $NodeCommand `
            -ArgumentList @($QuotedViteScript, "--host", "127.0.0.1", "--port", "5173") `
            -WorkingDirectory $FrontendDir `
            -WindowStyle Hidden `
            -RedirectStandardOutput (Join-Path $RuntimeDir "frontend.out.log") `
            -RedirectStandardError (Join-Path $RuntimeDir "frontend.err.log") `
            -PassThru
        $frontendEntry = Get-TrackedProcess $frontend.Id "frontend-launcher"
        if ($null -ne $frontendEntry) {
            $StartedProcesses.Add($frontendEntry)
            $RuntimeEntries.Add($frontendEntry)
        }
        $FrontendListenerDeadline = (Get-Date).AddSeconds(15)
        while ((Get-Date) -lt $FrontendListenerDeadline -and $null -eq (Get-PortOwner 5173)) {
            Start-Sleep -Milliseconds 100
        }
        Register-PortListener 5173 "frontend-listener" -StartedThisRun
    }
    else {
        Write-Host "React/Viteフロントエンド: 既に起動しています" -ForegroundColor DarkGreen
    }

    Write-Step "サービスの起動完了を待っています"
    $Deadline = (Get-Date).AddSeconds(45)
    while ((Get-Date) -lt $Deadline -and (-not (Test-BackendReady) -or -not (Test-FrontendReady))) {
        Start-Sleep -Milliseconds 300
    }
    if (-not (Test-BackendReady)) {
        throw "バックエンドが45秒以内に応答しませんでした。.room-harmony-demo/backend.err.log を確認してください。"
    }
    if (-not (Test-FrontendReady)) {
        throw "フロントエンドが45秒以内に応答しませんでした。.room-harmony-demo/frontend.err.log を確認してください。"
    }

    foreach ($portInfo in @(
        @{ port = 8000; role = "backend-listener" },
        @{ port = 5173; role = "frontend-listener" }
    )) {
        Register-PortListener $portInfo.port $portInfo.role
    }

    if ($RuntimeEntries.Count -gt 0) {
        [ordered]@{
            repoRoot = $RepoRoot
            startedAt = [datetime]::UtcNow.ToString("o")
            processes = @($RuntimeEntries)
        } | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $RuntimeFile -Encoding UTF8
    }

    Write-Host "`n起動完了: $DemoUrl" -ForegroundColor Green
    if (-not $NoBrowser) {
        Write-Step "Room Harmonyを開いています"
        $ChromeCandidates = @(
            "C:\Program Files\Google\Chrome\Application\chrome.exe",
            "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
        )
        $Chrome = $ChromeCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
        if ($null -ne $Chrome) {
            Start-Process -FilePath $Chrome -ArgumentList @("--app=$DemoUrl", "--start-maximized") | Out-Null
        }
        else {
            Start-Process $DemoUrl | Out-Null
        }
    }
    Write-Host "終了する場合は stop-demo.cmd をダブルクリックしてください。" -ForegroundColor Yellow
}
catch {
    New-Item -ItemType Directory -Force -Path $RuntimeDir | Out-Null
    ($_ | Out-String) | Set-Content -LiteralPath $LauncherErrorFile -Encoding UTF8
    Stop-StartedProcesses
    Write-Host "`n[エラー] $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

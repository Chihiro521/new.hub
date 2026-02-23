# ============================================
# News Hub 统一启动脚本
# ============================================
# 用法:
#   .\start.ps1              # 启动所有组件
#   .\start.ps1 -Backend     # 只启动后端
#   .\start.ps1 -Frontend    # 只启动前端
#   .\start.ps1 -Backend -Frontend  # 启动后端和前端
# ============================================

param(
    [switch]$Backend,
    [switch]$Frontend,
    [switch]$Elasticsearch,
    [switch]$Help
)

$Host.UI.RawUI.WindowTitle = "News Hub Launcher"

# 显示帮助信息
if ($Help) {
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "   News Hub 启动脚本" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "用法:" -ForegroundColor Yellow
    Write-Host "  .\start.ps1                    # 启动所有组件"
    Write-Host "  .\start.ps1 -Backend           # 只启动后端"
    Write-Host "  .\start.ps1 -Frontend          # 只启动前端"
    Write-Host "  .\start.ps1 -Elasticsearch     # 只启动 Elasticsearch"
    Write-Host "  .\start.ps1 -Backend -Frontend # 启动后端和前端"
    Write-Host ""
    Write-Host "组件说明:" -ForegroundColor Yellow
    Write-Host "  Backend        - FastAPI 后端服务 (端口 8000)"
    Write-Host "  Frontend       - Vue 3 前端 (端口 5173)"
    Write-Host "  Elasticsearch  - 搜索引擎 (端口 9200)"
    Write-Host ""
    exit 0
}

# 如果没有指定任何参数，启动所有组件
$startAll = -not ($Backend -or $Frontend -or $Elasticsearch)
if ($startAll) {
    $Backend = $true
    $Frontend = $true
    $Elasticsearch = $true
}

$projectRoot = $PSScriptRoot

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   News Hub Launcher" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 显示启动计划
Write-Host "启动计划:" -ForegroundColor Yellow
if ($Elasticsearch) { Write-Host "  ✓ Elasticsearch" -ForegroundColor Gray }
if ($Backend) { Write-Host "  ✓ Backend" -ForegroundColor Gray }
if ($Frontend) { Write-Host "  ✓ Frontend" -ForegroundColor Gray }
Write-Host ""

# Function to check if a port is in use
function Test-Port {
    param([int]$Port)
    $connection = Test-NetConnection -ComputerName localhost -Port $Port -WarningAction SilentlyContinue -InformationLevel Quiet
    return $connection
}

# Check MongoDB (required for backend)
if ($Backend) {
    Write-Host "检查前置条件..." -ForegroundColor Yellow
    Write-Host "  MongoDB (端口 27017)..." -NoNewline
    if (Test-Port 27017) {
        Write-Host " ✓" -ForegroundColor Green
    } else {
        Write-Host " ✗" -ForegroundColor Red
        Write-Host ""
        Write-Host "[错误] MongoDB 未运行！" -ForegroundColor Red
        Write-Host "后端需要 MongoDB，请先启动 MongoDB。" -ForegroundColor Yellow
        Read-Host "按 Enter 退出"
        exit 1
    }
    Write-Host ""
}

$componentsStarted = @()

# Start Elasticsearch
if ($Elasticsearch) {
    Write-Host "启动 Elasticsearch..." -ForegroundColor Yellow
    Write-Host "  检查端口 9200..." -NoNewline

    if (Test-Port 9200) {
        Write-Host " 已运行" -ForegroundColor Green
        $componentsStarted += "Elasticsearch (已存在)"
    } else {
        Write-Host " 启动中..." -ForegroundColor Gray
        $esPath = Join-Path $projectRoot "elasticsearch\elasticsearch-8.17.5\bin\elasticsearch.bat"

        if (Test-Path $esPath) {
            Start-Process -FilePath $esPath -WindowStyle Minimized
            Write-Host "  等待启动 (30秒)..." -ForegroundColor Gray
            Start-Sleep -Seconds 30

            if (Test-Port 9200) {
                Write-Host "  ✓ 启动成功" -ForegroundColor Green
                $componentsStarted += "Elasticsearch"
            } else {
                Write-Host "  ⚠ 可能未完全启动" -ForegroundColor Yellow
                $componentsStarted += "Elasticsearch (启动中)"
            }
        } else {
            Write-Host "  ✗ 未找到: $esPath" -ForegroundColor Red
        }
    }
    Write-Host ""
}

# Start Backend
if ($Backend) {
    Write-Host "启动后端..." -ForegroundColor Yellow
    Write-Host "  检查端口 8000..." -NoNewline

    if (Test-Port 8000) {
        Write-Host " 已运行" -ForegroundColor Green
        $componentsStarted += "Backend (已存在)"
    } else {
        Write-Host " 启动中..." -ForegroundColor Gray

        # 创建后端启动命令
        $backendDir = Join-Path $projectRoot "backend"
        $backendCmd = @"
`$Host.UI.RawUI.WindowTitle = 'News Hub Backend'
Write-Host '========================================' -ForegroundColor Cyan
Write-Host '   News Hub Backend' -ForegroundColor Cyan
Write-Host '========================================' -ForegroundColor Cyan
Write-Host ''

# 初始化 conda
`$condaRoot = `$null
`$condaActivated = `$false
try {
    `$condaRoot = (conda info --base 2>`$null).Trim()
} catch {}

if (`$condaRoot) {
    `$condaHook = Join-Path `$condaRoot 'shell\condabin\conda-hook.ps1'
    if (Test-Path `$condaHook) {
        . `$condaHook
        conda activate news-hub
        `$condaActivated = `$true
    }
}

Set-Location '$backendDir'
Write-Host 'API docs: http://localhost:8000/docs' -ForegroundColor Green
Write-Host 'Health:   http://localhost:8000/health' -ForegroundColor Green
Write-Host ''
Write-Host 'Press Ctrl+C to stop' -ForegroundColor Yellow
Write-Host ''

if (`$condaActivated) {
    python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
} else {
    `$condaPython = Join-Path `$condaRoot 'envs\news-hub\python.exe'
    if (Test-Path `$condaPython) {
        Write-Host '[INFO] conda activate failed, using python directly' -ForegroundColor Yellow
        & `$condaPython -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
    } else {
        Write-Host '[ERROR] Cannot find news-hub conda python, trying system python' -ForegroundColor Red
        python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
    }
}
"@

        Start-Process powershell -ArgumentList "-NoExit", "-Command", $backendCmd
        Write-Host "  ✓ 在新窗口中启动" -ForegroundColor Green
        $componentsStarted += "Backend"
        Start-Sleep -Seconds 3
    }
    Write-Host ""
}

# Start Frontend
if ($Frontend) {
    Write-Host "启动前端..." -ForegroundColor Yellow
    Write-Host "  检查端口 5173..." -NoNewline

    if (Test-Port 5173) {
        Write-Host " 已运行" -ForegroundColor Green
        $componentsStarted += "Frontend (已存在)"
    } else {
        Write-Host " 启动中..." -ForegroundColor Gray

        # 创建前端启动命令
        $frontendDir = Join-Path $projectRoot "frontend"
        $frontendCmd = @"
`$Host.UI.RawUI.WindowTitle = 'News Hub Frontend'
Write-Host '========================================' -ForegroundColor Cyan
Write-Host '   News Hub Frontend' -ForegroundColor Cyan
Write-Host '========================================' -ForegroundColor Cyan
Write-Host ''

Set-Location '$frontendDir'

# 检查 node_modules
if (-not (Test-Path 'node_modules')) {
    Write-Host '[INFO] Installing dependencies...' -ForegroundColor Yellow
    npm install
    if (`$LASTEXITCODE -ne 0) {
        Write-Host ''
        Write-Host '[ERROR] npm install failed' -ForegroundColor Red
        Read-Host 'Press Enter to exit'
        exit 1
    }
}

Write-Host ''
Write-Host 'Frontend: http://localhost:5173' -ForegroundColor Cyan
Write-Host 'Press Ctrl+C to stop' -ForegroundColor Yellow
Write-Host ''

npm run dev
"@

        Start-Process powershell -ArgumentList "-NoExit", "-Command", $frontendCmd
        Write-Host "  ✓ 在新窗口中启动" -ForegroundColor Green
        $componentsStarted += "Frontend"
        Start-Sleep -Seconds 2
    }
    Write-Host ""
}

# Summary
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   启动完成" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

if ($componentsStarted.Count -gt 0) {
    Write-Host "已启动的组件:" -ForegroundColor Green
    foreach ($component in $componentsStarted) {
        Write-Host "  ✓ $component" -ForegroundColor Gray
    }
    Write-Host ""
}

Write-Host "访问地址:" -ForegroundColor Yellow
if ($Frontend -or $startAll) {
    Write-Host "  前端:      http://localhost:5173" -ForegroundColor Cyan
}
if ($Backend -or $startAll) {
    Write-Host "  后端:      http://localhost:8000" -ForegroundColor Cyan
    Write-Host "  API 文档:  http://localhost:8000/docs" -ForegroundColor Cyan
    Write-Host "  健康检查:  http://localhost:8000/health" -ForegroundColor Cyan
}
if ($Elasticsearch -or $startAll) {
    Write-Host "  Elasticsearch: http://localhost:9200" -ForegroundColor Cyan
}
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "按任意键退出..." -ForegroundColor Gray
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")

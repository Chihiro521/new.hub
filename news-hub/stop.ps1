# ============================================
# News Hub 停止脚本
# ============================================
# 主要用于停止后台运行的 Elasticsearch
# 后端和前端直接关闭 PowerShell 窗口即可
# ============================================

param(
    [switch]$Backend,
    [switch]$Frontend,
    [switch]$Elasticsearch,
    [switch]$All,
    [switch]$Help
)

$Host.UI.RawUI.WindowTitle = "News Hub - Stop Services"

# 显示帮助信息
if ($Help) {
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "   News Hub 停止脚本" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "说明:" -ForegroundColor Yellow
    Write-Host "  后端和前端: 直接关闭 PowerShell 窗口即可"
    Write-Host "  Elasticsearch: 需要使用此脚本停止"
    Write-Host ""
    Write-Host "用法:" -ForegroundColor Yellow
    Write-Host "  .\stop.ps1                    # 停止 Elasticsearch"
    Write-Host "  .\stop.ps1 -All               # 停止所有组件"
    Write-Host "  .\stop.ps1 -Elasticsearch     # 停止 Elasticsearch"
    Write-Host "  .\stop.ps1 -Backend           # 强制停止后端"
    Write-Host "  .\stop.ps1 -Frontend          # 强制停止前端"
    Write-Host ""
    exit 0
}

# 默认停止 Elasticsearch
if (-not ($Backend -or $Frontend -or $Elasticsearch -or $All)) {
    $Elasticsearch = $true
}

if ($All) {
    $Backend = $true
    $Frontend = $true
    $Elasticsearch = $true
}

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   News Hub - 停止服务" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$stopped = @()

# Stop Elasticsearch (主要功能)
if ($Elasticsearch) {
    Write-Host "停止 Elasticsearch..." -ForegroundColor Yellow
    $esProcesses = Get-NetTCPConnection -LocalPort 9200 -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique

    if ($esProcesses) {
        foreach ($pid in $esProcesses) {
            try {
                $process = Get-Process -Id $pid -ErrorAction SilentlyContinue
                if ($process) {
                    Stop-Process -Id $pid -Force
                    Write-Host "  ✓ 已停止 Elasticsearch (PID: $pid)" -ForegroundColor Green
                    $stopped += "Elasticsearch"
                }
            } catch {
                Write-Host "  ✗ 无法停止进程 $pid" -ForegroundColor Red
            }
        }
    } else {
        Write-Host "  - Elasticsearch 未运行" -ForegroundColor Gray
    }
    Write-Host ""
}

# Stop Frontend (可选)
if ($Frontend) {
    Write-Host "停止前端..." -ForegroundColor Yellow
    Write-Host "  提示: 建议直接关闭前端的 PowerShell 窗口" -ForegroundColor Gray
    $frontendProcesses = Get-NetTCPConnection -LocalPort 5173 -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique

    if ($frontendProcesses) {
        foreach ($pid in $frontendProcesses) {
            try {
                $process = Get-Process -Id $pid -ErrorAction SilentlyContinue
                if ($process) {
                    Stop-Process -Id $pid -Force
                    Write-Host "  ✓ 已停止前端 (PID: $pid)" -ForegroundColor Green
                    $stopped += "Frontend"
                }
            } catch {
                Write-Host "  ✗ 无法停止进程 $pid" -ForegroundColor Red
            }
        }
    } else {
        Write-Host "  - 前端未运行" -ForegroundColor Gray
    }
    Write-Host ""
}

# Stop Backend (可选)
if ($Backend) {
    Write-Host "停止后端..." -ForegroundColor Yellow
    Write-Host "  提示: 建议直接关闭后端的 PowerShell 窗口" -ForegroundColor Gray
    $backendProcesses = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique

    if ($backendProcesses) {
        foreach ($pid in $backendProcesses) {
            try {
                $process = Get-Process -Id $pid -ErrorAction SilentlyContinue
                if ($process) {
                    Stop-Process -Id $pid -Force
                    Write-Host "  ✓ 已停止后端 (PID: $pid)" -ForegroundColor Green
                    $stopped += "Backend"
                }
            } catch {
                Write-Host "  ✗ 无法停止进程 $pid" -ForegroundColor Red
            }
        }
    } else {
        Write-Host "  - 后端未运行" -ForegroundColor Gray
    }
    Write-Host ""
}

# Summary
Write-Host "========================================" -ForegroundColor Cyan
if ($stopped.Count -gt 0) {
    Write-Host "已停止 $($stopped.Count) 个组件" -ForegroundColor Green
} else {
    Write-Host "没有组件需要停止" -ForegroundColor Gray
}
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "按任意键退出..." -ForegroundColor Gray
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
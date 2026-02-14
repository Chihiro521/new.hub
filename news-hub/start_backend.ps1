# ============================================
# Start News Hub Backend
# ============================================

$Host.UI.RawUI.WindowTitle = "News Hub Backend"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   Starting News Hub Backend" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$backendDir = Join-Path $PSScriptRoot "backend"

# Initialize conda
$condaRoot = $null
try {
    $condaRoot = (conda info --base 2>$null).Trim()
} catch {}

if ($condaRoot) {
    $condaHook = Join-Path $condaRoot "shell\condabin\conda-hook.ps1"
    if (Test-Path $condaHook) {
        . $condaHook
        conda activate news-hub
        
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[WARNING] Cannot activate news-hub environment" -ForegroundColor Yellow
            Write-Host "Trying system Python..." -ForegroundColor Gray
        }
    }
}

# If conda failed, try direct path
if (-not $Env:CONDA_DEFAULT_ENV -or $Env:CONDA_DEFAULT_ENV -ne "news-hub") {
    if ($condaRoot) {
        $envPath = Join-Path $condaRoot "envs\news-hub"
        $pythonExe = Join-Path $envPath "python.exe"
        if (Test-Path $pythonExe) {
            $Env:PATH = "$envPath;$envPath\Scripts;$Env:PATH"
            Write-Host "Using environment: $envPath" -ForegroundColor Gray
        }
    }
}

# Check uvicorn
$uvicornCmd = Get-Command uvicorn -ErrorAction SilentlyContinue
if (-not $uvicornCmd) {
    Write-Host "[ERROR] uvicorn not found" -ForegroundColor Red
    Write-Host "Please run .\install_deps.ps1 first" -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host "Working directory: $backendDir" -ForegroundColor Gray
Write-Host ""
Write-Host "Press Ctrl+C to stop" -ForegroundColor Yellow
Write-Host ""
Write-Host "API docs: http://localhost:8000/docs" -ForegroundColor Green
Write-Host "Health:   http://localhost:8000/health" -ForegroundColor Green
Write-Host ""

Set-Location $backendDir
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "[ERROR] Backend failed to start" -ForegroundColor Red
    Write-Host ""
    Write-Host "Common issues:" -ForegroundColor Yellow
    Write-Host "  1. Dependencies not installed - run .\install_deps.ps1"
    Write-Host "  2. Port 8000 in use"
    Write-Host "  3. MongoDB not running"
    Write-Host ""
    Read-Host "Press Enter to exit"
}

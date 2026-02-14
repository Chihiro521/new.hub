# ============================================
# News Hub - Install Python Dependencies
# ============================================

$ErrorActionPreference = "Stop"
$Host.UI.RawUI.WindowTitle = "News Hub - Install Dependencies"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   News Hub - Python Dependencies" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$BACKEND_DIR = Join-Path $PSScriptRoot "backend"

# Check conda
$condaCmd = Get-Command conda -ErrorAction SilentlyContinue
if (-not $condaCmd) {
    Write-Host "[ERROR] conda not found" -ForegroundColor Red
    Write-Host "Please ensure Anaconda/Miniconda is installed and in PATH" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Or use system Python directly:" -ForegroundColor Yellow
    Write-Host "  cd backend"
    Write-Host "  pip install -r requirements-core.txt --index-url https://pypi.org/simple"
    Read-Host "Press Enter to exit"
    exit 1
}

# Initialize conda
Write-Host "[1/5] Initializing Conda..." -ForegroundColor Green

$condaRoot = $null
try {
    $condaRoot = (conda info --base 2>$null).Trim()
} catch {}

if ($condaRoot) {
    $condaHook = Join-Path $condaRoot "shell\condabin\conda-hook.ps1"
    if (Test-Path $condaHook) {
        . $condaHook
    }
}

# Check/create environment
Write-Host "[2/5] Checking conda environment: news-hub" -ForegroundColor Green
$envList = conda env list 2>$null
$envExists = $envList | Select-String "news-hub"

if (-not $envExists) {
    Write-Host "[INFO] Environment news-hub does not exist, creating..." -ForegroundColor Yellow
    conda create -n news-hub python=3.10 -y
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] Failed to create conda environment" -ForegroundColor Red
        Read-Host "Press Enter to exit"
        exit 1
    }
}

# Activate environment
Write-Host "[3/5] Activating conda environment" -ForegroundColor Green
conda activate news-hub

if ($LASTEXITCODE -ne 0) {
    Write-Host "[WARNING] conda activate failed, trying direct path..." -ForegroundColor Yellow
    $envPath = Join-Path $condaRoot "envs\news-hub"
    $pythonExe = Join-Path $envPath "python.exe"
    if (Test-Path $pythonExe) {
        $Env:PATH = "$envPath;$envPath\Scripts;$Env:PATH"
        $Env:CONDA_DEFAULT_ENV = "news-hub"
        Write-Host "Using environment at: $envPath" -ForegroundColor Gray
    } else {
        Write-Host "[ERROR] Cannot activate environment" -ForegroundColor Red
        Read-Host "Press Enter to exit"
        exit 1
    }
}

# Clear any cached pip config that might point to broken mirrors
$Env:PIP_INDEX_URL = "https://pypi.org/simple"

Write-Host ""
Write-Host "[4/5] Installing core dependencies (FastAPI, MongoDB, ES)..." -ForegroundColor Green
Write-Host "      Using official PyPI" -ForegroundColor Gray
Write-Host ""

Set-Location $BACKEND_DIR
pip install -r requirements-core.txt --index-url https://pypi.org/simple

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "[ERROR] Core dependencies installation failed!" -ForegroundColor Red
    Write-Host ""
    Write-Host "Try manual install:" -ForegroundColor Yellow
    Write-Host "  conda activate news-hub"
    Write-Host "  cd backend"
    Write-Host "  pip install -r requirements-core.txt --index-url https://pypi.org/simple"
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "   Core dependencies installed!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Backend can now start (ES and crawler deps can be installed later)" -ForegroundColor Cyan
Write-Host ""

$continue = Read-Host "Install crawler dependencies? (y/N)"
if ($continue -eq "y" -or $continue -eq "Y") {
    Write-Host ""
    Write-Host "[5/5] Installing crawler dependencies (Scrapy, BeautifulSoup)..." -ForegroundColor Green
    pip install -r requirements-crawler.txt --index-url https://pypi.org/simple
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[WARNING] Crawler dependencies failed, can retry later" -ForegroundColor Yellow
    }
} else {
    Write-Host ""
    Write-Host "Skipping crawler dependencies. Install later with:" -ForegroundColor Yellow
    Write-Host "  pip install -r requirements-crawler.txt --index-url https://pypi.org/simple"
}

$installML = Read-Host "Install vector search dependencies? (~500MB download, y/N)"
if ($installML -eq "y" -or $installML -eq "Y") {
    Write-Host ""
    Write-Host "Installing PyTorch CPU version..." -ForegroundColor Green
    pip install torch --index-url https://download.pytorch.org/whl/cpu
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Installing Sentence-Transformers..." -ForegroundColor Green
        pip install sentence-transformers --index-url https://pypi.org/simple
    } else {
        Write-Host "[WARNING] PyTorch install failed, vector search will be unavailable" -ForegroundColor Yellow
    }
} else {
    Write-Host ""
    Write-Host "Skipping vector search dependencies. Install later with:" -ForegroundColor Yellow
    Write-Host "  pip install torch --index-url https://download.pytorch.org/whl/cpu"
    Write-Host "  pip install sentence-transformers"
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "   Installation complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Start backend:" -ForegroundColor Cyan
Write-Host "  conda activate news-hub"
Write-Host "  cd backend"
Write-Host "  python -m uvicorn app.main:app --reload --port 8000"
Write-Host ""
Write-Host "Access:" -ForegroundColor Cyan
Write-Host "  API docs: http://localhost:8000/docs"
Write-Host "  Health:   http://localhost:8000/health"
Write-Host ""
Read-Host "Press Enter to exit"

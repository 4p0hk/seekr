# startup.ps1
# Bootstraps the environment for seekr.py, run it once before you use seekr

$venvPath = ".\.venv"

Write-Host "=== Setting up Python virtual environment ==="

# 1. Create venv if missing
if (-not (Test-Path $venvPath)) {
    Write-Host "Creating virtual environment..."
    python -m venv .venv
} else {
    Write-Host "Virtual environment already exists."
}

# 2. Activate venv
$activate = Join-Path $venvPath "Scripts\Activate.ps1"
if (Test-Path $activate) {
    Write-Host "Activating virtual environment..."
    & $activate
} else {
    Write-Error "Could not find activation script at $activate"
    exit 1
}

# 3. Install dependencies
Write-Host "Installing dependencies..."
$deps = @(
    "rapidfuzz",
    "pyrekordbox",
    "tabulate",
    "colorama",
    "tqdm",
    "sqlcipher3-wheels"
)
pip install $deps -q

Write-Host "=== Environment ready. You can now run seekr.py ==="

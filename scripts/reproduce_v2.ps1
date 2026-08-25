# Reproduce the V2 evaluation from scratch
Write-Host "Running RecoverAI V2 Reproducibility Check..."

# Ensure we're in the project root
$scriptPath = $MyInvocation.MyCommand.Path
$dir = Split-Path (Split-Path $scriptPath)
Set-Location $dir

# Create and activate virtual environment if it doesn't exist
if (-Not (Test-Path "backend\.venv")) {
    Write-Host "Creating virtual environment..."
    python -m venv backend\.venv
}

# Install dependencies
Write-Host "Installing dependencies..."
& backend\.venv\Scripts\pip install -r backend\requirements.txt

# Run safety tests
Write-Host "Running safety tests..."
$env:PYTHONPATH = "$dir\backend"
& backend\.venv\Scripts\pytest backend\tests\ -v
if ($LASTEXITCODE -ne 0) {
    Write-Host "Safety tests failed!" -ForegroundColor Red
    exit $LASTEXITCODE
}

# Run batch evaluation
Write-Host "Running batch evaluation..."
& backend\.venv\Scripts\python scripts\evaluate_batch.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "Evaluation failed!" -ForegroundColor Red
    exit $LASTEXITCODE
}

Write-Host "Reproducibility Check Complete! Results are in data/v2/evaluation_results_v2.json and docs/evaluation.md" -ForegroundColor Green

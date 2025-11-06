# PowerShell setup script for Windows
Write-Host "🚀 Setting up One Smart Trade..." -ForegroundColor Green

# Backend setup
Write-Host "📦 Setting up backend..." -ForegroundColor Cyan
Set-Location backend
if (-not (Get-Command poetry -ErrorAction SilentlyContinue)) {
    Write-Host "Installing Poetry..." -ForegroundColor Yellow
    (Invoke-WebRequest -Uri https://install.python-poetry.org -UseBasicParsing).Content | python -
}
poetry install
Set-Location ..

# Frontend setup
Write-Host "📦 Setting up frontend..." -ForegroundColor Cyan
Set-Location frontend
if (-not (Get-Command pnpm -ErrorAction SilentlyContinue)) {
    Write-Host "Installing pnpm..." -ForegroundColor Yellow
    npm install -g pnpm
}
pnpm install
Set-Location ..

Write-Host "✅ Setup complete!" -ForegroundColor Green
Write-Host ""
Write-Host "To run backend: cd backend && poetry run uvicorn app.main:app --reload"
Write-Host "To run frontend: cd frontend && pnpm run dev"


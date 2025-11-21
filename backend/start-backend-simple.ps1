# Script simple para iniciar el backend sin Poetry (si ya tienes el entorno activo)
# Uso: .\start-backend-simple.ps1

Set-Location "$PSScriptRoot"

Write-Host "Iniciando backend (sin Poetry)..." -ForegroundColor Cyan
Write-Host "Asegúrate de tener el entorno virtual activado o las dependencias instaladas globalmente" -ForegroundColor Yellow
Write-Host ""

# Verificar si uvicorn está disponible
try {
    python -m uvicorn app.main:app --reload --port 8000
} catch {
    Write-Host "Error: uvicorn no está disponible." -ForegroundColor Red
    Write-Host ""
    Write-Host "Opciones:" -ForegroundColor Yellow
    Write-Host "  1. Instala Poetry y usa: .\start-dev.ps1" -ForegroundColor Cyan
    Write-Host "  2. Activa un entorno virtual con uvicorn instalado" -ForegroundColor Cyan
    Write-Host "  3. Instala uvicorn: pip install uvicorn[standard]" -ForegroundColor Cyan
    exit 1
}


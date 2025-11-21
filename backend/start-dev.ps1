# Script para iniciar el servidor de desarrollo del backend
# Uso: .\start-dev.ps1

Set-Location "$PSScriptRoot"

Write-Host "Iniciando servidor de desarrollo del backend..." -ForegroundColor Cyan
Write-Host "El servidor estará disponible en http://localhost:8000" -ForegroundColor Green
Write-Host "Presiona Ctrl+C para detener el servidor" -ForegroundColor Yellow
Write-Host ""

# Verificar si Poetry está instalado
if (-not (Get-Command poetry -ErrorAction SilentlyContinue)) {
    Write-Host "ERROR: Poetry no está instalado o no está en PATH." -ForegroundColor Red
    Write-Host "Por favor instala Poetry desde: https://python-poetry.org/docs/#installation" -ForegroundColor Yellow
    exit 1
}

# Verificar si el puerto 8000 está en uso
$portInUse = Test-NetConnection -ComputerName localhost -Port 8000 -InformationLevel Quiet -WarningAction SilentlyContinue
if ($portInUse) {
    Write-Host "ADVERTENCIA: El puerto 8000 ya está en uso." -ForegroundColor Yellow
    Write-Host "Por favor detén el proceso que está usando el puerto 8000 o cambia el puerto en vite.config.ts" -ForegroundColor Yellow
    Write-Host ""
}

# Iniciar el servidor
try {
    poetry run uvicorn app.main:app --reload --port 8000
} catch {
    Write-Host "Error al iniciar el servidor: $_" -ForegroundColor Red
    exit 1
}


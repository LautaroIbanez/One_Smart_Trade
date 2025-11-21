# Script para iniciar el servidor de desarrollo del backend
# Uso: .\start-dev.ps1

Set-Location "$PSScriptRoot"

Write-Host "Iniciando servidor de desarrollo del backend..." -ForegroundColor Cyan
Write-Host "El servidor estará disponible en http://localhost:8000" -ForegroundColor Green
Write-Host "Presiona Ctrl+C para detener el servidor" -ForegroundColor Yellow
Write-Host ""

# Verificar si Poetry está instalado
$poetryCmd = $null
if (Get-Command poetry -ErrorAction SilentlyContinue) {
    $poetryCmd = "poetry"
} else {
    # Intentar encontrar Poetry en ubicaciones comunes
    $poetryPaths = @(
        "$env:APPDATA\Python\Scripts\poetry.exe",
        "$env:LOCALAPPDATA\Programs\Python\Scripts\poetry.exe",
        "$env:USERPROFILE\.local\bin\poetry.exe",
        "$env:USERPROFILE\AppData\Roaming\Python\Scripts\poetry.exe"
    )
    
    foreach ($path in $poetryPaths) {
        if (Test-Path $path) {
            $poetryCmd = $path
            Write-Host "Poetry encontrado en: $path" -ForegroundColor Green
            break
        }
    }
    
    if (-not $poetryCmd) {
        Write-Host "ERROR: Poetry no está instalado o no está en PATH." -ForegroundColor Red
        Write-Host "Por favor instala Poetry desde: https://python-poetry.org/docs/#installation" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "O ejecuta manualmente:" -ForegroundColor Yellow
        Write-Host "  python -m pip install poetry" -ForegroundColor Cyan
        Write-Host "  poetry run uvicorn app.main:app --reload --port 8000" -ForegroundColor Cyan
        exit 1
    }
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
    & $poetryCmd run uvicorn app.main:app --reload --port 8000
} catch {
    Write-Host "Error al iniciar el servidor: $_" -ForegroundColor Red
    Write-Host ""
    Write-Host "Si Poetry no funciona, intenta:" -ForegroundColor Yellow
    Write-Host "  1. Activar el entorno virtual: poetry shell" -ForegroundColor Cyan
    Write-Host "  2. Ejecutar directamente: uvicorn app.main:app --reload --port 8000" -ForegroundColor Cyan
    exit 1
}


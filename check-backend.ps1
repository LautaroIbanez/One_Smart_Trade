# Script para verificar si el backend esta corriendo
# Uso: .\check-backend.ps1

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Verificacion del Backend" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

$backendUrl = "http://localhost:8000"
$healthUrl = "$backendUrl/health"
$recommendationUrl = "$backendUrl/api/v1/recommendation/today"

# Verificar puerto
Write-Host "1. Verificando puerto 8000..." -ForegroundColor Yellow
$portCheck = Test-NetConnection -ComputerName localhost -Port 8000 -InformationLevel Quiet -WarningAction SilentlyContinue

if ($portCheck) {
    Write-Host "   [OK] Puerto 8000 esta en uso" -ForegroundColor Green
} else {
    Write-Host "   [ERROR] Puerto 8000 NO esta en uso" -ForegroundColor Red
    Write-Host ""
    Write-Host "   El backend no esta corriendo." -ForegroundColor Red
    Write-Host "   Para iniciarlo, ejecuta:" -ForegroundColor Yellow
    Write-Host "     cd backend" -ForegroundColor White
    Write-Host "     .\start-dev.ps1" -ForegroundColor White
    Write-Host "   O:" -ForegroundColor Yellow
    Write-Host "     poetry run uvicorn app.main:app --reload --port 8000" -ForegroundColor White
    exit 1
}

Write-Host ""

# Verificar health endpoint
Write-Host "2. Verificando endpoint de salud..." -ForegroundColor Yellow
try {
    $healthResponse = Invoke-WebRequest -Uri $healthUrl -TimeoutSec 5 -UseBasicParsing -ErrorAction Stop
    if ($healthResponse.StatusCode -eq 200) {
        Write-Host "   [OK] Backend responde correctamente (200 OK)" -ForegroundColor Green
        Write-Host "   Respuesta: $($healthResponse.Content)" -ForegroundColor Gray
    } else {
        Write-Host "   [WARN] Backend responde con codigo: $($healthResponse.StatusCode)" -ForegroundColor Yellow
    }
} catch {
    Write-Host "   [ERROR] Backend NO responde: $_" -ForegroundColor Red
    Write-Host ""
    Write-Host "   El backend puede estar iniciando o tener problemas." -ForegroundColor Yellow
    Write-Host "   Revisa los logs del backend para mas detalles." -ForegroundColor Yellow
    exit 1
}

Write-Host ""

# Verificar endpoint de recomendacion
Write-Host "3. Verificando endpoint de recomendacion..." -ForegroundColor Yellow
try {
    $recResponse = Invoke-WebRequest -Uri $recommendationUrl -TimeoutSec 10 -UseBasicParsing -ErrorAction Stop
    if ($recResponse.StatusCode -eq 200) {
        Write-Host "   [OK] Endpoint de recomendacion responde (200 OK)" -ForegroundColor Green
    } elseif ($recResponse.StatusCode -eq 400 -or $recResponse.StatusCode -eq 503) {
        Write-Host "   [WARN] Endpoint responde pero no hay datos (codigo: $($recResponse.StatusCode))" -ForegroundColor Yellow
        Write-Host "   Esto es normal si la base de datos esta vacia." -ForegroundColor Gray
        Write-Host "   Ejecuta: python scripts/populate_database.py" -ForegroundColor Yellow
    } else {
        Write-Host "   [WARN] Endpoint responde con codigo: $($recResponse.StatusCode)" -ForegroundColor Yellow
    }
} catch {
    if ($_.Exception.Response -and ($_.Exception.Response.StatusCode -eq 400 -or $_.Exception.Response.StatusCode -eq 503)) {
        Write-Host "   [WARN] Endpoint responde pero no hay datos (codigo: $($_.Exception.Response.StatusCode))" -ForegroundColor Yellow
        Write-Host "   Esto es normal si la base de datos esta vacia." -ForegroundColor Gray
        Write-Host "   Ejecuta: python scripts/populate_database.py" -ForegroundColor Yellow
    } else {
        Write-Host "   [ERROR] Error al verificar endpoint: $_" -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "[OK] Backend esta corriendo y accesible" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Puedes iniciar el frontend ahora:" -ForegroundColor Yellow
Write-Host "  cd frontend" -ForegroundColor White
Write-Host "  pnpm run dev" -ForegroundColor White
Write-Host ""


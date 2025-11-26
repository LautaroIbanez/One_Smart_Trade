# Script de diagnóstico para problemas de frontend sin datos / timeouts
# Basado en: docs/runbooks/frontend_no_data.md
# Uso: .\scripts\diagnose_frontend_issues.ps1

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Diagnóstico: Frontend sin datos / timeouts" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

$issues = @()
$warnings = @()
$success = @()

# Paso 1: Verificar salud del backend
Write-Host "1. Verificando salud del backend..." -ForegroundColor Yellow
Write-Host "   NOTA: Si el pipeline inicial esta corriendo, el servidor puede tardar varios minutos en responder." -ForegroundColor Cyan
Write-Host "   Esto es normal durante el primer arranque. Espera a que termine el pipeline." -ForegroundColor Cyan
$backendUrl = "http://127.0.0.1:8000"
try {
    $healthResponse = Invoke-WebRequest -Uri "$backendUrl/health" -UseBasicParsing -TimeoutSec 60 -ErrorAction Stop
    if ($healthResponse.StatusCode -eq 200) {
        Write-Host "   [OK] Backend esta corriendo (Status: 200)" -ForegroundColor Green
        $success += "Backend corriendo"
    } elseif ($healthResponse.StatusCode -eq 202) {
        Write-Host "   [PROCESSING] Backend esta corriendo pero el pipeline inicial esta en ejecucion (Status: 202)" -ForegroundColor Yellow
        $json = $healthResponse.Content | ConvertFrom-Json
        Write-Host "      Estado: $($json.status)" -ForegroundColor Yellow
        if ($json.pipeline) {
            Write-Host "      Pipeline iniciado: $($json.pipeline.started_at)" -ForegroundColor Yellow
            Write-Host "      Pipeline corriendo: $($json.pipeline.running)" -ForegroundColor Yellow
        }
        $success += "Backend corriendo"
        $warnings += "Pipeline inicial en ejecucion - espera a que termine"
    } else {
        Write-Host "   [WARN] Backend responde con codigo: $($healthResponse.StatusCode)" -ForegroundColor Yellow
        $warnings += "Backend responde con codigo no estandar"
    }
} catch {
    # Intentar también con localhost por si acaso
    try {
        $healthResponse = Invoke-WebRequest -Uri "http://localhost:8000/health" -UseBasicParsing -TimeoutSec 60 -ErrorAction Stop
        if ($healthResponse.StatusCode -eq 200) {
            Write-Host "   [OK] Backend esta corriendo en localhost (Status: 200)" -ForegroundColor Green
            $backendUrl = "http://localhost:8000"
            $success += "Backend corriendo"
        } elseif ($healthResponse.StatusCode -eq 202) {
            Write-Host "   [PROCESSING] Backend esta corriendo en localhost pero el pipeline inicial esta en ejecucion (Status: 202)" -ForegroundColor Yellow
            $json = $healthResponse.Content | ConvertFrom-Json
            Write-Host "      Estado: $($json.status)" -ForegroundColor Yellow
            if ($json.pipeline) {
                Write-Host "      Pipeline iniciado: $($json.pipeline.started_at)" -ForegroundColor Yellow
            }
            $backendUrl = "http://localhost:8000"
            $success += "Backend corriendo"
            $warnings += "Pipeline inicial en ejecucion - espera a que termine"
        }
    } catch {
        Write-Host "   [ERROR] Backend NO esta corriendo en http://127.0.0.1:8000 o http://localhost:8000" -ForegroundColor Red
        Write-Host "      Error: $_" -ForegroundColor Red
        $issues += "Backend no esta corriendo"
        Write-Host ""
        Write-Host "   SOLUCION: Inicia el backend con:" -ForegroundColor Yellow
        Write-Host "      .\start-dev.ps1" -ForegroundColor Cyan
        Write-Host "      O: poetry run uvicorn app.main:app --reload --port 8000" -ForegroundColor Cyan
        Write-Host ""
    }
}

# Paso 2: Verificar estado del pipeline
Write-Host "2. Verificando estado del pipeline inicial..." -ForegroundColor Yellow
Write-Host "   NOTA: Si el pipeline esta corriendo, esto puede tardar varios minutos." -ForegroundColor Cyan
try {
    $recResponse = Invoke-WebRequest -Uri "$backendUrl/api/v1/recommendation/today" -UseBasicParsing -TimeoutSec 60 -ErrorAction Stop
    if ($recResponse.StatusCode -eq 202) {
        Write-Host "   [PROCESSING] Pipeline esta corriendo (202 Processing)" -ForegroundColor Yellow
        $json = $recResponse.Content | ConvertFrom-Json
        Write-Host "      Estado: $($json.status)" -ForegroundColor Yellow
        if ($json.pipeline) {
            Write-Host "      Iniciado: $($json.pipeline.started_at)" -ForegroundColor Yellow
            Write-Host "      Running: $($json.pipeline.running)" -ForegroundColor Yellow
        }
        $warnings += "Pipeline inicial en ejecucion - espera a que termine"
        Write-Host ""
        Write-Host "   NOTA: El frontend reintentara automaticamente. Espera a que el pipeline termine." -ForegroundColor Cyan
    } elseif ($recResponse.StatusCode -eq 200) {
        Write-Host "   [OK] Endpoint responde correctamente (200 OK)" -ForegroundColor Green
        $json = $recResponse.Content | ConvertFrom-Json
        if ($json.status -eq "no_data") {
            Write-Host "      [WARN] No hay recomendacion disponible aun" -ForegroundColor Yellow
            $warnings += "No hay recomendacion disponible"
        } else {
            Write-Host "      [OK] Hay datos disponibles" -ForegroundColor Green
            $success += "Datos disponibles en endpoint"
        }
    } else {
        Write-Host "   [WARN] Endpoint responde con codigo: $($recResponse.StatusCode)" -ForegroundColor Yellow
        $warnings += "Endpoint responde con codigo no estandar: $($recResponse.StatusCode)"
    }
} catch {
    if ($_.Exception.Response) {
        $statusCode = [int]$_.Exception.Response.StatusCode
        Write-Host "   [WARN] Endpoint responde con codigo: $statusCode" -ForegroundColor Yellow
        if ($statusCode -eq 202) {
            Write-Host "      Pipeline esta corriendo (202 Processing)" -ForegroundColor Yellow
            $warnings += "Pipeline inicial en ejecucion"
        }
    } else {
        Write-Host "   [ERROR] No se pudo conectar al endpoint" -ForegroundColor Red
        $issues += "No se puede conectar al endpoint de recomendacion"
    }
}
Write-Host ""

# Paso 3: Verificar datos curados
Write-Host "3. Verificando datos curados..." -ForegroundColor Yellow
$dataPaths = @(
    "data\curated\1d\latest.parquet",
    "data\curated\1h\latest.parquet",
    "data\curated\binance\BTCUSDT\1d\latest.parquet",
    "data\curated\binance\BTCUSDT\1h\latest.parquet"
)

$dataFound = $false
foreach ($path in $dataPaths) {
    if (Test-Path $path) {
        $file = Get-Item $path
        Write-Host "   [OK] $path existe (Ultima modificacion: $($file.LastWriteTime))" -ForegroundColor Green
        $dataFound = $true
    }
}

if (-not $dataFound) {
    Write-Host "   [ERROR] No se encontraron datos curados" -ForegroundColor Red
    $issues += "Datos curados faltantes"
    Write-Host ""
    Write-Host "   SOLUCION: Ejecuta el pipeline para poblar datos:" -ForegroundColor Yellow
    Write-Host "      python scripts\populate_database.py" -ForegroundColor Cyan
} else {
    $success += "Datos curados disponibles"
}
Write-Host ""

# Paso 4: Verificar base de datos
Write-Host "4. Verificando base de datos..." -ForegroundColor Yellow
if (Test-Path "data\trading.db") {
    $db = Get-Item "data\trading.db"
    $dbSize = [math]::Round($db.Length / 1KB, 2)
    Write-Host "   [OK] Base de datos existe (Tamano: $dbSize KB, Ultima modificacion: $($db.LastWriteTime))" -ForegroundColor Green
    $success += "Base de datos existe"
} else {
    Write-Host "   [WARN] Base de datos no encontrada (se creara automaticamente al iniciar el backend)" -ForegroundColor Yellow
    $warnings += "Base de datos no existe aun"
}
Write-Host ""

# Paso 5: Verificar configuración del frontend
Write-Host "5. Verificando configuración del frontend..." -ForegroundColor Yellow
$frontendEnv = "..\frontend\.env"
if (Test-Path $frontendEnv) {
    Write-Host "   [OK] Archivo .env encontrado en frontend" -ForegroundColor Green
    $envContent = Get-Content $frontendEnv
    $apiUrl = $envContent | Where-Object { $_ -match "VITE_API_BASE_URL" }
    if ($apiUrl) {
        Write-Host "      $apiUrl" -ForegroundColor Cyan
        $success += "VITE_API_BASE_URL configurado"
    } else {
        Write-Host "      [WARN] VITE_API_BASE_URL no esta configurado (usara proxy por defecto)" -ForegroundColor Yellow
        $warnings += "VITE_API_BASE_URL no configurado"
    }
} else {
    Write-Host "   [WARN] Archivo .env no encontrado en frontend (usara configuracion por defecto)" -ForegroundColor Yellow
    Write-Host "      Si el backend no esta en localhost:8000, crea frontend\.env con:" -ForegroundColor Cyan
    Write-Host "      VITE_API_BASE_URL=http://TU_HOST:TU_PUERTO" -ForegroundColor Cyan
    $warnings += "Archivo .env del frontend no existe"
}
Write-Host ""

# Paso 6: Verificar CORS
Write-Host "6. Verificando configuración CORS..." -ForegroundColor Yellow
Write-Host "   Los puertos comunes de desarrollo deberian estar en CORS_ORIGINS:" -ForegroundColor Cyan
Write-Host "   - http://localhost:5173 (Vite default)" -ForegroundColor Cyan
Write-Host "   - http://localhost:3000 (React default)" -ForegroundColor Cyan
Write-Host "   - http://127.0.0.1:5173 (Vite alternativo)" -ForegroundColor Cyan
Write-Host ""
Write-Host "   Si usas otro puerto, anadelo a backend\.env:" -ForegroundColor Yellow
Write-Host "   CORS_ORIGINS=[`"http://localhost:5173`",`"http://localhost:TU_PUERTO`"]" -ForegroundColor Cyan
Write-Host ""

# Resumen
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Resumen del Diagnóstico" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

if ($success.Count -gt 0) {
    Write-Host "[OK] Exitos:" -ForegroundColor Green
    foreach ($item in $success) {
        Write-Host "   - $item" -ForegroundColor Green
    }
    Write-Host ""
}

if ($warnings.Count -gt 0) {
    Write-Host "[WARN] Advertencias:" -ForegroundColor Yellow
    foreach ($item in $warnings) {
        Write-Host "   - $item" -ForegroundColor Yellow
    }
    Write-Host ""
}

if ($issues.Count -gt 0) {
    Write-Host "[ERROR] Problemas encontrados:" -ForegroundColor Red
    foreach ($item in $issues) {
        Write-Host "   - $item" -ForegroundColor Red
    }
    Write-Host ""
    Write-Host "SIGUIENTE PASO: Resuelve los problemas arriba antes de continuar." -ForegroundColor Yellow
} else {
    Write-Host "[OK] No se encontraron problemas criticos." -ForegroundColor Green
    Write-Host ""
    Write-Host "Si el frontend sigue sin datos:" -ForegroundColor Yellow
    Write-Host "   1. Asegurate de que el backend este corriendo" -ForegroundColor Cyan
    Write-Host "   2. Espera a que el pipeline inicial termine (si esta corriendo)" -ForegroundColor Cyan
    Write-Host "   3. Refresca el frontend (F5)" -ForegroundColor Cyan
    Write-Host "   4. Verifica en DevTools > Network que las peticiones vayan a la URL correcta" -ForegroundColor Cyan
}

Write-Host ""


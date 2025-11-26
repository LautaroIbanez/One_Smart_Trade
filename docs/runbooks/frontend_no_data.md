# Runbook: Frontend sin datos / timeouts

## Síntomas
- El dashboard muestra "Tiempo de espera excedido (25s)" o paneles vacíos.
- Los endpoints cargados desde el navegador retornan 504 o no muestran payloads.
- El backend está corriendo pero el frontend sigue sin datos luego de recargar.
- **Nota:** Si ves un mensaje de "procesando" o "La operación está en proceso" en lugar de timeout, el sistema está funcionando correctamente - el pipeline inicial está ejecutándose y el frontend reintentará automáticamente.

## Causas Comunes
1. **Pipeline inicial aún en ejecución**: el backend agenda el pipeline al iniciar cuando no hay recomendación para hoy; puede tardar varios minutos y generar timeouts en el UI.
2. **Frontend apuntando al host/puerto equivocado**: falta configurar `VITE_API_BASE_URL` cuando el backend no corre en `localhost:8000`.
3. **CORS bloqueando puertos alternativos**: si el frontend corre en un puerto no listado en `CORS_ORIGINS`, las peticiones serán rechazadas.
4. **Base de datos vacía**: la ingesta no terminó o falló y los endpoints responden sin datos.

## Diagnóstico Rápido
1. **Verificar salud del backend**
   ```powershell
   Invoke-WebRequest -Uri "http://localhost:8000/health" -UseBasicParsing
   ```
   - Respuesta 200 → el backend está vivo.
   - Si falla, inicia el backend (`poetry run uvicorn app.main:app --reload --port 8000`).

2. **Chequear si el pipeline inicial está corriendo**
   - El backend ejecuta automáticamente el pipeline si no hay recomendación del día. 
   - **Método 1: Desde la respuesta del endpoint** (recomendado)
     ```powershell
     $response = Invoke-WebRequest -Uri "http://localhost:8000/api/v1/recommendation/today" -UseBasicParsing
     if ($response.StatusCode -eq 202) {
         Write-Host "Pipeline está corriendo (202 Accepted - Processing)"
         $json = $response.Content | ConvertFrom-Json
         Write-Host "Estado: $($json.status)"
         Write-Host "Iniciado: $($json.pipeline.started_at)"
     }
     ```
   - **Método 2: Revisar logs del backend** - Busca mensajes como "Running initial pipeline on startup" o "Initial pipeline completed successfully"
   - Los endpoints ahora devuelven **HTTP 202** con estado "processing" cuando el pipeline está corriendo, evitando timeouts de 25s. El frontend maneja estos 202 automáticamente con reintentos.

3. **Probar los endpoints desde el navegador/CLI**
   ```powershell
   Invoke-WebRequest -Uri "http://localhost:8000/api/v1/recommendation/today" -UseBasicParsing
   ```
   - Si responde **200** con JSON → hay datos, refresca el frontend.
   - Si responde **202** → el pipeline está corriendo, espera y reintenta (el frontend lo hace automáticamente).
   - Si responde **400/503** pero no `ECONNREFUSED` → el backend respondió; revisa el mensaje en el JSON de respuesta.

4. **Confirmar a qué host/puerto está llamando el frontend**
   - Abre DevTools → Network → revisa una petición `/api/v1/*`.
   - Si el backend NO está en `localhost:8000`, crea `frontend/.env` con `VITE_API_BASE_URL=http://TU_HOST:TU_PUERTO` y reinicia `pnpm run dev`.

5. **Validar CORS cuando usas otro puerto**
   - Si el frontend corre en puertos 5174/5175/8080 (o cualquier otro), añade la URL a `CORS_ORIGINS` en `backend/.env` y reinicia el backend.

6. **Comprobar si la base de datos está vacía**
   ```bash
   cd backend
   python scripts/verify_endpoints.py
   ```
   - Si indica datos faltantes, ejecuta el pipeline manualmente:
   ```bash
   python scripts/populate_database.py
   ```

## Procedimiento de Mitigación
1. **Si el pipeline está corriendo (respuesta 202):**
   - Espera a que finalice. El frontend reintentará automáticamente cada pocos segundos.
   - Puedes verificar el progreso consultando el endpoint - cuando deje de devolver 202 y devuelva 200, el pipeline terminó.
   - Revisa los logs del backend para confirmar "Initial pipeline completed successfully".

2. **Si el pipeline ya terminó pero sigues sin datos:**
   - Refresca el frontend (F5).
   - Verifica que el endpoint responda 200: `Invoke-WebRequest -Uri "http://localhost:8000/api/v1/recommendation/today" -UseBasicParsing`

3. **Si sigues sin datos después del paso 2:**
   - Ajusta `VITE_API_BASE_URL` en `frontend/.env` y reinicia Vite (`pnpm run dev`).
   - Añade tu puerto a `CORS_ORIGINS` en `backend/.env` si es necesario y reinicia el backend.
   - Ejecuta `python scripts/populate_database.py` si la base estaba vacía.

4. **Verificación final:**
   - Verifica que `/api/v1/recommendation/today` responda 200 con JSON válido.
   - Si responde OK, el frontend debería cargar automáticamente (o tras un refresco).

## Puntos de Salida
- ✅ Backend responde 200 en `/health`.
- ✅ `/api/v1/recommendation/today` devuelve **200** con JSON válido (no 202, no timeout).
- ✅ Frontend muestra paneles con datos (automáticamente o tras un refresco).

## Notas Importantes

### Comportamiento Actual del Sistema
- **Los endpoints ahora devuelven HTTP 202** cuando el pipeline inicial está corriendo, en lugar de bloquear o causar timeouts.
- **El frontend maneja automáticamente los 202** con reintentos cada pocos segundos, mostrando un estado de "procesando" en lugar de errores de timeout.
- **El pipeline se ejecuta en background** al iniciar el backend, permitiendo que el servidor responda inmediatamente mientras el pipeline completa en segundo plano.

### Diferencia entre 202 y Timeout
- **HTTP 202 (Processing)**: Respuesta rápida que indica que el pipeline está corriendo. El frontend reintentará automáticamente.
- **Timeout (25s)**: Ocurre cuando el backend no responde en absoluto, generalmente por problemas de conectividad o configuración incorrecta.


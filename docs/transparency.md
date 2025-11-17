# Transparencia y Auditoría

Este documento describe el proceso de auditoría del sistema One Smart Trade, incluyendo cómo verificar hashes, interpretar el tracking error, y reproducir señales a partir de los snapshots.

## Contenido

1. [Verificación de Hashes](#verificación-de-hashes)
2. [Interpretación del Tracking Error](#interpretación-del-tracking-error)
3. [Reproducción de Señales desde Snapshots](#reproducción-de-señales-desde-snapshots)
4. [Dashboard de Observabilidad](#dashboard-de-observabilidad)
5. [Proceso de Auditoría](#proceso-de-auditoría)

---

## Verificación de Hashes

### Hashes Disponibles

Cada recomendación incluye tres hashes principales para trazabilidad:

1. **`code_commit`**: Hash del commit de Git que generó la señal
2. **`dataset_version`**: SHA-256 hash de los datasets curados utilizados
3. **`params_digest`**: SHA-256 hash de los parámetros de estrategia (`params.yaml`)

Adicionalmente, los exports incluyen:
- **`Content-MD5`**: Hash MD5 del archivo exportado (header HTTP)
- **`X-Export-File-Hash`**: Hash SHA-256 del archivo exportado (header HTTP)

### Verificación del Commit de Código

Para verificar que una señal fue generada con un commit específico:

```bash
# Obtener el commit hash de una recomendación
curl http://localhost:8000/api/v1/recommendation/{id}/snapshot | jq '.code_commit'

# Verificar que el commit existe
git show <commit_hash>

# Ver el estado del código en ese commit
git checkout <commit_hash>
```

### Verificación del Dataset

El hash del dataset (`dataset_version`) se calcula combinando los hashes SHA-256 de:
- Dataset curado 1d: `data/curated/{venue}/{symbol}/1d/curated.parquet`
- Dataset curado 1h: `data/curated/{venue}/{symbol}/1h/curated.parquet`

Para verificar manualmente:

```python
from app.utils.hashing import calculate_dataset_hash
from app.utils.dataset_metadata import get_dataset_version_hash

# Obtener el hash del dataset actual
current_hash = get_dataset_version_hash(interval="1d", venue="binance", symbol="BTCUSDT")

# Comparar con el hash almacenado en la recomendación
stored_hash = recommendation.dataset_version
assert current_hash == stored_hash, "Dataset has changed!"
```

### Verificación de Parámetros

El hash de parámetros (`params_digest`) se calcula a partir del contenido completo de `backend/app/quant/params.yaml`.

Para verificar:

```python
from app.utils.hashing import calculate_params_hash
from app.utils.dataset_metadata import get_params_digest
import yaml

# Obtener el hash actual
current_hash = get_params_digest()

# Leer params.yaml y calcular hash manualmente
with open("backend/app/quant/params.yaml", "r") as f:
    params = yaml.safe_load(f)
manual_hash = calculate_params_hash(params)

assert current_hash == manual_hash
```

### Verificación de Exports

Cuando exportas recomendaciones, puedes verificar la integridad del archivo:

```python
import hashlib

# Leer el archivo exportado
with open("recommendations_export.csv", "rb") as f:
    content = f.read()

# Calcular MD5
md5_hash = hashlib.md5(content).hexdigest()

# Calcular SHA-256
sha256_hash = hashlib.sha256(content).hexdigest()

# Comparar con headers HTTP recibidos
# Headers disponibles: Content-MD5, X-Export-File-Hash
```

O desde la línea de comandos:

```bash
# MD5
md5sum recommendations_export.csv

# SHA-256
sha256sum recommendations_export.csv
```

---

## Interpretación del Tracking Error

### Definición

El **tracking error** mide la diferencia entre el desempeño teórico (sin fricciones) y el desempeño realista (con fill model y fallos de ejecución).

```
tracking_error = equity_realistic - equity_theoretical
```

### Métricas Clave

1. **Mean Deviation (Desviación Media)**
   - Promedio de la diferencia entre las dos curvas
   - **Bueno**: < 0.5% del equity inicial
   - **Atención**: 0.5% - 2%
   - **Crítico**: > 2%

2. **Max Divergence (Máxima Divergencia)**
   - Mayor diferencia absoluta en un punto específico
   - **Bueno**: < 1%
   - **Atención**: 1% - 5%
   - **Crítico**: > 5%

3. **Correlation (Correlación)**
   - Correlación entre las dos curvas (Pearson)
   - **Excelente**: > 0.95
   - **Bueno**: 0.90 - 0.95
   - **Atención**: < 0.90

4. **RMSE (Root Mean Squared Error)**
   - Error cuadrático medio
   - **Bueno**: < 1%
   - **Atención**: 1% - 3%
   - **Crítico**: > 3%

5. **Tracking Sharpe**
   - Sharpe ratio del tracking error (anualizado)
   - Valores negativos indican que las fricciones reducen el Sharpe
   - **Bueno**: > -1.0
   - **Atención**: -1.0 a -2.0
   - **Crítico**: < -2.0

6. **Max Drawdown Divergence**
   - Diferencia en el máximo drawdown entre las dos curvas
   - **Bueno**: < 2%
   - **Atención**: 2% - 5%
   - **Crítico**: > 5%

### Interpretación de Ejemplos

#### Ejemplo 1: Tracking Error Bajo (Excelente)

```
Mean Deviation: 0.15%
Max Divergence: 0.8%
Correlation: 0.97
RMSE: 0.5%
Tracking Sharpe: -0.5
Max Drawdown Divergence: 1.2%
```

**Interpretación**: Las fricciones de ejecución tienen un impacto mínimo. El fill model es realista y las órdenes se ejecutan sin problemas significativos.

#### Ejemplo 2: Tracking Error Medio (Atención)

```
Mean Deviation: 1.2%
Max Divergence: 3.5%
Correlation: 0.92
RMSE: 2.1%
Tracking Sharpe: -1.5
Max Drawdown Divergence: 3.8%
```

**Interpretación**: Hay fricciones moderadas. Posibles causas:
- Slippage más alto de lo esperado
- Algunos trades no se completan (no-trade events)
- Spread más amplio durante volatilidad

#### Ejemplo 3: Tracking Error Alto (Crítico)

```
Mean Deviation: 4.5%
Max Divergence: 12.0%
Correlation: 0.85
RMSE: 6.8%
Tracking Sharpe: -3.2
Max Drawdown Divergence: 8.5%
```

**Interpretación**: Fricciones significativas. Acciones requeridas:
- Revisar el fill model (parámetros alpha, beta, gamma)
- Analizar órdenes que no se completan
- Considerar órdenes limit con mejores precios
- Revisar profundidad del order book

### Uso en Optimización

El tracking error debe considerarse al optimizar estrategias:

1. **Parámetros de Fill Model**: Ajustar `alpha`, `beta`, `gamma` para que coincidan con ejecuciones reales
2. **Tamaño de Orden**: Reducir tamaño si el tracking error es alto (problemas de liquidez)
3. **Tipo de Orden**: Preferir limit orders si el tracking error es alto
4. **Horarios de Trading**: Evitar horarios con baja liquidez si el tracking error es alto

---

## Reproducción de Señales desde Snapshots

### Obtención del Snapshot

Cada recomendación almacena un snapshot inmutable (WORM - Write Once Read Many) en:
- **Path**: `data/snapshots/{date}-{uuid}.json`
- **Metadata en DB**: Campo `snapshot_json` en `RecommendationORM`

Para obtener el snapshot:

```bash
# API endpoint
curl http://localhost:8000/api/v1/recommendation/{id}/snapshot | jq '.worm_snapshot'
```

O desde Python:

```python
from app.utils.worm_storage import WormRepository
from app.core.config import settings

worm_repo = WormRepository()
snapshot = worm_repo.read_snapshot(uuid="<uuid-from-snapshot_json>")
```

### Contenido del Snapshot

El snapshot contiene:

```json
{
  "payload": {
    "date": "2024-01-15T00:00:00",
    "signal": "BUY",
    "entry_optimal": 42000.0,
    "stop_loss": 41000.0,
    "take_profit": 44000.0,
    "confidence": 75.5,
    "narrative": "...",
    "indicators": {...},
    "factors": {...},
    "analysis": {...}
  },
  "metadata": {
    "code_commit": "a1b2c3d4e5f6...",
    "dataset_hash": "sha256:...",
    "params_hash": "sha256:...",
    "timestamp": "2024-01-15T12:00:00Z",
    "uuid": "...",
    "hash": "sha256:..."
  }
}
```

### Reproducción Paso a Paso

#### 1. Verificar el Código

```bash
# Checkout al commit específico
git checkout <code_commit>

# Verificar que no hay cambios locales
git status
git diff
```

#### 2. Verificar el Dataset

```python
from app.utils.dataset_metadata import get_dataset_version_hash

# Calcular hash del dataset actual
current_hash = get_dataset_version_hash(
    interval="1d",
    venue="binance",
    symbol="BTCUSDT"
)

# Comparar con el hash del snapshot
assert current_hash == snapshot["metadata"]["dataset_hash"], \
    "Dataset has changed! Need to restore from backup or use historical dataset."
```

Si el hash no coincide, necesitas restaurar el dataset histórico:

```python
# Restaurar dataset desde backup (si existe)
# O usar data histórica desde el exchange con el timestamp específico
```

#### 3. Verificar Parámetros

```python
from app.utils.dataset_metadata import get_params_digest

# Calcular hash de parámetros actuales
current_params_hash = get_params_digest()

# Comparar con el hash del snapshot
assert current_params_hash == snapshot["metadata"]["params_hash"], \
    "Parameters have changed! Need to restore params.yaml from that commit."

# Si no coincide, restaurar params.yaml
import yaml
from pathlib import Path

# Obtener params.yaml del commit específico
git show <code_commit>:backend/app/quant/params.yaml > params_restored.yaml

# Cargar y verificar
with open("params_restored.yaml", "r") as f:
    restored_params = yaml.safe_load(f)
```

#### 4. Reproducir la Señal

```python
from app.quant.signal_engine import generate_signal
from datetime import datetime

# Parsear fecha del snapshot
snapshot_date = datetime.fromisoformat(snapshot["payload"]["date"])

# Generar señal con el código, dataset y parámetros verificados
result = generate_signal(
    date=snapshot_date,
    # El generate_signal usará automáticamente los params.yaml actuales
)

# Comparar resultados
expected_signal = snapshot["payload"]["signal"]
expected_entry = snapshot["payload"]["entry_optimal"]
expected_confidence = snapshot["payload"]["confidence"]

assert result["signal"] == expected_signal, "Signal mismatch!"
assert abs(result["entry_optimal"] - expected_entry) < 1.0, "Entry price mismatch!"
assert abs(result["confidence"] - expected_confidence) < 1.0, "Confidence mismatch!"
```

### Script de Reproducción Completo

Ver `backend/scripts/reproduce_signal.py` (si existe) o crear uno:

```python
#!/usr/bin/env python3
"""Reproduce a signal from a snapshot."""

import sys
import json
from pathlib import Path
from datetime import datetime

from app.utils.worm_storage import WormRepository
from app.utils.dataset_metadata import get_dataset_version_hash, get_params_digest
from app.quant.signal_engine import generate_signal
from app.utils.hashing import get_git_commit_hash

def reproduce_signal(recommendation_id: int):
    """Reproduce a signal from its snapshot."""
    # 1. Obtener snapshot
    worm_repo = WormRepository()
    # ... (fetch recommendation from DB and get snapshot)
    
    # 2. Verificar hashes
    current_commit = get_git_commit_hash()
    current_dataset = get_dataset_version_hash()
    current_params = get_params_digest()
    
    # 3. Checkout commit si es necesario
    # 4. Restaurar dataset si es necesario
    # 5. Restaurar params si es necesario
    # 6. Reproducir señal
    # 7. Comparar resultados
    
    print("Signal reproduced successfully!")

if __name__ == "__main__":
    recommendation_id = int(sys.argv[1])
    reproduce_signal(recommendation_id)
```

---

## Dashboard de Observabilidad

### Acceso

- **Público**: `GET /api/v1/observability/public/dashboard`
- **Privado**: `GET /api/v1/observability/private/dashboard`

### Métricas Expuestas

#### Métricas de Performance

1. **Rolling Sharpe Ratio** (7d, 30d, 90d)
   - Umbrales: 0.5 (7d), 0.8 (30d), 1.0 (90d)
   - Alertas cuando cae por debajo del umbral

2. **Hit Rate** (7d, 30d, 90d)
   - Umbrales: 40% (7d), 45% (30d), 50% (90d)
   - Porcentaje de trades ganadores

3. **Max Drawdown** (7d, 30d, 90d)
   - Umbrales: 10% (7d), 15% (30d), 20% (90d)
   - Alertas cuando excede el umbral

#### Métricas de Ejecución

4. **Equity Slope** (bps/day)
   - Umbral: -10 bps/day
   - Pendiente de la curva de equity

5. **Tracking Error Mean**
   - Umbral: 2%
   - Desviación media entre curvas teórica y realista

6. **Tracking Error Correlation**
   - Umbral: 90%
   - Correlación entre curvas

7. **Fill Rate**
   - Umbral: 85%
   - Tasa de ejecución de órdenes

#### Métricas de Riesgo

8. **Current Drawdown**
   - Umbral: 20%
   - Drawdown actual desde el peak

### Alertas de Degradación

Las alertas se activan cuando:

1. **Breach de Umbral**: Una métrica cae por debajo (o excede) su umbral
2. **Degradación > X%**: Una métrica se degrada más del X% desde un baseline

Por defecto, `X = 20%`.

#### Severidad

- **Warning**: Degradación 0% - 40%
- **Critical**: Degradación > 40%

### Ejemplo de Respuesta

```json
{
  "status": "ok",
  "metrics": {
    "rolling_sharpe_30d": 0.75,
    "hit_rate_30d": 48.5,
    "max_drawdown_30d": 12.3,
    "tracking_error_mean": 0.015,
    "tracking_error_correlation": 0.94,
    "current_drawdown_pct": 8.5
  },
  "thresholds": {
    "rolling_sharpe_30d": 0.8,
    "hit_rate_30d": 45.0,
    "max_drawdown_30d": 15.0,
    "tracking_error_mean": 0.02,
    "tracking_error_correlation": 0.90,
    "current_drawdown_pct": 20.0
  },
  "alerts": [
    {
      "metric": "rolling_sharpe_30d",
      "current_value": 0.75,
      "threshold": 0.8,
      "degradation_pct": 6.25,
      "severity": "warning",
      "type": "threshold_breach",
      "message": "rolling_sharpe_30d is 6.25% below threshold (0.75 vs 0.80)"
    }
  ],
  "alerts_count": 1,
  "timestamp": "2024-01-15T12:00:00Z"
}
```

---

## Proceso de Auditoría

### Auditoría de Señal Individual

1. **Obtener recomendación** con su snapshot
2. **Verificar hashes** (código, dataset, parámetros)
3. **Reproducir señal** con el código, dataset y parámetros verificados
4. **Comparar resultados** con el snapshot original
5. **Documentar discrepancias** si existen

### Auditoría de Export

1. **Obtener export audit record** desde `/api/v1/recommendation/export/audit`
2. **Verificar hash del archivo** (`file_hash` en audit record)
3. **Comparar con Content-MD5 y X-Export-File-Hash** de la descarga
4. **Verificar metadata** (`commit_hash`, `dataset_hash`, `params_hash`)
5. **Validar filtros** aplicados en el export

### Auditoría Continua

El dashboard de observabilidad permite monitoreo continuo:

1. **Polling cada 30 segundos** del dashboard público/privado
2. **Alertas automáticas** cuando métricas se degradan
3. **Integración con sistemas externos** (Prometheus, Grafana)
4. **Webhooks** para notificaciones (futuro)

### Checklist de Auditoría

- [ ] Hashes verificados (código, dataset, parámetros)
- [ ] Señal reproducible desde snapshot
- [ ] Tracking error dentro de rangos aceptables
- [ ] Métricas de observabilidad dentro de umbrales
- [ ] No hay alertas críticas activas
- [ ] Exports verificables con hashes

---

## Referencias

- [Ejecución y Tracking Error](./execution.md)
- [Arquitectura de Robustez](./architecture/robustness.md)
- [Gestión de Riesgo](./risk-management.md)
- [API de Export](./api.md#export)




# Confianza Calibrada - Plan Operacional Completo

## Visión General

Este documento describe el plan operacional completo para instrumentar métricas de confianza calibradas que mapean probabilidades heurísticas a probabilidades empíricamente calibradas basadas en el historial de señales.

## 1. Instrumentación de Datos

### 1.1 Registro de Señales

Cada señal generada en producción se persiste automáticamente en la tabla `signal_outcomes` con los siguientes campos:

- `confidence_raw`: Score heurístico original (0-100)
- `strategy_id`: Identificador de la estrategia/ensemble que generó la señal
- `regime`: Régimen de mercado detectado (calm, balanced, stress, unknown)
- `vol_bucket`: Bucket de volatilidad (low, balanced, high, unknown)
- `decision_ts`: Timestamp de la decisión
- `horizon`: Horizonte de la señal en minutos
- `outcome`: Resultado observado (win, loss, breakeven, open)
- `pnl_pct`: PnL porcentual realizado
- `features_regimen`: Features del régimen (momentum_alignment, vol_regime_*, slope_*, etc.)
- `metadata`: Metadatos adicionales (signal_breakdown, votes, risk_metrics)

**Implementación:** `RecommendationService._log_signal_emission()` registra automáticamente cada recomendación.

### 1.2 Construcción de Datasets

El script `scripts/confidence/build_dataset.py` realiza:

1. **Lectura de datos:** Lee filas de `signal_outcomes` con filtros opcionales (fechas, regímenes, buckets)
2. **Derivación de hit:** Calcula `hit = 1` si `outcome == "win"` o `pnl_pct >= 0`, `hit = 0` en caso contrario
3. **Features agregadas:** Calcula métricas rolling por régimen/bucket:
   - `rolling_hit_rate_50`: Hit rate de las últimas 50 señales
   - `rolling_confidence_mean_50`: Confianza promedio rolling
   - `rolling_pnl_mean_50`: PnL promedio rolling
   - Features extraídas de `features_regimen` (momentum_alignment, vol_regime_*, etc.)
4. **Particionamiento:** Exporta datasets Parquet particionados por `market_regime/vol_bucket`
5. **Metadatos:** Guarda manifiesto en `artifacts/confidence/datasets.json` con:
   - Hash del query
   - Rango de fechas
   - Conteo de filas
   - Commit hash
   - Timestamp de creación

**Uso:**
```bash
python scripts/confidence/build_dataset.py \
  --start-date 2024-01-01 \
  --end-date 2024-12-31 \
  --regimes calm,balanced,stress \
  --vol-buckets low,balanced,high
```

## 2. Entrenamiento de Calibradores

### 2.1 Implementación de Calibradores

El módulo `backend/app/confidence/calibrator.py` implementa:

- **PlattCalibrator:** Regresión logística (Platt scaling) usando `sklearn.linear_model.LogisticRegression`
- **IsotonicCalibrator:** Regresión isotónica usando `sklearn.isotonic.IsotonicRegression`

Ambos implementan la interfaz `BaseCalibrator` con métodos `fit()` y `predict_proba()`.

### 2.2 Script de Entrenamiento

El script `scripts/confidence/train_calibrators.py`:

1. **Carga dataset:** Lee el dataset Parquet particionado
2. **Agrupa por régimen:** Entrena un calibrador por cada régimen de mercado
3. **Evalúa candidatos:** Prueba ambos tipos (Platt e isotónico) y selecciona el mejor según ECE
4. **Calcula métricas:**
   - **Brier Score:** `mean((y_prob - y_true)^2)`
   - **ECE (Expected Calibration Error):** Error de calibración esperado en bins
   - **Reliability Curve:** Puntos de accuracy vs confidence por bin
5. **Filtra por umbrales:** Solo guarda calibradores con `ECE <= 0.05` y `Brier <= 0.08`
6. **Versiona artefactos:** Guarda en `artifacts/confidence/{regime}/`:
   - `calibrator.pkl`: Modelo serializado con joblib
   - `metadata.json`: Metadatos con métricas, tipo, dataset usado, commit hash
7. **Actualiza manifiesto:** Registra en `artifacts/confidence/manifest.json`

**Uso:**
```bash
python scripts/confidence/train_calibrators.py \
  --dataset-path artifacts/confidence/datasets/20241201T120000Z_abc12345 \
  --regimes calm,balanced,stress \
  --calibrators platt,isotonic \
  --max-ece 0.05 \
  --max-brier 0.08
```

## 3. Integración en Runtime

### 3.1 Carga de Calibradores

`ConfidenceService` (en `backend/app/confidence/service.py`):

1. **Al inicializar:** Escanea `artifacts/confidence/` y carga calibradores por régimen
2. **Valida umbrales:** Rechaza calibradores con ECE o Brier por encima de umbrales
3. **Cachea modelos:** Mantiene diccionario `{regime: LoadedCalibrator}` en memoria

### 3.2 Uso en Recomendaciones

`RecommendationService._apply_confidence_calibration()`:

1. **Detecta régimen:** Extrae régimen de `signal_payload.factors` o `market_regime`
2. **Obtiene calibrador:** Busca por régimen, fallback a "default" o calibrador único
3. **Calibra:** Convierte `confidence_raw` (0-100) a probabilidad (0-1), aplica calibrador, convierte de vuelta (0-100)
4. **Construye metadata:** Incluye ECE, tipo de calibrador, régimen usado
5. **Calcula confidence_band:** Intervalo `[lower, upper]` basado en ECE del calibrador
6. **Fallback:** Si no hay calibrador disponible o ECE > umbral, usa `confidence_raw` con aviso

### 3.3 Exposición en API/UI

**Campos en respuesta API:**
- `confidence_raw`: Score heurístico original
- `confidence_calibrated`: Probabilidad calibrada (null si no disponible)
- `confidence_band`: `{lower, upper, note}` con intervalo histórico
- `calibration_metadata`: `{ece, calibrator_type, regime, band_note}`

**UI:**
- Muestra ambos valores con tooltip explicativo
- Copy en análisis: "Históricamente, señales con 70% calibrado acertaron 69-71%"
- Indicador visual si calibrador no disponible o degradado

## 4. Monitoreo y Reentrenamiento

### 4.1 Script de Monitoreo

`scripts/confidence/monitor.py` ejecuta semanalmente:

1. **Carga señales recientes:** Últimos N días (default: 28) desde `signal_outcomes`
2. **Filtra outcomes cerrados:** Solo señales con `outcome != "open"`
3. **Calcula métricas por régimen:**
   - Brier Score sobre `confidence_calibrated` vs `hit`
   - ECE sobre probabilidades calibradas
   - Reliability curve
4. **Compara con umbrales:** `Brier > 0.08` o `ECE > 0.05` → drift detectado
5. **Registra en diagnostics.csv:** Timestamp, régimen, métricas, status
6. **Dispara alertas:**
   - Slack: Webhook con resumen de regímenes con drift
   - Prometheus: Push métricas a Pushgateway (`confidence_calibration_brier`, `confidence_calibration_ece`)
7. **Reentrenamiento automático (opcional):** Si drift detectado, ejecuta `train_calibrators.py` con dataset más reciente

**Uso:**
```bash
python scripts/confidence/monitor.py \
  --lookback-days 28 \
  --min-rows 200 \
  --max-brier 0.08 \
  --max-ece 0.05 \
  --slack-webhook $SLACK_ALERT_WEBHOOK \
  --pushgateway $PROM_PUSHGATEWAY
```

### 4.2 Integración en Scheduler

Añadir en `backend/app/main.py`:

```python
@scheduler.scheduled_job("cron", day_of_week="mon", hour=2, minute=0, id="confidence_monitor")
async def job_confidence_monitor() -> None:
    """Weekly confidence calibration monitoring."""
    import subprocess
    result = subprocess.run(
        ["python", "scripts/confidence/monitor.py", "--lookback-days", "28"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        logger.error("Confidence monitoring failed", extra={"stderr": result.stderr})
```

## 5. Notebook de Validación

`notebooks/confidence/validation.ipynb` proporciona:

1. **Carga de dataset:** Lee dataset Parquet generado
2. **Entrenamiento interactivo:** Prueba múltiples calibradores por régimen
3. **Visualización:**
   - Reliability curves por régimen/calibrador
   - Comparación de métricas (Brier, ECE)
   - Distribución de confidencias vs outcomes
4. **Generación de reporte HTML:** Exporta reporte completo con:
   - Tabla resumen por régimen
   - Gráficos de reliability curves embebidos
   - Métricas y status (Good/Warning/Poor)
   - Timestamp y dataset usado

**Uso:**
1. Ejecutar todas las celdas
2. Revisar reliability curves
3. Validar métricas
4. Reporte HTML se guarda en `artifacts/confidence/validation_report_*.html`

## 6. Interpretación del Score Calibrado

### 6.1 ¿Qué significa el porcentaje?

El `confidence_calibrated` representa la probabilidad empírica de que la señal resulte en un trade ganador, basada en el historial de señales similares (mismo régimen, volatilidad similar).

**Ejemplo:**
- `confidence_raw = 75%`: Score heurístico del ensemble
- `confidence_calibrated = 68%`: Históricamente, señales con score 75% en régimen "calm" acertaron 68% de las veces
- `confidence_band = [65%, 71%]`: Intervalo de confianza basado en ECE

### 6.2 Cuándo usar calibrado vs raw

- **Usar calibrado:** Cuando hay suficiente historial (N > 200 señales por régimen) y ECE < 0.05
- **Usar raw:** Cuando no hay calibrador disponible, ECE > umbral, o régimen desconocido
- **Degradación:** Si ECE aumenta por encima de umbral, el sistema automáticamente degrada a raw con aviso

## 7. Métricas y Umbrales

### 7.1 Brier Score

Mide la precisión de las probabilidades: `mean((y_prob - y_true)^2)`

- **Rango:** [0, 1] (0 = perfecto, 1 = peor)
- **Umbral aceptable:** < 0.08
- **Interpretación:** Error cuadrático promedio entre probabilidad predicha y resultado real

### 7.2 Expected Calibration Error (ECE)

Mide cuán bien calibradas están las probabilidades:

- **Rango:** [0, 1] (0 = perfectamente calibrado)
- **Umbral aceptable:** < 0.05
- **Cálculo:** Promedio ponderado de `|accuracy - confidence|` por bin
- **Interpretación:** Diferencia promedio entre confianza y accuracy observada

### 7.3 Reliability Curve

Gráfico de accuracy vs confidence por bins:

- **Línea diagonal:** Calibración perfecta
- **Por encima:** Sobreconfianza (confianza > accuracy)
- **Por debajo:** Subconfianza (confianza < accuracy)

## 8. Flujo Completo

```
1. Producción genera señal
   ↓
2. RecommendationService._log_signal_emission() → signal_outcomes
   ↓
3. Trade se cierra → update_signal_outcome() con outcome/pnl
   ↓
4. Semanalmente: build_dataset.py → dataset Parquet
   ↓
5. Mensualmente: train_calibrators.py → calibradores versionados
   ↓
6. ConfidenceService carga calibradores al arrancar
   ↓
7. Cada recomendación: _apply_confidence_calibration() → confidence_calibrated
   ↓
8. Semanalmente: monitor.py → detecta drift, alertas, reentrenamiento
   ↓
9. Notebook validation.ipynb → reportes HTML para auditoría
```

## 9. Troubleshooting

### Calibrador no disponible
- **Causa:** No hay suficientes datos históricos o calibrador rechazado por umbrales
- **Solución:** Usar `confidence_raw` con aviso en UI

### ECE alto
- **Causa:** Cambio de régimen o drift en distribución
- **Solución:** Reentrenar con dataset más reciente, ajustar umbrales si necesario

### Datos insuficientes
- **Causa:** Menos de 200 señales por régimen
- **Solución:** Esperar acumulación de datos o combinar regímenes similares

## 10. Referencias

- [Platt Scaling (1999)](https://www.researchgate.net/publication/2594015_Probabilistic_Outputs_for_Support_Vector_Machines_and_Comparisons_to_Regularized_Likelihood_Methods)
- [Expected Calibration Error](https://arxiv.org/abs/1706.04599)
- [Reliability Diagrams](https://scikit-learn.org/stable/modules/calibration.html)

### Campos expuestos en la API/UI

- `confidence_raw`: score heurístico del ensemble (sin calibración).
- `confidence_calibrated`: probabilidad ajustada según el régimen histórico.
- `confidence_band`: intervalo `[lower, upper]` con la tasa de acierto observada para buckets similares. Se calcula dinámicamente usando el ECE del calibrador.

En la UI se muestran ambos valores con un tooltip: “Históricamente, señales con esta confianza acertaron X–Y% de las veces”. El copy del análisis también refleja esta información para dar contexto al usuario.

## Monitoreo recurrente

El script `scripts/confidence/monitor.py` evalúa ventanas recientes (por defecto 28 días) y calcula:

- Brier Score
- Expected Calibration Error (ECE)
- Reliability curve por régimen

Si alguna métrica supera los umbrales (`Brier > 0.08`, `ECE > 0.05`) se dispara:

- Registro en `diagnostics.csv`
- Alertas opcionales vía Slack (`SLACK_ALERT_WEBHOOK`) y métricas en Prometheus Pushgateway (`PROM_PUSHGATEWAY`)

### Integración en CI / scheduler

1. Configura los secretos `CONFIDENCE_MONITOR_DATABASE_URL` y `SLACK_ALERT_WEBHOOK` en GitHub Actions o variables del scheduler interno.
2. Programa la ejecución diaria del workflow `confidence-monitor.yml` o añade una tarea APScheduler interna que invoque:

```bash
python scripts/confidence/monitor.py --lookback-days 28 --min-rows 200
```

3. Si el job detecta drift, dispara automáticamente `scripts/confidence/train_calibrators.py` con el dataset más reciente y documenta el evento en `diagnostics.csv`.

## Notebook de validación

`notebooks/confidence/validation.ipynb` ofrece una guía reproducible para entrenar calibradores y graficar reliability curves antes de promover artefactos.

## Observabilidad / Grafana

El monitor exporta métricas a Prometheus (`confidence_calibration_brier`, `confidence_calibration_ece`). Crea un dashboard con paneles de tipo *Time Series* usando las consultas:

```
confidence_calibration_brier{regime="calm"}
confidence_calibration_ece{regime="stress"}
```

Agrega, además, un panel *Stat* que compare `avg_over_time(confidence_calibration_ece[7d])` con el umbral deseado. Los datos de producción (`confidence_calibrated` vs `hit`) pueden graficarse vía Prometheus si también ingieres la métrica `signal_outcomes_hit` (añadir en el plan futuro).



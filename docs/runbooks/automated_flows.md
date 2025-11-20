# Runbooks: Flujos Automáticos

Este documento describe los flujos automáticos del sistema One Smart Trade, incluyendo ingestión, clasificación de régimen, triggers de recalibración y redeploy de parámetros.

---

## Flujo 1: Ingesta → Clasificación de Régimen

### Objetivo

Ingerir datos de múltiples activos, curarlos, clasificar régimen y actualizar métricas de health-check.

### Descripción

Este flujo se ejecuta automáticamente en el scheduler para mantener datos actualizados y clasificación de régimen en tiempo real.

### Pasos

#### 1. Ingesta de Datos

**Componente:** `DataIngestion`

```python
from app.data.ingestion import DataIngestion
from app.data.universe import DEFAULT_UNIVERSE

ingestion = DataIngestion()

for asset in DEFAULT_UNIVERSE.assets:
    ingestion.ingest_asset(asset)
```

**Acciones:**
- Descarga datos raw desde exchange (Binance, etc.)
- Guarda en `data/raw/{venue}/{symbol}/{interval}/data.parquet`
- Valida integridad de datos
- Registra métricas Prometheus (`INGESTION_SUCCESS`, `INGESTION_FAILURE`)

**Frecuencia:** Según configuración del scheduler (típicamente diario)

**Error Handling:**
- Si falla ingestión: `INGESTION_FAILURE` incrementado
- Log estructurado con error y asset
- No bloquea procesamiento de otros activos

#### 2. Curación de Datos

**Componente:** `DataCuration`

```python
from app.data.curation import DataCuration

curation = DataCuration(universe_config=DEFAULT_UNIVERSE)

# Cura cada activo
for asset in DEFAULT_UNIVERSE.assets:
    curation.curate_asset(asset)
```

**Acciones:**
- Calcula indicadores técnicos (RSI, MACD, ATR, etc.)
- Calcula métricas de volatilidad
- Guarda en `data/curated/{venue}/{symbol}/{interval}/data.parquet`
- Valida calidad de datos (gaps, outliers)

**Frecuencia:** Después de ingestión exitosa

**Error Handling:**
- Si falla curación: Log warning, datos raw se mantienen
- Continúa con siguiente activo

#### 3. Clasificación de Régimen

**Componente:** `RegimeClassifier`

```python
from app.quant.regime import RegimeClassifier
from app.data.curation import DataCuration

curation = DataCuration()
classifier = RegimeClassifier(method="hmm", n_regimes=3)

for asset in DEFAULT_UNIVERSE.assets:
    df_1d = curation.get_latest_curated("1d", venue=asset.venue, symbol=asset.symbol)
    if not df_1d.empty:
        regime_proba = classifier.fit_predict_proba(df_1d)
        current_proba = regime_proba.iloc[-1].to_dict()
        
        # Actualizar métricas Prometheus
        from app.observability.performance_metrics import REGIME_PROBABILITY
        for regime, proba in current_proba.items():
            REGIME_PROBABILITY.labels(
                asset=asset.symbol,
                venue=asset.venue,
                regime=regime
            ).set(float(proba))
```

**Acciones:**
- Extrae features (volatilidad, skew, volumen)
- Entrena modelo con ventana rodante
- Predice probabilidades de régimen (calm, balanced, stress)
- Actualiza métricas Prometheus

**Frecuencia:** Cada hora (o según configuración)

**Error Handling:**
- Si no hay suficientes datos: Log debug, métricas se mantienen
- Si falla clasificación: Log warning, usa probabilidades previas

#### 4. Cálculo de Drift

**Componente:** `PerformanceMonitor`

```python
from app.observability.performance_metrics import PerformanceMonitor

monitor = PerformanceMonitor(asset="BTCUSDT", venue="binance")
regime_status = monitor.update_regime_health(price_data)
```

**Acciones:**
- Calcula media histórica de probabilidades
- Calcula drift: `current - historical_mean`
- Actualiza `REGIME_DRIFT` en Prometheus
- Alerta si P(stress) > 60% por N sesiones consecutivas

**Frecuencia:** Cada hora

**Alertas:**
- Si P(stress) > 60% por 3+ sesiones: AlertService.notify(severity="warning")
- Si P(stress) > 60% por 6+ sesiones: AlertService.notify(severity="critical")

---

## Flujo 2: Trigger de Recalibración

### Objetivo

Detectar degradación de performance y lanzar recalibración automática cuando métricas exceden umbrales.

### Descripción

Este flujo se ejecuta automáticamente cuando `PerformanceMonitor` detecta cambios significativos en Sharpe ratio o volatilidad.

### Pasos

#### 1. Monitoreo Continuo

**Componente:** `PerformanceMonitor`

```python
from app.backtesting.monitoring import PerformanceMonitor

monitor = PerformanceMonitor(
    window_days=30,
    trigger_pct=0.15,  # 15% de cambio
)

# Ejecutado cada hora por scheduler
baseline_metrics = {"rolling_sharpe_30d": 1.5, "rolling_volatility_30d": 0.3}
event = monitor.detect_recalibration_triggers(
    trades_df,
    baseline_metrics,
    asset="BTCUSDT",
    venue="binance",
    regime_classifier=regime_classifier,
    price_data=price_df,
)
```

**Acciones:**
- Calcula métricas rodantes (Sharpe, volatilidad) en ventana de 30 días
- Compara con baseline (último champion)
- Si `|current - baseline| / baseline > trigger_pct` → genera `RecalibrationEvent`

**Frecuencia:** Cada hora

**Triggers:**
- Sharpe variation > 15%
- Volatility variation > 15%

#### 2. Generación de RecalibrationEvent

**Componente:** `RecalibrationEvent`

```python
@dataclass
class RecalibrationEvent:
    asset: str
    venue: str
    trigger_reason: str  # "sharpe_variation" o "volatility_variation"
    baseline_metrics: dict[str, float]
    current_metrics: dict[str, float]
    regime_snapshot: dict[str, float]  # Probabilidades actuales
    triggered_at: datetime
```

**Acciones:**
- Captura snapshot de métricas actuales
- Captura snapshot de régimen (probabilidades)
- Registra timestamp de trigger
- Log estructurado con detalles

#### 3. Ejecución de RecalibrationJob

**Componente:** `RecalibrationJob`

```python
from app.backtesting.recalibration import RecalibrationJob, AdaptiveCampaignOptimizer

job = RecalibrationJob(
    asset="BTCUSDT",
    venue="binance",
    regime_snapshot=event.regime_snapshot,
    trigger_event=event,
    params_version="v2.1.0",
)

optimizer = AdaptiveCampaignOptimizer(
    require_statistical_significance=True,
    significance_alpha=0.05,
    regime_classifier=regime_classifier,
)

results = job.execute(
    optimizer,
    params_variants,  # Variantes de parámetros a probar
    start_date=start,
    end_date=end,
)
```

**Acciones:**
- Ejecuta optimización con variantes de parámetros
- Usa snapshot de régimen como contexto
- Evalúa candidatos con `AdaptiveCampaignOptimizer`
- Solo promueve champion si mejora es estadísticamente significativa

**Frecuencia:** Cuando se detecta trigger (asíncrono)

**Error Handling:**
- Si falla optimización: Log error, mantiene champion anterior
- Si no hay mejoras significativas: Log info, no promueve

#### 4. Test de Significancia Estadística

**Componente:** `statistical_significance_test`

```python
from app.backtesting.monitoring import statistical_significance_test

is_significant, p_value, reason = statistical_significance_test(
    candidate_sharpe=2.1,
    baseline_sharpe=1.5,
    candidate_returns=candidate_returns,
    baseline_returns=baseline_returns,
    alpha=0.05,
)
```

**Acciones:**
- Realiza t-test de Sharpe ratios
- Calcula p-value
- Retorna `is_significant` si p < alpha
- Registra test en metadata del champion

**Umbral:** p < 0.05 para significancia

#### 5. Promoción de Champion

**Componente:** `record_champion_promotion`

```python
from app.db.crud import record_champion_promotion

record_champion_promotion(
    db,
    asset="BTCUSDT",
    venue="binance",
    params=best_candidate.params,
    metrics=best_candidate.metrics,
    params_version="v2.1.0",
    trained_on_regime=event.regime_snapshot,
    statistical_test={
        "is_significant": True,
        "p_value": 0.03,
        "reason": "sharpe_improvement",
    },
)
```

**Acciones:**
- Guarda nuevo champion en `strategy_champions` table
- Marca champion anterior como `is_active=False`
- Registra `params_version`, `trained_on_regime`, `statistical_test`
- Log info con detalles de promoción

---

## Flujo 3: Redeploy de Parámetros

### Objetivo

Detectar transiciones persistentes de régimen y aplicar playbooks de parámetros correspondientes automáticamente.

### Descripción

Este flujo se ejecuta en cada iteración del backtest y cuando se detecta cambio persistente de régimen (EMA > 0.6).

### Pasos

#### 1. Detección de Régimen en Tiempo Real

**Componente:** `RegimeClassifier` (en BacktestEngine)

```python
# En cada iteración del backtest
regime_classifier = RegimeClassifier(method="hmm", n_regusters=3)
regime_proba_df = regime_classifier.fit_predict_proba(df_slice)
regime_probabilities = regime_proba_df.iloc[-1].to_dict()
```

**Acciones:**
- Clasifica régimen en cada barra del backtest
- Obtiene probabilidades actuales
- Pasa a `RegimeTransitionManager`

**Frecuencia:** En cada iteración del backtest (cada día en backtest histórico)

#### 2. Filtrado EMA de Probabilidades

**Componente:** `RegimeTransitionDetector`

```python
from app.quant.regime_transition import RegimeTransitionDetector, RegimeTransitionConfig

config = RegimeTransitionConfig(
    ema_alpha=0.3,
    transition_threshold=0.6,  # EMA > 0.6 para transición
    min_observations=3,
)
detector = RegimeTransitionDetector(config=config)

transition_info = detector.update(regime_probabilities)
```

**Acciones:**
- Calcula EMA de probabilidades: `EMA = alpha * current + (1 - alpha) * EMA_prev`
- Filtra ruido de corto plazo
- Detecta transición cuando `EMA > 0.6` persistente

**Características:**
- Requiere mínimo de observaciones antes de detectar
- EMA suaviza fluctuaciones de corto plazo
- Threshold evita falsos positivos

#### 3. Detección de Transición Persistente

**Componente:** `RegimeTransitionDetector.update()`

```python
transition_info = detector.update(regime_probabilities)

# Retorna:
{
    "transition_detected": True,
    "current_regime": "stress",
    "dominant_regime": "stress",
    "ema_probability": 0.65,
    "raw_probabilities": {"calm": 0.1, "balanced": 0.25, "stress": 0.65},
    "reason": "persistent_transition_to_stress",
}
```

**Acciones:**
- Compara EMA con threshold (0.6)
- Si `EMA > threshold` y régimen cambió → transición detectada
- Actualiza `current_regime` del detector

**Condiciones:**
- EMA debe ser > 0.6
- Régimen debe haber cambiado respecto al anterior
- Requiere confirmación (mínimo de observaciones)

#### 4. Aplicación de Playbook

**Componente:** `RegimeTransitionManager`

```python
from app.quant.regime_transition import RegimeTransitionManager
from app.quant.regime_playbooks import RegimePlaybookManager
from app.quant.strategies import PARAMS

playbook_manager = RegimePlaybookManager()
playbook_manager.initialize_defaults()

manager = RegimeTransitionManager(
    detector=detector,
    playbook_manager=playbook_manager,
)

result = manager.process_transition(regime_probabilities, PARAMS.copy())
```

**Acciones:**
- Si transición detectada → aplica playbook correspondiente
- Merge de playbook params con base params
- Playbook tiene precedencia sobre base params
- Retorna params actualizados

**Playbooks:**
- `calm`: Parámetros agresivos (lookback corto, thresholds bajos)
- `balanced`: Parámetros estándar
- `stress`: Parámetros conservadores (lookback largo, thresholds altos)

#### 5. Actualización de Parámetros en Signal Engine

**Componente:** `BacktestEngine.run_backtest()`

```python
# Temporalmente actualiza PARAMS para signal generation
if self._current_regime_params:
    import app.quant.strategies as strategies_module
    original_params = strategies_module.PARAMS.copy()
    strategies_module.PARAMS = self._current_regime_params
    
    try:
        signal_data = generate_signal(df_h_slice, df_slice)
    finally:
        strategies_module.PARAMS = original_params
```

**Acciones:**
- Reemplaza temporalmente `PARAMS` global con playbook params
- Genera señal con parámetros del régimen actual
- Restaura `PARAMS` original después de generar señal
- Log info cuando se detecta transición

**Frecuencia:** En cada iteración del backtest (cada día)

#### 6. Asignación Dinámica de Capital

**Componente:** `DynamicCapitalAllocator`

```python
from app.quant.capital_allocation import DynamicCapitalAllocator, CapitalAllocationRules

rules = CapitalAllocationRules(
    base_size_pct=1.0,
    stress_multiplier=0.5,  # Reduce a 50% en stress
    calm_multiplier=1.2,    # Aumenta a 120% en calm
)
allocator = DynamicCapitalAllocator(rules=rules)

position_size_pct_dynamic = allocator.allocate(regime_probabilities)
```

**Acciones:**
- Calcula `position_size_pct` basado en probabilidades de régimen
- Si P(stress) > 0.5 → reduce sizing a 50%
- Si P(calm) > 0.6 → aumenta sizing a 120%
- Aplica límites min/max

**Fórmula:**
```python
if P(stress) > 0.5:
    size_pct = base_size_pct * stress_multiplier
else:
    size_pct = base_size_pct * (
        P(calm) * calm_multiplier +
        P(balanced) * balanced_multiplier +
        P(stress) * stress_multiplier
    )
```

#### 7. Apertura de Posición con Sizing Ajustado

**Componente:** `BacktestEngine.run_backtest()`

```python
if self.capital_allocator and regime_probabilities:
    position_size_pct_dynamic = self.capital_allocator.allocate(regime_probabilities)
else:
    position_size_pct_dynamic = position_size_pct

desired_size = (capital * position_size_pct_dynamic) / entry_price
```

**Acciones:**
- Usa sizing dinámico si `capital_allocator` está configurado
- Calcula tamaño de posición basado en capital disponible y sizing dinámico
- Abre posición con tamaño ajustado

---

## Resumen de Flujos

### Diagrama de Flujos

```
┌─────────────────────────────────────────────────────────────┐
│                    FLUJO 1: INGESTA → RÉGIMEN               │
└─────────────────────────────────────────────────────────────┘
    │
    ├─ 1. Ingesta de datos (DataIngestion)
    ├─ 2. Curación de datos (DataCuration)
    ├─ 3. Clasificación de régimen (RegimeClassifier)
    ├─ 4. Actualización métricas Prometheus
    ├─ 5. Cálculo de drift
    └─ 6. Alertas si P(stress) > 60% por N sesiones

┌─────────────────────────────────────────────────────────────┐
│              FLUJO 2: TRIGGER DE RECALIBRACIÓN              │
└─────────────────────────────────────────────────────────────┘
    │
    ├─ 1. Monitoreo continuo (PerformanceMonitor)
    ├─ 2. Detecta cambio > 15% en Sharpe/Volatilidad
    ├─ 3. Genera RecalibrationEvent
    ├─ 4. RecalibrationJob.execute()
    ├─ 5. Optimización con variantes
    ├─ 6. Test de significancia estadística
    └─ 7. Promueve champion si mejora significativa

┌─────────────────────────────────────────────────────────────┐
│            FLUJO 3: REDEPLOY DE PARÁMETROS                  │
└─────────────────────────────────────────────────────────────┘
    │
    ├─ 1. Detección de régimen en tiempo real
    ├─ 2. Filtrado EMA de probabilidades
    ├─ 3. Detección de transición persistente (EMA > 0.6)
    ├─ 4. Aplicación de playbook
    ├─ 5. Actualización de parámetros en signal engine
    ├─ 6. Asignación dinámica de capital
    └─ 7. Apertura de posición con sizing ajustado
```

### Frecuencias

- **Flujo 1 (Ingesta → Régimen):** Diario (ingesta), Cada hora (clasificación)
- **Flujo 2 (Recalibración):** Cuando se detecta trigger (asíncrono)
- **Flujo 3 (Redeploy):** En cada iteración del backtest (tiempo real)

### Configuración

Ver `docs/architecture/robustness.md` para configuración completa de variables de entorno y thresholds.







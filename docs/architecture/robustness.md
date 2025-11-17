# Robustez y Adaptabilidad - Arquitectura del Sistema

## Visión General

Este documento describe la arquitectura de robustez y adaptabilidad del sistema One Smart Trade, incluyendo soporte multi-activo, clasificación probabilística de régimen, reoptimización automática, análisis de sensibilidad, monitoreo continuo y operativa en cambios de régimen.

## Tabla de Contenidos

1. [Arquitectura Multi-Activo](#arquitectura-multi-activo)
2. [Clasificación Probabilística de Régimen](#clasificación-probabilística-de-régimen)
3. [Reoptimización y Triggers Automáticos](#reoptimización-y-triggers-automáticos)
4. [Análisis de Sensibilidad Integral](#análisis-de-sensibilidad-integral)
5. [Monitoreo Continuo de Performance](#monitoreo-continuo-de-performance)
6. [Operativa en Cambios de Régimen](#operativa-en-cambios-de-régimen)
7. [Flujos Automáticos](#flujos-automáticos)

---

## Arquitectura Multi-Activo

### Objetivo

Unificar ingesta y curación de múltiples activos (BTC, ETH, índices sintéticos) across diferentes mercados (spot, futures) con normalización homogénea de datos.

### Componentes Principales

#### AssetSpec

Define especificaciones de un activo:

```python
@dataclass(frozen=True)
class AssetSpec:
    symbol: str          # Símbolo del activo (e.g., "BTCUSDT")
    venue: str           # Exchange/venue (e.g., "binance")
    quote: str           # Moneda de cotización (e.g., "USDT")
    asset_class: Literal["crypto", "index", "forex", "commodity"]
```

**Propiedades:**
- `storage_key`: Retorna `{venue}/{symbol}` para particionamiento
- `display_name`: Retorna `{symbol} ({venue})` para visualización

#### MarketUniverseConfig

Gestiona colecciones de activos:

```python
@dataclass(frozen=True)
class MarketUniverseConfig:
    assets: Sequence[AssetSpec]
```

**Métodos:**
- `get_asset(symbol, venue)`: Obtiene un activo específico
- `get_assets_by_venue(venue)`: Filtra por venue
- `get_assets_by_class(asset_class)`: Filtra por clase de activo

### Particionamiento de Datos

**Estructura de almacenamiento:**
```
data/
├── raw/
│   └── {venue}/
│       └── {symbol}/
│           └── {interval}/
│               └── data.parquet
└── curated/
    └── {venue}/
        └── {symbol}/
            └── {interval}/
                └── data.parquet
```

**Beneficios:**
- Trazabilidad: Ruta completa identifica fuente
- Flexibilidad: Fácil agregar nuevos activos/venues
- Validación cruzada: Comparación entre activos/mercados
- Escalabilidad: Particionamiento eficiente

### Universos Predefinidos

**DEFAULT_UNIVERSE:**
- BTCUSDT (binance, crypto)
- ETHUSDT (binance, crypto)

**EXTENDED_UNIVERSE:**
- Incluye DEFAULT_UNIVERSE
- NQ=F (yfinance, index)

### Integración con Ingesta y Curación

**DataIngestion:**
- `ingest_asset(asset: AssetSpec)`: Ingresa datos para un activo específico
- `ingest_timeframe(interval, venue, symbol)`: Ingresa timeframe específico

**DataCuration:**
- `curate_asset(asset: AssetSpec)`: Cura datos para un activo
- `curate_universe(config: MarketUniverseConfig)`: Cura universo completo
- `curate_interval(interval, venue, symbol)`: Cura intervalo específico

---

## Clasificación Probabilística de Régimen

### Objetivo

Identificar estados del mercado (calm, balanced, stress) usando modelos no paramétricos y devolver distribuciones de probabilidad en vez de etiquetas discretas.

### Modelos Implementados

#### HmmRegimeClassifier

Usa Hidden Markov Model gaussiano para identificar regímenes:

```python
@dataclass
class HmmRegimeClassifier:
    n_regimes: int = 3
    covariance_type: Literal["spherical", "diag", "full", "tied"] = "full"
    random_state: int = 42
```

**Características:**
- Modelo probabilístico que captura transiciones entre estados
- Distribución posterior sobre regímenes
- Entrenamiento con ventana rodante

#### KMeansRegimeClassifier

Usa k-means clustering como alternativa no paramétrica:

```python
@dataclass
class KMeansRegimeClassifier:
    n_regimes: int = 3
    random_state: int = 42
```

**Características:**
- Más rápido que HMM
- Convierte distancias a probabilidades (inverso normalizado)
- No captura secuencialidad

### RegimeClassifier Unificado

Wrapper que unifica ambos modelos:

```python
@dataclass
class RegimeClassifier:
    method: Literal["hmm", "kmeans"] = "hmm"
    n_regimes: int = 3
    window_size: int = 252        # Ventana rodante
    refit_every: int = 21         # Refit cada N observaciones
```

**Métodos:**
- `fit_predict_proba(df)`: Entrena y predice probabilidades
- `_extract_features(df)`: Extrae volatilidad, skew, volumen normalizado

### Features Extraídas

1. **Volatilidad:** Rolling std de returns (30 días) o calculado dinámicamente
2. **Skew:** Rolling skew de returns (30 días)
3. **Volumen:** Normalizado por rolling mean para capturar cambios relativos

### Integración con Signal Engine

El `generate_signal()` usa probabilidades de régimen para ajustar pesos de estrategias:

```python
# Breakout strategy: ajuste exponencial si P(high_vol) aumenta
adaptive_weight = np.exp(regime_exponential_factor * p_high_vol)
breakout_bias *= adaptive_weight

# Volatility strategy: promedio ponderado por probabilidades
vol_bias = (
    p_calm * vol_low_bias +
    p_balanced * vol_mid_bias +
    p_stress * vol_high_bias
)
```

**Configuración (params.yaml):**
```yaml
regime_classifier:
  enabled: false
  method: "hmm"
  exponential_factor: 2.0
  window_size: 252
  refit_every: 21
```

---

## Reoptimización y Triggers Automáticos

### Objetivo

Detectar cambios significativos en métricas de performance y lanzar jobs de recalibración automática cuando se exceden umbrales definidos.

### Componentes

#### PerformanceMonitor

Calcula métricas rodantes y detecta triggers:

```python
class PerformanceMonitor:
    def __init__(
        self,
        window_days: int = 30,
        trigger_pct: float = 0.15,  # 15% de cambio
    ):
```

**Métricas Monitoreadas:**
- `rolling_sharpe_30d`: Sharpe ratio en ventana de 30 días
- `rolling_volatility_30d`: Volatilidad en ventana de 30 días

**Trigger Conditions:**
- Si `|current - baseline| / baseline > trigger_pct`, se genera `RecalibrationEvent`

#### RecalibrationEvent

Evento que dispara recalibración:

```python
@dataclass
class RecalibrationEvent:
    asset: str
    venue: str
    trigger_reason: str
    baseline_metrics: dict[str, float]
    current_metrics: dict[str, float]
    regime_snapshot: dict[str, float]  # Probabilidades de régimen
    triggered_at: datetime
```

#### RecalibrationJob

Ejecuta recalibración:

```python
@dataclass
class RecalibrationJob:
    asset: str
    venue: str
    trigger_event: RecalibrationEvent
    params_version: str | None = None
```

**Proceso:**
1. Ejecuta optimización con variantes de parámetros
2. Usa snapshot de régimen para contexto
3. Promueve champion solo si mejora es estadísticamente significativa

#### AdaptiveCampaignOptimizer

Extiende `CampaignOptimizer` con:

- Tests de significancia estadística para promoción
- Tracking de régimen durante entrenamiento
- Persistencia de tests estadísticos en metadata

**Statistical Test:**
```python
def statistical_significance_test(
    candidate_sharpe: float,
    baseline_sharpe: float,
    candidate_returns: np.ndarray,
    baseline_returns: np.ndarray,
    alpha: float = 0.05,
) -> tuple[bool, float, str]:
    # t-test de Sharpe ratios
```

### Persistencia de Versiones

**StrategyChampionORM:**
- `params_version`: Versión de parámetros
- `trained_on_regime`: Snapshot de régimen durante entrenamiento
- `statistical_test`: Resultados de test (p-value, reason, is_significant)

### Flujo de Recalibración

```
1. PerformanceMonitor detecta cambio > 15% en Sharpe/Volatilidad
2. Se genera RecalibrationEvent con snapshot de régimen
3. RecalibrationJob ejecuta optimización
4. AdaptiveCampaignOptimizer evalúa candidatos
5. Si mejora es significativa (p < 0.05), se promueve champion
6. Se registra params_version, trained_on_regime, statistical_test
```

---

## Análisis de Sensibilidad Integral

### Objetivo

Realizar barridos sistemáticos de parámetros clave y evaluar su impacto en métricas centrales (Calmar, max DD) usando pruebas estadísticas.

### Componentes

#### SensitivityRunner

Ejecuta barridos sistemáticos:

```python
class SensitivityRunner:
    def run(
        self,
        param_grid: dict[str, Sequence[Any]],
        *,
        start_date,
        end_date,
        base_params: dict[str, Any] | None = None,
    ) -> pd.DataFrame:
```

**Input:**
- `param_grid`: Dict con parámetros y valores, e.g.:
  ```python
  {
      "breakout.lookback": [10, 15, 20, 25, 30],
      "volatility.low_threshold": [0.15, 0.2, 0.25],
      "aggregate.vector_bias.momentum_bias_weight": [0.15, 0.2, 0.25, 0.3],
  }
  ```

**Output:**
- DataFrame con métricas por combinación (calmar, max_dd, sharpe, cagr, etc.)

#### Análisis Estadístico

**ANOVA:**
```python
analysis = runner.analyze_dominance(results_df, method="anova")
```
- F-statistic y p-value por parámetro
- Rango de impacto (max - min)
- Identifica parámetros dominantes

**Correlación:**
```python
analysis = runner.analyze_dominance(results_df, method="correlation")
```
- Pearson correlation entre parámetro y métrica
- Identifica relaciones lineales

**Bootstrap:**
```python
bootstrap = runner.bootstrap_analysis(results_df, n_bootstrap=1000)
```
- Intervalos de confianza para efectos de parámetros
- Distribución de efectos mediante resampling

#### Identificación de Zonas Seguras

```python
safe_zones = runner.identify_safe_zones(
    results_df,
    target_metric="calmar",
    min_score=1.5,
    max_dd_threshold=15.0,
)
```

**Output:**
- Rangos óptimos por parámetro (min, max, mean)
- Mejores parámetros y métricas asociadas
- Conteo de combinaciones seguras

#### Visualización

**Tornado Chart:**
```python
plot_tornado_chart(analysis, output_path="tornado.png")
```
- Top N parámetros por impacto
- Marca parámetros significativos (*)

**Response Surface:**
```python
plot_response_surface(
    results_df,
    "breakout.lookback",
    "volatility.low_threshold",
    target_metric="calmar",
)
```
- Superficie 2D de interacción entre parámetros
- Interpolación cúbica para visualización suave

**Parameter Distributions:**
```python
plot_parameter_distributions(results_df, "breakout.lookback")
```
- Distribución de métricas por valor de parámetro
- Error bars (±1 std)

---

## Monitoreo Continuo de Performance

### Objetivo

Exponer métricas financieras via Prometheus y alertar cuando caen por debajo de umbrales definidos.

### Métricas Prometheus

#### Métricas Financieras

- `strategy_rolling_sharpe{asset, venue, horizon}`: Sharpe rodante (7d, 30d, 90d)
- `strategy_hit_rate{asset, venue, horizon}`: Hit rate rodante (%)
- `strategy_equity_slope{asset, venue}`: Pendiente de equity (bps/día)
- `strategy_max_drawdown{asset, venue, horizon}`: Drawdown máximo (%)
- `strategy_profit_factor{asset, venue, horizon}`: Factor de beneficio

#### Health-Check de Régimen

- `strategy_regime_probability{asset, venue, regime}`: Probabilidad actual (calm, balanced, stress)
- `strategy_regime_drift{asset, venue, regime}`: Drift respecto a media histórica
- `strategy_stress_alert_count{asset, venue}`: Sesiones consecutivas con stress > threshold

### PerformanceMonitor

Actualiza métricas desde backtest:

```python
monitor = PerformanceMonitor(
    asset="BTCUSDT",
    venue="binance",
    regime_classifier=regime_classifier,
)

monitor.update_rolling_metrics(trades, equity_curve, horizons=[7, 30, 90])
regime_status = monitor.update_regime_health(price_data)
alerts = monitor.check_threshold_alerts(thresholds)
```

### ContinuousMonitoringService

Servicio que automatiza monitoreo:

```python
service = ContinuousMonitoringService(
    asset="BTCUSDT",
    venue="binance",
    thresholds={
        "rolling_sharpe_30d": 0.5,
        "hit_rate_30d": 40.0,
        "equity_slope": -10.0,
    },
    stress_threshold=0.6,
    stress_alert_sessions=3,
)
```

**Job Scheduler:**
- Ejecuta cada hora (`hour="*/1"`)
- Actualiza métricas desde backtest
- Verifica alertas y notifica

### Health Checks

**Regime Health:**
- Calcula probabilidades de régimen actuales
- Compara con media histórica (drift)
- Alerta si P(stress) > 60% durante N sesiones consecutivas

**Threshold Alerts:**
- Sharpe < threshold → warning/critical
- Hit rate < threshold → warning/critical
- Equity slope < threshold → warning/critical

---

## Operativa en Cambios de Régimen

### Objetivo

Adaptar asignación de capital y parámetros de estrategia basado en probabilidades de régimen detectadas.

### Asignación Dinámica de Capital

#### CapitalAllocationRules

Reglas de sizing basadas en régimen:

```python
@dataclass
class CapitalAllocationRules:
    base_size_pct: float = 1.0
    calm_multiplier: float = 1.2      # +20% en calm
    balanced_multiplier: float = 1.0  # Estándar
    stress_multiplier: float = 0.5    # -50% en stress
    stress_threshold: float = 0.5
```

**Cálculo:**
```python
if P(stress) > 0.5:
    size_pct = base_size_pct * stress_multiplier  # Reduce exposición
else:
    size_pct = base_size_pct * (
        P(calm) * calm_multiplier +
        P(balanced) * balanced_multiplier +
        P(stress) * stress_multiplier
    )
```

#### KellyAllocation

Criterio de Kelly con ajustes por régimen:

```python
kelly_fraction = (win_rate * (1 + win_loss_ratio) - 1) / win_loss_ratio

if P(stress) > threshold:
    kelly_fraction *= 0.3  # Reduce agresividad
elif P(calm) > 0.6:
    kelly_fraction *= 1.5  # Aumenta agresividad
```

### Playbooks por Régimen

#### RegimePlaybook

Template de parámetros por régimen:

```python
@dataclass
class RegimePlaybook:
    regime: str  # "calm", "balanced", "stress"
    params: dict[str, Any]
    description: str
```

**Playbooks Predefinidos:**

**Calm (mercados trending, baja volatilidad):**
- Lookback más corto (15)
- Thresholds bajos (0.15/0.4)
- Mayor peso momentum (0.3)
- Thresholds agresivos (±0.12)

**Balanced (condiciones normales):**
- Parámetros estándar
- Lookback 20, thresholds 0.2/0.5
- Pesos balanceados

**Stress (alta volatilidad, choppy):**
- Lookback más largo (30)
- Thresholds altos (0.25/0.6)
- Menor peso momentum (0.15)
- Thresholds conservadores (±0.18)

### Detección de Transiciones

#### RegimeTransitionDetector

Detecta cambios persistentes usando EMA:

```python
@dataclass
class RegimeTransitionConfig:
    ema_alpha: float = 0.3
    transition_threshold: float = 0.6  # EMA > 0.6 para transición
    min_observations: int = 3
```

**Proceso:**
1. Calcula EMA de probabilidades de régimen
2. Filtra ruido de corto plazo
3. Detecta transición cuando EMA > threshold
4. Requiere confirmación antes de conmutar

#### RegimeTransitionManager

Gestiona transiciones y aplicación de playbooks:

```python
manager = RegimeTransitionManager(
    detector=transition_detector,
    playbook_manager=playbook_manager,
)

result = manager.process_transition(regime_probabilities, base_params)
# Retorna params actualizados si detecta transición persistente
```

### Integración con BacktestEngine

**Flujo:**
1. Detecta régimen en cada iteración (HMM/KMeans)
2. Calcula EMA de probabilidades
3. Si EMA > threshold persistente → transición detectada
4. Aplica playbook correspondiente
5. Calcula sizing dinámico basado en probabilidades
6. Genera señal con parámetros del playbook
7. Abre posición con sizing ajustado

---

## Flujos Automáticos

### Flujo 1: Ingesta → Clasificación de Régimen

```
1. Ingesta de datos (DataIngestion.ingest_asset)
   ↓
2. Curación de datos (DataCuration.curate_asset)
   ↓
3. Clasificación de régimen (RegimeClassifier.fit_predict_proba)
   ↓
4. Actualización de métricas Prometheus (REGIME_PROBABILITY)
   ↓
5. Cálculo de drift (REGIME_DRIFT)
   ↓
6. Alerta si P(stress) > 60% por N sesiones
```

### Flujo 2: Trigger de Recalibración

```
1. Monitoreo continuo (PerformanceMonitor.check_trigger)
   ↓
2. Detecta cambio > 15% en Sharpe/Volatilidad
   ↓
3. Genera RecalibrationEvent con snapshot de régimen
   ↓
4. RecalibrationJob.execute()
   ↓
5. Optimización con variantes (AdaptiveCampaignOptimizer)
   ↓
6. Test de significancia estadística
   ↓
7. Si mejora significativa → promueve champion
   ↓
8. Registra params_version, trained_on_regime, statistical_test
```

### Flujo 3: Redeploy de Parámetros

```
1. Transición de régimen detectada (RegimeTransitionDetector)
   ↓
2. EMA > 0.6 persistente
   ↓
3. RegimeTransitionManager.process_transition()
   ↓
4. Aplica playbook correspondiente
   ↓
5. Actualiza parámetros en signal engine
   ↓
6. Calcula asignación de capital dinámica
   ↓
7. Aplica sizing ajustado en nuevas posiciones
```

### Flujo 4: Análisis de Sensibilidad → Optimización

```
1. SensitivityRunner.run() con malla de parámetros
   ↓
2. Evalúa todas las combinaciones
   ↓
3. Análisis estadístico (ANOVA/correlación/bootstrap)
   ↓
4. Identifica parámetros dominantes
   ↓
5. Identifica zonas seguras
   ↓
6. Visualiza resultados (tornado charts, response surfaces)
   ↓
7. Exporta resultados (CSV, JSON)
   ↓
8. Usa rangos óptimos para próximos barridos
```

### Flujo 5: Monitoreo Continuo → Alertas

```
1. Job scheduler ejecuta cada hora
   ↓
2. ContinuousMonitoringService.update_metrics()
   ↓
3. Actualiza métricas Prometheus (Sharpe, hit rate, equity slope)
   ↓
4. Actualiza régimen health (probabilidades, drift)
   ↓
5. Verifica thresholds (check_alerts)
   ↓
6. Si métrica < threshold → AlertService.notify()
   ↓
7. Si stress > 60% por N sesiones → alerta crítica
   ↓
8. Logs estructurados para auditoría
```

---

## Configuración y Deployment

### Variables de Entorno

```bash
# Régimen
REGIME_CLASSIFIER_ENABLED=true
REGIME_METHOD=hmm
REGIME_EXPONENTIAL_FACTOR=2.0

# Recalibración
RECALIBRATION_TRIGGER_PCT=0.15
RECALIBRATION_ALPHA=0.05

# Monitoreo
MONITORING_ENABLED=true
MONITORING_THRESHOLDS_SHARPE=0.5
MONITORING_THRESHOLDS_HIT_RATE=40.0
MONITORING_STRESS_THRESHOLD=0.6
MONITORING_STRESS_SESSIONS=3

# Capital Allocation
CAPITAL_ALLOCATION_ENABLED=true
CAPITAL_STRESS_MULTIPLIER=0.5
CAPITAL_CALM_MULTIPLIER=1.2
```

### Scheduler Jobs

```python
# Monitoreo de performance (cada hora)
@scheduler.scheduled_job("cron", hour="*/1", minute=0)
async def job_monitor_performance():
    # Actualiza métricas y verifica alertas
    pass

# Recalibración automática (cuando se detecta trigger)
# Ejecutado automáticamente por RecalibrationJob
```

---

## Referencias

- [Análisis de Sensibilidad](./backtest.md#sensitivity-analysis)
- [Monitoreo de Performance](./deployment.md#observability)
- [Runbooks Automáticos](./runbooks/automated_flows.md)




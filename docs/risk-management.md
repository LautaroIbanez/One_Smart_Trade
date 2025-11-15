# Risk Management System

## Overview

The risk management system provides comprehensive position sizing, drawdown control, auto-shutdown, and ruin simulation capabilities. It is implemented through a unified `UnifiedRiskManager` that integrates all risk management operations.

## Architecture

### Unified Risk Manager

The `UnifiedRiskManager` centralizes all risk management logic:

- **Position Sizing**: Risk-based, Kelly criterion, volatility targeting
- **Drawdown Tracking**: Real-time drawdown monitoring and adjustment
- **Auto-Shutdown**: Automatic suspension of trading based on drawdown or performance degradation
- **Ruin Simulation**: Monte Carlo estimation of ruin probability

### Components

1. **RiskSizer**: Risk-based position sizing (1% of capital per trade by default)
2. **DrawdownController**: Dynamic risk reduction based on current drawdown
3. **KellySizer**: Kelly criterion sizing with truncation (max 50% of full Kelly)
4. **VolatilityTargeting**: Volatility-based position adjustment
5. **AutoShutdownManager**: Automatic shutdown and size reduction
6. **RuinSimulator**: Monte Carlo ruin probability estimation

## Position Sizing

### Risk-Based Sizing

Position size is calculated to risk a fixed percentage of capital per trade:

```
units = (capital * risk_budget_pct) / risk_per_unit
```

Where:
- `capital`: Current equity
- `risk_budget_pct`: Risk budget percentage (default: 1.0%)
- `risk_per_unit`: |entry_price - stop_loss|

**Example:**
- Capital: $10,000
- Risk budget: 1%
- Entry: $50,000
- Stop loss: $48,000
- Risk per unit: $2,000
- Units: ($10,000 * 0.01) / $2,000 = 0.05 BTC

### Kelly Criterion Sizing

The Kelly criterion optimizes position size based on win rate and payoff ratio:

```
full_kelly = win_rate - (1 - win_rate) / payoff_ratio
truncated_kelly = full_kelly * kelly_cap  # kelly_cap = 0.5 (50% of full Kelly)
```

**Safety Features:**
- Truncation: Maximum 50% of full Kelly (configurable)
- Absolute cap: Maximum 25% of capital

**Example:**
- Win rate: 60%
- Payoff ratio: 2.0 (avg_win / avg_loss)
- Full Kelly: 0.6 - (1 - 0.6) / 2.0 = 0.4 (40%)
- Truncated (50%): 0.4 * 0.5 = 0.2 (20% of capital)

### Volatility Targeting

Position size is adjusted to maintain target portfolio volatility:

```
adjusted_units = base_units * (target_vol / realized_vol)
```

Where:
- `target_vol`: Target volatility (default: 10% annualized)
- `realized_vol`: Realized volatility (from historical data)
- Adjustment clamped between 0.5x and 2.0x

**Example:**
- Base units: 0.1 BTC
- Target volatility: 10%
- Realized volatility: 15%
- Adjusted: 0.1 * (0.10 / 0.15) = 0.067 BTC (reduced for higher volatility)

### Combined Sizing

The system can combine multiple sizing methods:

1. **Risk + Kelly**: Takes minimum of risk-based and Kelly sizes (conservative)
2. **With Volatility**: Applies volatility targeting adjustment
3. **With Drawdown**: Applies drawdown-based risk reduction

**Order of Operations:**
1. Calculate base size (risk-based or Kelly, or minimum of both)
2. Apply volatility targeting (if enabled)
3. Apply drawdown adjustment (if drawdown > 0)

## Drawdown Control

### Dynamic Risk Reduction

Risk budget is reduced as drawdown increases:

```
risk_multiplier = 1.0 - (current_dd_pct / max_drawdown_pct)
effective_risk = base_risk * risk_multiplier
```

Where:
- `current_dd_pct`: Current drawdown percentage
- `max_drawdown_pct`: Maximum drawdown for full risk reduction (default: 50%)
- Multiplier clamped between 0.0 and 1.0

**Example:**
- Base risk: 1%
- Current drawdown: 10%
- Max drawdown: 50%
- Risk multiplier: 1.0 - (10 / 50) = 0.8
- Effective risk: 1% * 0.8 = 0.8%

**Formula:**
```
r = risk_budget_pct * (1 - DD / 50%)
```

At 0% drawdown: 100% of base risk
At 25% drawdown: 50% of base risk
At 50% drawdown: 0% of base risk (trading suspended)

## Auto-Shutdown

### Drawdown Hard-Stop

Trading is automatically suspended when drawdown exceeds a threshold:

```
if current_drawdown_pct >= max_drawdown_pct:
    shutdown = True
```

**Default Policy:**
- Max drawdown: 20%
- Action: Suspend new positions
- Recovery: Manual intervention or automatic reset after recovery

### Performance Guard

Trading can be suspended or size reduced based on performance metrics:

**Metrics:**
- Rolling Sharpe ratio (30-day)
- Hit rate (percentage of winning trades)
- Equity curve slope

**Conditions:**
- If rolling Sharpe < threshold (default: 0.2) for N trades (default: 50)
- If hit rate < threshold (default: 40%) for N trades

**Actions:**
1. **Full Shutdown**: Suspend all new positions
2. **Size Reduction**: Reduce position size by factor (default: 0.5 = 50%)

## Ruin Simulation

### Monte Carlo Estimation

The system estimates the probability of hitting a ruin threshold using Monte Carlo simulation:

```
ruin_probability = P(equity <= threshold * initial_capital)
```

**Parameters:**
- `win_rate`: Historical win rate (from trade history)
- `payoff_ratio`: Average win / Average loss (from trade history)
- `horizon`: Number of trades to simulate (default: 250)
- `threshold`: Ruin threshold (default: 0.5 = -50% drawdown)
- `trials`: Number of Monte Carlo simulations (default: 5000)

**Formula:**
```
For each simulation:
  outcomes = random(horizon) < win_rate ? payoff_ratio : -1.0
  equity_path = cumsum(outcomes)
  ruin = min(equity_path) <= log(threshold)
  
ruin_probability = mean(ruin)
```

### Alert Threshold

**Default Alert:** Risk of ruin >= 5%

When risk of ruin exceeds 5%, alerts are triggered:
- Prometheus metric: `risk_risk_of_ruin`
- Alert condition: `risk_risk_of_ruin >= 0.05`

## API Usage

### Unified Risk Manager

```python
from app.backtesting.unified_risk_manager import UnifiedRiskManager

# Initialize
risk_manager = UnifiedRiskManager(
    base_capital=10000.0,
    risk_budget_pct=1.0,
    use_kelly=True,
    kelly_cap=0.5,
    volatility_targeting=True,
    target_volatility=0.10,
)

# Size a trade
sizing_result = risk_manager.size_trade(
    entry=50000.0,
    stop=48000.0,
    win_rate=0.6,
    payoff_ratio=2.0,
    realized_vol=0.15,
)

# Update drawdown
metrics = risk_manager.update_drawdown(
    current_equity=9500.0,
    trades=trade_history,
)

# Check shutdown
shutdown_status = risk_manager.check_shutdown()

# Simulate ruin
ruin_prob = risk_manager.simulate_ruin()
```

### REST API Endpoints

#### Calculate Position Size

```bash
POST /api/v1/risk/sizing
{
  "capital": 10000.0,
  "entry": 50000.0,
  "stop": 48000.0,
  "volatility": 15.0,
  "use_kelly": true,
  "win_rate": 0.6,
  "payoff_ratio": 2.0,
  "kelly_cap": 0.5,
  "risk_budget_pct": 1.0,
  "current_drawdown_pct": 5.0
}
```

**Response:**
```json
{
  "units": 0.05,
  "notional": 2500.0,
  "risk_amount": 100.0,
  "risk_percentage": 1.0,
  "explanation": "...",
  "parameters": {
    "kelly": {
      "full_kelly": 0.4,
      "truncated_kelly": 0.2,
      "applied_fraction": 0.2
    }
  }
}
```

#### Get Sizing from Recommendation

```bash
GET /api/v1/risk/sizing/from-recommendation?capital=10000&risk_budget_pct=1.0
```

Automatically uses current recommendation's entry/stop levels.

## Prometheus Metrics

### Risk Metrics

All risk metrics are exposed via Prometheus:

- `risk_current_drawdown_pct`: Current drawdown percentage
- `risk_peak_equity`: Peak equity value
- `risk_current_equity`: Current equity value
- `risk_risk_of_ruin`: Estimated risk of ruin (0.0 to 1.0)
- `risk_suggested_fraction`: Suggested position size fraction
- `risk_budget_pct`: Base risk budget percentage
- `risk_effective_budget_pct`: Effective risk budget after adjustments
- `risk_shutdown_active`: Whether shutdown is active (1=active, 0=inactive)
- `risk_size_reduction_active`: Whether size reduction is active
- `risk_size_reduction_factor`: Size reduction multiplier

### Alert Rules

**Risk of Ruin Alert:**
```yaml
- alert: HighRiskOfRuin
  expr: risk_risk_of_ruin > 0.05
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "Risk of ruin exceeds 5%"
    description: "Strategy {{ $labels.strategy }} on {{ $labels.asset }} has risk of ruin = {{ $value }}"
```

**Shutdown Alert:**
```yaml
- alert: TradingShutdown
  expr: risk_shutdown_active > 0
  for: 1m
  labels:
    severity: critical
  annotations:
    summary: "Trading shutdown is active"
    description: "Strategy {{ $labels.strategy }} on {{ $labels.asset }} has been shut down"
```

## Formulas Summary

### Risk-Based Sizing
```
units = (capital * risk_budget_pct) / |entry - stop|
```

### Kelly Criterion
```
full_kelly = win_rate - (1 - win_rate) / payoff_ratio
truncated_kelly = full_kelly * kelly_cap  # kelly_cap = 0.5 (50%)
applied_kelly = min(truncated_kelly, max_fraction)  # max_fraction = 0.25 (25%)
```

### Drawdown Risk Multiplier
```
risk_multiplier = 1.0 - (current_dd_pct / max_drawdown_pct)
effective_risk = base_risk * max(0.0, min(1.0, risk_multiplier))
```

### Volatility Targeting
```
scale_factor = target_vol / realized_vol
adjusted_units = base_units * max(0.5, min(2.0, scale_factor))
```

### Ruin Simulation
```
For each Monte Carlo trial:
  outcomes = [payoff_ratio if random() < win_rate else -1.0] * horizon
  equity_path = cumsum(outcomes)
  ruin = min(equity_path) <= log(threshold)

ruin_probability = mean([ruin for each trial])
```

## Best Practices

1. **Start Conservative**: Use 1% risk budget for new strategies
2. **Monitor Drawdown**: Update drawdown metrics after each trade
3. **Use Kelly Truncation**: Always truncate Kelly to 50% or less
4. **Enable Volatility Targeting**: Adjust size for market volatility
5. **Set Shutdown Thresholds**: Configure appropriate max drawdown (e.g., 20%)
6. **Monitor Ruin Risk**: Alert when risk of ruin > 5%
7. **Regular Review**: Review risk metrics weekly or monthly

## Configuration

### Default Parameters

```python
base_capital: float = 10000.0
risk_budget_pct: float = 1.0  # 1% per trade
max_drawdown_pct: float = 50.0  # 50% max DD for full risk reduction
kelly_cap: float = 0.5  # 50% of full Kelly
target_volatility: float = 0.10  # 10% annualized
ruin_threshold: float = 0.5  # -50% drawdown
ruin_horizon: int = 250  # 250 trades
ruin_alert_threshold: float = 0.05  # 5%
```

### Shutdown Policy

```python
max_drawdown_pct: float = 20.0  # 20% max drawdown
min_rolling_sharpe: float = 0.2  # Minimum Sharpe
min_hit_rate: float = 40.0  # 40% minimum hit rate
lookback_trades: int = 50  # Last 50 trades
consecutive_breaches: int = 1  # Breach threshold once
reduction_factor: float = 0.5  # 50% size reduction
```

## Troubleshooting

### Issue: Position size too small
- Check if drawdown adjustment is too aggressive
- Verify stop loss distance is reasonable
- Consider reducing risk budget percentage

### Issue: Risk of ruin too high
- Reduce position sizes
- Improve win rate or payoff ratio
- Increase stop loss distance (reduce risk per trade)

### Issue: Frequent shutdowns
- Review shutdown thresholds (may be too strict)
- Check if drawdown calculation is correct
- Verify equity tracking is accurate

## References

- [Kelly Criterion](https://en.wikipedia.org/wiki/Kelly_criterion)
- [Volatility Targeting](https://www.investopedia.com/terms/v/volatility-targeting.asp)
- [Risk of Ruin](https://www.investopedia.com/terms/r/riskofruin.asp)
- [Drawdown Management](https://www.investopedia.com/terms/d/drawdown.asp)



## Documentación y Gobernanza: Políticas Psicológicas y Éticas

### Objetivos

Garantizar que el uso de One Smart Trade promueva prácticas responsables, reduzca sesgos psicológicos comunes y minimice riesgos operativos y financieros. Estas políticas establecen límites claros, mecanismos automáticos de enfriamiento, alertas de apalancamiento y una oferta educativa continua.

### 1) Límites de riesgo

- Límite por operación: por defecto, 1% del capital. Máximo permitido sin override: 2%. Cualquier solicitud de mayor riesgo requiere justificación y registro.
- Límite diario: suma de riesgos comprometidos en nuevas operaciones no debe exceder 3% del capital. Al superar 2%, se activa una advertencia dura (hard warning).
- Límite de drawdown: a -10% se reduce el riesgo efectivo en la curva; a -20% se suspenden nuevas entradas (ver Auto-Shutdown).
- Límite de exposición por activo: notional máximo por activo del 25% del capital para evitar concentración.

### 2) Triggers de cooldown (enfriamiento)

- Pérdidas consecutivas: con 3 pérdidas seguidas en horizontes cortos, se aplica reducción del 50% del tamaño por 24 horas o 10 operaciones (lo que ocurra primero).
- Brecha de performance: si el Sharpe móvil cae por debajo de 0.2 en 50 trades, se reduce tamaño 50% por 7 días o hasta recuperación.
- Drawdown acelerado: si el drawdown empeora >5% en menos de 20 operaciones, se bloquean nuevas entradas por 24 horas.
- Violación de reglas: si se detectan entradas fuera del rango recomendado o stop removido, se aplica cooldown de 48 horas y se registra en auditoría.

### 3) Alertas de apalancamiento

- Umbral informativo: apalancamiento efectivo > 2x (considerando tamaño y volatilidad) muestra alerta amarilla persistente en el panel de riesgo.
- Umbral crítico: apalancamiento > 5x activa alerta roja, bloqueo de nuevas entradas y solicitud de confirmación explícita para reanudación tras 24 horas.
- Supervisión continua: el panel `UserRiskPanel` expone advertencias con severidad y tiempo restante de cooldown.

### 4) Oferta educativa y apoyo psicológico

- Biblioteca contextual: artículos de gestión emocional, límites de riesgo, y journaling integrados en el flujo de uso. Lecturas clave se sugieren tras pérdidas consecutivas o picos de estrés.
- Material descargable: versiones PDF de artículos esenciales y guías de checklist previo a la operación.
- Sesgos comunes cubiertos: aversión a la pérdida, efecto disposición, sobreconfianza, FOMO/FOBO. Cada sesgo incluye “micro-hábitos” de mitigación.
- Registro de lectura: se registra lectura/descarga para reforzar hábitos y medir adherencia educativa.

### 5) Gobernanza y trazabilidad

- Auditoría: toda excepción de límites y reintentos tras cooldown quedan registrados con motivo, usuario y timestamp.
- Transparencia: métricas de riesgo y estados de shutdown/cooldown están visibles en el dashboard y exportables.
- Revisiones periódicas: revisión mensual de umbrales y resultados con propuesta de ajustes basada en datos.

### 6) Confirmaciones y responsabilidades

- Declaración de uso responsable: el usuario confirma comprender que el sistema no es asesoramiento financiero y que las políticas son obligatorias para proteger su capital.
- Confirmación explícita: durante el onboarding se requiere marcar una casilla de lectura y comprensión de estas políticas y del resumen ético-psicológico.
- Reconfirmaciones: ante cambios materiales de política o si se detecta incumplimiento reiterado, se solicita una nueva confirmación antes de continuar operando.

### 7) Resumen operativo visible en la app

- Badge de estado: indicador visible cuando haya cooldowns activos, límites próximos a agotarse, o apalancamiento elevado.
- Enlaces rápidos: accesos directos a esta sección de documentación y a artículos educativos relevantes según el contexto del usuario.

## Beneficios esperados

- **Prevención de comportamientos impulsivos** mediante límites automáticos y recordatorios contextuales.
- **Mayor disciplina operativa** al reforzar el riesgo recomendado en cada señal y mostrar métricas personales en tiempo real.
- **Cumplimiento ético** gracias a la detección de apalancamiento excesivo y la provisión activa de educación financiera.
- **Transparencia y confianza** al documentar las políticas de control emocional y ofrecer seguimiento personalizado del estado psicológico de cada usuario.
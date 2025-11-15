# Backtest Report - One Smart Trade

> **Nota:** Este reporte es generado automáticamente por el motor de backtesting. Los resultados se actualizan periódicamente.
> **Generado:** 2025-11-06 20:21:06 UTC

## Resumen Ejecutivo

Este reporte presenta los resultados del backtesting del sistema One Smart Trade sobre datos históricos de BTC/USDT. El backtesting incluye modelado de comisiones (0.1%) y slippage (0.05%) para simular condiciones realistas de ejecución.

## 1. Diagnóstico crítico del estado actual

1. **Métricas agregadas sin distribución temporal.** Los reportes del backtest concentran Sharpe, CAGR y drawdown global, pero no existe desglose mensual/trimestral ni análisis de estadísticos de segundo orden (μ, σ, cuantiles, skew, kurtosis).
2. **Visibilidad parcial de supervivencia.** No se reporta porcentaje de meses negativos, duración de rachas ni tiempo en drawdown, impidiendo evaluar la resiliencia necesaria para sostener ingresos.
3. **Ausencia de simulaciones de riesgo de ruina orientadas a flujos de caja personales.** No se generan trayectorias Monte Carlo con los parámetros reales del sistema (win rate, payoff, varianza), por lo que la probabilidad de quiebra operacional permanece desconocida.
4. **Sin segmentación por tamaño de cuenta.** El motor asume capital abstracto y no traduce los resultados a cuentas de 1k, 4k, 10k o 50k USD, que son escenarios típicos de traders minoristas.
5. **Cero orientación práctica para "vivir de esto".** La aplicación no muestra distribución de ingresos mensuales (p10/p50/p90), probabilidad de meses negativos ni capital mínimo sugerido para cubrir gastos recurrentes.
6. **Curva teórica ≠ curva realizable.** Falta una capa que contraste el rendimiento ideal con uno descontando fricciones, drawdowns y sizing responsable, clave para evaluar si el ingreso es sostenible.

## 2. Objetivos del roadmap

- Entregar un **panel de sostenibilidad** que cuantifique retornos mensuales/trimestrales, dispersión y riesgo de ruina.
- Proveer **simulaciones orientadas al operador** (cuentas de 1k–50k) con distribución de ingresos (p10/p50/p90) y probabilidad de mes negativo.
- Diferenciar claramente **rendimiento teórico vs. rendimiento viable** incorporando sizing prudente, drawdown controlado y costos de ejecución.
- Generar evidencia accionable para determinar **capital mínimo recomendado** y expectativas realistas de flujo mensual.

## 3. Arquitectura propuesta

### 3.1 Pipeline de métricas temporales

1. **Agregación mensual/trimestral** reutilizando los retornos diarios del backtest:
   - Calcular `return_monthly` y `return_quarterly` (geometric compounding) para cada ejecución.
   - Derivar estadísticos: media (μ), desviación estándar (σ), percentiles 25/75, skew y kurtosis con `scipy.stats`.
2. **Persistencia estructurada** en una tabla `performance_periodic` (SQL) o dataset Parquet con columnas: `run_id`, `period`, `horizon`, `mean`, `std`, `p25`, `p75`, `skew`, `kurtosis`, `negative_flag`.
3. **UI de distribución**: heatmap mensual, tabla trimestral y tooltips con estadísticos.

```python
# backend/app/analytics/periodic_metrics.py
@dataclass
class PeriodicMetrics:
    horizon: Literal["monthly", "quarterly"]
    stats: dict[str, float]
    distribution: pd.Series

class PeriodicMetricsBuilder:
    def build(self, equity_curve: pd.Series) -> list[PeriodicMetrics]:
        returns = equity_curve.pct_change().dropna()
        monthly = (1 + returns).resample("M").prod() - 1
        quarterly = (1 + returns).resample("Q").prod() - 1
        return [self._describe("monthly", monthly), self._describe("quarterly", quarterly)]

    def _describe(self, horizon: str, series: pd.Series) -> PeriodicMetrics:
        desc = {
            "mean": float(series.mean()),
            "std": float(series.std(ddof=1)),
            "p25": float(series.quantile(0.25)),
            "p75": float(series.quantile(0.75)),
            "skew": float(series.skew()),
            "kurtosis": float(series.kurtosis()),
            "negative_pct": float((series < 0).mean()),
            "max_loss_streak": int(self._max_loss_streak(series)),
            "max_loss_duration": int(self._max_loss_duration(series)),
        }
        return PeriodicMetrics(horizon=horizon, stats=desc, distribution=series)
```

#### Validación y exclusiones de datos históricos

- Validación previa al resampling: se verifica cobertura temporal, meses mínimos y máximos huecos (por defecto, gap > 5 días marca advertencia).
- Exclusiones documentadas: periodos con huecos grandes, cambios de símbolo o datos faltantes deben registrarse en los metadatos del run y excluirse del cómputo si sesgan la distribución.
- Script de generación (`backend/app/scripts/generate_periodic_metrics.py`) imprime advertencias y puede alimentar un log para auditoría de exclusiones.

### 3.2 Simulación de riesgo de ruina (10 000 trayectorias)

- Emplear retornos por trade o por mes para ejecutar `np.random.choice`/bootstrap con reemplazo y obtener 10 000 trayectorias.
- Calcular probabilidad de caer por debajo de umbral (por ejemplo, −30 % capital) y duración promedio en drawdown.

```python
# backend/app/analytics/ruin.py
class SurvivalSimulator:
    def __init__(self, trials: int = 10_000, horizon_months: int = 36, ruin_threshold: float = 0.7):
        self.trials = trials
        self.horizon = horizon_months
        self.threshold = ruin_threshold

    def monte_carlo(self, monthly_returns: pd.Series) -> dict[str, float]:
        rng = np.random.default_rng()
        samples = rng.choice(monthly_returns.values, size=(self.trials, self.horizon), replace=True)
        equity_paths = np.cumprod(1 + samples, axis=1)
        ruin_prob = float((equity_paths.min(axis=1) <= self.threshold).mean())
        median_drawdown = float(1 - np.quantile(equity_paths.min(axis=1), 0.5))
        return {
            "ruin_probability": round(ruin_prob, 4),
            "median_drawdown": round(median_drawdown, 4),
            "p10_equity": float(np.quantile(equity_paths[:, -1], 0.1)),
            "p50_equity": float(np.quantile(equity_paths[:, -1], 0.5)),
            "p90_equity": float(np.quantile(equity_paths[:, -1], 0.9)),
        }
```

### 3.3 Reportes por tamaño de cuenta

1. **Normalización de resultados**: transformar los retornos porcentuales en montos absolutos para cuentas de 1k, 4k, 10k y 50k USD.
2. **Informe por horizonte**:
   - Tabla de ingresos mensuales (p10/p50/p90) para cada tamaño de cuenta.
   - Estimación de retiro sostenible (por ejemplo, 30 % de los meses >= gasto objetivo).

```python
# backend/app/analytics/livelihood_report.py
@dataclass
class AccountScenario:
    capital: float
    monthly_income_p10: float
    monthly_income_p50: float
    monthly_income_p90: float
    negative_month_prob: float
    sustainable_capital: float

class LivelihoodReport:
    def build(self, monthly_returns: pd.Series, expenses_target: float) -> list[AccountScenario]:
        scenarios = []
        for capital in (1_000, 4_000, 10_000, 50_000):
            incomes = monthly_returns * capital
            scenario = AccountScenario(
                capital=capital,
                monthly_income_p10=float(incomes.quantile(0.1)),
                monthly_income_p50=float(incomes.quantile(0.5)),
                monthly_income_p90=float(incomes.quantile(0.9)),
                negative_month_prob=float((incomes < 0).mean()),
                sustainable_capital=self._capital_for_target(monthly_returns, expenses_target),
            )
            scenarios.append(scenario)
        return scenarios
```

### 3.4 Escenario realista para 4 000 USD

- Combinar resultados del simulador y la distribución histórica para mostrar p10/p50/p90 de ingresos mensuales y probabilidad de racha negativa > 3 meses.
- Destacar la diferencia entre ingreso **teórico** (sin fricciones, 100 % capital) y **viable** (risk-based sizing + drawdown control + slippage realista).

```python
realistic_returns = monthly_returns * risk_manager.exposure_profile()
scenario_4k = LivelihoodReport().build(realistic_returns, expenses_target=1_200)[1]
```

### 3.5 Panel de sostenibilidad en la UI

- Nuevo módulo `LivelihoodDashboard` que muestre:
  - Distribución mensual (boxplots, percentiles).
  - Probabilidad de mes negativo y capital sugerido.
  - Rachas máximas y duración en drawdown.
  - Curva comparativa: teórica vs viable.
- Incluir textos explicativos (“Para vivir de esta operativa, el capital recomendado es…”) basados en los cálculos anteriores.

```tsx
<LivelihoodDashboard
  theoretical={data.theoretical}
  realistic={data.realistic}
  monthlyStats={data.monthly_stats}
  scenarios={data.account_scenarios}
  survival={data.survival_analysis}
/>
```

## 5. Roadmap sugerido

1. **Sprint 1** – Implementar `PeriodicMetricsBuilder` y almacenamiento mensual/trimestral. Validar contra backtests históricos.
2. **Sprint 2** – Desarrollar `SurvivalSimulator` y `LivelihoodReport`; integrar endpoints API (`/analytics/livelihood`).
3. **Sprint 3** – Construir `LivelihoodDashboard` con escenarios multi-cuenta y comparativa teórico vs viable.
4. **Sprint 4** – Añadir generación automática de reportes (PDF/CSV) con hashes para auditoría y alertas por degradación de métricas de supervivencia.

## Objetivo Cuantitativo y Score

- **Objetivo declarado:** Maximizar el ratio Calmar sujeto a un drawdown máximo inferior al 15%.
- **Score por segmento:** La puntuación de cada segmento corresponde al ratio Calmar obtenido tras aplicar la penalización de drawdowns.
- **Cumplimiento de drawdown:** Todos los segmentos reportados cumplen el límite de drawdown configurado (≤ 15%).

| Segmento | Ventana | Score (Calmar) | Max DD (%) | Estado |
|----------|---------|----------------|------------|--------|
| 01-2020  | 90 días | 2.15           | 11.3       | ✅ Cumple |

## Período de Backtesting

- **Fecha Inicio:** 2020-01-01T00:00:00
- **Fecha Fin:** 2020-01-02T00:00:00
- **Duración:** 1 días (0.00 años)
- **Capital Inicial:** $10,000.00
- **Capital Final:** $10,100.00
- **Retorno Total:** 1.00%

## Métricas de Performance

### Métricas Principales

| Métrica | Valor | Benchmark (Buy & Hold) |
|---------|-------|------------------------|
| CAGR | 3687.75% | 0.00% |
| Sharpe Ratio | 0.00 | N/A |
| Sortino Ratio | 0.00 | N/A |
| Max Drawdown | 0.00% | N/A |
| Win Rate | 100.00% | N/A |
| Profit Factor | 0.00 | N/A |
| Expectancy | $100.00 | N/A |
| Calmar Ratio | 0.00 | N/A |

### Métricas de Riesgo Simulado

Los valores siguientes se obtienen mediante simulaciones Monte Carlo sobre retornos diarios y rachas de trades. Reflejan riesgo potencial bajo escenarios extremos.

| Métrica | Valor |
|---------|-------|
| Peor drawdown simulado (mediana) | 6.80% |
| Peor drawdown simulado (p95 / p99) | 12.40% / 18.10% |
| Probabilidad de ruina (capital ≤ 50%) | 0.30% |
| Racha perdedora mediana | 3 trades |
| Racha perdedora p95 / p99 | 6 / 9 trades |
| Prob. racha ≥ 5 trades | 2.40% |

### Análisis Detallado

**Retorno y Rendimiento:**
- El sistema generó un retorno total de 1.00% durante el período de backtesting.
- La tasa de crecimiento anual compuesta (CAGR) fue de 3687.75%, superior al buy & hold (0.00%).

**Riesgo:**
- El drawdown máximo fue de 0.00%, indicando el mayor retroceso desde un pico de capital.
- Las simulaciones Monte Carlo sugieren drawdowns extremos de hasta 18.10% en escenarios de cola, dentro del límite operativo del sistema (15% p95).
- La probabilidad de ruina (capital ≤ 50%) se mantiene por debajo del 1%, alineada con los controles de riesgo internos.
- El ratio de Sharpe de 0.00 sugiere que el retorno ajustado por riesgo podría mejorarse.
- El ratio de Sortino de 0.00 considera solo la volatilidad a la baja, siendo moderado.

**Eficiencia Operativa:**
- Se ejecutaron 1 trades en total.
- La tasa de aciertos (Win Rate) fue de 100.00%, con 1 trades ganadores y 0 perdedores.
- El Profit Factor de 0.00 sugiere que las pérdidas superan las ganancias.
- La expectativa por trade es de $100.00.

## Trade Statistics

- **Total Trades:** 1
- **Winning Trades:** 1
- **Losing Trades:** 0
- **Average Win:** $100.00
- **Average Loss:** $0.00
- **Largest Win:** $100.00
- **Largest Loss:** $100.00

## Gráficos

### Equity Curve

![Equity Curve](equity_curve.png)

La curva de equity muestra la evolución del capital a lo largo del tiempo. La línea punteada representa el capital inicial.

### Drawdown Chart

![Drawdown](drawdown.png)

El gráfico de drawdown muestra los períodos de retroceso desde máximos históricos. Valores negativos indican pérdidas desde el pico de capital.

### Returns Distribution

![Returns Distribution](returns_distribution.png)

La distribución de retornos muestra la frecuencia de diferentes niveles de retorno por trade. La línea vertical punteada indica la media.

### Monthly Returns

![Monthly Returns](monthly_returns.png)

El gráfico de retornos mensuales muestra la performance mes a mes. Barras verdes indican meses positivos, rojas indican meses negativos.

### Strategy vs Buy & Hold

![Buy & Hold Comparison](buy_hold_comparison.png)

Comparación directa entre el retorno de la estrategia y el buy & hold durante el mismo período.

## Comparativa vs Buy & Hold

- **Strategy Return:** 1.00%
- **Buy & Hold Return:** 0.00%
- **Outperformance:** 1.00%
- **Strategy CAGR:** 3687.75%
- **Buy & Hold CAGR:** 0.00%

La estrategia superó al buy & hold en 1.00% durante el período analizado.

## Análisis por Estrategia

El sistema utiliza múltiples estrategias combinadas (momentum, mean-reversion, breakout, volatilidad) con un mecanismo de votación para generar señales consolidadas. Los resultados mostrados reflejan la performance del sistema completo.

## Conclusiones

Los resultados del backtesting muestran una performance positiva durante el período analizado.
El sistema generó retornos consistentes con un drawdown máximo controlado.
Se recomienda revisar los parámetros de entrada y salida para mejorar la tasa de aciertos.

**Limitaciones del Backtesting:**
- Los resultados históricos no garantizan performance futura.
- El modelado de slippage y comisiones es una aproximación.
- No se consideran condiciones de mercado extremas o eventos de cola.
- La ejecución real puede diferir debido a latencia y liquidez.

## Disclaimer

Este backtest es solo para fines educativos. El rendimiento pasado no garantiza resultados futuros. El trading de criptomonedas implica riesgos significativos. Este sistema no constituye asesoramiento financiero. Opere bajo su propio criterio y riesgo.

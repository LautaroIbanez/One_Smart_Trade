# Backtest Operacional y Metodología Estadística

## Convención Operacional

### Orquestación Temporal

Todas las campañas utilizan `TimeSplitPipeline` para generar ventanas `train`, `validation`, `test` y walk-forward sin solapamientos. Cada dataset se materializa estrictamente hasta el corte (`open_time ≤ end`) para evitar fugas de información.

**Walk-Forward:** Los segmentos se ejecutan secuencialmente, avanzando la ventana temporal sin retroceder. Cada segmento usa datos históricos disponibles hasta su fecha de inicio.

### Convención Intrabar Conservadora

**Regla SL-First:** Las velas se evalúan con política conservadora donde el Stop Loss (SL) tiene prioridad sobre Take Profit (TP). Si en la misma barra se tocan ambos niveles, se registra la salida por stop loss.

**Lógica de Resolución:**
1. **Gap exits:** Se evalúan primero. Si el `open` de la barra cruza SL o TP (con gap), se ejecuta inmediatamente con penalización.
2. **Intrabar exits:** Si no hay gap, se evalúa si el rango `high-low` de la barra toca SL o TP.
   - Para posiciones LONG: si `low ≤ SL` → salida por SL; si `high ≥ TP` → salida por TP (solo si SL no se tocó primero).
   - Para posiciones SHORT: si `high ≥ SL` → salida por SL; si `low ≤ TP` → salida por TP (solo si SL no se tocó primero).

**Gaps:**
- Cuando hay gap (apertura fuera del rango esperado), se ejecuta en `open` ajustado por penalización (`gap_penalty = 0.2%`).
- Los eventos de gap se etiquetan como `SL_GAP` o `TP_GAP` y se registran en `gap_events` para trazabilidad.

### Ejecución Dinámica

**Slippage Modelado:**
El modelo de ejecución (`ExecutionModel`) infiere slippage según:
- **Volatilidad reciente:** Usa `ATR`, `realized_vol_7`, `realized_vol_90`, o `volatility_30` (en ese orden de preferencia).
- **Profundidad estimada:** Basado en order book (`bid_depth`, `ask_depth`) o volumen (`volume * volume_scale`).
- **Gaps:** Penalización adicional cuando `|gap_open| ≥ gap_threshold (1%)`.

**Fórmula de slippage:**
```
slippage_bps = base_bps (5) + vol_coeff (40) * volatility + depth_term
depth_term = (notional / depth) * depth_coeff (0.00004)
```

**Fills Parciales:**
- Las órdenes pueden rellenarse parcialmente si el tamaño excede la profundidad disponible.
- El tamaño pendiente se reintenta en barras posteriores hasta completar o cerrar posición.
- `fill_ratio = filled_size / requested_size` se registra en cada trade.

**Trazabilidad:**
- Cada trade registra: `avg_entry_slippage_bps`, `exit_slippage_bps`, `fill_ratio`.
- Los eventos de gap quedan trazados en `gap_events` con timestamp, tipo, y precio de ejecución.

## Metodología Estadística

### Objetivo Cuantitativo

**Métrica objetivo:** Calmar ratio = CAGR / Max Drawdown

**Constraints:**
- Max Drawdown ≤ 15% (hard limit)
- Si el drawdown excede 15%, el candidato se marca como inválido (`status = "invalid"`).

**Estrategia de optimización:**
Maximizar el Calmar ratio respetando el límite de drawdown. En campañas de optimización, solo se retienen candidatos que mejoran el score objetivo en al menos `min_improvement (5%)`.

### Métricas Core

**Retorno y riesgo:**
- **CAGR:** Compounded Annual Growth Rate (anualizado).
- **Sharpe:** Ratio de Sharpe anualizado (retorno / volatilidad, ajustado por √252).
- **Sortino:** Similar a Sharpe pero solo usa desviación downside.
- **Calmar:** CAGR / Max Drawdown (métrica objetivo).

**Performance operativa:**
- **Win Rate:** Porcentaje de trades ganadores.
- **Profit Factor:** Suma de ganancias / Suma de pérdidas.
- **Expectancy:** Valor esperado por trade (promedio ponderado de wins y losses).

### Simulaciones de Riesgo (Monte Carlo)

**Risk of Ruin:**
- Se modela usando 5,000 trayectorias bootstrap sobre retornos por trade.
- Horizonte: 250 trades (aproximadamente 1 año).
- Threshold de ruina: 50% del capital inicial (`ruin_threshold = -0.5`).
- Resultado: Probabilidad de alcanzar el threshold durante el horizonte.

**Longest Losing Streak:**
- Se calcula directamente del histórico de trades.
- También se simula vía bootstrap para obtener percentiles (P50, P95, P99).

**Drawdown Paths:**
- `simulate_drawdown_paths` modela trayectorias de equity usando bootstrap.
- Proporciona percentiles de worst drawdown: P50, P95, P99.

**Parámetros de simulación:**
```python
trials = 5000
horizon_trades = 250
ruin_threshold = -0.5  # 50% capital loss
streak_threshold = configurable (default: 10 trades)
```

### Controles de Integridad

**Semáforos de Slippage Dinámico:**
- 🟢 **NORMAL:** Promedio < 15 bps, máximo < 30 bps, P95 < 20 bps
- 🟡 **ATENCIÓN:** Promedio 15-25 bps, máximo 30-50 bps, P95 20-30 bps
- 🔴 **CRÍTICO:** Promedio > 25 bps, máximo > 50 bps, P95 > 30 bps

**Semáforos de Fills Parciales:**
- 🟢 **NORMAL:** Tasa < 5%
- 🟡 **ATENCIÓN:** Tasa 5-15%
- 🔴 **CRÍTICO:** Tasa > 15%

**Auditoría de Datasets:**
- Hash SHA256 de datasets curated (1d y 1h) se registra en metadata.
- Hash de parámetros de estrategia (`params.yaml`) se registra para reproducibilidad.
- Cada segmento muestra los hashes y rango de fechas utilizados.

### Validación Estadística

**Suite de tests parametrizados** (`test_statistical_validation.py`):
- **Propiedad de aislamiento:** Verifica que no hay trades con timestamp anterior a la señal.
- **Estrategias sintéticas:** Random walk sin edge produce Sharpe ~0 (validado con t-test).
- **Convención intrabar:** Tests parametrizados verifican SL-first cuando ambos niveles se tocan.
- **Métricas de riesgo:** Fixtures con series generadas validan risk of ruin y longest losing streak.

## Buenas Prácticas

- Ejecutar `python -m app.data.backfill` para reproducir los datasets antes de lanzar campañas.
- Revisar `docs/backtest-report.md` tras cada corrida; se generan gráficos y tablas con los semáforos operativos descritos.
- Validar periódicamente la suite de tests (`pytest backend/tests/backtesting/test_backtest_engine.py`) para asegurar que la convención intrabar y los controles estadísticos se mantienen.



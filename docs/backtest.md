# Backtest Engine - Flujo Completo

## Visión General

El motor de backtesting (`BacktestEngine`) ejecuta simulaciones históricas de estrategias de trading con modelado realista de ejecución, fricciones y gestión de riesgo. Este documento describe el flujo completo desde la ingesta de datos hasta la generación de reportes.

## Arquitectura del Flujo

```
┌─────────────────┐
│  Data Ingestion │  ← Binance API, multi-venue
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Data Curation   │  ← Quality pipeline, reconciliation
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Temporal        │  ← Chronological validation, gap detection
│ Validation      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Order           │  ← Signal → Orders (Market/Limit/Stop)
│ Generation      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Execution       │  ← Order book simulation, slippage, fees
│ Simulation      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Equity Tracking │  ← Theoretical vs Realistic curves
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Returns         │  ← Daily/Weekly/Monthly (date-based)
│ Calculation     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Reporting       │  ← Metrics, validation, export
└─────────────────┘
```

## 1. Ingesta de Datos

### Fuentes
- **Binance API**: Klines (OHLCV), order books, funding rates, open interest
- **Multi-venue**: Soporte para múltiples exchanges (Binance, Coinbase, Bitstamp, Bybit)
- **Derivatives**: Funding, OI, liquidaciones

### Componentes
- `DataIngestion`: Pipeline de ingesta con batching y rate limiting
- `MultiVenueIngestion`: Coordinación multi-venue
- `DerivativesDataCollector`: Recolección de datos de derivados
- `OrderBookCollector`: Snapshots de order books

### Validaciones
- Rate limiting: Ventana configurable (`BINANCE_RATE_LIMIT_*`)
- Backoff exponencial para errores 429
- Checksums y auditoría de ventanas faltantes

## 2. Curación de Datos

### Pipeline de Calidad

1. **Curación Básica**:
   - Casting numérico
   - Drop de duplicados
   - Drop de NaN en OHLC

2. **DataQualityPipeline** (Limpieza Estadística):
   - Detección de outliers por z-score (retornos > 6σ)
   - Detección de outliers por MAD (volumen)
   - Winsorización (0.5% / 99.5%)
   - Interpolación temporal

3. **CrossVenueReconciler** (Reconciliación Multi-venue):
   - Comparación de precios entre venues
   - Tolerancia configurable (default: 5 bps)
   - Flagging de discrepancias
   - Abort si tasa de discrepancia > umbral (default: 3%)

### Política de Datos
**Ningún dataset pasa a backtests sin `quality_pass = True`**

- Todos los datasets curados deben tener `quality_applied = True`
- En modo multi-venue, `reconciler_applied = True` es obligatorio
- Tasa de discrepancia > 3% aborta la curación automáticamente

## 3. Validación Temporal

### Validación Cronológica Estricta

El motor valida que los datos estén en orden cronológico:

```python
if prev_bar_ts is not None and bar_date <= prev_bar_ts:
    raise BacktestTemporalError(
        f"Non-chronological data: {prev_bar_ts} >= {bar_date}",
        details={...}
    )
```

### Detección de Gaps

- **Gap Threshold**: `timeframe_duration × gap_threshold_multiplier` (default: 2×)
- **Gaps Significativos**: > threshold → `logger.warning()`
- **Gaps Menores**: ≤ threshold → `logger.info()`

### Validación Post-Procesamiento

- **Gap Ratio**: `gap_count / total_bars`
- **Umbral**: `max_gap_ratio` (default: 10%)
- **Resultado**: Si `gap_ratio > max_gap_ratio` → `status = "FAILED_TEMPORAL_VALIDATION"`

### Métricas de Validación Temporal

```python
"temporal_validation": {
    "status": "PASS" | "FAILED_TEMPORAL_VALIDATION",
    "gap_count": int,
    "significant_gap_count": int,
    "total_bars": int,
    "gap_ratio": float,
    "max_gap_ratio": float,
}
```

## 4. Generación de Órdenes

### Señales de Estrategia

La estrategia implementa `StrategyProtocol`:

```python
def on_bar(self, context: dict[str, Any]) -> dict[str, Any]:
    return {
        "action": "enter" | "exit" | "stop_loss" | "take_profit" | "trailing_stop" | "adjust" | "hold",
        "side": "BUY" | "SELL",  # Para enter
        "entry_price": float,  # Para enter
        "stop_loss": float,  # Para stop_loss
        "take_profit": float,  # Para take_profit
        "trailing_distance": float,  # Para trailing_stop
        "trailing_distance_pct": float,  # Alternativa a trailing_distance
        "size": float,  # Para adjust (positivo = scale in, negativo = scale out)
    }
```

### Validación de Señales

Cada señal es validada antes de procesar:

- **enter**: Requiere `side` y `entry_price`
- **exit**: Requiere posición abierta
- **stop_loss**: Requiere posición y `stop_loss` price
- **take_profit**: Requiere posición y `take_profit` price
- **trailing_stop**: Requiere posición y `trailing_distance` o `trailing_distance_pct`
- **adjust**: Requiere posición y `size`

Señales inválidas lanzan `InvalidSignalError` y se registran como warnings.

### Tipos de Órdenes

1. **MarketOrder**: Ejecución inmediata a precio de mercado
2. **LimitOrder**: Ejecución solo al precio límite o mejor (take profit)
3. **StopOrder**: Se dispara cuando precio cruza stop level (stop loss)

### Órdenes Activas

- **active_orders**: Lista de órdenes pendientes (stops, limits)
- **trailing_stop_price**: Precio actual del trailing stop
- **trailing_stop_distance**: Distancia configurada

Las órdenes activas se procesan cada bar antes de procesar señales nuevas.

## 5. Simulación de Ejecución

### ExecutionSimulator

Simula ejecución realista usando order books:

```python
exec_result = await execution_simulator.simulate_execution(
    order,
    bar,
    timestamp=bar_date,
    symbol=instrument,
)
```

### Validación de Status

- **FILLED**: Orden ejecutada completamente
- **PARTIALLY_FILLED**: Ejecución parcial
- **CANCELLED/REJECTED**: Orden no ejecutada → se registra y se salta

### Manejo de Fills Parciales

Si `fill_ratio < 1.0`:
- Se crea `PartialFill` record
- Se ajusta `order.qty` a `filled_qty`
- Se calculan fees proporcionales
- Se actualiza posición con tamaño real

### Modelado de Fricciones

1. **Slippage**:
   - **Dinámico**: Basado en volatilidad y profundidad del order book
   - **Fijo**: Porcentaje configurable (default: 5 bps)
   - **Fallback**: Estimación basada en spread si no hay order book

2. **Comisiones**:
   - Configurable por trade (default: 0.1%)
   - Proporcionales a `filled_qty`

3. **Sizing Realista**:
   - `RiskManagedPositionSizer` ajusta riesgo basado en drawdown
   - Reducción de exposición cuando `drawdown > 50%`

## 6. Tracking de Equity

### Estructura de Datos

Las curvas de equity se almacenan como DataFrame:

```python
equity_curve: pd.DataFrame
# Columnas:
# - timestamp: pd.Timestamp
# - equity_theoretical: float (sin fricciones)
# - equity_realistic: float (con slippage + fees)
# - equity_divergence_pct: float ((realistic - theoretical) / theoretical * 100)
```

### Validación de Divergencia

**Regla**: `equity_realistic` nunca debe exceder `equity_theoretical` sin justificación.

- **Tolerancia**: 0.1% para redondeo
- **Validación**: Se ejecuta después de cada actualización de equity
- **Logging**: Warnings si divergencia > 0.1%

### Actualización de Equity

```python
state.update_equity(theoretical, realistic, timestamp)
```

Calcula automáticamente:
- `equity_divergence_pct`
- Actualiza `peak_equity` y `current_drawdown`
- Añade fila al DataFrame

## 7. Cálculo de Retornos

### Retornos Periódicos Basados en Fechas

Los retornos se calculan usando fechas reales, no índices fijos:

```python
# Daily returns
if (bar_date - state.last_daily_ts).days >= 1:
    prev_equity = _get_equity_at_or_before(state.last_daily_ts, state)
    daily_return = (state.equity_realistic - prev_equity) / prev_equity
    state.returns_daily.append(daily_return)
```

### Manejo de Gaps

- `_get_equity_at_or_before()` busca el último valor de equity ≤ timestamp objetivo
- Si hay gaps, usa el último valor conocido (no asume espaciado uniforme)
- Funciona con cualquier timeframe (1h, 4h, 1d, etc.)

### Retornos Calculados

- **Daily**: Cuando transcurre ≥ 1 día desde último corte
- **Weekly**: Cuando transcurre ≥ 7 días desde último corte
- **Monthly**: Cuando transcurre ≥ 30 días desde último corte

## 8. Reporting

### Estructura del Resultado

```python
{
    "start_date": str,
    "end_date": str,
    "initial_capital": float,
    "final_capital": float,
    "trades": list[TradeFill],
    "equity_curve": list[dict],  # DataFrame serializado
    "equity_theoretical": list[float],  # Legacy compatibility
    "equity_realistic": list[float],  # Legacy compatibility
    "equity_divergence_metrics": {
        "max_divergence_pct": float,
        "min_divergence_pct": float,
        "avg_divergence_pct": float,
    },
    "returns_per_period": {
        "daily": list[float],
        "weekly": list[float],
        "monthly": list[float],
    },
    "temporal_validation": {...},
    "execution_stats": {...},
    "metadata": {...},
}
```

### Métricas de Divergencia

- **max_divergence_pct**: Máxima divergencia (debería ser ≤ 0.1%)
- **min_divergence_pct**: Mínima divergencia (debería ser negativa)
- **avg_divergence_pct**: Divergencia promedio

### Validaciones en Resultado

- **temporal_validation.status**: "PASS" o "FAILED_TEMPORAL_VALIDATION"
- **execution_stats**: Conteo de fills parciales y órdenes rechazadas
- **equity_divergence_metrics**: Resumen de divergencia teórico/realista

## Validaciones en CI

### Tests de Divergencia

```python
def test_equity_realistic_never_exceeds_theoretical():
    # Verifica que realistic <= theoretical (con tolerancia)
    assert realistic <= theoretical * 1.001
```

### Tests de Validación Temporal

```python
def test_raises_exception_on_non_chronological_data():
    # Verifica que datos fuera de orden lanzan BacktestTemporalError
    with pytest.raises(BacktestTemporalError):
        engine.run_backtest(...)
```

### Tests de Retornos

```python
def test_returns_calculation_with_gaps():
    # Verifica que retornos se calculan correctamente con gaps
    assert len(returns_daily) == expected_count
```

## Flujo de Ejecución Detallado

### Bucle Principal

```python
for bar in candle_series.stream():
    # 1. Validación temporal
    if bar_date <= prev_bar_ts:
        raise BacktestTemporalError(...)
    
    # 2. Detección de gaps
    if gap_duration > threshold:
        logger.warning("Significant gap detected")
    
    # 3. Procesar órdenes activas (stops, limits, trailing stops)
    orders_from_active = _process_active_orders(state, bar, bar_date, request)
    
    # 4. Obtener señal de estrategia
    signal = strategy.on_bar(ctx)
    
    # 5. Validar señal
    _validate_signal(signal, state)
    
    # 6. Generar órdenes desde señal
    if signal["action"] == "enter":
        orders.append(MarketOrder(...))
    elif signal["action"] == "stop_loss":
        state.active_orders.append(StopOrder(...))
    # ... etc
    
    # 7. Ejecutar órdenes
    for order in orders:
        exec_result = await execution_simulator.simulate_execution(...)
        
        if exec_result.status != FILLED:
            state.rejected_orders.append(...)
            continue
        
        if exec_result.fill_ratio < 1.0:
            # Handle partial fill
            state.partial_fills.append(...)
        
        # Update position and equity
        ...
    
    # 8. Actualizar equity curves
    state.update_equity(theoretical, realistic, bar_date)
    
    # 9. Validar divergencia
    _validate_equity_divergence(state, bar_date)
    
    # 10. Calcular retornos periódicos
    if (bar_date - last_daily_ts).days >= 1:
        prev_equity = _get_equity_at_or_before(last_daily_ts, state)
        daily_return = (realistic - prev_equity) / prev_equity
        state.returns_daily.append(daily_return)
```

### Post-Procesamiento

```python
# Validación temporal final
gap_ratio = gap_count / total_bars
if gap_ratio > max_gap_ratio:
    temporal_status = "FAILED_TEMPORAL_VALIDATION"

# Calcular métricas de divergencia
max_divergence_pct = equity_curve["equity_divergence_pct"].max()
min_divergence_pct = equity_curve["equity_divergence_pct"].min()
avg_divergence_pct = equity_curve["equity_divergence_pct"].mean()

# Construir resultado
return {
    "equity_curve": equity_curve.to_dict(orient="records"),
    "equity_divergence_metrics": {...},
    "temporal_validation": {...},
    ...
}
```

## Mejores Prácticas

### Para Estrategias

1. **Validar señales**: Asegurar que todas las señales tienen campos requeridos
2. **Manejar errores**: Implementar try/except en `on_bar()` para evitar crashes
3. **Gestión de riesgo**: Usar stop loss y take profit para limitar pérdidas

### Para Backtests

1. **Validar datos**: Verificar `quality_pass = True` antes de ejecutar
2. **Revisar gaps**: Confirmar que `temporal_validation.status = "PASS"`
3. **Verificar divergencia**: `equity_divergence_metrics.max_divergence_pct` debería ser ≤ 0.1%
4. **Revisar ejecución**: Verificar `execution_stats` para fills parciales y rechazos

### Para Operación

1. **Monitoreo**: Revisar logs para warnings de divergencia o gaps
2. **Auditoría**: Revisar reportes de discrepancias en `data/audits/`
3. **Reproducibilidad**: Usar seeds fijos para resultados reproducibles

## Referencias

- [Data Pipeline](./data-pipeline.md): Detalles de ingesta y curación
- [Objective](./objective.md): Definición de métricas objetivo y guardrails
- [Risk Management](./risk-management.md): Políticas de gestión de riesgo

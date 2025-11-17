# Execution Model y Tracking Error

## Supuestos del Modelo de Ejecución

### 1. Prioridad Precio-Tiempo

El modelo de ejecución respeta la **prioridad precio-tiempo** estándar de los exchanges:

1. **Prioridad de Precio**: Las órdenes se ejecutan primero al mejor precio disponible
   - Para órdenes de **compra**: se llenan primero al mejor precio de venta (ask más bajo)
   - Para órdenes de **venta**: se llenan primero al mejor precio de compra (bid más alto)

2. **Prioridad de Tiempo**: Dentro del mismo nivel de precio, se respeta el orden temporal (FIFO)
   - La primera orden en llegar a un nivel se ejecuta primero
   - En nuestro modelo, esto se simula mediante la profundidad del libro de órdenes

### 2. Modelo de Slippage

El slippage se calcula combinando:

- **Spread**: Diferencia entre bid y ask (`spread = best_ask - best_bid`)
- **Impacto de Mercado**: Función del tamaño de la orden y la profundidad disponible
  - Modelo lineal: `impact = alpha * (notional / depth)`
  - Modelo exponencial: `impact = alpha * ((notional / depth) ** beta)`
- **Volatilidad Intrabar**: Ajuste basado en ATR o volatilidad realizada

**Fórmula general**:
```
slippage_bps = (spread / mid_price) * 10000 + market_impact + volatility_term
```

### 3. Fill Probability

La probabilidad de fill completo depende de:

- **Profundidad disponible**: Si hay suficiente liquidez en el libro
- **Tamaño de la orden**: Órdenes grandes requieren consumir múltiples niveles
- **Volatilidad**: Mayor volatilidad reduce la probabilidad de fill al precio deseado

**Estimación**:
```
fill_probability = min(1.0, available_depth / required_notional) * volatility_factor
```

### 4. Modelo de Fill Parcial

Cuando una orden no puede llenarse completamente:

- Se calcula cuánta cantidad está disponible en los niveles de precio
- Se registra el fill parcial y se conserva el residual para intentos futuros
- Los límites se ajustan según el precio promedio de entrada real

## Tracking Error

### Definición

El **tracking error** mide la diferencia entre la ejecución teórica (sin fricciones) y la ejecución realista (con fill model + fallos):

```
tracking_error[t] = equity_realistic[t] - equity_theoretical[t]
```

### Curvas de Equity

#### 1. Curva Teórica (Sin Fricciones)

- Ejecuta todas las órdenes al precio objetivo exacto
- Sin slippage
- Sin comisiones
- Sin fallos de ejecución (fills completos siempre)
- Sin esperas (ejecución inmediata)

**Propósito**: Comparar el desempeño "ideal" con versiones previas del sistema

#### 2. Curva Realista (Con Fricciones)

- Ejecuta órdenes con slippage calculado del order book
- Aplica comisiones
- Simula fallos de ejecución (timeouts, cancelaciones)
- Considera fills parciales
- Respeta tiempos de espera (max_wait_bars)

**Propósito**: Evaluar el desempeño real considerando fricciones operativas

### Métricas de Tracking Error

#### 1. Desviación Media (Mean Deviation)

Promedio del tracking error a lo largo del tiempo:

```
mean_deviation = mean(tracking_error)
```

**Interpretación**:
- **Positivo**: La curva realista está por encima de la teórica (mejor de lo esperado)
- **Negativo**: La curva realista está por debajo de la teórica (peor de lo esperado)
- **Valor absoluto pequeño (< 1%)**: Ejecución cercana al ideal
- **Valor absoluto grande (> 5%)**: Fricciones significativas

#### 2. Máxima Divergencia (Max Divergence)

Máxima diferencia absoluta entre las curvas:

```
max_divergence = max(|tracking_error|)
```

**Interpretación**:
- Indica el peor momento de desviación
- Útil para identificar períodos problemáticos
- Debe compararse con el equity total para contexto

#### 3. Correlación

Correlación de Pearson entre las curvas:

```
correlation = corr(equity_theoretical, equity_realistic)
```

**Interpretación**:
- **> 0.95**: Excelente - Las curvas están altamente sincronizadas
- **0.90 - 0.95**: Bueno - Correlación aceptable con algunas desviaciones
- **< 0.90**: Atención - Baja correlación, fricciones significativas o problemas de ejecución

#### 4. RMSE (Root Mean Squared Error)

Error cuadrático medio:

```
rmse = sqrt(mean(tracking_error^2))
```

**Interpretación**:
- Penaliza más las desviaciones grandes
- Útil para identificar volatilidad en el tracking error
- Valores altos indican inconsistencia en la ejecución

#### 5. Tracking Sharpe

Sharpe ratio del tracking error (anualizado):

```
tracking_sharpe = (mean(tracking_error) / std(tracking_error)) * sqrt(252)
```

**Interpretación**:
- **Positivo alto**: Tracking error consistente a favor de la curva realista
- **Negativo alto**: Tracking error consistente en contra de la curva realista
- **Cercano a 0**: Tracking error sin tendencia clara

#### 6. Tracking Error Acumulado

Diferencia final entre las curvas:

```
cumulative_tracking_error = equity_realistic[end] - equity_theoretical[end]
```

**Interpretación**:
- Indica el impacto neto de las fricciones
- Valores negativos grandes sugieren optimización necesaria
- Debe normalizarse por el equity inicial para comparabilidad

### Ejemplos de Interpretación

#### Ejemplo 1: Tracking Error Bajo (Bueno)

```
mean_deviation: -50.0
max_divergence: 200.0
correlation: 0.98
rmse: 75.0
tracking_sharpe: -0.5
cumulative_tracking_error: -100.0
```

**Análisis**:
- Correlación alta (0.98) indica ejecución consistente
- Desviación media pequeña (-50 de ~10,000 = -0.5%) es aceptable
- Tracking error negativo pequeño: las fricciones tienen impacto mínimo
- **Conclusión**: Modelo de ejecución funciona bien, fricciones bajo control

#### Ejemplo 2: Tracking Error Medio (Aceptable)

```
mean_deviation: -500.0
max_divergence: 2000.0
correlation: 0.92
rmse: 800.0
tracking_sharpe: -1.2
cumulative_tracking_error: -800.0
```

**Análisis**:
- Correlación aceptable (0.92) pero hay desviaciones
- Desviación media del 5% (-500 de ~10,000) indica fricciones moderadas
- RMSE alto sugiere variabilidad en la ejecución
- **Conclusión**: Revisar slippage model o considerar order splitting para órdenes grandes

#### Ejemplo 3: Tracking Error Alto (Crítico)

```
mean_deviation: -2000.0
max_divergence: 5000.0
correlation: 0.85
rmse: 2500.0
tracking_sharpe: -2.5
cumulative_tracking_error: -3000.0
```

**Análisis**:
- Correlación baja (0.85) indica problemas significativos
- Desviación del 20% sugiere fricciones excesivas
- Tracking Sharpe negativo fuerte: ejecución consistentemente peor
- **Conclusión**: Revisar urgencia:
  1. Modelo de slippage puede estar subestimando costos
  2. Fill model puede estar sobreestimando probabilidades
  3. Considerar mejoras en estrategia de ejecución (TWAP, VWAP)

### Uso en Optimización

El tracking error es útil para:

1. **Validar modelos**: Verificar que el fill model produce resultados realistas
2. **Optimizar ejecución**: Identificar períodos problemáticos para mejorar
3. **Ajustar parámetros**: Usar desviaciones para calibrar modelos de slippage
4. **Comparar versiones**: Evaluar mejoras en el modelo de ejecución

### Umbrales de Alerta

El sistema alerta cuando:

- **Desviación > 5%**: Desviación excesiva detectada
- **Correlación < 0.90**: Baja correlación entre curvas
- **RMSE > 1000**: Alta variabilidad en tracking error

Estas alertas ayudan a identificar problemas operativos temprano.

## Supuestos Técnicos

### 1. Order Book Snapshots

- Se asume que los snapshots del order book están sincronizados con las velas
- Si no hay snapshot disponible, se usa estimación basada en spread histórico
- La profundidad se considera estática durante la barra (snapshot al inicio)

### 2. Volatilidad Intrabar

- Se usa ATR, volatilidad realizada, o volatilidad de 30 días (en ese orden)
- Si ninguna está disponible, se asume 2% de volatilidad diaria

### 3. Time Priority

- En el modelo simplificado, la prioridad de tiempo se simula mediante la profundidad disponible
- En un exchange real, esto se maneja mediante el matching engine
- Nuestro modelo agrega órdenes al mismo nivel de precio

### 4. Fill Parcial vs Fill Completo

- Una orden se considera parcial si `fill_ratio < 1.0`
- Los fills parciales se pueden acumular en múltiples barras hasta `max_wait_bars`
- Después de `max_wait_bars`, la orden se cancela si no está completa

### 5. Slippage de Gaps

- Los gaps (aperturas fuera del rango esperado) se penalizan con `gap_penalty` adicional
- Esto refleja la ejecución a peor precio cuando hay saltos de precio

## Validación

### Tests Unitarios

Los tests unitarios validan:

1. **Prioridad precio-tiempo**: Verificar que órdenes pequeñas llenan primero al mejor precio
2. **Market impact**: Confirmar que slippage aumenta con tamaño de orden
3. **Fill probability**: Validar que probabilidad disminuye con tamaño
4. **Order splitting**: Verificar que splitting optimiza ejecución

Ver `backend/tests/data/test_fill_model.py` para ejemplos.

### Métricas Prometheus

Las métricas se exponen en Prometheus para monitoreo continuo:

- `execution_slippage_real_bps`: Histograma de slippage realizado
- `execution_fill_rate`: Gauge de fill rate
- `tracking_error_mean_deviation`: Gauge de desviación media
- `tracking_error_correlation`: Gauge de correlación

Ver `backend/app/observability/execution_metrics.py` para detalles.




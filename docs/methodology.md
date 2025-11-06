# Metodología - One Smart Trade

## Visión General

One Smart Trade es un sistema cuantitativo diseñado para generar recomendaciones diarias de trading para BTC/USDT basándose en análisis multi-timeframe, indicadores técnicos avanzados y métricas de riesgo.

## Arquitectura del Sistema

### 1. Ingesta de Datos

**Fuente:** API pública de Binance (sin autenticación)

**Timeframes:**
- 15 minutos
- 30 minutos
- 1 hora
- 4 horas
- 1 día
- 1 semana

**Datos Recopilados:**
- OHLCV (Open, High, Low, Close, Volume)
- Volumen
- Timestamps

**Persistencia:**
- Datos crudos en formato Parquet (columnar, eficiente)
- Dataset curado con agregados diarios

### 2. Indicadores Técnicos

#### Indicadores de Tendencia
- **EMA/SMA múltiples:** 9, 21, 50, 100, 200 períodos
- **MACD:** Momentum y divergencias
- **ADX:** Fuerza de la tendencia

#### Indicadores de Momentum
- **RSI:** Sobrecompra/sobreventa
- **StochRSI:** RSI estocástico
- **Momentum:** Velocidad de cambio de precio

#### Indicadores de Volatilidad
- **ATR:** Rango verdadero promedio
- **Bollinger Bands:** Desviación estándar
- **Keltner Channels:** Volatilidad basada en ATR

#### Indicadores de Volumen
- **VWAP:** Precio promedio ponderado por volumen
- **Volume Profile:** Distribución de volumen por precio
- **On-Balance Volume (OBV):** Acumulación de volumen

### 3. Factores Cross-Timeframe

- **Momentum Multi-Timeframe:** Comparación de momentum entre timeframes
- **Divergencias:** Detección de divergencias alcistas/bajistas
- **Slope de Medias:** Pendiente de medias móviles
- **Régimen de Volatilidad:** Identificación de regímenes (alta/baja volatilidad)

### 4. Estrategias Combinadas

#### Estrategia 1: Momentum-Trend
- Señales basadas en alineación de medias móviles
- Confirmación con momentum positivo
- Filtro de volatilidad

#### Estrategia 2: Mean-Reversion
- Identificación de extremos estadísticos
- Señales contrarias en condiciones de sobrecompra/sobreventa
- Validación con volumen

#### Estrategia 3: Breakout
- Detección de rupturas de niveles clave
- Confirmación con volumen
- Filtro de falsos breakouts

#### Estrategia 4: Volatilidad
- Trading en rangos de volatilidad
- Ajuste de posiciones según régimen

### 5. Generación de Señales

#### Proceso de Consolidación

1. **Cálculo Individual:** Cada estrategia genera su propia señal
2. **Ponderación:** Las estrategias se ponderan según performance histórica
3. **Votación:** Sistema de votación ponderada
4. **Validación:** Verificación de consistencia cross-timeframe

#### Tipos de Señal

- **BUY:** Expectativa de movimiento alcista
- **HOLD:** Neutralidad o espera
- **SELL:** Expectativa de movimiento bajista

### 6. Gestión de Riesgo

#### Stop Loss Dinámico

- Basado en múltiplos de ATR
- Ajustado según volatilidad actual
- Validación contra niveles de soporte/resistencia

#### Take Profit Dinámico

- Ratio riesgo/recompensa mínimo 1:2
- Ajustado según volatilidad
- Niveles múltiples posibles

#### Rango de Entrada

- Confluencia de soportes/resistencias
- VWAP intradía
- Niveles de liquidez reciente

### 7. Cálculo de Confianza

#### Factores Considerados

1. **Performance Histórica:** Win rate de estrategias activas
2. **Consistencia:** Acuerdo entre estrategias
3. **Condiciones de Mercado:** Alineación con régimen actual
4. **Probabilidad Monte Carlo:** Simulaciones de escenarios

#### Fórmula

```
Confianza = (Performance_Weight × Win_Rate) + 
            (Consistency_Weight × Agreement) + 
            (Market_Weight × Regime_Alignment) + 
            (MC_Weight × MC_Probability)
```

### 8. Análisis Textual

El análisis textual incluye:

- **Contexto de Mercado:** Descripción del régimen actual
- **Momentum:** Dirección y fuerza del momentum
- **Volatilidad:** Nivel y expectativas
- **Riesgo:** Evaluación de riesgo y drawdown esperado
- **Eventos:** Consideración de eventos macro si aplica

## Limitaciones

1. **Datos Históricos:** Limitado a datos disponibles de Binance
2. **Slippage:** No considera slippage real en ejecución
3. **Comisiones:** Considera comisiones estándar pero puede variar
4. **Condiciones de Mercado:** Puede fallar en mercados extremos
5. **Latencia:** No diseñado para trading de alta frecuencia
6. **Liquidez:** Asume liquidez suficiente en BTC/USDT

## Disclaimers Legales

- Este software es solo para fines educativos y de investigación
- No constituye asesoramiento financiero
- El trading de criptomonedas conlleva riesgos significativos
- Los resultados pasados no garantizan resultados futuros
- Use bajo su propia responsabilidad
- Consulte con un asesor financiero profesional antes de tomar decisiones de inversión

## Versión del Modelo

**Versión Actual:** 0.1.0

**Última Actualización:** 2024-01-XX

**Próxima Recalibración:** Según performance y condiciones de mercado

## Referencias

- Binance API Documentation
- Technical Analysis of the Financial Markets (John J. Murphy)
- Quantitative Trading (Ernest P. Chan)


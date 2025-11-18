# Ejecución Real vs. Teórica: Tracking Error y Criterios de Aceptación

## Resumen Ejecutivo

Este documento describe cómo el sistema calcula y monitorea el tracking error entre la ejecución teórica (backtest ideal) y la ejecución realista (con fricciones), así como los criterios de aceptación para campañas y estrategias en producción.

---

## Flujo de Cálculo

### 1. Motor de Backtesting (`BacktestEngine`)

El motor de backtesting mantiene **dos curvas de equity** simultáneamente:

- **`equity_theoretical`**: Ejecución perfecta sin fricciones
  - Precios de entrada/salida exactos según señales
  - Sin comisiones, sin slippage
  - Fills completos e inmediatos

- **`equity_realistic`**: Ejecución con fricciones realistas
  - Slippage basado en orderbook depth
  - Comisiones aplicadas
  - Fills parciales y rechazos de órdenes
  - Tiempo de ejecución y latencia

**Ubicación:** `backend/app/backtesting/engine.py`

```python
# Durante cada bar del backtest:
state.update_equity(theoretical, realistic, bar_date)

# Se calcula tracking error periódicamente:
if len(state.equity_curve) >= 2:
    tracking_stats = TrackingErrorCalculator.from_curves(
        theoretical=state.equity_curve["equity_theoretical"],
        realistic=state.equity_curve["equity_realistic"],
        bars_per_year=bars_per_year,
    )
    state.tracking_error_stats.append(tracking_stats.to_dict())
```

### 2. Cálculo de Tracking Error (`TrackingErrorCalculator`)

El módulo `TrackingErrorCalculator` calcula métricas de tracking error:

**Métricas principales:**
- **RMSE (Root Mean Squared Error)**: Error cuadrático medio entre curvas
- **Tracking Error Anualizado**: RMSE escalado a período anual
- **% de barras con divergencia > umbral**: Porcentaje de períodos donde la divergencia excede un umbral (p.ej., 10 bps)
- **Divergencia máxima (bps)**: Máxima diferencia absoluta entre curvas
- **Divergencia media (bps)**: Diferencia promedio entre curvas

**Ubicación:** `backend/app/backtesting/tracking_error.py`

```python
tracking_error = TrackingErrorCalculator.from_curves(
    theoretical=equity_theoretical,
    realistic=equity_realistic,
    divergence_threshold_bps=10.0,  # 10 bps por defecto
    bars_per_year=365,  # Para anualización
)

# Métricas disponibles:
# - tracking_error.rmse
# - tracking_error.annualized_tracking_error
# - tracking_error.bars_with_divergence_above_threshold_pct
# - tracking_error.mean_divergence_bps
# - tracking_error.max_divergence_bps
```

### 3. Persistencia y Reportes

**Al final del backtest:**
- El tracking error se incluye en `BacktestResult`
- Se serializa en JSON/Parquet para análisis posterior

**En reportes:**
- `PerformanceService` genera gráficos comparando ambas curvas
- La UI muestra una pestaña "Ejecución real vs. teórica" con visualización de divergencias
- Alertas se disparan cuando el tracking error excede umbrales configurados

**Ubicación:** 
- Persistencia: `backend/app/backtesting/persistence.py`
- Reportes: `backend/app/services/performance_service.py`
- API: `backend/app/api/v1/performance.py`

---

## Criterios de Aceptación

### 1. Campañas con Tracking Error > 3% NO se Publican

**Umbral:** Tracking error anualizado > 3.0%

**Implementación:** `backend/app/backtesting/champion.py`

```python
MAX_ANNUALIZED_TRACKING_ERROR_PCT = 3.0

def _check_tracking_error(record: dict[str, Any]) -> tuple[bool, str | None]:
    """Verifica que el tracking error no exceda el umbral."""
    tracking_error = record.get("tracking_error_summary", {})
    annualized_te = tracking_error.get("annualized_tracking_error", 0.0)
    
    # Convertir a porcentaje si está en decimal
    if annualized_te < 1.0:
        annualized_te_pct = annualized_te * 100.0
    else:
        annualized_te_pct = annualized_te
    
    if annualized_te_pct > MAX_ANNUALIZED_TRACKING_ERROR_PCT:
        return False, f"Tracking error anualizado {annualized_te_pct:.2f}% excede umbral {MAX_ANNUALIZED_TRACKING_ERROR_PCT}%"
    
    return True, None
```

**Consecuencias:**
- Estrategias con tracking error > 3% son **rechazadas automáticamente**
- No pueden promoverse como "champion"
- Se registra el motivo del rechazo en los logs
- El record incluye `tracking_error_check: {"passed": False, "rejection_reason": "..."}`

### 2. Validación en Optimizador de Campañas

El `CampaignOptimizer` también filtra candidatos con tracking error excesivo:

**Ubicación:** `backend/app/backtesting/optimizer.py`

```python
if self.max_annualized_tracking_error_pct is not None:
    annualized_te = tracking_error_summary.get("annualized_tracking_error", 0.0)
    # Convertir a porcentaje y comparar
    if annualized_te_pct > self.max_annualized_tracking_error_pct:
        # Candidato rechazado - no se evalúa completamente
        continue
```

### 3. Recalibración Automática

El sistema monitorea el tracking error en producción y dispara recalibración cuando se exceden umbrales:

**Umbrales configurados en `config/performance.yaml`:**
- `tracking_error.max_rmse_pct: 0.03` (3%)
- `tracking_error.max_divergence_days: 3` (3 días consecutivos)

**Ubicación:** `backend/app/services/monitoring_service.py`

---

## Guía de Interpretación para Usuarios

### ¿Qué es el Tracking Error?

El **tracking error** mide cuánto se desvía la ejecución real de la ejecución teórica. Una desviación pequeña indica que el modelo de ejecución es realista y que los resultados del backtest son confiables.

### Interpretación de Métricas

#### 1. RMSE (Root Mean Squared Error)

**¿Qué significa?**
- Mide la diferencia promedio entre las curvas teórica y realista
- Se expresa en las mismas unidades que la equity (USD, porcentaje, etc.)

**Interpretación:**
- **RMSE < 1%**: Excelente fidelidad de ejecución
  - Ejemplo: Si la equity teórica es $10,000, un RMSE de $100 (1%) significa que en promedio la ejecución real se desvía solo $100 del ideal
  
- **RMSE 1-3%**: Buena fidelidad, aceptable para producción
  - La ejecución real es generalmente fiable, con pequeñas diferencias

- **RMSE > 3%**: Advertencia - ejecución puede no ser confiable
  - **NO se acepta para publicación como champion**
  - Indica que el modelo de ejecución necesita ajustes o que las condiciones de mercado son muy diferentes

#### 2. Tracking Error Anualizado

**¿Qué significa?**
- RMSE escalado a un período anual para comparabilidad
- Permite comparar tracking error entre estrategias con diferentes períodos de prueba

**Interpretación:**
- **< 2% anualizado**: Ejecución muy fiel
- **2-3% anualizado**: Ejecución aceptable (límite para champions)
- **> 3% anualizado**: **RECHAZADO** - No se publica como champion

#### 3. Divergencia Máxima (bps)

**¿Qué significa?**
- El punto donde la diferencia entre curvas fue mayor
- Se expresa en basis points (1 bps = 0.01%)

**Interpretación:**
- **< 50 bps (0.5%)**: Divergencia máxima pequeña
- **50-100 bps (0.5-1.0%)**: Divergencia moderada, aceptable
- **> 100 bps (1.0%)**: Divergencia significativa - revisar condiciones de mercado en ese momento

#### 4. % de Barras con Divergencia > Umbral

**¿Qué significa?**
- Porcentaje de períodos donde la divergencia excedió un umbral (p.ej., 10 bps)
- Indica frecuencia de eventos de alta divergencia

**Interpretación:**
- **< 5% de barras**: Pocos eventos de divergencia alta - ejecución estable
- **5-10% de barras**: Frecuencia moderada - monitorear
- **> 10% de barras**: Alta frecuencia de divergencias - puede indicar problemas sistemáticos

### Ejemplos Prácticos

#### Ejemplo 1: Tracking Error Aceptable

```
Equity teórica final: $10,000
Equity realista final: $9,950
RMSE: $75 (0.75%)
Tracking Error Anualizado: 1.2%
Divergencia máxima: 45 bps
% barras con divergencia > 10 bps: 3.5%

Interpretación: ✅ ACEPTABLE
- La ejecución realista perdió $50 vs teórica (0.5%)
- El tracking error es bajo (< 2% anualizado)
- Pocos eventos de alta divergencia
- Esta estrategia puede promoverse como champion
```

#### Ejemplo 2: Tracking Error Rechazado

```
Equity teórica final: $10,000
Equity realista final: $9,600
RMSE: $450 (4.5%)
Tracking Error Anualizado: 5.2%
Divergencia máxima: 180 bps
% barras con divergencia > 10 bps: 18%

Interpretación: ❌ RECHAZADO
- Pérdida significativa de $400 vs teórica (4%)
- Tracking error > 3% anualizado → NO se publica
- Alta frecuencia de divergencias (18% de barras)
- El modelo de ejecución no es confiable para esta estrategia
```

#### Ejemplo 3: Caso Límite

```
Equity teórica final: $10,000
Equity realista final: $9,700
RMSE: $280 (2.8%)
Tracking Error Anualizado: 2.9%
Divergencia máxima: 95 bps
% barras con divergencia > 10 bps: 8%

Interpretación: ⚠️ LÍMITE (Aceptable pero monitorear)
- Tracking error justo debajo del umbral de 3%
- Se acepta para publicación, pero debe monitorearse en producción
- Considerar ajustar parámetros de ejecución si es posible
```

---

## Monitoreo en Producción

### Tracking Error Rolling

El sistema calcula tracking error rolling comparando:
- **PnL teórica**: Resultados esperados basados en backtest del champion
- **PnL real**: Resultados reales de fills en producción

**Configuración:** `config/performance.yaml`

```yaml
tracking_error:
  max_rmse_pct: 0.03  # 3% máximo
  max_divergence_days: 3  # 3 días consecutivos con divergencia > umbral
  divergence_threshold_pct: 0.02  # 2% umbral para divergencia
  rolling_window_days: 30  # Ventana de 30 días
```

### Alertas Automáticas

Cuando el tracking error excede umbrales:
1. **Alerta a Slack/Email**: Notificación inmediata
2. **Recalibración automática**: Si está habilitada, se dispara `RecalibrationJob`
3. **Logs estructurados**: Registro detallado para análisis

---

## Best Practices

### 1. Revisar Tracking Error Antes de Publicar

- Siempre verificar que `annualized_tracking_error < 3%`
- Revisar eventos de alta divergencia (% de barras con divergencia > umbral)
- Considerar el contexto de mercado (alta volatilidad puede aumentar tracking error)

### 2. Interpretar en Contexto

- Tracking error alto puede indicar:
  - Condiciones de mercado cambiantes
  - Modelo de ejecución subestimando fricciones
  - Falta de liquidez en períodos específicos

### 3. Ajustar Modelos de Ejecución

Si el tracking error es consistentemente alto:
- Revisar parámetros de slippage
- Validar profundidad del orderbook
- Considerar ajustar estimaciones de fill probability

---

## Referencias Técnicas

- **Tracking Error Calculator**: `backend/app/backtesting/tracking_error.py`
- **Backtest Engine**: `backend/app/backtesting/engine.py`
- **Champion Promotion**: `backend/app/backtesting/champion.py`
- **Monitoring Service**: `backend/app/services/monitoring_service.py`
- **Performance API**: `backend/app/api/v1/performance.py`

---

## Preguntas Frecuentes

**P: ¿Por qué mi estrategia tiene tracking error alto?**

R: Puede deberse a:
- Alta frecuencia de trading (más fricciones)
- Condiciones de baja liquidez
- Modelo de ejecución que subestima slippage
- Volatilidad extrema en el mercado

**P: ¿Puedo forzar la publicación de una estrategia con tracking error > 3%?**

R: No. El sistema rechaza automáticamente estrategias que exceden el umbral. Si necesitas publicar una estrategia con tracking error alto, considera ajustar los parámetros de ejecución o mejorar el modelo de fricciones.

**P: ¿Cómo interpreto el tracking error en producción vs. backtest?**

R: En producción, el tracking error se calcula comparando el champion (backtest) con los resultados reales. Si el tracking error en producción es significativamente mayor que en backtest, puede indicar que las condiciones de mercado cambiaron o que el modelo necesita actualización.


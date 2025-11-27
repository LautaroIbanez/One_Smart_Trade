# Manual Test: Frontend Guardrails

Este documento describe cómo probar manualmente los guardrails del frontend para datos desactualizados y sin trades.

## Setup

1. Asegúrate de que el backend esté corriendo
2. Abre el frontend en el navegador (normalmente http://localhost:5173)
3. Abre las DevTools del navegador (F12) y ve a la pestaña Network

## Test 1: Mockear API response con latest_open_time=2024-11-11 y metrics_status=NO_TRADES

### Pasos:

1. **Interceptar llamadas a la API** usando el Network tab o un interceptor:

```javascript
// En la consola del navegador, ejecuta esto para interceptar las llamadas:
const originalFetch = window.fetch;
window.fetch = async function(...args) {
  const url = args[0];
  
  // Mock /api/v1/operational/data-status
  if (url.includes('/api/v1/operational/data-status')) {
    return new Response(JSON.stringify({
      status: "ok",
      latest_open_time: "2024-11-11T00:00:00Z",
      latest_open_time_date: "2024-11-11",
      age_hours: 720, // 30 days
      age_days: 30,
      has_recent_data: false,
      interval: "1d",
      venue: "binance",
      symbol: "BTCUSDT",
    }), {
      headers: { 'Content-Type': 'application/json' }
    });
  }
  
  // Mock /api/v1/performance/summary
  if (url.includes('/api/v1/performance/summary')) {
    return new Response(JSON.stringify({
      status: "degraded",
      metrics_status: "NO_TRADES",
      trade_count: 0,
      metrics: {
        total_trades: 0,
        winning_trades: 0,
        losing_trades: 0,
        win_rate: 0,
        profit_factor: 1.0,
        sharpe_ratio: 0.0,
        calmar_ratio: 0.0,
        max_drawdown: 0.0,
        cagr: 0.0,
        expectancy_r: 0.0,
        avg_rr: 1.0,
      },
      no_trade_diagnostics: {
        root_cause: "enter_signals_zero_size",
        reason: "Strategy generated 5 enter signals but position sizer calculated zero size for all of them.",
        signal_counts: {
          enter: 5,
          total: 10,
        },
        signals_with_zero_size: 5,
        rejected_orders_count: 0,
        total_bars: 1000,
      },
      no_trade_root_cause: "enter_signals_zero_size",
    }), {
      headers: { 'Content-Type': 'application/json' }
    });
  }
  
  return originalFetch.apply(this, args);
};
```

2. **Recargar la página** (F5 o Ctrl+R)

3. **Verificar que aparece el warning modal**:
   - Debe aparecer un modal rojo con el título "⚠️ Advertencia"
   - El mensaje debe incluir: "Datos desactualizados: última vela 2024-11-11 (hace 30 días)"
   - El mensaje debe incluir: "Sin trades simulados; revise diagnóstico"
   - Debe mostrar el diagnóstico con el root_cause

4. **Verificar que los charts muestran mensaje**:
   - En la página de Performance, los charts (WeeklyHeatmap, ReturnsHistogram, RealVsTheoretical, SignalCompliance) deben mostrar:
     - "Sin trades simulados"
     - "Revise diagnóstico para entender por qué no se ejecutaron trades durante el backtest."

5. **Verificar el banner degradado**:
   - Debe aparecer un banner amarillo/rojo en PerformanceSummary
   - El banner debe explicar "Datos desactualizados / sin trades simulados"

## Test 2: Mockear API response con metrics_status=DEV_FALLBACK

### Pasos:

1. **Interceptar llamadas** con este mock:

```javascript
const originalFetch = window.fetch;
window.fetch = async function(...args) {
  const url = args[0];
  
  if (url.includes('/api/v1/operational/data-status')) {
    return new Response(JSON.stringify({
      status: "ok",
      latest_open_time: "2024-11-11T00:00:00Z",
      latest_open_time_date: "2024-11-11",
      age_hours: 720,
      age_days: 30,
      has_recent_data: false,
    }), {
      headers: { 'Content-Type': 'application/json' }
    });
  }
  
  if (url.includes('/api/v1/performance/summary')) {
    return new Response(JSON.stringify({
      status: "degraded",
      metrics_status: "DEV_FALLBACK",
      trade_count: 10,
      dev_bypass: "trade_count_guardrail",
      fallback_reason: "Development mode: Fallback metrics (10 trades < 50)",
      metrics: {
        total_trades: 10,
        winning_trades: 5,
        losing_trades: 5,
        win_rate: 50,
        profit_factor: 1.2,
        sharpe_ratio: 0.5,
        calmar_ratio: 0.3,
        max_drawdown: 5.0,
        cagr: 10.0,
        expectancy_r: 0.1,
        avg_rr: 1.5,
      },
    }), {
      headers: { 'Content-Type': 'application/json' }
    });
  }
  
  return originalFetch.apply(this, args);
};
```

2. **Recargar la página**

3. **Verificar**:
   - Debe aparecer el warning modal con "Modo desarrollo: métricas de respaldo"
   - Debe mostrar "Datos desactualizados: última vela 2024-11-11"

## Test 3: Verificar que el banner rojo explica correctamente

### Pasos:

1. Usar el mock del Test 1 (latest_open_time=2024-11-11, metrics_status=NO_TRADES)

2. **Verificar el banner en PerformanceSummary**:
   - Debe ser rojo (backgroundColor con rgba(239, 68, 68, ...))
   - Debe decir "⚠️ Modo Degradado" o similar
   - El mensaje debe explicar claramente:
     - "Datos desactualizados / sin trades simulados"
     - O mensajes separados para cada condición

3. **Verificar que los charts no muestran gráficos vacíos**:
   - WeeklyHeatmap: debe mostrar mensaje en lugar de gráfico vacío
   - ReturnsHistogram: debe mostrar mensaje en lugar de gráfico vacío
   - RealVsTheoretical: debe mostrar mensaje en lugar de gráfico vacío
   - SignalCompliance: debe mostrar mensaje en lugar de gráfico vacío

## Limpiar mocks

Para restaurar el comportamiento normal:

```javascript
// Si usaste window.fetch, restaura:
window.fetch = originalFetch;

// O simplemente recarga la página sin los mocks
```

## Notas

- Los mocks deben aplicarse antes de que React Query haga las llamadas
- Puedes usar herramientas como MSW (Mock Service Worker) para mocks más robustos
- Verifica en la consola que no haya errores de JavaScript
- Verifica que los componentes se rendericen correctamente sin crashes


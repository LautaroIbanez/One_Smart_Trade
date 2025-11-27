# Test Manual: Observabilidad - Diagnóstico de Backtest

## Objetivo
Verificar que el dashboard de Observabilidad muestra correctamente la información de diagnóstico cuando `metrics_status ≠ PASS`, específicamente cuando `root_cause=enter_signals_zero_size`.

## Prerrequisitos
1. Backend ejecutándose
2. Frontend ejecutándose
3. Acceso al dashboard de Observabilidad

## Pasos del Test

### 1. Simular respuesta con `root_cause=enter_signals_zero_size`

#### Opción A: Usar el backend real con datos que generen este escenario
1. Asegúrate de que el backtest genere señales de entrada pero con tamaño cero
2. Esto puede ocurrir cuando:
   - `stop_loss_distance=0` en las señales
   - Capital insuficiente
   - Límites de riesgo que resultan en tamaño cero

#### Opción B: Mockear la respuesta de la API (para testing rápido)
1. Abre las DevTools del navegador (F12)
2. Ve a la pestaña "Network"
3. Intercepta la respuesta de `/api/v1/performance/summary`
4. Modifica la respuesta para incluir:
```json
{
  "status": "success",
  "metrics": {
    "total_trades": 0
  },
  "metrics_status": "NO_TRADES",
  "signal_counts": {
    "enter": 5,
    "exit": 0,
    "hold": 10,
    "total": 15
  },
  "rejected_orders_count": 0,
  "no_trade_diagnostics": {
    "root_cause": "enter_signals_zero_size",
    "reason": "Strategy generated 5 enter signals but position sizer calculated zero size for 5 of them. This may indicate insufficient capital, risk limits, or invalid stop loss distances.",
    "signal_counts": {
      "enter": 5,
      "exit": 0,
      "hold": 10,
      "total": 15
    },
    "signals_with_zero_size": 5,
    "rejected_orders_count": 0
  },
  "no_trade_root_cause": "enter_signals_zero_size"
}
```

### 2. Verificar la UI en Observabilidad

1. Navega a la página del Dashboard
2. Localiza la sección "Dashboard de Observabilidad"
3. Verifica que aparece una nueva sección "🔍 Diagnóstico de Backtest" con:
   - Fondo rojo/amarillo (indicando problema)
   - Tarjetas mostrando:
     - **Señales de Entrada**: 5
     - **Trades Generados**: 0
   - Mensaje: "⚠️ 5 señales de entrada generadas pero tamaño de posición = 0"
   - Causa Raíz: "⚠️ Señales de entrada con tamaño cero"
   - Detalles: El mensaje completo de `no_trade_diagnostics.reason`
   - Desglose de Señales: Muestra el breakdown de todas las señales

### 3. Verificar otros escenarios

#### Escenario 1: Sin señales (`root_cause=no_signals_generated`)
```json
{
  "metrics_status": "NO_TRADES",
  "signal_counts": {
    "enter": 0,
    "hold": 10,
    "total": 10
  },
  "no_trade_root_cause": "no_signals_generated"
}
```
**Verificar**: Mensaje muestra "No se generaron señales de entrada durante el backtest"

#### Escenario 2: Órdenes rechazadas (`root_cause=orders_rejected`)
```json
{
  "metrics_status": "NO_TRADES",
  "signal_counts": {
    "enter": 5,
    "total": 5
  },
  "rejected_orders_count": 3,
  "no_trade_root_cause": "orders_rejected"
}
```
**Verificar**: 
- Tarjeta adicional muestra "Órdenes Rechazadas: 3"
- Mensaje: "3 órdenes fueron rechazadas por el simulador de ejecución"
- Causa Raíz: "⚠️ Órdenes rechazadas por simulador"

#### Escenario 3: DEV_FALLBACK con señales
```json
{
  "metrics_status": "DEV_FALLBACK",
  "metrics": {
    "total_trades": 10
  },
  "signal_counts": {
    "enter": 15,
    "total": 15
  },
  "rejected_orders_count": 0
}
```
**Verificar**: 
- Sección de diagnóstico aparece
- Muestra "15 señales de entrada generadas, 10 trades ejecutados"
- Tipo de issue: "conversión_parcial"

### 4. Verificar que la sección NO aparece cuando `metrics_status=PASS`

1. Asegúrate de que el backtest tenga `metrics_status="PASS"`
2. Verifica que la sección "🔍 Diagnóstico de Backtest" NO aparece en el dashboard de Observabilidad

## Resultados Esperados

✅ La sección de diagnóstico aparece cuando `metrics_status ≠ PASS`
✅ Muestra correctamente `signal_counts.enter` vs `total_trades`
✅ Diferencia entre "sin señales", "tamaño cero" y "órdenes rechazadas"
✅ Muestra la causa raíz correcta según `root_cause`
✅ Muestra el mensaje detallado de `no_trade_diagnostics.reason`
✅ Muestra el desglose completo de señales cuando está disponible
✅ La sección NO aparece cuando `metrics_status=PASS`

## Notas

- Si usas mockeo, asegúrate de limpiar la caché de React Query después del test
- Para testing más realista, ejecuta un backtest real que genere el escenario deseado
- Los colores y estilos pueden variar, pero la información debe ser clara y accesible


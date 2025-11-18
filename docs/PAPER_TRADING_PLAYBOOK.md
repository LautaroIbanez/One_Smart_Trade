# Paper Trading Playbook

Guía completa para ejecutar trading manual (paper trading) basado en las recomendaciones diarias del sistema.

## Objetivo

Este playbook te permite ejecutar manualmente las señales generadas por el sistema en una cuenta de paper trading, siguiendo las instrucciones de ejecución incluidas en cada recomendación.

## Prerequisitos

1. **Cuenta de Paper Trading**:
   - Binance Testnet: https://testnet.binancefuture.com/
   - O cualquier exchange con cuenta demo/paper trading

2. **Capital de Paper Trading**:
   - Recomendado: $10,000 USD (equivalente)
   - Mínimo: $1,000 USD (para sizing mínimo)

3. **Acceso al Sistema**:
   - API funcionando: `http://localhost:8000`
   - O acceso a base de datos directamente

## Flujo Diario

### 1. Obtener Recomendación (12:00 UTC)

**Opción A: Via API**
```bash
curl http://localhost:8000/api/v1/recommendation/today | jq
```

**Opción B: Via Frontend**
- Abrir: `http://localhost:5173`
- Ver recomendación del día en el dashboard

**Opción C: Via Script**
```bash
cd backend
poetry run python -c "
import asyncio
from app.services.recommendation_service import RecommendationService

async def get_today():
    service = RecommendationService()
    result = await service.get_today_recommendation()
    if result:
        print(f\"Signal: {result.get('signal')}\")
        print(f\"Entry: {result.get('entry_range', {}).get('optimal')}\")
        print(f\"SL: {result.get('stop_loss_take_profit', {}).get('stop_loss')}\")
        print(f\"TP: {result.get('stop_loss_take_profit', {}).get('take_profit')}\")
        exec_plan = result.get('execution_plan', {})
        if exec_plan:
            print(f\"\\nExecution Plan:\")
            print(exec_plan.get('instructions', ''))
    else:
        print('No recommendation available')

asyncio.run(get_today())
"
```

### 2. Revisar Execution Plan

Cada recomendación incluye un `execution_plan` con:

- **Ventana operativa**: Cuándo ejecutar
- **Tipo de orden**: Limit o Market
- **Tamaño sugerido**: Cantidad en BTC
- **Instrucciones paso a paso**: Guía detallada
- **Notas y advertencias**: Información importante

**Ejemplo de execution plan**:
```json
{
  "operational_window": {
    "optimal_start": "2025-01-15T12:00:00+00:00",
    "optimal_end": "2025-01-15T16:00:00+00:00",
    "acceptable_end": "2025-01-16T12:00:00+00:00",
    "timezone": "UTC"
  },
  "order_type": "limit",
  "suggested_size": {
    "units": 0.05,
    "notional_usd": 2500.0,
    "risk_amount_usd": 50.0,
    "risk_pct": 1.0
  },
  "instructions": "1. Verifica la señal: COMPRA\n2. Precio actual: $50,000.00\n..."
}
```

### 3. Validar Pre-requisitos

Antes de ejecutar, verifica:

- ✅ **Capital disponible**: Suficiente para el tamaño sugerido
- ✅ **Ventana operativa**: Estás dentro de la ventana óptima o aceptable
- ✅ **Precio actual**: Verifica que el precio esté en rango de entrada
- ✅ **Límites de riesgo**: No excedas límites diarios (3% riesgo diario)

### 4. Ejecutar Orden

#### Para Señal BUY

**Orden Limit (recomendado)**:
1. Abre tu exchange de paper trading
2. Ve a "Spot Trading" o "Futures" (según tu configuración)
3. Selecciona BTC/USDT
4. Crea orden **LIMIT BUY**:
   - Precio: `entry_range.optimal` (del execution plan)
   - Cantidad: `suggested_size.units` (del execution plan)
   - Tipo: Limit
   - Time in Force: GTC (Good Till Cancel)

**Orden Market (si precio está en rango)**:
- Usa Market order solo si el precio actual está dentro de `entry_range.min` y `entry_range.max`
- Cantidad: `suggested_size.units`

#### Para Señal SELL

**Orden Limit (recomendado)**:
1. Crea orden **LIMIT SELL**:
   - Precio: `entry_range.optimal`
   - Cantidad: `suggested_size.units`
   - Tipo: Limit
   - Time in Force: GTC

**Orden Market**:
- Solo si precio está en rango óptimo

#### Para Señal HOLD

- **No ejecutes ninguna orden**
- Espera a la siguiente recomendación (mañana 12:00 UTC)

### 5. Configurar Stop Loss y Take Profit

**INMEDIATAMENTE después de que la orden se ejecute**:

#### Stop Loss

1. Ve a "Positions" o "Open Orders"
2. Selecciona tu posición BTC
3. Configura **Stop Loss**:
   - Precio: `stop_loss_take_profit.stop_loss` (del execution plan)
   - Tipo: Stop Market o Stop Limit
   - Cantidad: Toda la posición

#### Take Profit

1. Configura **Take Profit**:
   - Precio: `stop_loss_take_profit.take_profit` (del execution plan)
   - Tipo: Limit
   - Cantidad: Toda la posición

**⚠️ IMPORTANTE**: No ejecutes sin configurar SL/TP. El riesgo sin stop loss es ilimitado.

### 6. Monitorear Posición

**Durante la posición abierta**:

- **Revisa diariamente**: Verifica que SL/TP sigan configurados
- **No modifiques**: No cambies SL/TP a menos que haya una nueva recomendación
- **Cierra manualmente**: Solo si hay una nueva señal que lo requiera

**Tracking**:
- Registra entrada: Precio, cantidad, timestamp
- Registra salida: Precio, razón (TP/SL), timestamp
- Calcula P&L: `(exit_price - entry_price) * quantity * side_multiplier`

### 7. Registrar Resultado

**Al cerrar posición**:

1. **Registra en sistema** (opcional):
   ```bash
   # Si el sistema tiene endpoint para registrar ejecución manual
   curl -X POST http://localhost:8000/api/v1/execution/register \
     -H "Content-Type: application/json" \
     -d '{
       "recommendation_id": 123,
       "entry_price": 50000.0,
       "exit_price": 51000.0,
       "exit_reason": "take_profit",
       "quantity": 0.05
     }'
   ```

2. **Registra en tu hoja de cálculo**:
   - Fecha
   - Señal (BUY/SELL/HOLD)
   - Entry price
   - Exit price
   - Exit reason (TP/SL)
   - P&L
   - Tracking error (diferencia con TP/SL teórico)

## Ejemplo Completo

### Día 1: Señal BUY

**Recomendación recibida** (12:00 UTC):
```json
{
  "signal": "BUY",
  "entry_range": {
    "min": 49500.0,
    "max": 50500.0,
    "optimal": 50000.0
  },
  "stop_loss_take_profit": {
    "stop_loss": 49000.0,
    "take_profit": 51250.0
  },
  "execution_plan": {
    "order_type": "limit",
    "suggested_size": {
      "units": 0.05,
      "notional_usd": 2500.0,
      "risk_amount_usd": 50.0
    },
    "operational_window": {
      "optimal_end": "2025-01-15T16:00:00+00:00"
    }
  }
}
```

**Ejecución** (12:30 UTC):
1. Precio actual: $50,100 (dentro de rango)
2. Crear orden LIMIT BUY: 0.05 BTC @ $50,000
3. Orden ejecutada a las 13:15 UTC @ $50,000
4. Configurar SL: $49,000 (Stop Market)
5. Configurar TP: $51,250 (Limit)

**Resultado** (Día 3, 10:00 UTC):
- TP ejecutado @ $51,250
- P&L: (51,250 - 50,000) * 0.05 = $62.50
- Tracking: Perfecto (ejecutado exactamente en TP)

### Día 2: Señal HOLD

**Recomendación recibida**:
```json
{
  "signal": "HOLD"
}
```

**Acción**: No ejecutar ninguna orden. Mantener posición abierta si existe.

### Día 3: Señal SELL

**Recomendación recibida**:
- Cerrar posición anterior (si existe)
- Ejecutar nueva señal SELL siguiendo el mismo proceso

## Gestión de Riesgo

### Límites Diarios

- **Riesgo máximo por trade**: 1% del capital
- **Riesgo máximo diario**: 3% del capital
- **Máximo trades por día**: 7 (límite preventivo)

### Sizing

**Si tienes capital personalizado**:
- El sistema calcula sizing basado en tu capital
- Usa `recommended_position_size` del API response

**Si usas capital mínimo**:
- Usa `suggested_size.units` del execution plan
- Basado en capital mínimo de $1,000

### Drawdown

**Si drawdown > 10%**:
- Reduce tamaño de posición en 50%
- Considera pausar trading hasta recuperación

**Si drawdown > 20%**:
- Detén trading completamente
- Revisa estrategia y ejecución

## Troubleshooting

### Problema: Orden no se ejecuta

**Causa**: Precio no alcanzó el límite  
**Solución**:
- Si pasaron 4 horas y no se ejecutó, considera cancelar
- Revisa si el precio está moviéndose en dirección opuesta
- Considera ajustar a Market order si precio está en rango

### Problema: SL/TP no se configuró a tiempo

**Causa**: Olvido o error  
**Solución**:
- Configura inmediatamente cuando te des cuenta
- Si el precio ya se movió significativamente, considera cerrar manualmente
- Revisa si aún tiene sentido mantener la posición

### Problema: Tracking error alto

**Causa**: Ejecución diferente a teórica  
**Solución**:
- Es normal tener tracking error pequeño (< 1%)
- Si tracking error > 5%, revisa:
  - Slippage en ejecución
  - Timing de entrada/salida
  - Configuración de SL/TP

## Métricas a Trackear

### Por Trade

- Entry price vs optimal
- Exit price vs TP/SL teórico
- Tracking error (bps)
- P&L realizado
- Tiempo en posición

### Agregadas

- Win rate
- Average win/loss
- Risk/Reward ratio realizado
- Max drawdown
- Sharpe ratio (si tienes suficientes trades)

## Checklist Diario

- [ ] Obtener recomendación (12:00 UTC)
- [ ] Revisar execution plan
- [ ] Verificar capital disponible
- [ ] Verificar ventana operativa
- [ ] Ejecutar orden (si señal != HOLD)
- [ ] Configurar SL/TP inmediatamente
- [ ] Registrar entrada en tracking
- [ ] Monitorear posición (si abierta)
- [ ] Registrar salida (si se cerró)
- [ ] Actualizar métricas

## Recursos Adicionales

- **API Documentation**: `docs/api.md`
- **E2E Flow**: `docs/E2E_FLOW.md`
- **Risk Management**: `docs/risk-management.md`
- **Execution Model**: `docs/execution.md`

## Soporte

Si encuentras problemas:

1. Revisa logs: `backend/logs/app.log`
2. Verifica API: `curl http://localhost:8000/health`
3. Consulta runbooks: `docs/runbooks/`
4. Revisa issues conocidos en documentación


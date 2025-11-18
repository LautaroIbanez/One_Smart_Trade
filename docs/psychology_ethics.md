# Políticas Psicológicas y Éticas - One Smart Trade

## Resumen Ejecutivo

One Smart Trade implementa políticas estrictas de gestión de riesgo y protección psicológica para garantizar un uso responsable del sistema. Este documento detalla los límites exactos, triggers automáticos y mecanismos de protección implementados.

**IMPORTANTE**: Este sistema es informativo y no constituye asesoramiento financiero. Las políticas son obligatorias y están diseñadas para proteger tu capital.

## 1. Límites de Riesgo Exactos

### 1.1 Límite por Operación

- **Límite por defecto**: 1% del equity disponible
- **Límite máximo sin override**: 2% del equity disponible
- **Validación**: Se valida ANTES de generar cualquier recomendación
- **Bloqueo**: Si no hay capital validado, NO se generan señales

### 1.2 Límite Diario de Riesgo

- **Límite absoluto**: 3% del equity disponible por día
- **Hard warning**: Se activa al alcanzar 2% del equity diario
- **Bloqueo automático**: Al alcanzar 3%, se bloquean nuevas operaciones hasta el siguiente día
- **Cálculo**: Suma de todos los riesgos comprometidos en operaciones abiertas durante las últimas 24 horas

### 1.3 Límite Preventivo de Trades

- **Límite preventivo**: 7 trades en 24 horas
- **Bloqueo automático**: Al intentar el trade #8, se bloquea automáticamente
- **Duración**: 12 horas de cooldown después del límite preventivo
- **Razón**: Prevenir sobreoperación y fatiga de decisión

### 1.4 Límite de Drawdown

- **Advertencia**: Drawdown > 10% activa alertas y sugerencias educativas
- **Reducción de tamaño**: Drawdown > 15% reduce automáticamente el tamaño de posición en 50%
- **Auto-shutdown**: Drawdown > 20% suspende nuevas entradas hasta recuperación

## 2. Triggers de Cooldown (Enfriamiento)

### 2.1 Cooldown por Pérdidas Consecutivas

- **Trigger**: 3 pérdidas consecutivas
- **Duración**: 24 horas
- **Efecto**: Bloqueo de nuevas operaciones
- **Mensaje**: "Cooldown activo: 3 pérdidas consecutivas detectadas. Toma un descanso y revisa tu estrategia."

### 2.2 Cooldown por Sobreoperación

- **Trigger**: 7 trades en 24 horas (límite preventivo alcanzado)
- **Duración**: 12 horas
- **Efecto**: Bloqueo de nuevas operaciones
- **Mensaje**: "Límite preventivo alcanzado: Has realizado 7 trades en las últimas 24 horas. Descansa 12 horas antes de continuar."

### 2.3 Cooldown por Drawdown Acelerado

- **Trigger**: Drawdown empeora >5% en menos de 20 operaciones
- **Duración**: 24 horas
- **Efecto**: Bloqueo de nuevas entradas
- **Mensaje**: "Drawdown acelerado detectado. Revisa tu estrategia antes de continuar."

### 2.4 Cooldown por Brecha de Performance

- **Trigger**: Sharpe móvil < 0.2 en los últimos 50 trades
- **Duración**: 7 días o hasta recuperación
- **Efecto**: Reducción del 50% del tamaño de posición
- **Mensaje**: "Performance degradada detectada. Tamaño de posición reducido automáticamente."

## 3. Alertas de Apalancamiento

### 3.1 Umbral de Advertencia

- **Trigger**: Apalancamiento efectivo > 2.0×
- **Tipo**: Advertencia (amarilla)
- **Efecto**: Alerta persistente en el panel de riesgo
- **Mensaje**: "Apalancamiento elevado: {leverage}×. Considera reducir exposición."

### 3.2 Umbral Crítico (Hard Stop)

- **Trigger**: Apalancamiento efectivo > 3.0×
- **Persistencia requerida**: 60 minutos continuos
- **Tipo**: Bloqueo automático (rojo)
- **Efecto**: Bloqueo de nuevas entradas hasta reducir apalancamiento
- **Mensaje**: "Apalancamiento excesivo detectado ({leverage}×). Reduzca la exposición antes de continuar."

## 4. Validación de Capital

### 4.1 Requisito de Capital Validado

- **Bloqueo**: NO se generan señales sin capital validado
- **Validación**: Se verifica ANTES de cualquier generación de señal
- **Mensaje**: "Señal bloqueada por seguridad: valida tu capital. Usa /api/v1/risk/sizing con tu capital disponible."
- **Auditoría**: Cada bloqueo se registra en `risk_audit` con tipo `capital_missing`

### 4.2 Cómo Validar Capital

1. Conectar cuenta de trading (sincronización automática)
2. O ingresar capital manualmente usando `/api/v1/risk/sizing`

## 5. Mensajes de Bloqueo en la UI

### 5.1 Bloqueo por Capital Faltante

```
⚠️ Capital No Validado

Debes conectar tu cuenta o ingresar capital para recibir señales.
Usa /api/v1/risk/sizing con tu capital disponible.

Para proteger tu capital y recibir recomendaciones personalizadas,
necesitamos validar tu capital disponible.
```

### 5.2 Bloqueo por Riesgo Diario Excedido

```
🚫 Riesgo Diario Excedido

Has alcanzado el límite diario de riesgo (3% del equity).
No se pueden generar nuevas señales hasta el siguiente día.

Riesgo acumulado hoy: {risk_pct}%
Límite diario: 3%
```

### 5.3 Bloqueo por Límite Preventivo

```
⏸️ Límite Preventivo Alcanzado

Has realizado 7 trades en las últimas 24 horas.
Para proteger tu capital, debes esperar 12 horas antes de continuar.

Trades realizados: {trades_count}
Tiempo restante: {remaining_hours} horas
```

### 5.4 Bloqueo por Cooldown

```
❄️ Cooldown Activo

{reason}

Tiempo restante: {remaining_time}
```

## 6. Oferta Educativa

### 6.1 Biblioteca de Artículos

- **Total de artículos**: 15 artículos educativos
- **Categorías**: Gestión emocional, límites de riesgo, journaling, descanso
- **Artículos críticos**: Marcados con badge "⚠️ Crítico"
- **Micro-hábitos**: Cada artículo incluye acciones prácticas recomendadas

### 6.2 Sugerencias Contextuales

- **Tras N pérdidas**: Se sugiere "Gestión Emocional"
- **Ante sobreexposición**: Se sugiere "Checklist de Riesgo"
- **Durante drawdown**: Se sugiere "Gestión de Drawdown"
- **Con apalancamiento alto**: Se sugiere "Límites de Riesgo"

### 6.3 Historial de Lectura

- Registro automático de lecturas
- Seguimiento de artículos completados
- Recordatorios para artículos críticos no leídos

## 7. Auditoría y Trazabilidad

### 7.1 Registro de Eventos

Todos los bloqueos y validaciones se registran en `risk_audit` con:
- Tipo de evento (`capital_missing`, `overexposed`, `leverage_hard_stop`, `cooldown`, `risk_limit_violation`)
- Razón detallada
- Contexto (equity, leverage, trades_count, etc.)
- Timestamp

### 7.2 Alertas Internas

- **Webhook/Slack**: Se envía alerta cuando un usuario se bloquea por capital o riesgo
- **Propósito**: Permitir que soporte pueda intervenir proactivamente
- **Información incluida**: User ID, tipo de bloqueo, razón, contexto

## 8. Confirmaciones y Responsabilidades

### 8.1 Onboarding

Durante el onboarding, el usuario debe:
1. Leer las políticas psicológicas y éticas
2. Confirmar comprensión mediante checkbox
3. Aceptar que el sistema no es asesoramiento financiero

### 8.2 Reconfirmaciones

Se solicita nueva confirmación cuando:
- Se detecta incumplimiento reiterado
- Hay cambios materiales en las políticas
- Se activan múltiples bloqueos en corto tiempo

## 9. Resumen de Límites Exactos

| Límite | Valor | Acción |
|--------|-------|--------|
| Riesgo por operación (default) | 1% | Validación previa |
| Riesgo por operación (máximo) | 2% | Requiere override |
| Riesgo diario (hard warning) | 2% | Alerta visible |
| Riesgo diario (bloqueo) | 3% | Bloqueo automático |
| Trades en 24h (preventivo) | 7 | Bloqueo automático |
| Pérdidas consecutivas (cooldown) | 3 | Cooldown 24h |
| Apalancamiento (advertencia) | 2.0× | Alerta amarilla |
| Apalancamiento (hard stop) | 3.0× | Bloqueo automático |
| Drawdown (advertencia) | 10% | Alerta y sugerencias |
| Drawdown (reducción) | 15% | Reducción 50% tamaño |
| Drawdown (shutdown) | 20% | Auto-shutdown |

## 10. Referencias

- [Gestión de Riesgo](./risk-management.md) - Documentación técnica completa
- [Arquitectura](./ARCHITECTURE.md) - Diseño del sistema
- [API](./api.md) - Endpoints disponibles

---

**Última actualización**: 2024-11-18
**Versión**: 1.0


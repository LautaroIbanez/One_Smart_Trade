/**
 * Type guard to check if a recommendation is tradable (has all required fields for chart display).
 * 
 * A recommendation is considered "tradable" if:
 * - It has a signal (BUY, SELL, HOLD)
 * - It has entry_range with min, max, optimal
 * - It has stop_loss_take_profit with stop_loss and take_profit
 * - It has current_price
 * 
 * Non-tradable statuses include: capital_missing, daily_risk_limit_exceeded, cooldown, shutdown, etc.
 */
export function isTradableRecommendation(data: unknown): data is {
  signal: 'BUY' | 'HOLD' | 'SELL'
  entry_range: {
    min: number
    max: number
    optimal: number
  }
  stop_loss_take_profit: {
    stop_loss: number
    take_profit: number
    stop_loss_pct: number
    take_profit_pct: number
  }
  current_price: number
  [key: string]: unknown
} {
  if (!data || typeof data !== 'object') {
    return false
  }

  const rec = data as Record<string, unknown>

  // Check for non-tradable statuses first
  const status = rec.status
  if (status === 'capital_missing' || 
      status === 'daily_risk_limit_exceeded' || 
      status === 'cooldown' || 
      status === 'shutdown' ||
      status === 'error') {
    return false
  }

  // Check for required fields
  if (!rec.signal || !['BUY', 'HOLD', 'SELL'].includes(rec.signal as string)) {
    return false
  }

  // Check entry_range
  const entryRange = rec.entry_range
  if (!entryRange || typeof entryRange !== 'object') {
    return false
  }
  const entry = entryRange as Record<string, unknown>
  if (typeof entry.min !== 'number' || 
      typeof entry.max !== 'number' || 
      typeof entry.optimal !== 'number') {
    return false
  }

  // Check stop_loss_take_profit
  const sltp = rec.stop_loss_take_profit
  if (!sltp || typeof sltp !== 'object') {
    return false
  }
  const sltpObj = sltp as Record<string, unknown>
  if (typeof sltpObj.stop_loss !== 'number' || 
      typeof sltpObj.take_profit !== 'number') {
    return false
  }

  // Check current_price
  if (typeof rec.current_price !== 'number') {
    return false
  }

  return true
}

/**
 * Get a user-friendly message for non-tradable recommendation statuses.
 */
export function getNonTradableMessage(data: Record<string, unknown>): string {
  const status = data.status as string

  switch (status) {
    case 'capital_missing':
      return 'Capital no disponible. No se puede generar señal de trading.'
    case 'daily_risk_limit_exceeded':
      return 'Límite diario de riesgo excedido. No se pueden generar nuevas señales hoy.'
    case 'cooldown':
      return `Período de enfriamiento activo. ${data.reason || 'Operaciones bloqueadas temporalmente.'}`
    case 'shutdown':
      return 'Sistema en mantenimiento. No se pueden generar señales en este momento.'
    case 'error':
      return data.message ? String(data.message) : 'Error al generar recomendación.'
    default:
      return 'Señal no disponible en este momento.'
  }
}


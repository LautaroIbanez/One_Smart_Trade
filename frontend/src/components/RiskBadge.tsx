import './RiskBadge.css'

interface RiskBadgeProps {
  riskFraction: number
  className?: string
}

export function RiskBadge({ riskFraction, className = '' }: RiskBadgeProps) {
  const formatPercent = (value: number) => `${(value * 100).toFixed(1)}%`

  return (
    <div className={`risk-badge ${className}`}>
      <span className="risk-badge-label">
        Riesgo sugerido:
        <span
          className="tooltip-trigger"
          data-tooltip="El riesgo sugerido es el porcentaje de tu equity que deberías arriesgar en esta operación. Se calcula como: (Precio de Entrada - Stop Loss) × Tamaño de Posición / Equity. Por defecto es 1% del equity. Puedes ajustar el tamaño de la posición usando la API /api/v1/risk/sizing con tu capital disponible."
          aria-label="Información sobre riesgo sugerido"
        >
          ℹ️
        </span>
      </span>
      <span className="risk-badge-value highlight">
        {formatPercent(riskFraction)} del equity
      </span>
    </div>
  )
}

export default RiskBadge




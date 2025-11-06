import './RiskPanel.css'

type Props = { risk: Record<string, any> | undefined }

export default function RiskPanel({ risk }: Props) {
  if (!risk) return null
  const items = [
    { label: 'RR', value: risk.risk_reward_ratio },
    { label: 'Prob. SL', value: `${risk.sl_probability}%` },
    { label: 'Prob. TP', value: `${risk.tp_probability}%` },
    { label: 'Drawdown esp.', value: risk.expected_drawdown },
    { label: 'Volatilidad', value: `${risk.volatility}%` },
  ]
  return (
    <div className="risk-panel">
      <h2>Riesgo</h2>
      <div className="risk-grid">
        {items.map((it) => (
          <div key={it.label} className="risk-item">
            <span className="risk-label">{it.label}</span>
            <span className="risk-value">{String(it.value)}</span>
          </div>
        ))}
      </div>
    </div>
  )
}



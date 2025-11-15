import { useMemo, useState } from 'react'
import { submitLivelihoodFeedback, useLivelihoodFromRun } from '../api/hooks'
import './LivelihoodDashboard.css'

type Scenario = {
  capital: number
  monthly_income_p10: number
  monthly_income_p50: number
  monthly_income_p90: number
  negative_month_prob: number
  sustainable_capital: number
}

export default function LivelihoodDashboard({ runId, enabled = true }: { runId?: string; enabled?: boolean }) {
  if (!enabled) return null
  const [expenses, setExpenses] = useState<number>(() => {
    const stored = localStorage.getItem('expensesTargetUSD')
    return stored ? Number(stored) : 1200
  })
  const [ruinThreshold, setRuinThreshold] = useState<number>(0.7)
  const [horizon, setHorizon] = useState<number>(36)
  const { data, isLoading } = useLivelihoodFromRun(runId, expenses, 10000, horizon, ruinThreshold)

  const scenarios: Scenario[] = useMemo(() => (data?.scenarios as Scenario[]) || [], [data])
  const survival = data?.survival
  const [rating, setRating] = useState<number>(0)
  const [comments, setComments] = useState<string>('')
  const [submitted, setSubmitted] = useState<boolean>(false)

  return (
    <section className="livelihood-dashboard" aria-label="Panel de sostenibilidad">
      <header className="ld-header">
        <h2>Sostenibilidad y escenarios</h2>
        <div className="ld-controls">
          <label title="Gasto mensual objetivo para evaluar sostenibilidad">
            Gastos objetivo (USD)
            <input
              type="number"
              value={expenses}
              onChange={(e) => setExpenses(Number(e.target.value || 0))}
              min={0}
            onBlur={() => localStorage.setItem('expensesTargetUSD', String(expenses))} />
          </label>
          <label title="Umbral de ruina como fracción de equity (0.7 = -30%)">
            Umbral de ruina
            <input
              type="number"
              step={0.05}
              min={0.1}
              max={0.95}
              value={ruinThreshold}
              onChange={(e) => setRuinThreshold(Number(e.target.value))}
            />
          </label>
          <label title="Horizonte de simulación en meses">
            Horizonte (meses)
            <input
              type="number"
              min={6}
              max={120}
              value={horizon}
              onChange={(e) => setHorizon(Number(e.target.value))}
            />
          </label>
        </div>
      </header>

      {isLoading ? (
        <div className="ld-loading">Calculando escenarios...</div>
      ) : (
        <>
          <div className="ld-widgets">
            <div className="widget" title="Probabilidad de caer por debajo del umbral de ruina">
              <div className="widget-title">Riesgo de ruina</div>
              <div className="widget-value">{(survival?.ruin_probability ?? 0).toFixed(2)}</div>
            </div>
            <div className="widget" title="Mediana del drawdown mínimo en trayectorias simuladas">
              <div className="widget-title">Drawdown mediano</div>
              <div className="widget-value">{(survival?.median_drawdown ?? 0).toFixed(2)}</div>
            </div>
            <div className="widget" title="Equity simulado en p10/p50/p90 al final del horizonte">
              <div className="widget-title">Equity final p10/p50/p90</div>
              <div className="widget-value">
                {[(survival?.p10_equity ?? 0), (survival?.p50_equity ?? 0), (survival?.p90_equity ?? 0)].map((v, i) => (
                  <span key={i}>{v.toFixed(2)}{i < 2 ? ' / ' : ''}</span>
                ))}
              </div>
            </div>
          </div>

          <table className="ld-table" aria-label="Escenarios por tamaño de cuenta">
            <thead>
              <tr>
                <th>Capital</th>
                <th title="Ingreso mensual p10 (conservador)">p10</th>
                <th title="Ingreso mensual p50 (mediano)">p50</th>
                <th title="Ingreso mensual p90 (optimista)">p90</th>
                <th title="Probabilidad de mes negativo">Mes negativo %</th>
                <th title="Capital mínimo sugerido para cubrir gastos objetivo">Capital sugerido</th>
              </tr>
            </thead>
            <tbody>
              {scenarios.map((s) => (
                <tr key={s.capital}>
                  <td>${s.capital.toLocaleString()}</td>
                  <td>${s.monthly_income_p10.toFixed(2)}</td>
                  <td>${s.monthly_income_p50.toFixed(2)}</td>
                  <td>${s.monthly_income_p90.toFixed(2)}</td>
                  <td>{(s.negative_month_prob * 100).toFixed(1)}%</td>
                  <td>${Number.isFinite(s.sustainable_capital) ? s.sustainable_capital.toFixed(2) : '∞'}</td>
                </tr>
              ))}
            </tbody>
          </table>

          <p className="ld-note">
            Teórico vs Viable: los escenarios reflejan sizing prudente y drawdown controlado al calcular la distribución de ingresos; para un desglose de curvas teóricas y viables, consulta el panel de performance.
          </p>
          <div className="ld-feedback">
            <div className="ld-feedback-title">Feedback beta</div>
            {submitted ? (
              <div className="ld-feedback-thanks">¡Gracias por tu feedback!</div>
            ) : (
              <form
                onSubmit={async (e) => {
                  e.preventDefault()
                  if (rating < 1) return
                  try {
                    await submitLivelihoodFeedback({
                      rating,
                      comments,
                      context: { expenses, ruinThreshold, horizon },
                    })
                    setSubmitted(true)
                  } catch (err) {
                    // ignore
                  }
                }}
                className="ld-feedback-form"
              >
                <label>
                  Valoración (1-5)
                  <input type="number" min={1} max={5} value={rating} onChange={(e) => setRating(Number(e.target.value))} />
                </label>
                <label>
                  Comentarios
                  <textarea value={comments} onChange={(e) => setComments(e.target.value)} placeholder="¿Qué mejorarías?" />
                </label>
                <button type="submit" className="btn-primary" disabled={rating < 1}>
                  Enviar
                </button>
              </form>
            )}
          </div>
        </>
      )}
    </section>
  )
}



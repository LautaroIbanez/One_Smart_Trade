import { useMemo, useState } from 'react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, AreaChart, Area } from 'recharts'
import { submitLivelihoodFeedback, useLivelihoodFromRun, useLatestRunId } from '../api/hooks'
import './LivelihoodDashboard.css'

type Scenario = {
  capital: number
  monthly_income_p10: number
  monthly_income_p50: number
  monthly_income_p90: number
  negative_month_prob: number
  sustainable_capital: number
}

export default function LivelihoodDashboard() {
  const { data: runIdData } = useLatestRunId()
  const runId = runIdData?.run_id || undefined
  
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

      {isLoading || !runId ? (
        <div className="ld-loading">
          {!runId ? 'Buscando última campaña completada...' : 'Calculando escenarios...'}
        </div>
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

          {/* Income Curves: Theoretical vs Viable */}
          {data?.income_curves && Object.keys(data.income_curves).length > 0 && (
            <div className="ld-income-curves">
              <h3>Curvas de Ingresos: Teórico vs Viable</h3>
              <div className="ld-curves-grid">
                {Object.entries(data.income_curves).map(([capital, curves]: [string, any]) => (
                  <div key={capital} className="ld-curve-card">
                    <h4>Capital: ${Number(capital).toLocaleString()}</h4>
                    <ResponsiveContainer width="100%" height={250}>
                      <AreaChart data={(() => {
                        const theoretical = curves.theoretical || []
                        const viable = curves.viable || []
                        const maxLen = Math.max(theoretical.length, viable.length)
                        const data: any[] = []
                        for (let i = 0; i < maxLen; i++) {
                          const t = theoretical[i]
                          const v = viable[i]
                          if (t || v) {
                            data.push({
                              timestamp: t?.timestamp || v?.timestamp || '',
                              theoretical: t?.income || 0,
                              viable: v?.income || 0,
                            })
                          }
                        }
                        return data
                      })()}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="timestamp" tickFormatter={(val) => new Date(val).toLocaleDateString('es-ES', { month: 'short', year: '2-digit' })} />
                        <YAxis label={{ value: 'Ingreso (USD)', angle: -90, position: 'insideLeft' }} />
                        <Tooltip formatter={(value: number) => `$${value.toFixed(2)}`} labelFormatter={(val) => new Date(val).toLocaleDateString('es-ES')} />
                        <Legend />
                        <Area type="monotone" dataKey="theoretical" stroke="#8884d8" fill="#8884d8" fillOpacity={0.3} name="Teórico" />
                        <Area type="monotone" dataKey="viable" stroke="#82ca9d" fill="#82ca9d" fillOpacity={0.3} name="Viable" />
                      </AreaChart>
                    </ResponsiveContainer>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Periodic Metrics */}
          {data?.periodic_metrics && (
            <div className="ld-periodic-metrics">
              <h3>Métricas Periódicas</h3>
              <div className="ld-metrics-grid">
                {(['monthly', 'quarterly'] as const).map((horizon) => {
                  const metrics = data.periodic_metrics?.[horizon]
                  if (!metrics) return null
                  const stats = metrics.stats || {}
                  return (
                    <div key={horizon} className="ld-metrics-card">
                      <h4>{horizon === 'monthly' ? 'Mensual' : 'Trimestral'}</h4>
                      <div className="ld-metrics-stats">
                        <div className="metric-row">
                          <span className="metric-label">Media:</span>
                          <span className="metric-value">{(stats.mean * 100).toFixed(2)}%</span>
                        </div>
                        <div className="metric-row">
                          <span className="metric-label">Std Dev:</span>
                          <span className="metric-value">{(stats.std * 100).toFixed(2)}%</span>
                        </div>
                        <div className="metric-row">
                          <span className="metric-label">p25 / p75:</span>
                          <span className="metric-value">{(stats.p25 * 100).toFixed(2)}% / {(stats.p75 * 100).toFixed(2)}%</span>
                        </div>
                        <div className="metric-row">
                          <span className="metric-label">Skew:</span>
                          <span className="metric-value">{stats.skew?.toFixed(2) || 'N/A'}</span>
                        </div>
                        <div className="metric-row">
                          <span className="metric-label">Kurtosis:</span>
                          <span className="metric-value">{stats.kurtosis?.toFixed(2) || 'N/A'}</span>
                        </div>
                        <div className="metric-row">
                          <span className="metric-label">Mes Negativo %:</span>
                          <span className="metric-value">{(stats.negative_pct * 100).toFixed(1)}%</span>
                        </div>
                        <div className="metric-row">
                          <span className="metric-label">Max Loss Streak:</span>
                          <span className="metric-value">{metrics.max_loss_streak || 0}</span>
                        </div>
                        <div className="metric-row">
                          <span className="metric-label">Max Loss Duration:</span>
                          <span className="metric-value">{metrics.max_loss_duration || 0} {horizon === 'monthly' ? 'meses' : 'trimestres'}</span>
                        </div>
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          <p className="ld-note">
            Teórico vs Viable: las curvas muestran la diferencia entre ingresos teóricos (sin fricciones) y viables (con costos de ejecución, slippage y comisiones). Los escenarios reflejan sizing prudente y drawdown controlado.
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



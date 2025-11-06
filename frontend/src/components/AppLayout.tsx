import { ReactNode } from 'react'
import './AppLayout.css'

type Props = { children: ReactNode }

export default function AppLayout({ children }: Props) {
  return (
    <div className="app-layout">
      <header className="app-header">
        <h1>One Smart Trade</h1>
      </header>
      <main className="app-main">{children}</main>
      <footer className="app-footer">
        <div className="disclaimer">
          Este dashboard es informativo y no constituye asesoramiento financiero. El trading de criptomonedas implica riesgos significativos.
        </div>
        <nav className="footer-links">
          <a href="/docs/INSTALLATION.md" target="_blank" rel="noreferrer">Instalación</a>
          <a href="/docs/methodology.md" target="_blank" rel="noreferrer">Metodología</a>
          <a href="/docs/backtest-report.md" target="_blank" rel="noreferrer">Backtesting</a>
        </nav>
      </footer>
    </div>
  )
}



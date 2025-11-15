import { ReactNode } from 'react'
import OnboardingPoliciesModal from './OnboardingPoliciesModal'
import './AppLayout.css'

type Props = { children: ReactNode }

export default function AppLayout({ children }: Props) {
  return (
    <div className="app-layout">
      <OnboardingPoliciesModal />
      <header className="app-header">
        <h1>One Smart Trade</h1>
      </header>
      <main className="app-main">{children}</main>
      <footer className="app-footer">
        <div className="disclaimer">
          Este dashboard es informativo y no constituye asesoramiento financiero. El trading de criptomonedas implica riesgos significativos.
        </div>
        <nav className="footer-links" aria-label="Enlaces de documentación">
          <a href="/docs/INSTALLATION.md" target="_blank" rel="noreferrer" aria-label="Guía de instalación">
            Instalación
          </a>
          <a href="/docs/methodology.md" target="_blank" rel="noreferrer" aria-label="Metodología del sistema">
            Metodología
          </a>
          <a href="/docs/backtest-report.md" target="_blank" rel="noreferrer" aria-label="Reporte de backtesting">
            Backtesting
          </a>
          <a href="/docs/api.md" target="_blank" rel="noreferrer" aria-label="Documentación de API">
            API
          </a>
        </nav>
      </footer>
    </div>
  )
}



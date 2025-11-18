import { useEffect, useState } from 'react'
import './OnboardingPoliciesModal.css'

const STORAGE_KEY = 'policiesAcceptedV1'

export default function OnboardingPoliciesModal() {
  const [isOpen, setIsOpen] = useState(false)
  const [isChecked, setIsChecked] = useState(false)

  useEffect(() => {
    try {
      const accepted = localStorage.getItem(STORAGE_KEY) === 'true'
      if (!accepted) {
        setIsOpen(true)
      }
    } catch {
      setIsOpen(true)
    }
  }, [])

  const handleConfirm = () => {
    if (!isChecked) return
    try {
      localStorage.setItem(STORAGE_KEY, 'true')
    } catch {
      // ignore storage errors; proceed anyway
    }
    setIsOpen(false)
  }

  if (!isOpen) return null

  return (
    <div className="onboarding-modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="policies-title">
      <div className="onboarding-modal">
        <h2 id="policies-title">Políticas Psicológicas y Éticas</h2>
        <p className="modal-intro">
          Este sistema es informativo y no constituye asesoramiento financiero. Para proteger tu capital:
        </p>
        <ul className="modal-list">
          <li><strong>Límites de riesgo</strong>: 1% por operación (máx. 2% sin override). Límite diario: 3% (hard warning al 2%).</li>
          <li><strong>Límite preventivo</strong>: máximo 7 trades en 24 horas. El trade #8 se bloquea automáticamente.</li>
          <li><strong>Cooldowns</strong>: 3 pérdidas consecutivas activan cooldown de 24 horas. Drawdown >20% suspende nuevas entradas.</li>
          <li><strong>Apalancamiento</strong>: advertencia >2×; hard stop >3× bloquea nuevas entradas hasta reducir exposición.</li>
          <li><strong>Capital validado</strong>: no se generan señales sin capital verificado. Debes conectar tu cuenta o ingresar capital manualmente.</li>
          <li><strong>Educación</strong>: materiales de gestión emocional, límites y journaling disponibles en la app.</li>
        </ul>
        <p className="modal-link">
          Revisa la documentación completa: <a href="/docs/psychology_ethics.md" target="_blank" rel="noreferrer">Políticas Psicológicas y Éticas</a> | <a href="/docs/risk-management.md" target="_blank" rel="noreferrer">Gestión de Riesgo</a>.
        </p>
        <label className="confirm-row">
          <input
            type="checkbox"
            checked={isChecked}
            onChange={(e) => setIsChecked(e.target.checked)}
            aria-label="Confirmo que leí y comprendo estas políticas"
          />
          <span>Confirmo que leí y comprendo estas políticas</span>
        </label>
        <div className="modal-actions">
          <button
            type="button"
            className="btn-primary"
            onClick={handleConfirm}
            disabled={!isChecked}
            aria-disabled={!isChecked}
          >
            Continuar
          </button>
        </div>
      </div>
    </div>
  )
}



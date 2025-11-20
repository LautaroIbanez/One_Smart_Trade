import { useState, useEffect } from 'react'
import './AuditTrailModal.css'

interface AuditTrailData {
  recommendation_id: number
  date: string
  timestamp: string
  code_commit: string | null
  dataset_hash: string | null
  params_hash: string | null
  snapshot_json: {
    code_commit?: string
    dataset_hash?: string
    params_hash?: string
    worm_uuid?: string
    worm_path?: string
    worm_hash?: string
  } | null
  worm_snapshot?: {
    uuid: string
    path: string
    hash: string
    timestamp: string
  }
}

interface AuditTrailModalProps {
  recommendationId: number
  isOpen: boolean
  onClose: () => void
}

function AuditTrailModal({ recommendationId, isOpen, onClose }: AuditTrailModalProps) {
  const [data, setData] = useState<AuditTrailData | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [copiedHash, setCopiedHash] = useState<string | null>(null)

  useEffect(() => {
    if (isOpen && recommendationId) {
      fetchSnapshot()
    }
  }, [isOpen, recommendationId])

  const fetchSnapshot = async () => {
    setLoading(true)
    setError(null)
    try {
      const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'
      const response = await fetch(`${API_BASE_URL}/api/v1/recommendation/${recommendationId}/snapshot`)
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }
      const snapshotData = await response.json()
      setData(snapshotData)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error al cargar el rastro de auditoría')
    } finally {
      setLoading(false)
    }
  }

  const copyToClipboard = async (text: string, hashType: string) => {
    try {
      await navigator.clipboard.writeText(text)
      setCopiedHash(hashType)
      setTimeout(() => setCopiedHash(null), 2000)
    } catch (err) {
      console.error('Failed to copy:', err)
    }
  }

  const codeCommit = data?.code_commit || data?.snapshot_json?.code_commit
  const datasetHash = data?.dataset_hash || data?.snapshot_json?.dataset_hash
  const paramsHash = data?.params_hash || data?.snapshot_json?.params_hash
  const wormHash = data?.snapshot_json?.worm_hash || data?.worm_snapshot?.hash

  if (!isOpen) return null

  return (
    <div className="audit-trail-modal-overlay" onClick={onClose}>
      <div className="audit-trail-modal" onClick={(e) => e.stopPropagation()}>
        <div className="audit-trail-modal-header">
          <h2>Rastro de Auditoría</h2>
          <button type="button" className="close-button" onClick={onClose} aria-label="Cerrar">
            ×
          </button>
        </div>

        <div className="audit-trail-modal-content">
          {loading && <div className="loading">Cargando...</div>}
          {error && <div className="error">{error}</div>}
          {data && !loading && (
            <>
              <div className="audit-info-section">
                <div className="info-item">
                  <span className="info-label">ID de Recomendación:</span>
                  <span className="info-value">{data.recommendation_id}</span>
                </div>
                <div className="info-item">
                  <span className="info-label">Fecha:</span>
                  <span className="info-value">{data.date}</span>
                </div>
                <div className="info-item">
                  <span className="info-label">Timestamp:</span>
                  <span className="info-value">{new Date(data.timestamp).toLocaleString('es-ES')}</span>
                </div>
              </div>

              <div className="audit-hash-section">
                <h3>Hashes de Verificación</h3>

                <div className="hash-item">
                  <div className="hash-header">
                    <span className="hash-label">Code Commit (Git):</span>
                    <button
                      type="button"
                      className={`copy-button ${copiedHash === 'commit' ? 'copied' : ''}`}
                      onClick={() => codeCommit && copyToClipboard(codeCommit, 'commit')}
                      disabled={!codeCommit}
                      aria-label="Copiar commit hash"
                    >
                      {copiedHash === 'commit' ? '✓ Copiado' : '📋 Copiar'}
                    </button>
                  </div>
                  <code className="hash-value">{codeCommit || 'N/A'}</code>
                </div>

                <div className="hash-item">
                  <div className="hash-header">
                    <span className="hash-label">Dataset Hash:</span>
                    <button
                      type="button"
                      className={`copy-button ${copiedHash === 'dataset' ? 'copied' : ''}`}
                      onClick={() => datasetHash && copyToClipboard(datasetHash, 'dataset')}
                      disabled={!datasetHash}
                      aria-label="Copiar dataset hash"
                    >
                      {copiedHash === 'dataset' ? '✓ Copiado' : '📋 Copiar'}
                    </button>
                  </div>
                  <code className="hash-value">{datasetHash || 'N/A'}</code>
                </div>

                <div className="hash-item">
                  <div className="hash-header">
                    <span className="hash-label">Params Hash:</span>
                    <button
                      type="button"
                      className={`copy-button ${copiedHash === 'params' ? 'copied' : ''}`}
                      onClick={() => paramsHash && copyToClipboard(paramsHash, 'params')}
                      disabled={!paramsHash}
                      aria-label="Copiar params hash"
                    >
                      {copiedHash === 'params' ? '✓ Copiado' : '📋 Copiar'}
                    </button>
                  </div>
                  <code className="hash-value">{paramsHash || 'N/A'}</code>
                </div>

                {wormHash && (
                  <div className="hash-item">
                    <div className="hash-header">
                      <span className="hash-label">WORM Snapshot Hash:</span>
                      <button
                        type="button"
                        className={`copy-button ${copiedHash === 'worm' ? 'copied' : ''}`}
                        onClick={() => wormHash && copyToClipboard(wormHash, 'worm')}
                        aria-label="Copiar WORM hash"
                      >
                        {copiedHash === 'worm' ? '✓ Copiado' : '📋 Copiar'}
                      </button>
                    </div>
                    <code className="hash-value">{wormHash}</code>
                    {data.snapshot_json?.worm_uuid && (
                      <div className="worm-info">
                        <div className="worm-detail">
                          <span className="worm-label">UUID:</span>
                          <code className="worm-value">{data.snapshot_json.worm_uuid}</code>
                        </div>
                        {data.snapshot_json.worm_path && (
                          <div className="worm-detail">
                            <span className="worm-label">Path:</span>
                            <code className="worm-value">{data.snapshot_json.worm_path}</code>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )}
              </div>

              <div className="audit-explanation">
                <h3>Explicación</h3>
                <ul>
                  <li>
                    <strong>Code Commit:</strong> Hash del commit de git utilizado para generar esta señal
                  </li>
                  <li>
                    <strong>Dataset Hash:</strong> Hash SHA-256 de los datasets curatos utilizados (1d, 1h)
                  </li>
                  <li>
                    <strong>Params Hash:</strong> Hash SHA-256 de la configuración de parámetros (params.yaml)
                  </li>
                  <li>
                    <strong>WORM Snapshot Hash:</strong> Hash SHA-256 del snapshot inmutable almacenado en WORM
                  </li>
                </ul>
                <p className="verification-note">
                  Estos hashes permiten verificar de forma independiente que la señal fue generada con el código,
                  datos y parámetros especificados. El snapshot WORM garantiza inmutabilidad y trazabilidad completa.
                </p>
              </div>
            </>
          )}
        </div>

        <div className="audit-trail-modal-footer">
          <button type="button" className="close-footer-button" onClick={onClose}>
            Cerrar
          </button>
        </div>
      </div>
    </div>
  )
}

export default AuditTrailModal







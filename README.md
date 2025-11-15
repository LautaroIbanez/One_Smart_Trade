# One Smart Trade

Sistema profesional de recomendaciones diarias para trading de BTC basado en análisis cuantitativo multi-timeframe.

## Arquitectura

```
One Smart Trade/
├── backend/          # FastAPI + motor cuantitativo
├── frontend/         # React/Vite dashboard
├── shared/           # Utilidades compartidas
├── docs/             # Documentación completa
└── scripts/          # Scripts de setup y ejecución
```

## Requisitos

- Python 3.11 o 3.12
- Node.js 20+
- Poetry (gestión de dependencias Python)
- pnpm (gestión de dependencias Node)

## Instalación Rápida

### Backend

```bash
cd backend
poetry install
poetry run python -m pytest
```

### Frontend

```bash
cd frontend
pnpm install
pnpm run build
```

## Ejecución

### Desarrollo

**Backend:**
```bash
cd backend
poetry run uvicorn app.main:app --reload --port 8000
```

**Frontend:**
```bash
cd frontend
pnpm run dev
```

### Producción

Ver `docs/INSTALLATION.md` para instrucciones completas de despliegue.

## Documentación
- [Instalación](docs/INSTALLATION.md)
- [Metodología](docs/methodology.md)
- [Backtest Report](docs/backtest-report.md)
- [Runbooks](docs/runbooks/)

## Objetivo Cuantitativo y Gobernanza

- **Objetivo cuantitativo:** Maximizar el ratio Calmar manteniendo drawdown p95 ≤ 15% y preservando capital por encima del 50%.
- **Metodología de validación:** Pipeline walk-forward con etapas de entrenamiento, validación, walk y out-of-sample, más simulaciones Monte Carlo para stress de rachas y drawdowns.
- **Reglas de promoción:** El candidato challenger reemplaza al champion cuando mejora el score objetivo en ≥5% y cumple los límites de drawdown y riesgo simulados.
- **Métricas de riesgo:** Reportamos drawdowns simulados (mediana/p95/p99), probabilidad de ruina y distribución de rachas perdedoras para contextualizar resiliencia operativa.

## Datasets Curados

- Regenera los parquet tras cambios de indicadores ejecutando `cd backend && poetry run python -m app.scripts.curate --interval all`. Si necesitas un intervalo específico, cambia `--interval`.
- Antes de regenerar, crea una copia versionada de los dataset actuales con `cp backend/data/curated/<interval>/latest.parquet backend/data/curated/<interval>/<YYYYMMDD>_pre-factor-upgrade.parquet`. Ajusta la etiqueta para el experimento (por ejemplo, `_post-factor-upgrade`).
- Después de curar, ejecuta el mismo comando de copia usando una etiqueta nueva. Así puedes comparar métricas de señal con herramientas internas (`app.quant`) apuntando al archivo versionado deseado.
- Para validar el impacto, corre los tests cuantitativos: `cd backend && poetry run pytest tests/quant/test_indicators_and_factors.py`.

## Calibración de estrategias

- Ajusta los umbrales sin redeploy editando `backend/app/quant/params.yaml`. Ejemplo: `mean_reversion.rsi_buy` para modificar el gatillo de sobreventa.
- Tras modificar el YAML, vuelve a ejecutar los backtests (`poetry run pytest tests/quant/test_strategies_and_signal.py`) para verificar regresiones.
- Los valores por defecto se aplican si alguna clave falta o si el YAML es inválido; mantén comentarios en un archivo aparte para evitar errores de parseo.

## Disclaimer Legal

Este software es solo para fines educativos y de investigación. No constituye asesoramiento financiero. El trading de criptomonedas conlleva riesgos significativos. Use bajo su propia responsabilidad.

## Licencia

Ver LICENSE para más detalles.
# Frontend - One Smart Trade

## Arquitectura UI
- AppLayout con header/footer y disclaimer
- Dashboard con:
  - RecommendationCard (señal actual, rango, SL/TP, confianza)
  - PriceLevelsChart (precio vs niveles)
  - IndicatorsPanel (RSI, MACD, ATR, vol.)
  - RiskPanel (RR, prob. SL/TP, drawdown esperado)
  - HistoryTable (historial reciente)

## Hooks API
- useTodayRecommendation, useRecommendationHistory, useMarketData
- useInvalidateAll para invalidación manual (botón Refrescar)

## Accesibilidad y Tema
- Estados de carga/error con roles aria
- Tema oscuro con variables CSS

## Tests
- Vitest + Testing Library: smoke test de Dashboard y unit tests de componentes

## Lighthouse
- Objetivo: Performance ≥ 90, Accessibility ≥ 85
- Resultado actual (dev env puede variar):
  - Perf: [pendiente]
  - Accesibilidad: [pendiente]
  - Best Practices: [pendiente]
  - SEO: [pendiente]

Para ejecutar Lighthouse: usar Chrome DevTools > Lighthouse o `lighthouse http://localhost:5173`.


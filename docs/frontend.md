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

### Objetivo
- Performance: ≥ 90
- Accessibility: ≥ 85
- Best Practices: ≥ 90
- SEO: ≥ 80

### Ejecución
```bash
# Instalar Lighthouse CLI
npm install -g lighthouse

# Ejecutar en build de producción
cd frontend
pnpm run build
pnpm run preview
# En otra terminal:
lighthouse http://localhost:4173 --view
```

### Optimizaciones Implementadas
- Lazy loading de componentes pesados
- Code splitting automático (Vite)
- Imágenes optimizadas (si aplica)
- CSS variables para tema oscuro eficiente
- React Query para caching y reducción de requests

### Accesibilidad
- Roles ARIA en componentes interactivos
- Etiquetas `aria-label` en botones e iconos
- Contraste WCAG AA (mínimo 4.5:1)
- Navegación por teclado funcional
- Focus visible en elementos interactivos

### Resultados Esperados (Build de Producción)
- Performance: 90-95 (depende de datos de red)
- Accessibility: 90-95
- Best Practices: 95+
- SEO: 85-90

**Nota:** Los resultados en desarrollo pueden ser menores debido a hot-reload y source maps.


# Objetivo del Sistema de Backtesting

## Definición de la Métrica Objetivo

El sistema está diseñado para **maximizar el ratio Calmar** sujeto a un límite de drawdown máximo.

### Métrica Principal: Calmar Ratio

```
Calmar = CAGR / Max Drawdown
```

Donde:
- **CAGR**: Compound Annual Growth Rate (tasa de crecimiento anual compuesta)
- **Max Drawdown**: Máximo drawdown porcentual durante el período de backtest

### Objetivo Configurable

El sistema utiliza una infraestructura de campañas con objetivo configurable:

- **Pipeline**: Train/Validation/Walk-Forward/Out-of-Sample (OOS)
- **Métricas de riesgo calculadas**: Sharpe, Calmar, riesgo de ruina, rachas
- **Optimización**: Maximización de Calmar con penalización por drawdown

### Calmar Penalizado

Para penalizar estrategias con drawdowns prolongados:

```
Calmar_Penalizado = Calmar * (1 - longest_drawdown_days / total_days)
```

Esto reduce el score de estrategias que pasan mucho tiempo en drawdown, incluso si tienen buen Calmar base.

## Guardrails Numéricos

El sistema implementa guardrails automáticos que rechazan campeones que no cumplen los siguientes criterios:

### Guardrails de Validación Pre-Ejecución

- **Ventana mínima**: ≥ 730 días (2 años)
- **Cobertura mensual**: ≥ 90% de barras esperadas
- **Gaps máximos**: No más de 1 día consecutivo sin datos

### Guardrails de Métricas Post-Ejecución

| Métrica | Umbral | Acción |
|---------|--------|--------|
| Calmar OOS | ≥ 1.5 | Rechazar si menor |
| Max Drawdown (realistic) | ≤ 25% | Rechazar si mayor |
| Risk of Ruin | ≤ 5% | Rechazar si mayor |
| OOS Length | ≥ 120 días | Rechazar si menor |
| Divergencia CAGR teórico/realista | ≤ 5% | Rechazar si mayor |
| Calmar CI Lower Bound | ≥ 1.0 | Rechazar si menor (inestable) |
| Número de trades | ≥ 50 | Rechazar si menor |
| Duración mínima | ≥ 24 meses | Rechazar si menor |

### Intervalos de Confianza Bootstrap

- **Trials**: 5,000 bootstrap samples
- **Percentiles reportados**: p5, p50, p95 para Calmar, CAGR, Sharpe
- **Estabilidad**: Si `calmar_ci_low < 1.0`, la campaña se marca como "inestable"

## Procedimiento para Reproducir una Campaña

### 1. Identificar la Campaña

Obtener el `campaign_id` o `run_id` de la campaña a reproducir.

### 2. Comando CLI

```bash
# Desde el directorio backend/
poetry run python -m app.scripts.reproduce_campaign \
    --campaign-id <CAMPAIGN_ID> \
    --seed <SEED> \
    --output-dir data/backtest_results/
```

### 3. Parámetros de Reproducción

- **seed**: Seed aleatoria usada en la simulación original (almacenada en metadata)
- **campaign_id**: Identificador único de la campaña
- **output-dir**: Directorio donde guardar resultados

### 4. Verificación

El script generará:
- `metadata.json`: Parámetros y configuración
- `trades.parquet`: Trades ejecutados
- `equity.parquet`: Curvas de equity (theoretical y realistic)
- `returns_per_period.json`: Retornos por período
- Checksums SHA256 para verificación de integridad

### 5. Comparación

Comparar checksums y métricas con la ejecución original:

```bash
# Verificar checksum
sha256sum data/backtest_results/<run_id>/trades.parquet

# Comparar métricas
poetry run python -m app.scripts.compare_campaigns \
    --original <ORIGINAL_RUN_ID> \
    --reproduced <REPRODUCED_RUN_ID>
```

## Checklist "Go / No-Go" para Liberar Estrategia

Antes de liberar una estrategia a producción, verificar todos los siguientes criterios:

### Validación de Datos

- [ ] Backtest window >= 3 años (≥ 1,095 días)
- [ ] Cobertura mensual >= 90% en todos los meses
- [ ] Sin gaps > 1 día consecutivo

### Métricas de Performance

- [ ] Walk-forward Calmar promedio >= 1.5
- [ ] Calmar OOS >= 1.5
- [ ] Max DD realistic <= 25%
- [ ] Calmar CI lower bound (p5) >= 1.0

### Métricas de Riesgo

- [ ] Risk of ruin (10k USD) <= 5%
- [ ] Equity realistic vs theoretical delta <= 5% CAGR
- [ ] Equity divergence 7-day <= 5%

### Validación Estadística

- [ ] Bootstrap CI muestra estabilidad (p5 Calmar >= 1.0)
- [ ] Número de trades >= 50
- [ ] OOS length >= 120 días

### Reproducibilidad

- [ ] Campaña reproducible con seed original
- [ ] Checksums verificados
- [ ] Métricas coinciden dentro de tolerancia (< 0.1% diferencia)

### Observabilidad

- [ ] Métricas registradas en Prometheus
- [ ] Alertas configuradas (risk_of_ruin, equity_divergence)
- [ ] Dashboard actualizado con métricas

### Documentación

- [ ] Parámetros documentados
- [ ] Resultados guardados con metadata completa
- [ ] Reporte generado y auditado

## Alertas Automáticas

El sistema emite alertas automáticas cuando:

### Risk of Ruin

- **Warning (Amarillo)**: `risk_of_ruin > 10%`
- **Critical (Rojo)**: `risk_of_ruin > 20%`

### Equity Divergence

- **Warning**: `equity_realistic` diverge de `equity_theoretical` > 5% en 7 días

### Métricas Registradas

Todas las campañas registran en Prometheus:
- `campaign_calmar_realistic`
- `campaign_max_drawdown_realistic`
- `campaign_risk_of_ruin`
- `campaign_equity_divergence_pct`
- `campaign_equity_divergence_7d_pct`

## Reglas de Despliegue

El endpoint `/api/v1/performance/summary` **bloquea la publicación** de resultados si:

1. `oos_days < 120`: Período OOS insuficiente
2. `metrics.status != "PASS"`: Métricas no pasan guardrails

Esto previene la publicación de resultados inválidos o incompletos.

## Referencias

- [Backtest Report](./backtest-report.md): Documentación detallada del sistema de backtesting
- [Risk Management](./risk-management.md): Políticas de gestión de riesgo
- [Architecture](./ARCHITECTURE.md): Arquitectura general del sistema



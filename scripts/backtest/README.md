# Backtest Scripts

Scripts para análisis de backtesting y validación de estrategias.

## run_sensitivity.py

Ejecuta análisis de sensibilidad con variaciones ±20% de parámetros críticos para validar estabilidad de estrategias antes de promover campeones.

### Uso

```bash
cd backend
poetry run python ../scripts/backtest/run_sensitivity.py \
    --start-date 2023-01-01 \
    --end-date 2024-01-01 \
    --output-dir artifacts/sensitivity \
    --campaign-id my_campaign_001
```

### Argumentos

- `--start-date` (requerido): Fecha de inicio del backtest (YYYY-MM-DD)
- `--end-date` (requerido): Fecha de fin del backtest (YYYY-MM-DD)
- `--params-path` (opcional): Ruta al archivo `params.yaml`. Si no se especifica, busca en ubicaciones comunes.
- `--output-dir` (opcional): Directorio de salida para resultados (default: `artifacts/sensitivity`)
- `--campaign-id` (opcional): ID de campaña. Si no se especifica, se genera automáticamente.
- `--critical-params` (opcional): Lista de parámetros críticos a validar. Si no se especifica, usa la lista por defecto.

### Parámetros Críticos por Defecto

El script valida variaciones ±20% de los siguientes parámetros:

- `breakout.lookback`
- `volatility.low_threshold`
- `volatility.high_threshold`
- `aggregate.vector_bias.momentum_bias_weight`
- `aggregate.vector_bias.breakout_slope_weight`
- `aggregate.buy_threshold`
- `aggregate.sell_threshold`
- `aggregate.vector_bias.momentum_alignment`
- `aggregate.multi_timeframe.ema21_slope_weight`
- `aggregate.multi_timeframe.intraday_momentum_weight`

### Salida

El script genera un archivo Parquet en `{output_dir}/{campaign_id}.parquet` con los siguientes campos:

- `params_id`: ID único de cada combinación de parámetros
- `campaign_id`: ID de la campaña
- `calmar`, `sharpe`, `max_dd`, `cagr`, `win_rate`, `profit_factor`: Métricas de performance
- `valid`: Si el backtest fue válido
- Columnas para cada parámetro variado con sus valores
- `start_date`, `end_date`, `created_at`: Metadatos

### Integración con Pipeline de Campeones

Los resultados generados por este script son automáticamente validados por `SensitivityGuard` antes de promover un campeón. Ver `docs/architecture/robustness.md` para más detalles.

### Ejemplo Completo

```bash
# 1. Ejecutar análisis de sensibilidad
poetry run python ../scripts/backtest/run_sensitivity.py \
    --start-date 2023-01-01 \
    --end-date 2024-01-01 \
    --campaign-id candidate_001

# 2. El pipeline de campeones automáticamente validará estos resultados
# cuando se intente promover un campeón con params_id="candidate_001"
```

### Notas

- El análisis puede tomar tiempo dependiendo del número de combinaciones de parámetros
- Se recomienda ejecutar en un entorno con suficientes recursos computacionales
- Los resultados se pueden usar para identificar parámetros sensibles y ajustar la estrategia


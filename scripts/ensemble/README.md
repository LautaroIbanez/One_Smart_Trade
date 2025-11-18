# Ensemble Weight Management

Sistema para gestionar pesos dinámicos del ensemble de estrategias basado en performance histórica.

## Componentes

### 1. MetaWeightStore (`app/strategies/weight_store.py`)
Almacena y recupera pesos del ensemble por régimen de mercado.

### 2. WeightUpdater (`app/strategies/weight_updater.py`)
Calcula pesos basados en métricas de performance (Sharpe, Calmar, hit rate, drawdown).

### 3. StrategyEnsemble (modificado)
Carga pesos dinámicos desde el store, con fallback a pesos uniformes si no hay datos.

## Uso

### Actualizar pesos manualmente

```bash
# Actualizar todos los regímenes
cd backend
poetry run python -m scripts.ensemble.update_weights --regime all

# Actualizar un régimen específico
poetry run python -m scripts.ensemble.update_weights --regime bull

# Dry run (calcular sin guardar)
poetry run python -m scripts.ensemble.update_weights --regime all --dry-run

# Usar método diferente
poetry run python -m scripts.ensemble.update_weights --method proportional_sharpe
```

### Parámetros

- `--regime`: Régimen a actualizar (`bull`, `bear`, `range`, `neutral`, `all`)
- `--method`: Método de cálculo (`softmax_sharpe`, `proportional_sharpe`, `calmar_weighted`)
- `--lookback-days`: Días hacia atrás para calcular métricas (default: 60)
- `--output-dir`: Directorio para guardar artifacts (default: `artifacts/ensemble`)
- `--dry-run`: Calcular sin guardar en base de datos

### Programar actualización automática

Agregar al scheduler en `app/main.py`:

```python
@scheduler.scheduled_job("cron", day_of_week="mon", hour=2, minute=0, id="update_ensemble_weights")
async def job_update_ensemble_weights() -> None:
    """Weekly job to update ensemble weights."""
    from scripts.ensemble.update_weights import main
    exit_code = main(["--regime", "all"])
    if exit_code != 0:
        logger.error("Failed to update ensemble weights")
```

## Métodos de Cálculo

### softmax_sharpe (default)
Usa softmax de Sharpe ratio penalizado por drawdown:
- `score = sharpe * (1 - normalized_dd * 0.5)`
- Normaliza con softmax (temperatura=1.0)

### proportional_sharpe
Pesos proporcionales a `max(0, sharpe)`:
- `weight_i = sharpe_i / sum(sharpe_j)`

### calmar_weighted
Pesos proporcionales a `max(0, calmar)`:
- `weight_i = calmar_i / sum(calmar_j)`

## Base de Datos

Los pesos se almacenan en la tabla `ensemble_weights`:
- `regime`: Régimen de mercado
- `strategy_name`: Nombre de la estrategia
- `weight`: Peso normalizado (0-1)
- `metrics`: JSON con métricas usadas (sharpe, calmar, hit_rate, etc.)
- `snapshot_date`: Fecha del snapshot (YYYY-MM-DD)
- `is_active`: Si es el peso activo para este régimen

## Artifacts

El script genera `artifacts/ensemble/weights.json` con:
- Timestamp de cálculo
- Pesos por régimen
- Métricas por estrategia
- Metadatos

## Migración

Ejecutar migración de Alembic:

```bash
cd backend
poetry run alembic upgrade head
```

Esto crea la tabla `ensemble_weights`.

## Testing

Ejecutar tests:

```bash
cd backend
poetry run pytest tests/strategies/test_strategy_ensemble_weights.py -v
```


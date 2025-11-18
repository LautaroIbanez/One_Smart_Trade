# Meta-Learner Training

Sistema de meta-learning para combinar estrategias de forma óptima usando machine learning.

## Componentes

### 1. MetaLearner (`app/strategies/meta_learner.py`)
Clase que encapsula modelos de ML (Logistic Regression, Gradient Boosting) para aprender a combinar señales de estrategias.

**Features:**
- Señales de cada subestrategia (signal, confidence)
- Features de régimen (regime, vol_bucket)
- Estado de volatilidad (volatility, ATR)
- Features técnicas (momentum, RSI)

**Modelos soportados:**
- `logistic`: Regresión logística regularizada (L2)
- `gradient_boosting`: Gradient Boosting Classifier

### 2. Script de Entrenamiento (`scripts/strategies/train_meta_learner.py`)
Entrena modelos por régimen usando datos históricos de `signal_outcomes`.

### 3. StrategyEnsemble (modificado)
Usa el meta-learner cuando está disponible y calibrado (ECE < threshold), degrada a votación clásica si ECE es alto.

## Uso

### Entrenar modelos

```bash
# Entrenar para todos los regímenes
cd backend
poetry run python -m scripts.strategies.train_meta_learner --regime all

# Entrenar para un régimen específico
poetry run python -m scripts.strategies.train_meta_learner --regime bull

# Usar Gradient Boosting
poetry run python -m scripts.strategies.train_meta_learner --model-type gradient_boosting

# Ajustar lookback
poetry run python -m scripts.strategies.train_meta_learner --lookback-days 180 --min-samples 50
```

### Parámetros

- `--regime`: Régimen a entrenar (`bull`, `bear`, `range`, `neutral`, `all`)
- `--model-type`: Tipo de modelo (`logistic`, `gradient_boosting`)
- `--lookback-days`: Días hacia atrás para datos de entrenamiento (default: 365)
- `--min-samples`: Mínimo de muestras requeridas (default: 100)
- `--output-dir`: Directorio de salida (default: `artifacts/meta_learner`)

### Artifacts Generados

```
artifacts/meta_learner/
├── bull/
│   ├── model.pkl          # Modelo entrenado
│   └── metrics.json       # Métricas (ROC-AUC, ECE, etc.)
├── bear/
│   ├── model.pkl
│   └── metrics.json
├── range/
│   ├── model.pkl
│   └── metrics.json
├── neutral/
│   ├── model.pkl
│   └── metrics.json
└── training_summary.json  # Resumen de entrenamiento
```

## Métricas

El script reporta:
- **ROC-AUC**: Área bajo la curva ROC
- **Brier Score**: Error cuadrático de probabilidades
- **ECE (Expected Calibration Error)**: Error de calibración esperado
- **Log Loss**: Pérdida logarítmica
- **Accuracy**: Precisión

## Degradación Automática

`StrategyEnsemble` degrada automáticamente a votación clásica si:
1. No existe modelo para el régimen detectado
2. ECE > threshold (default: 0.15)
3. Error al cargar o usar el modelo

Cuando se degrada, se registra una alerta en el sistema.

## Programar Reentrenamiento

Agregar al scheduler en `app/main.py`:

```python
@scheduler.scheduled_job("cron", day_of_week="sun", hour=3, minute=0, id="train_meta_learner")
async def job_train_meta_learner() -> None:
    """Weekly job to retrain meta-learner models."""
    from scripts.strategies.train_meta_learner import main
    exit_code = main(["--regime", "all", "--lookback-days", "365"])
    if exit_code != 0:
        logger.error("Failed to train meta-learner models")
```

## Testing

Ejecutar tests:

```bash
cd backend
poetry run pytest tests/strategies/test_meta_learner_integration.py -v
```

## Notas

- Los modelos se entrenan por régimen para capturar patrones específicos
- ECE threshold de 0.15 es conservador; ajustar según necesidades
- Se requiere mínimo 100 muestras por régimen para entrenar
- Los modelos se versionan por fecha de entrenamiento en `metrics.json`


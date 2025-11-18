"""Seed knowledge base with initial educational content."""
from pathlib import Path
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.core.database import SessionLocal
from app.core.config import settings
from app.db.models import KnowledgeArticleORM
from app.core.logging import logger


ARTICLES = [
    {
        "title": "Gestión Emocional en Trading",
        "slug": "gestion-emocional-trading",
        "category": "emotional_management",
        "summary": "Aprende a controlar tus emociones durante las operaciones y tomar decisiones racionales bajo presión.",
        "content": """# Gestión Emocional en Trading

## Introducción

El trading no es solo números y gráficos. Tus emociones juegan un papel crucial en cada decisión que tomas. Las pérdidas pueden generar frustración, miedo y ansiedad, mientras que las ganancias pueden crear euforia y sobreconfianza.

## Principios Fundamentales

### 1. Reconocer tus Emociones

El primer paso es ser consciente de cómo te sientes. ¿Estás operando por miedo, codicia o simplemente siguiendo tu plan?

### 2. Separar Emoción de Decisión

Antes de abrir o cerrar una posición, pregunta: "¿Estoy siguiendo mi estrategia o reaccionando emocionalmente?"

### 3. Toma de Descansos

Si te sientes abrumado, toma un descanso. El mercado seguirá ahí mañana.

## Técnicas Prácticas

- **Respiración profunda**: Antes de tomar una decisión importante, respira profundamente 3 veces.
- **Journaling**: Escribe tus pensamientos y emociones antes y después de cada trade.
- **Meditación**: Practica mindfulness para aumentar tu autocontrol.

## Cuando Activamos un Cooldown

Si el sistema detecta una racha perdedora o sobreoperación, es momento de detenerte. No es una derrota, es protección. Usa este tiempo para reflexionar, estudiar tus trades pasados y regresar con una mentalidad clara.

## Conclusión

El mejor trader no es el que nunca siente emociones, sino el que las reconoce y las controla. La gestión emocional es una habilidad que se desarrolla con la práctica constante.
""",
        "tags": ["emoción", "control", "psicología"],
        "trigger_conditions": {"trigger": "cooldown"},
        "priority": 10,
    },
    {
        "title": "Límites de Riesgo: Protegiendo tu Capital",
        "slug": "limites-riesgo-proteccion-capital",
        "category": "risk_limits",
        "summary": "Comprende por qué los límites de riesgo son esenciales y cómo aplicarlos correctamente.",
        "content": """# Límites de Riesgo: Protegiendo tu Capital

## ¿Por Qué los Límites de Riesgo?

Tu capital es tu herramienta más valiosa. Sin él, no puedes operar. Los límites de riesgo no son restricciones, son protección.

## Regla del 1%

Una regla fundamental es nunca arriesgar más del 1% de tu equity en una sola operación. Esto te permite:
- Sobrevivir rachas perdedoras
- Mantener la calma durante drawdowns
- Operar con confianza

## Apalancamiento Efectivo

El apalancamiento efectivo mide cuánto capital nominal tienes expuesto vs. tu equity disponible.

### Por Qué Importa

- **Apalancamiento > 3×**: Riesgo extremo. El sistema activa un hard stop para protegerte.
- **Apalancamiento 2-3×**: Zona de precaución. Monitorea de cerca.
- **Apalancamiento < 2×**: Zona segura.

## Cómo Reducir el Apalancamiento

1. Cierra posiciones parcialmente
2. Espera a que las posiciones existentes lleguen a TP o SL antes de abrir nuevas
3. Aumenta tu capital si es apropiado (no como reacción emocional)

## Cuando el Sistema Detecta Apalancamiento Excesivo

Si el sistema bloquea nuevas operaciones por apalancamiento excesivo, no es un castigo. Es una red de seguridad que te obliga a reducir el riesgo antes de continuar.

## Conclusión

Los límites de riesgo son tu mejor amigo en el trading. Respétalos, y ellos te protegerán de ti mismo.
""",
        "tags": ["riesgo", "apalancamiento", "capital"],
        "trigger_conditions": {"trigger": "leverage"},
        "priority": 10,
    },
    {
        "title": "La Importancia del Descanso",
        "slug": "importancia-descanso",
        "category": "rest",
        "summary": "Descubre por qué el descanso es crucial para el éxito en el trading a largo plazo.",
        "content": """# La Importancia del Descanso

## El Descanso No Es Perder Tiempo

En un mundo donde parece que debemos estar constantemente operando, el descanso es visto como una pérdida de oportunidades. Nada más lejos de la verdad.

## Beneficios del Descanso

### 1. Claridad Mental

Cuando estás cansado, tu capacidad de tomar buenas decisiones disminuye. El descanso restaura tu claridad mental.

### 2. Reducción de Errores

Los traders descansados cometen menos errores. Los traders fatigados operan de forma impulsiva.

### 3. Perspectiva

El tiempo lejos del mercado te permite ver el panorama general, no solo los movimientos intradiarios.

## Cuándo Tomar un Descanso

- Después de una racha perdedora
- Cuando te sientas emocionalmente agotado
- Si has estado operando intensamente durante días
- Cuando el sistema activa un cooldown

## Actividades Durante el Descanso

- Revisa tus trades pasados
- Estudia el mercado sin presión
- Dedica tiempo a tu vida personal
- Medita o practica mindfulness
- Lee sobre trading (no solo técnicas, también psicología)

## El Cooldown Automático

Cuando el sistema detecta condiciones que requieren un descanso (racha perdedora, sobreoperación), activa un cooldown. Aprovéchalo. Es una oportunidad para reiniciar, no una derrota.

## Conclusión

El mejor trader es el que sabe cuándo NO operar. El descanso es una herramienta de gestión de riesgo tan importante como los stop losses.
""",
        "tags": ["descanso", "salud mental", "prevención"],
        "trigger_conditions": {"trigger": "cooldown"},
        "priority": 8,
    },
    {
        "title": "Journaling: Tu Mejor Herramienta de Mejora",
        "slug": "journaling-mejora-trading",
        "category": "journaling",
        "summary": "Aprende cómo llevar un diario de trading puede transformar tu performance.",
        "content": """# Journaling: Tu Mejor Herramienta de Mejora

## ¿Qué es el Journaling?

El journaling (o diario de trading) es el registro sistemático de tus operaciones, pensamientos, emociones y lecciones aprendidas.

## Por Qué es Fundamental

### 1. Autoconocimiento

Al escribir sobre tus trades, descubres patrones en tu comportamiento que de otra forma pasarían desapercibidos.

### 2. Aprendizaje Continuo

Cada trade es una oportunidad de aprendizaje. El journaling asegura que no pierdas esas lecciones.

### 3. Rendición de Cuentas

Saber que vas a escribir sobre cada decisión te ayuda a mantenerte disciplinado.

## Qué Incluir en tu Journal

### Para Cada Trade

- **Setup**: ¿Por qué entraste?
- **Emociones**: ¿Cómo te sentiste antes, durante y después?
- **Resultado**: ¿Qué pasó?
- **Lecciones**: ¿Qué aprendiste?

### Diario General

- **Estado mental**: ¿Cómo te sientes hoy?
- **Condiciones del mercado**: ¿Cómo está el mercado?
- **Errores**: ¿Qué hiciste mal?
- **Aciertos**: ¿Qué hiciste bien?

## Ejemplo de Entrada

**Fecha**: 2024-01-15
**Estado mental**: Estresado después de 2 pérdidas seguidas
**Trade**: Entrada en BTCUSDT
**Setup**: RSI sobreventa + soporte técnico
**Emoción**: Ansiedad por recuperar pérdidas anteriores
**Resultado**: Pérdida del 1.5%
**Lección**: NO debería haber operado estando estresado. Debo esperar a estar emocionalmente estable.

## Durante los Cooldowns

El cooldown es el momento perfecto para revisar tu journal. Busca patrones:
- ¿Opero peor cuando estoy estresado?
- ¿Qué setups funcionan mejor para mí?
- ¿Qué emociones preceden a mis peores trades?

## Herramientas

- **Notebook físico**: Para algunos, escribir a mano ayuda a procesar mejor.
- **Documento digital**: Fácil de buscar y analizar.
- **Apps especializadas**: Hay apps diseñadas específicamente para journaling de trading.

## Conclusión

El trader que no hace journaling es como un estudiante que no toma notas. Puede tener algunos éxitos, pero no mejorará de forma sistemática. El journaling es la diferencia entre un trader casual y un trader profesional.
""",
        "tags": ["journaling", "aprendizaje", "disciplina"],
        "trigger_conditions": None,
        "priority": 9,
    },
    {
        "title": "Sobreoperación: El Enemigo Silencioso",
        "slug": "sobreoperacion-enemigo-silencioso",
        "category": "emotional_management",
        "summary": "Aprende a reconocer y evitar la sobreoperación, uno de los errores más comunes.",
        "content": """# Sobreoperación: El Enemigo Silencioso

## ¿Qué es la Sobreoperación?

La sobreoperación ocurre cuando operas más de lo que tu estrategia requiere, generalmente motivado por emociones como:

- **Codicia**: Querer más ganancias rápidas
- **Aburrimiento**: Necesidad de "estar en el mercado"
- **Revancha**: Intentar recuperar pérdidas rápidamente

## Señales de Sobreoperación

- Más de 8 operaciones en 24 horas
- Operar en setups que normalmente ignorarías
- Reducir el tamaño de posición para "encajar" más trades
- Sentir necesidad compulsiva de estar siempre operando

## Por Qué es Peligrosa

### 1. Aumenta las Comisiones

Cada trade tiene un costo. Más trades = más costos, incluso si ganas.

### 2. Disminuye la Calidad

Cuando operas mucho, operas mal. La calidad > cantidad.

### 3. Agotamiento Emocional

La sobreoperación es emocionalmente agotadora y lleva a malas decisiones.

## El Cooldown como Protección

Cuando el sistema detecta sobreoperación (más de 8 trades en 24h), activa un cooldown de 12 horas. Aprovéchalo:

1. Revisa tus trades de las últimas 24h
2. Identifica qué te llevó a sobreoperar
3. Regresa con un plan más disciplinado

## Cómo Evitarla

- **Limítate a setups específicos**: No operes todo lo que veas
- **Respeto los horarios**: Define horarios de trading y respétalos
- **Ten un máximo diario**: "No más de 3 operaciones por día"
- **Usa el journaling**: Registra tus emociones para identificar patrones

## Conclusión

Más trades no significa más ganancias. El mejor trader es selectivo y paciente. Aprende a decir "no" a oportunidades que no cumplen tu criterio.
""",
        "tags": ["sobreoperación", "disciplina", "prevención"],
        "trigger_conditions": {"trigger": "overtrading"},
        "priority": 9,
    },
    {
        "title": "Rachas Perdedoras: Cómo Manejarlas",
        "slug": "rachas-perdedoras-manejo",
        "category": "emotional_management",
        "summary": "Estrategias para mantener la calma y la disciplina durante rachas perdedoras.",
        "content": """# Rachas Perdedoras: Cómo Manejarlas

## Las Rachas Perdedoras Son Normales

Incluso los mejores traders tienen rachas perdedoras. Es parte del juego. Lo importante es cómo las manejas.

## Respuestas Comunes (y Peligrosas)

### 1. Aumentar el Tamaño

"Si pierdo más, debo apostar más para recuperar rápido" ❌

Esto lleva al riesgo de ruina. Nunca aumentes el tamaño después de una pérdida.

### 2. Cambiar de Estrategia

"Mi estrategia no funciona, necesito otra" ❌

Las rachas perdedoras pueden ocurrir incluso con buenas estrategias. Cambiar constantemente es peor.

### 3. Operar Más

"Necesito más oportunidades para recuperar" ❌

Esto es sobreoperación y empeora las cosas.

## Respuesta Correcta

### 1. Mantener la Disciplina

Sigue tu plan. Si tu estrategia es sólida, las rachas perdedoras son temporales.

### 2. Reducir el Tamaño (opcional)

Si te sientes emocionalmente afectado, reduce el tamaño temporalmente. No es rendirse, es proteger tu capital mental.

### 3. Tomar un Descanso

Después de 3 pérdidas seguidas, el sistema activa un cooldown de 24 horas. Úsalo para:
- Revisar tus trades
- Verificar que sigues tu plan
- Recargar mentalmente

## Análisis Post-Racha

Después de una racha perdedora:

1. **¿Fue mala suerte o error?**: Revisa si seguiste tu plan o cometiste errores.
2. **¿Tu estrategia sigue siendo válida?**: Analiza los datos con calma.
3. **¿Necesitas ajustes menores?**: Pequeños ajustes, no cambios radicales.

## Conclusión

Las rachas perdedoras prueban tu disciplina. Si mantienes la calma y sigues tu plan, superarás cualquier racha. Si reaccionas emocionalmente, las rachas perdedoras se convertirán en períodos de pérdidas catastróficas.
""",
        "tags": ["rachas", "disciplina", "recuperación"],
        "trigger_conditions": {"trigger": "cooldown"},
        "priority": 9,
    },
]


def seed_knowledge_base():
    """Seed knowledge base with initial articles."""
    db = SessionLocal()
    try:
        existing_slugs = {a.slug for a in db.query(KnowledgeArticleORM).all()}
        
        for article_data in ARTICLES:
            if article_data["slug"] in existing_slugs:
                logger.info(f"Article {article_data['slug']} already exists, skipping")
                continue
            
            article = KnowledgeArticleORM(**article_data)
            db.add(article)
            logger.info(f"Added article: {article_data['title']}")
        
        db.commit()
        logger.info("Knowledge base seeded successfully")
    except Exception as e:
        db.rollback()
        logger.error(f"Error seeding knowledge base: {e}", exc_info=True)
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_knowledge_base()





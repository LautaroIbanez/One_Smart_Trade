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
        "trigger_conditions": {"trigger": "cooldown", "losing_streak": 3},
        "priority": 10,
        "micro_habits": [
            "Antes de cada trade, respira profundamente 3 veces",
            "Escribe en tu journal cómo te sientes antes de operar",
            "Si sientes emociones fuertes, espera 10 minutos antes de decidir",
        ],
        "is_critical": True,
        "download_url": "/api/v1/knowledge/articles/gestion-emocional-trading/pdf",
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
        "trigger_conditions": {"trigger": "leverage", "threshold": 2.0},
        "priority": 10,
        "micro_habits": [
            "Revisa tu apalancamiento efectivo antes de cada nueva operación",
            "Si el apalancamiento > 2×, considera cerrar posiciones parcialmente",
            "Registra en tu journal cada vez que el sistema te alerta sobre apalancamiento",
        ],
        "is_critical": True,
        "download_url": "/api/v1/knowledge/articles/limites-riesgo-proteccion-capital/pdf",
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
        "micro_habits": [
            "Durante un cooldown, dedica tiempo a revisar tus trades pasados",
            "Toma un descanso de 30 minutos después de 4 horas de trading",
            "Usa el tiempo de cooldown para leer material educativo",
        ],
        "is_critical": False,
        "download_url": "/api/v1/knowledge/articles/importancia-descanso/pdf",
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
        "micro_habits": [
            "Escribe en tu journal antes y después de cada trade",
            "Revisa tu journal semanalmente para identificar patrones",
            "Usa tu journal para analizar tus emociones durante trades",
        ],
        "is_critical": False,
        "download_url": "/api/v1/knowledge/articles/journaling-mejora-trading/pdf",
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
        "trigger_conditions": {"trigger": "overtrading", "trades_24h": 6},
        "priority": 9,
        "micro_habits": [
            "Cuenta tus trades diarios y detente en 6",
            "Si sientes necesidad de operar más, toma un descanso de 1 hora",
            "Registra en tu journal por qué quieres operar más",
        ],
        "is_critical": True,
        "download_url": "/api/v1/knowledge/articles/sobreoperacion-enemigo-silencioso/pdf",
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
        "trigger_conditions": {"trigger": "cooldown", "losing_streak": 3},
        "priority": 9,
        "micro_habits": [
            "Después de cada pérdida, escribe en tu journal: '¿Seguí mi plan?'",
            "Si tienes 2 pérdidas seguidas, toma un descanso de 1 hora antes de la siguiente operación",
            "Revisa tus últimos 10 trades después de una racha perdedora",
        ],
        "is_critical": True,
        "download_url": "/api/v1/knowledge/articles/rachas-perdedoras-manejo/pdf",
    },
    {
        "title": "Aversión a la Pérdida: El Sesgo que Te Hace Perder Más",
        "slug": "aversion-perdida-sesgo-cognitivo",
        "category": "emotional_management",
        "summary": "Comprende cómo la aversión a la pérdida te hace tomar malas decisiones y cómo superarla.",
        "content": """# Aversión a la Pérdida: El Sesgo que Te Hace Perder Más

## ¿Qué es la Aversión a la Pérdida?

La aversión a la pérdida es un sesgo cognitivo que hace que las pérdidas psicológicamente duelan el doble que las ganancias nos alegran. Esto lleva a comportamientos irracionales en el trading.

## Cómo Se Manifiesta

### 1. Mantener Pérdidas Demasiado Tiempo

Cuando una posición está en pérdida, tu mente te dice: "Espera, puede recuperarse". Pero si tu stop loss está bien colocado, mantener la posición viola tu plan.

### 2. Cerrar Ganancias Prematuramente

Por el contrario, cuando tienes una ganancia pequeña, tu mente te dice: "Tómala antes de que se convierta en pérdida". Esto te hace cerrar posiciones ganadoras antes de tiempo.

### 3. Rechazar Operaciones Válidas

Después de una pérdida, puedes volverte demasiado conservador y rechazar setups válidos por miedo a perder de nuevo.

## Por Qué Es Peligrosa

- **Rompe tu disciplina**: Te hace violar tu plan de trading
- **Reduce tu win rate**: Cierras ganancias temprano y mantienes pérdidas
- **Aumenta el estrés**: La indecisión constante es agotadora

## Cómo Superarla

### 1. Confía en tu Plan

Si tu stop loss está bien colocado según tu análisis, respétalo. No dejes que las emociones lo muevan.

### 2. Enfócate en el Proceso, No en el Resultado

Una operación puede ser correcta incluso si resulta en pérdida. Lo importante es seguir tu proceso.

### 3. Usa el Journaling

Registra tus emociones antes y después de cada trade. Identifica cuándo la aversión a la pérdida está afectando tus decisiones.

### 4. Practica la Aceptación

Las pérdidas son parte del trading. Acepta que perderás operaciones, incluso con un buen plan.

## Conclusión

La aversión a la pérdida es natural, pero puede ser superada con disciplina y autoconocimiento. El mejor trader no es el que nunca siente miedo, sino el que reconoce el miedo y sigue su plan de todas formas.
""",
        "tags": ["sesgos", "psicología", "disciplina"],
        "trigger_conditions": {"trigger": "cooldown", "losing_streak": 2},
        "priority": 8,
        "micro_habits": [
            "Antes de mover un stop loss, pregunta: '¿Esto viola mi plan original?'",
            "Si sientes ganas de cerrar una ganancia temprano, espera 10 minutos antes de decidir",
            "Registra en tu journal cada vez que sientas miedo a perder",
        ],
        "is_critical": False,
        "download_url": "/api/v1/knowledge/articles/aversion-perdida-sesgo-cognitivo/pdf",
    },
    {
        "title": "Efecto Disposición: Por Qué Mantienes Pérdidas y Cierras Ganancias",
        "slug": "efecto-disposicion-trading",
        "category": "emotional_management",
        "summary": "Aprende sobre el efecto disposición y cómo te hace tomar decisiones subóptimas.",
        "content": """# Efecto Disposición: Por Qué Mantienes Pérdidas y Cierras Ganancias

## ¿Qué es el Efecto Disposición?

El efecto disposición es la tendencia a vender activos que están en ganancia demasiado pronto y mantener activos que están en pérdida demasiado tiempo. Es una manifestación de la aversión a la pérdida.

## El Problema

### Mantener Pérdidas

Cuando una posición está en pérdida, tu mente racionaliza: "Espera, puede recuperarse". Pero si tu análisis técnico dice que debes salir, debes salir.

### Cerrar Ganancias Temprano

Cuando una posición está en ganancia, tu mente dice: "Tómala antes de que se convierta en pérdida". Pero si tu análisis dice que el movimiento continúa, debes mantenerla.

## Por Qué Ocurre

- **Miedo a perder ganancias**: "Una ganancia pequeña es mejor que una pérdida"
- **Esperanza irracional**: "Esta pérdida se recuperará si espero"
- **Falta de confianza**: No confías en tu análisis cuando las emociones están involucradas

## Cómo Combatirlo

### 1. Usa Take Profit y Stop Loss Objetivos

Define tus niveles ANTES de entrar. Una vez definidos, no los muevas por emociones.

### 2. Enfócate en el Ratio Riesgo/Beneficio

Si tu plan dice que el TP está a 3× el SL, mantén la posición hasta el TP. No cierres en 1.5× solo porque tienes miedo.

### 3. Revisa tus Trades

Analiza cuántas veces cerraste ganancias temprano y cuántas veces mantuviste pérdidas. Identifica el patrón.

### 4. Practica la Disciplina

Cada vez que sientas ganas de cerrar una ganancia temprano o mantener una pérdida, recuerda: "Estoy siguiendo mi plan, no mis emociones".

## Conclusión

El efecto disposición es uno de los sesgos más costosos en el trading. Superarlo requiere disciplina férrea y confianza en tu proceso. Recuerda: el mejor trade es el que sigue tu plan, no el que sigue tus emociones.
""",
        "tags": ["sesgos", "disciplina", "psicología"],
        "trigger_conditions": None,
        "priority": 7,
        "micro_habits": [
            "Define TP y SL antes de cada entrada, y no los muevas",
            "Si sientes ganas de cerrar una ganancia, revisa tu plan original",
            "Registra en tu journal cada vez que violes tu TP o SL por emociones",
        ],
        "is_critical": False,
        "download_url": "/api/v1/knowledge/articles/efecto-disposicion-trading/pdf",
    },
    {
        "title": "Sobreconfianza: El Arrogante Pierde",
        "slug": "sobreconfianza-trading",
        "category": "emotional_management",
        "summary": "La sobreconfianza después de ganancias puede ser tan peligrosa como el miedo después de pérdidas.",
        "content": """# Sobreconfianza: El Arrogante Pierde

## ¿Qué es la Sobreconfianza?

La sobreconfianza es la tendencia a sobreestimar tus habilidades y subestimar los riesgos, especialmente después de una racha ganadora.

## Señales de Sobreconfianza

- **Aumentar el tamaño de posición** después de ganancias
- **Ignorar tu plan** porque "sabes lo que haces"
- **Operar en setups que normalmente evitarías**
- **Pensar que eres invencible** después de ganancias

## Por Qué es Peligrosa

### 1. Aumenta el Riesgo

Cuando estás sobreconfiado, tomas más riesgo del que deberías. Una pérdida grande puede eliminar semanas de ganancias.

### 2. Rompe la Disciplina

La sobreconfianza te hace pensar que las reglas no aplican para ti. Esto lleva a violar tu plan.

### 3. Lleva a Pérdidas Catastróficas

El trader sobreconfiado es el que más pierde, porque no respeta los límites de riesgo.

## Cómo Evitarla

### 1. Mantén el Tamaño de Posición Constante

No aumentes el tamaño después de ganancias. Si tu plan dice 1% de riesgo, mantén 1% siempre.

### 2. Revisa tus Trades Ganadores

Analiza si ganaste por habilidad o por suerte. Sé honesto contigo mismo.

### 3. Recuerda las Pérdidas

Mantén un registro de tus pérdidas. Recuerda que el trading es difícil y que puedes perder en cualquier momento.

### 4. Respeta tu Plan

Incluso después de una racha ganadora, sigue tu plan. Las reglas existen por una razón.

## El Equilibrio

El mejor trader no es ni demasiado confiado ni demasiado temeroso. Es disciplinado y respeta su plan, sin importar si está en racha ganadora o perdedora.

## Conclusión

La sobreconfianza es el enemigo silencioso del trader exitoso. Mantén la humildad, respeta tu plan, y recuerda: el mercado puede quitarte todo en un instante si te vuelves complaciente.
""",
        "tags": ["sobreconfianza", "disciplina", "riesgo"],
        "trigger_conditions": {"trigger": "winning_streak", "streak_count": 5},
        "priority": 7,
        "micro_habits": [
            "Después de 3 ganancias seguidas, revisa si estás siguiendo tu plan",
            "Nunca aumentes el tamaño de posición después de ganancias",
            "Registra en tu journal: '¿Gané por habilidad o por suerte?'",
        ],
        "is_critical": False,
        "download_url": "/api/v1/knowledge/articles/sobreconfianza-trading/pdf",
    },
    {
        "title": "FOMO y FOBO: Los Enemigos del Trader Disciplinado",
        "slug": "fomo-fobo-trading",
        "category": "emotional_management",
        "summary": "Aprende a reconocer y evitar el FOMO (Fear Of Missing Out) y FOBO (Fear Of Better Options).",
        "content": """# FOMO y FOBO: Los Enemigos del Trader Disciplinado

## ¿Qué es FOMO?

FOMO (Fear Of Missing Out) es el miedo a perderte una oportunidad. Te hace entrar en trades que no cumplen tu criterio solo porque otros están ganando.

## ¿Qué es FOBO?

FOBO (Fear Of Better Options) es el miedo a que haya una mejor oportunidad. Te hace cerrar posiciones válidas o no entrar en trades porque esperas algo mejor.

## Cómo Se Manifiestan

### FOMO

- **Entrar tarde**: Ves un movimiento y entras sin esperar tu setup
- **Operar fuera de horario**: Operas cuando no deberías porque "no quieres perderte nada"
- **Ignorar tu plan**: Entras en trades que no cumplen tu criterio

### FOBO

- **No entrar**: Ves un setup válido pero no entras porque esperas algo mejor
- **Cerrar temprano**: Cierras posiciones porque piensas que hay mejores oportunidades
- **Parálisis por análisis**: Analizas tanto que nunca actúas

## Por Qué Son Peligrosos

- **Rompen tu disciplina**: Te hacen operar fuera de tu plan
- **Aumentan el estrés**: La constante búsqueda de oportunidades es agotadora
- **Reducen tu win rate**: Operar por FOMO/FOBO reduce la calidad de tus trades

## Cómo Combatirlos

### 1. Ten un Plan Claro

Define exactamente qué setups operas y cuándo. Si un trade no cumple tu criterio, no lo operes, sin importar cuán tentador sea.

### 2. Acepta que Perderás Oportunidades

No puedes operar todas las oportunidades. Acepta que perderás algunas y enfócate en las que sí cumplan tu criterio.

### 3. Usa el Journaling

Registra cada vez que sientas FOMO o FOBO. Identifica los patrones y trabaja en ellos.

### 4. Practica la Paciencia

El mejor trader es paciente. Espera sus setups y no se deja llevar por la emoción del momento.

## Conclusión

FOMO y FOBO son emociones naturales, pero pueden ser controladas con disciplina y un plan claro. Recuerda: es mejor perder una oportunidad que perder dinero en un mal trade.
""",
        "tags": ["fomo", "fobo", "disciplina", "psicología"],
        "trigger_conditions": None,
        "priority": 6,
        "micro_habits": [
            "Antes de entrar en un trade, pregunta: '¿Cumple mi criterio o es FOMO?'",
            "Si sientes FOMO, espera 30 minutos antes de decidir",
            "Registra en tu journal cada trade que entraste por FOMO o FOBO",
        ],
        "is_critical": False,
        "download_url": "/api/v1/knowledge/articles/fomo-fobo-trading/pdf",
    },
    {
        "title": "Checklist de Riesgo: Tu Red de Seguridad",
        "slug": "checklist-riesgo-seguridad",
        "category": "risk_limits",
        "summary": "Un checklist sistemático para verificar que cada operación cumple con tus límites de riesgo.",
        "content": """# Checklist de Riesgo: Tu Red de Seguridad

## ¿Por Qué un Checklist?

Un checklist te ayuda a verificar sistemáticamente que cada operación cumple con tus límites de riesgo antes de ejecutarla. Es tu red de seguridad contra errores emocionales.

## Checklist Pre-Operación

### 1. Límite de Riesgo por Operación

- [ ] ¿El riesgo de esta operación es ≤ 1% de mi equity?
- [ ] ¿He calculado el tamaño de posición correctamente?
- [ ] ¿Mi stop loss está bien colocado según mi análisis?

### 2. Límite de Riesgo Diario

- [ ] ¿Mi riesgo acumulado hoy + este riesgo ≤ 3% de mi equity?
- [ ] ¿Estoy cerca del límite diario? (Si > 2%, precaución)
- [ ] ¿Cuántos trades he hecho hoy? (Máximo 7 antes del límite preventivo)

### 3. Apalancamiento

- [ ] ¿Mi apalancamiento efectivo después de esta operación ≤ 2×?
- [ ] ¿Estoy en zona segura o de precaución?

### 4. Estado Emocional

- [ ] ¿Estoy emocionalmente estable?
- [ ] ¿No estoy operando por revancha, codicia o miedo?
- [ ] ¿He descansado lo suficiente?

### 5. Setup y Plan

- [ ] ¿Este trade cumple mi criterio de entrada?
- [ ] ¿He definido TP y SL antes de entrar?
- [ ] ¿Sigo mi plan o estoy improvisando?

## Checklist Post-Operación

### Después de Abrir una Posición

- [ ] ¿Registré el trade en mi journal?
- [ ] ¿Anoté mis emociones antes de entrar?
- [ ] ¿Verifiqué que el tamaño de posición es correcto?

### Después de Cerrar una Posición

- [ ] ¿Registré el resultado en mi journal?
- [ ] ¿Analicé qué salió bien y qué salió mal?
- [ ] ¿Actualicé mi riesgo acumulado diario?

## Cuándo Usar el Checklist

- **Siempre antes de cada operación**: No importa cuán seguro te sientas
- **Especialmente después de pérdidas**: Cuando las emociones están altas
- **Después de ganancias**: Para evitar sobreconfianza

## El Checklist como Hábito

Haz del checklist un hábito automático. Con el tiempo, se convertirá en parte natural de tu proceso y te protegerá de errores costosos.

## Conclusión

Un checklist de riesgo no es una restricción, es una herramienta de protección. El mejor trader no es el que nunca revisa, sino el que siempre verifica antes de actuar.
""",
        "tags": ["checklist", "riesgo", "disciplina", "proceso"],
        "trigger_conditions": {"trigger": "leverage", "threshold": 1.5},
        "priority": 10,
        "micro_habits": [
            "Imprime o guarda este checklist y revísalo antes de cada operación",
            "Marca cada ítem mentalmente antes de entrar en un trade",
            "Si no puedes marcar todos los ítems, no operes",
        ],
        "is_critical": True,
    },
    {
        "title": "Gestión de Drawdown: Cómo Mantener la Calma en la Tormenta",
        "slug": "gestion-drawdown-mantener-calma",
        "category": "risk_limits",
        "summary": "Estrategias para manejar drawdowns sin perder la disciplina ni la confianza.",
        "content": """# Gestión de Drawdown: Cómo Mantener la Calma en la Tormenta

## ¿Qué es un Drawdown?

Un drawdown es la reducción del capital desde un pico. Es normal y esperado en el trading. Lo importante es cómo lo manejas.

## Tipos de Drawdown

### Drawdown Normal

- **Hasta 10%**: Parte normal del trading
- **Respuesta**: Mantener disciplina, seguir tu plan

### Drawdown Moderado

- **10-20%**: Requiere atención
- **Respuesta**: Revisar tu estrategia, considerar reducir tamaño temporalmente

### Drawdown Severo

- **> 20%**: Crítico
- **Respuesta**: El sistema puede activar auto-shutdown. Revisa todo tu proceso.

## Cómo Manejar un Drawdown

### 1. No Aumentes el Tamaño

Aumentar el tamaño después de pérdidas es el error más común y peligroso. Nunca lo hagas.

### 2. Revisa tu Estrategia (Con Calma)

Espera a estar emocionalmente estable antes de revisar. Las decisiones emocionales empeoran las cosas.

### 3. Considera Reducir Temporalmente

Si el drawdown te está afectando emocionalmente, reduce el tamaño temporalmente. No es rendirse, es proteger tu capital mental.

### 4. Usa el Cooldown

Si el sistema activa un cooldown durante un drawdown, aprovéchalo. Es tiempo para reflexionar, no para desesperarse.

### 5. Mantén la Perspectiva

Un drawdown del 15% puede recuperarse con 3-4 buenos trades. Mantén la perspectiva a largo plazo.

## Señales de Alarma

- **Pérdidas consecutivas > 5**: Revisa tu estrategia
- **Drawdown > 20%**: Considera pausar y reevaluar
- **Violación constante de reglas**: Necesitas un descanso

## Recuperación

### Después de un Drawdown

1. **Analiza qué pasó**: ¿Fue mala suerte o errores?
2. **Ajusta si es necesario**: Pequeños ajustes, no cambios radicales
3. **Vuelve con disciplina**: Sigue tu plan, no intentes recuperar rápido

## Conclusión

Los drawdowns son parte del trading. El mejor trader no es el que nunca tiene drawdowns, sino el que los maneja con disciplina y calma. Recuerda: el mercado siempre da oportunidades. Lo importante es estar vivo para tomarlas.
""",
        "tags": ["drawdown", "riesgo", "recuperación", "disciplina"],
        "trigger_conditions": {"trigger": "drawdown", "threshold": 10},
        "priority": 9,
        "micro_habits": [
            "Revisa tu drawdown diariamente, pero no te obsesiones",
            "Si el drawdown > 10%, reduce el tamaño de posición en 50%",
            "Registra en tu journal cómo te sientes durante drawdowns",
        ],
        "is_critical": True,
    },
    {
        "title": "Plan de Trading: Tu Hoja de Ruta al Éxito",
        "slug": "plan-trading-hoja-ruta",
        "category": "risk_limits",
        "summary": "Cómo crear y seguir un plan de trading que te guíe hacia el éxito consistente.",
        "content": """# Plan de Trading: Tu Hoja de Ruta al Éxito

## ¿Por Qué Necesitas un Plan?

Un plan de trading es tu hoja de ruta. Define qué operas, cuándo operas, y cómo gestionas el riesgo. Sin un plan, estás navegando a ciegas.

## Componentes de un Plan de Trading

### 1. Objetivos

- **Objetivo de ganancia mensual**: Realista y alcanzable
- **Objetivo de riesgo máximo**: Por operación y diario
- **Objetivo de número de trades**: Calidad sobre cantidad

### 2. Estrategia

- **Setups que operas**: Define exactamente qué buscas
- **Condiciones de entrada**: Criterios claros y objetivos
- **Condiciones de salida**: TP y SL bien definidos

### 3. Gestión de Riesgo

- **Riesgo por operación**: Máximo 1% (o 2% con override)
- **Riesgo diario máximo**: 3%
- **Apalancamiento máximo**: 2× (zona segura)

### 4. Reglas de Disciplina

- **Horarios de trading**: Define cuándo operas
- **Límite de trades diarios**: Máximo 7 antes del límite preventivo
- **Reglas de cooldown**: Respeta los períodos de enfriamiento

### 5. Proceso de Revisión

- **Journaling diario**: Registra cada trade
- **Revisión semanal**: Analiza tu performance
- **Ajustes mensuales**: Pequeños ajustes basados en datos

## Cómo Crear tu Plan

### Paso 1: Define tus Objetivos

Sé específico y realista. "Ganar dinero" no es un objetivo. "Ganar 5% mensual con máximo 1% de riesgo por trade" sí lo es.

### Paso 2: Define tu Estrategia

Elige setups que entiendas y puedas ejecutar consistentemente. No intentes operar todo.

### Paso 3: Establece Límites

Define límites claros de riesgo. Estos límites te protegerán de ti mismo.

### Paso 4: Escribe tu Plan

Un plan que no está escrito no es un plan. Escríbelo y revísalo regularmente.

### Paso 5: Sigue tu Plan

Un plan que no sigues no sirve. La disciplina es la diferencia entre un plan y un deseo.

## Revisar y Ajustar

### Cuándo Revisar

- **Semanalmente**: Revisa tu performance
- **Mensualmente**: Analiza si necesitas ajustes
- **Después de drawdowns**: Verifica que sigues tu plan

### Cómo Ajustar

- **Pequeños ajustes**: No cambios radicales
- **Basado en datos**: No en emociones
- **Conservador**: Mejor ajustar poco que mucho

## Conclusión

Un plan de trading es tu mejor herramienta. Te da estructura, te protege de emociones, y te guía hacia el éxito. Pero un plan solo funciona si lo sigues. La disciplina es la clave.
""",
        "tags": ["plan", "estrategia", "disciplina", "objetivos"],
        "trigger_conditions": None,
        "priority": 8,
        "micro_habits": [
            "Escribe tu plan de trading y revísalo cada semana",
            "Antes de cada trade, verifica que cumple con tu plan",
            "Registra en tu journal cada vez que violas tu plan",
        ],
        "is_critical": False,
    },
    {
        "title": "Psicología del Mercado: Entendiendo la Masa",
        "slug": "psicologia-mercado-masa",
        "category": "emotional_management",
        "summary": "Comprende cómo la psicología de la masa afecta los mercados y cómo usarlo a tu favor.",
        "content": """# Psicología del Mercado: Entendiendo la Masa

## El Mercado es una Masa de Emociones

El mercado no es solo números y gráficos. Es una masa de traders tomando decisiones basadas en emociones: miedo, codicia, esperanza, pánico.

## Ciclos Emocionales del Mercado

### 1. Optimismo

- **Características**: Precios suben, todos son optimistas
- **Riesgo**: Sobreconfianza, FOMO
- **Oportunidad**: Tomar ganancias, ser cauteloso

### 2. Euforia

- **Características**: Precios en máximos, todos compran
- **Riesgo**: Burbuja, sobrecompra extrema
- **Oportunidad**: Considerar tomar ganancias, prepararse para corrección

### 3. Ansiedad

- **Características**: Primera corrección, dudas aparecen
- **Riesgo**: Pánico temprano, ventas prematuras
- **Oportunidad**: Posibles entradas en correcciones

### 4. Miedo

- **Características**: Caídas continuas, pánico crece
- **Riesgo**: Venta de pánico, pérdidas grandes
- **Oportunidad**: Posibles entradas en sobreventa extrema

### 5. Pánico

- **Características**: Caídas masivas, todos venden
- **Riesgo**: Pérdidas catastróficas
- **Oportunidad**: Posibles rebotes (pero muy arriesgado)

### 6. Desesperación

- **Características**: Precios en mínimos, nadie quiere comprar
- **Riesgo**: Entrar demasiado temprano
- **Oportunidad**: Posibles entradas en fondo (con cuidado)

## Cómo Usarlo a Tu Favor

### 1. Contrarian Thinking

Cuando todos son optimistas, sé cauteloso. Cuando todos tienen miedo, busca oportunidades (con cuidado).

### 2. Identifica el Ciclo

Reconoce en qué fase del ciclo emocional está el mercado. Esto te ayuda a ajustar tu estrategia.

### 3. No Sigas la Masa

La masa suele estar equivocada en los extremos. Sé independiente en tu análisis.

### 4. Usa Indicadores de Sentimiento

Indicadores como RSI extremo, volumen alto, o noticias pueden indicar emociones extremas.

## Protección Contra la Masa

### 1. Sigue tu Plan

Tu plan te protege de las emociones de la masa. Sigue tu plan, no la multitud.

### 2. Mantén la Calma

Cuando el mercado está en pánico o euforia, mantén la calma. Las emociones extremas son temporales.

### 3. Usa Stop Losses

Los stop losses te protegen cuando la masa se vuelve irracional.

## Conclusión

Entender la psicología del mercado te ayuda a tomar mejores decisiones. Pero recuerda: no intentes predecir la masa, solo protégete de ella y busca oportunidades cuando la emoción es extrema.
""",
        "tags": ["psicología", "mercado", "sentimiento", "análisis"],
        "trigger_conditions": None,
        "priority": 6,
        "micro_habits": [
            "Observa el sentimiento del mercado antes de operar",
            "Si el mercado está en euforia extrema, sé cauteloso",
            "Registra en tu journal cómo el sentimiento del mercado afecta tus decisiones",
        ],
        "is_critical": False,
        "download_url": "/api/v1/knowledge/articles/psicologia-mercado-masa/pdf",
    },
    {
        "title": "Sesgos Cognitivos en Trading: Conoce a tu Enemigo",
        "slug": "sesgos-cognitivos-trading",
        "category": "emotional_management",
        "summary": "Los sesgos cognitivos son trampas mentales que distorsionan tu percepción y decisiones. Aprende a identificarlos y combatirlos.",
        "content": """# Sesgos Cognitivos en Trading: Conoce a tu Enemigo

## ¿Qué son los Sesgos Cognitivos?

Los sesgos cognitivos son errores sistemáticos en el pensamiento que afectan nuestras decisiones. En trading, estos sesgos pueden costarte dinero.

## Sesgos Más Comunes en Trading

### 1. Sesgo de Confirmación

**Qué es**: Buscar información que confirma tus creencias e ignorar la que las contradice.

**Ejemplo**: Solo recuerdas los trades ganadores y olvidas los perdedores.

**Cómo combatirlo**: Lleva un journal objetivo. Registra TODOS los trades, ganadores y perdedores.

### 2. Sesgo de Anclaje

**Qué es**: Depender demasiado de la primera información que recibes.

**Ejemplo**: Si viste BTC a $50k, piensas que $45k es "barato" aunque el análisis técnico diga lo contrario.

**Cómo combatirlo**: Siempre analiza desde cero. No te ancles a precios pasados.

### 3. Sesgo de Disponibilidad

**Qué es**: Sobreestimar la probabilidad de eventos que son fáciles de recordar.

**Ejemplo**: Después de ver noticias de un crash, sobreestimas la probabilidad de otro crash.

**Cómo combatirlo**: Usa datos históricos, no anécdotas recientes.

### 4. Sesgo de Resultado

**Qué es**: Juzgar la calidad de una decisión por su resultado, no por el proceso.

**Ejemplo**: Un trade ganador por suerte te hace pensar que tu estrategia es buena.

**Cómo combatirlo**: Evalúa el proceso, no solo el resultado. ¿Seguiste tu plan?

### 5. Ilusión de Control

**Qué es**: Creer que tienes más control sobre los resultados de lo que realmente tienes.

**Ejemplo**: Pensar que puedes predecir el mercado con precisión.

**Cómo combatirlo**: Acepta la incertidumbre. El mercado es impredecible. Enfócate en gestionar el riesgo, no en predecir.

## Cómo Identificar tus Sesgos

### 1. Usa el Journaling

Registra tus pensamientos y emociones. Con el tiempo, verás patrones de sesgos.

### 2. Revisa tus Trades

Analiza tus trades perdedores. ¿Qué pensabas antes de entrar? ¿Qué sesgo te llevó a esa decisión?

### 3. Busca Feedback Objetivo

Pide a otros que revisen tus decisiones. Los demás ven tus sesgos más fácilmente que tú.

## Cómo Combatir los Sesgos

### 1. Ten un Plan Escrito

Un plan escrito te protege de decisiones emocionales basadas en sesgos.

### 2. Usa Checklists

Un checklist te fuerza a considerar todos los factores, no solo los que confirman tu sesgo.

### 3. Practica la Humildad

Acepta que puedes estar equivocado. El mercado siempre tiene la razón.

### 4. Revisa Regularmente

Revisa tus decisiones regularmente. Identifica patrones de sesgos y trabaja en ellos.

## Conclusión

Los sesgos cognitivos son parte de la naturaleza humana. No puedes eliminarlos completamente, pero puedes reconocerlos y minimizar su impacto. El mejor trader no es el que no tiene sesgos, sino el que los reconoce y los controla.
""",
        "tags": ["sesgos", "psicología", "cognición", "decisiones"],
        "trigger_conditions": None,
        "priority": 8,
        "micro_habits": [
            "Registra en tu journal qué pensabas antes de cada trade",
            "Revisa tus trades perdedores y busca qué sesgo te llevó a esa decisión",
            "Pregunta a otros traders sobre tus decisiones para obtener perspectiva objetiva",
        ],
        "is_critical": False,
        "download_url": "/api/v1/knowledge/articles/sesgos-cognitivos-trading/pdf",
    },
    {
        "title": "Mindfulness y Trading: La Mente Clara Gana",
        "slug": "mindfulness-trading-mente-clara",
        "category": "emotional_management",
        "summary": "El mindfulness puede mejorar significativamente tu trading al aumentar tu autocontrol y reducir las decisiones emocionales.",
        "content": """# Mindfulness y Trading: La Mente Clara Gana

## ¿Qué es el Mindfulness?

El mindfulness es la práctica de estar presente y consciente del momento actual, sin juzgar. En trading, esto significa operar con una mente clara y enfocada.

## Por Qué el Mindfulness Ayuda en Trading

### 1. Reduce el Estrés

El trading es estresante. El mindfulness te ayuda a manejar el estrés sin que afecte tus decisiones.

### 2. Aumenta el Autocontrol

Te ayuda a reconocer emociones sin reaccionar a ellas. Puedes sentir miedo sin operar por miedo.

### 3. Mejora la Concentración

Una mente clara se concentra mejor. Puedes analizar el mercado sin distracciones.

### 4. Reduce la Reactividad

Te ayuda a pausar antes de actuar. En lugar de reaccionar emocionalmente, respondes racionalmente.

## Cómo Practicar Mindfulness en Trading

### 1. Meditación Diaria

Dedica 10-15 minutos cada día a meditar. Esto entrena tu mente para estar presente.

### 2. Respiración Consciente

Antes de cada trade, respira profundamente 3 veces. Esto te centra y reduce la ansiedad.

### 3. Observa tus Emociones

Cuando sientas emociones fuertes (miedo, codicia, ansiedad), obsérvalas sin juzgar. No las reprimas, pero no actúes por ellas.

### 4. Practica la Aceptación

Acepta que el mercado es impredecible. Acepta las pérdidas como parte del proceso. La resistencia causa sufrimiento.

### 5. Mantén la Atención Plena Durante el Trading

Mientras operas, mantén tu atención en el presente. No pienses en trades pasados o futuros. Solo el trade actual.

## Ejercicios Prácticos

### Ejercicio 1: Respiración Pre-Trade

Antes de cada trade:
1. Cierra los ojos
2. Respira profundamente 3 veces
3. Observa cómo te sientes
4. Abre los ojos y procede con tu análisis

### Ejercicio 2: Observación de Emociones

Cuando sientas una emoción fuerte:
1. Identifica la emoción: "Estoy sintiendo miedo"
2. Observa dónde la sientes en tu cuerpo
3. Respira y deja que pase
4. Decide racionalmente, no emocionalmente

### Ejercicio 3: Meditación Post-Trade

Después de cada trade:
1. Siéntate cómodamente
2. Respira profundamente
3. Observa tus pensamientos sobre el trade
4. Déjalos pasar sin aferrarte a ellos

## Durante los Cooldowns

Los cooldowns son perfectos para practicar mindfulness:
- Medita durante el cooldown
- Reflexiona sobre tus emociones
- Practica la aceptación de la situación
- Regresa con una mente más clara

## Conclusión

El mindfulness no es una técnica mágica, pero puede mejorar significativamente tu trading. Una mente clara toma mejores decisiones. Practica regularmente y verás la diferencia.
""",
        "tags": ["mindfulness", "meditación", "autocontrol", "concentración"],
        "trigger_conditions": {"trigger": "cooldown"},
        "priority": 7,
        "micro_habits": [
            "Medita 10 minutos cada mañana antes de operar",
            "Antes de cada trade, respira profundamente 3 veces",
            "Durante un cooldown, practica meditación en lugar de obsesionarte con el mercado",
        ],
        "is_critical": False,
        "download_url": "/api/v1/knowledge/articles/mindfulness-trading-mente-clara/pdf",
    },
    {
        "title": "Construyendo Resiliencia Mental en Trading",
        "slug": "resiliencia-mental-trading",
        "category": "emotional_management",
        "summary": "La resiliencia mental es la capacidad de recuperarte de las adversidades. En trading, es esencial para el éxito a largo plazo.",
        "content": """# Construyendo Resiliencia Mental en Trading

## ¿Qué es la Resiliencia Mental?

La resiliencia mental es la capacidad de adaptarte y recuperarte de las adversidades. En trading, significa poder manejar pérdidas, drawdowns y rachas perdedoras sin perder la confianza ni la disciplina.

## Por Qué es Importante

### 1. El Trading es Difícil

Vas a perder. Vas a tener drawdowns. Vas a tener rachas perdedoras. La resiliencia te ayuda a superarlas.

### 2. Previene el Burnout

Sin resiliencia, las pérdidas te agotan emocionalmente. Con resiliencia, las manejas y sigues adelante.

### 3. Mantiene la Disciplina

La resiliencia te ayuda a mantener la disciplina incluso cuando las cosas van mal.

## Cómo Construir Resiliencia

### 1. Acepta las Pérdidas

Las pérdidas son parte del trading. Aceptarlas te ayuda a manejarlas mejor.

### 2. Enfócate en el Proceso

No te obsesiones con los resultados. Enfócate en seguir tu plan. Los resultados vendrán.

### 3. Mantén la Perspectiva

Una pérdida no define tu carrera. Un drawdown no es permanente. Mantén la perspectiva a largo plazo.

### 4. Aprende de las Adversidades

Cada pérdida es una oportunidad de aprendizaje. Analiza qué salió mal y cómo mejorar.

### 5. Construye un Sistema de Apoyo

Habla con otros traders. Comparte tus experiencias. No estás solo en esto.

### 6. Cuida tu Salud Mental

El trading es mentalmente agotador. Duerme bien, come bien, haz ejercicio. Tu mente necesita estar saludable.

## Estrategias Prácticas

### 1. Después de una Pérdida

- Respira profundamente
- Acepta la pérdida
- Analiza qué salió mal (si algo salió mal)
- Sigue tu plan

### 2. Durante un Drawdown

- Mantén la perspectiva
- Revisa tu estrategia (con calma)
- Considera reducir tamaño temporalmente
- No cambies todo de golpe

### 3. Después de una Racha Perdedora

- Usa el cooldown para descansar
- Revisa tus trades
- Verifica que seguiste tu plan
- Regresa con una mentalidad renovada

## El Poder de la Mentalidad de Crecimiento

### Mentalidad Fija vs. Mentalidad de Crecimiento

**Mentalidad Fija**: "Soy mal trader" después de pérdidas.

**Mentalidad de Crecimiento**: "Puedo mejorar" después de pérdidas.

La mentalidad de crecimiento te ayuda a ver las adversidades como oportunidades de aprendizaje, no como fracasos.

## Construyendo Hábitos Resilientes

### 1. Journaling Regular

Registra tus pensamientos y emociones. Esto te ayuda a procesar las adversidades.

### 2. Revisión Periódica

Revisa tus trades regularmente. Aprende de ellos, no te obsesiones con ellos.

### 3. Práctica de Gratitud

Agradece las lecciones aprendidas, incluso de las pérdidas. Esto cambia tu perspectiva.

### 4. Establece Límites

Los límites de riesgo te protegen. Respétalos. Son tu red de seguridad.

## Conclusión

La resiliencia mental no se construye de la noche a la mañana. Se desarrolla con la práctica constante. Cada pérdida que manejas bien, cada drawdown que superas, cada racha perdedora de la que te recuperas, te hace más resiliente. El mejor trader no es el que nunca pierde, sino el que se recupera de las pérdidas y sigue adelante.
""",
        "tags": ["resiliencia", "mentalidad", "recuperación", "psicología"],
        "trigger_conditions": {"trigger": "drawdown", "threshold": 10},
        "priority": 8,
        "micro_habits": [
            "Después de cada pérdida, escribe en tu journal: '¿Qué aprendí de esto?'",
            "Practica la gratitud: agradece las lecciones aprendidas, incluso de las pérdidas",
            "Mantén la perspectiva: recuerda que un drawdown no es permanente",
        ],
        "is_critical": False,
        "download_url": "/api/v1/knowledge/articles/resiliencia-mental-trading/pdf",
    },
]


def seed_knowledge_base():
    """Seed knowledge base with initial articles."""
    db = SessionLocal()
    try:
        existing_slugs = {a.slug for a in db.query(KnowledgeArticleORM).all()}
        
        for article_data in ARTICLES:
            slug = article_data["slug"]
            if slug in existing_slugs:
                # Update existing article with new fields if they're missing
                existing = db.query(KnowledgeArticleORM).filter(KnowledgeArticleORM.slug == slug).first()
                if existing:
                    # Update fields that might be missing
                    if "micro_habits" in article_data and not existing.micro_habits:
                        existing.micro_habits = article_data.get("micro_habits")
                    if "download_url" in article_data and not existing.download_url:
                        existing.download_url = article_data.get("download_url")
                    if "pdf_path" in article_data and not existing.pdf_path:
                        existing.pdf_path = article_data.get("pdf_path")
                    elif "download_url" in article_data and existing.download_url and not existing.pdf_path:
                        # Set pdf_path from slug if download_url exists but pdf_path doesn't
                        existing.pdf_path = f"education/{existing.slug}.pdf"
                    if "is_critical" in article_data:
                        existing.is_critical = article_data.get("is_critical", False)
                    logger.info(f"Updated article: {article_data['title']}")
                else:
                    logger.info(f"Article {slug} already exists, skipping")
                continue
            
            # Set default values for optional fields
            article_data.setdefault("micro_habits", None)
            article_data.setdefault("download_url", None)
            article_data.setdefault("is_critical", False)
            article_data.setdefault("pdf_path", None)
            
            # Set pdf_path if download_url is provided but pdf_path is not
            if article_data.get("download_url") and not article_data.get("pdf_path"):
                slug = article_data.get("slug", "")
                article_data["pdf_path"] = f"education/{slug}.pdf"
            
            article = KnowledgeArticleORM(**article_data)
            db.add(article)
            logger.info(f"Added article: {article_data['title']}")
        
        db.commit()
        logger.info(f"Knowledge base seeded successfully with {len(ARTICLES)} articles")
    except Exception as e:
        db.rollback()
        logger.error(f"Error seeding knowledge base: {e}", exc_info=True)
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_knowledge_base()





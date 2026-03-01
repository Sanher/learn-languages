# learn-languages

Implementación inicial de una actividad de juego de **pronunciación guiada** con arquitectura por servicios (a nivel de código de dominio).

## Qué incluye

- Servicios de juego separados por tipo (`language_games/services`).
- Actividades por idioma dentro de cada servicio (ej. japonés vs inglés).
 - Incluye `shadowing_score` reusable, con implementación de constantes/métodos para japonés.
 - Incluye `pronunciation_match` reusable (audio + intento del usuario + validación de match), con implementación inicial para japonés.
 - Incluye `kanji_match` reusable para idiomas no occidentales, con implementación inicial para japonés.
 - Incluye `script_speed_round` reusable por sistema de escritura y alias `kana_speed_round` para japonés.
 - Incluye `grammar_particle_fix` reusable, con implementación inicial para particulas japonesas.
 - Incluye `sentence_order` reusable: para idiomas orientales devuelve linea script + romanizado y muestra traduccion literal tras enviar (con estado de reintento que la oculta).
 - Incluye `listening_gap_fill` reusable con ayudas progresivas por nivel (opciones+romanizado al inicio; luego menos ayudas), traduccion mostrada tras envio y estado de reintento.
 - Incluye `context_quiz` reusable como señal diagnostica de nivel; el planificador reduce su frecuencia cuando mejora la racha/precision.
 - Todos los juegos de escritura aplican asistencia progresiva por nivel (romanizado/traduccion al inicio; menos ayuda al avanzar) y exponen `retry_state` para reintento ocultando traducciones.
 - Juegos de audio (`pronunciation_match`, `shadowing_score`) muestran alerta de consumo STT/TTS a partir del 3er reintento.
- Política por idioma configurable por día de semana:
  - lunes a viernes `ja` (default)
  - fin de semana `en` (default)
- Notificaciones configurables por idioma, día y hora.
- Pipeline de actividad de pronunciación:
  - entrada esperada y reconocida,
  - métricas de confianza, ritmo, pausas y estabilidad de pitch,
  - feedback por palabra,
  - siguiente paso sugerido.

## Archivos clave

- `language_games/policy.py`
- `language_games/scheduling.py`
- `language_games/services/`
- `language_games/orchestrator.py`
- `language_games/pronunciation.py`
- `demo_pronunciation_activity.py`
- `tests/test_pronunciation.py`

## Ejecutar demo

```bash
python demo_pronunciation_activity.py
```

## Dependencias

```bash
pip install -r requirements.txt
```

## Frontend común básico (web)

- Ruta: `/web/`
- Carga estado + juego único diario desde `/api/games/daily`
- Evalúa y reintenta juegos por `/api/games/evaluate`
- Cambio persistente de idioma por `/api/ui/language`
- Selector de traducción secundaria en topbar (`Off | Español`) por `/api/ui/secondary-translation`
- Las líneas de traducción usan bundles `*_translations` (EN base + ES secundaria cuando esté activa)

## Ejecutar tests

```bash
pytest
```

## Ejemplo rápido de configuración semanal y notificaciones

```python
from datetime import datetime

from language_games import (
    GameActivity,
    GameServiceRegistry,
    GamesOrchestrator,
    InMemoryGameService,
    LanguageScheduleConfig,
    NotificationRule,
)

config = LanguageScheduleConfig(
    default_language="ja",
    language_by_weekday={0: "ja", 1: "ja", 2: "ja", 3: "ja", 4: "ja", 5: "en", 6: "en"},
    notifications_by_language={
        "ja": [NotificationRule(weekday=0, hour=8, minute=0)],
        "en": [NotificationRule(weekday=6, hour=19, minute=30)],
    },
)

registry = GameServiceRegistry()
registry.register(
    InMemoryGameService(
        game_type="vocab_match",
        activities_by_language={
            "ja": [GameActivity("ja-1", "ja", "vocab_match", "Relaciona hiragana y lectura")],
            "en": [GameActivity("en-1", "en", "vocab_match", "Match words and definitions")],
        },
    )
)

orchestrator = GamesOrchestrator(registry=registry, schedule_config=config)
today = orchestrator.daily_games(datetime.now(), game_types=["vocab_match"])
```


## Documento de arquitectura

- `ESTRUCTURA_GENERAL.md`: visión general de servicios, flujo de análisis de audio y plan de implementación por fases.


## Operativa Git

- `GIT_REMOTE_SETUP.md`: pasos para configurar remoto (`origin`) y trabajar con `pull/push` también desde Codex web.

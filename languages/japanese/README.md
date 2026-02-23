# Japanese Learning Add-on (server integrated)

Módulo inicial para un add-on/app de aprendizaje de japonés orientado a sesiones diarias dentro de servidor.

## Objetivos cubiertos

- **7-8 minijuegos** disponibles, con selección diaria de **4 o 5** sin repetir hasta agotar la rotación.
- Generación/adaptación de ejercicios con **OpenAI API** usando memoria de progreso.
- Integración con **ElevenLabs** para audio japonés y evaluación asistida de pronunciación.
- Interfaz web embebible (por ejemplo, panel iframe en servidor).
- Arquitectura preparada para añadir más idiomas en carpetas hermanas (`languages/<idioma>`).

## Estructura

```text
languages/
  japanese/
    app/
      api.py                 # FastAPI + rutas
      game_engine.py         # Lógica de selección de juegos y dificultad
      memory.py              # Persistencia de progreso (SQLite)
      services/
        openai_client.py
        elevenlabs_client.py
    web/
      index.html             # UI diaria
      app.js
      styles.css
    tests/
      test_game_engine.py
```

## Idea pedagógica (anti-aburrimiento)

1. **Interleaving**: mezcla vocabulario, gramática, escucha y speaking.
2. **Rotación fuerte**: nunca repetir juego dos días seguidos (salvo pool agotado).
3. **Micro-progresión**: subir dificultad cuando acierto > 80% sostenido.
4. **Objetivo diario corto**: 12-20 min para facilitar consistencia.
5. **Eventos sorpresa**: bonus game opcional 1-2 veces por semana.
6. **Errores recurrentes**: reinsertar solo los ítems fallados 48h después.
7. **Feedback emocional**: mensajes positivos y comparativa “yo de hace 7 días”.

## Juegos incluidos (pool inicial)

1. `kanji_match` – Emparejar kanji con significado (servicio reusable para idiomas no occidentales).
2. `kana_speed_round` – Lectura rápida hiragana/katakana (alias de servicio genérico `script_speed_round`).
3. `grammar_particle_fix` – Completar partículas correctas (servicio reusable con contenido inicial ja).
4. `sentence_order` – Ordenar palabras en una frase natural (linea kanji + romanizado, traduccion literal tras enviar y ocultable en reintento).
5. `listening_gap_fill` – Escucha + huecos con apoyo progresivo (opciones/romanizado al inicio), traduccion tras envio y reintento sin traduccion.
6. `pronunciation_match` – Escuchar audio, repetir y validar match de pronunciación.
7. `shadowing_score` – Repetición de audio con scoring.
8. `context_quiz` – Elegir expresión adecuada según situación (modo diagnostico, con menor frecuencia cuando sube el progreso).

Notas de progresion:
- En juegos de escritura, las ayudas (romanizado/traduccion guia) se reducen con el progreso y el reintento oculta traducciones.
- En juegos de audio, desde el 3er reintento se devuelve aviso de mayor consumo STT/TTS.
- `kana_speed_round` usa TTS (ElevenLabs) para reproducir la secuencia y evalúa por transcript reconocido + ritmo.

## Variables de entorno sugeridas

- `OPENAI_API_KEY`
- `OPENAI_MODEL` (default: `gpt-4o-mini`)
- `ELEVENLABS_API_KEY`
- `ELEVENLABS_VOICE_ID`
- `ELEVENLABS_MODEL_ID` (default: `eleven_multilingual_v2`)

Also supported in Home Assistant add-on options (`/data/options.json`) when env vars are not exported.

Persistencia de progreso:
- El progreso del usuario se guarda de forma persistente entre reinicios.

## Observabilidad (logs con hora para HA)

- La API (`languages/japanese/app/api.py`) emite logs con timestamp (`YYYY-MM-DD HH:MM:SS`).
- Se registran entradas/salidas de todas las rutas `/api/*` con latencia y código HTTP.
- También se registran eventos clave:
  - carga de juegos diarios,
  - cambio de idioma,
  - cierre de sesión,
  - inicio/fin/error en evaluaciones de juego.

## Ejecución local de referencia

```bash
pip install -r requirements.txt
uvicorn languages.japanese.app.api:app --reload --port 8107
```

Luego abrir `http://localhost:8107/web/`.

API de frontend común:
- `POST /api/games/daily` -> estado UI + un único juego aleatorio del día (no lista completa).
- `POST /api/games/evaluate` -> evaluación por tipo de juego + estado de reintento.
- `POST /api/ui/language` -> cambia idioma de forma permanente (guarda nivel por idioma).
- `POST /api/audio/tts` -> genera audio TTS (data URL) para juegos de lectura/pronunciación.
- `POST /api/audio/stt` -> transcribe audio del usuario (multipart) para juegos de lectura/pronunciación.

Comportamiento HA del frontend:
- No muestra usuario ni notas.
- Barra superior fija:
  - Izquierda: idioma actual + `Change` (persistente).
  - Derecha: nivel actual + `Cambiar nivel para hoy` (solo override del día).
- Solo se muestra un juego en pantalla (aleatorio entre los disponibles).
- Los juegos muestran alias en castellano.
- En `sentence_order` se usa drag-and-drop con banco de fragmentos y zona de orden final.
- Panel lateral derecho con la lista de todos los juegos disponibles para pruebas (`all_games`).
- En `context_quiz` se usan radio buttons (sin mostrar solución en el enunciado), con romaji entre paréntesis en opciones japonesas.
- Barra superior con `Score de hoy` (promedio de evaluaciones de la sesión).

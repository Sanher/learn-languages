# Japanese Learning Add-on (Home Assistant integrated)

Módulo inicial para un add-on/app de aprendizaje de japonés orientado a sesiones diarias dentro de Home Assistant.

## Objetivos cubiertos

- **6-7 minijuegos** disponibles, con selección diaria de **3 o 4** sin repetir hasta agotar la rotación.
- Generación/adaptación de ejercicios con **OpenAI API** usando memoria de progreso.
- Integración con **ElevenLabs** para audio japonés y evaluación asistida de pronunciación.
- Interfaz web embebible (por ejemplo, panel iframe en Home Assistant).
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

1. `kanji_match` – Emparejar kanji con significado.
2. `kana_speed_round` – Lectura rápida hiragana/katakana.
3. `grammar_particle_fix` – Completar partículas correctas.
4. `sentence_order` – Ordenar palabras en una frase natural.
5. `listening_gap_fill` – Escucha + huecos.
6. `shadowing_score` – Repetición de audio con scoring.
7. `context_quiz` – Elegir expresión adecuada según situación.

## Variables de entorno sugeridas

- `OPENAI_API_KEY`
- `OPENAI_MODEL` (default: `gpt-4o-mini`)
- `ELEVENLABS_API_KEY`
- `ELEVENLABS_VOICE_ID`
- `JAPANESE_DB_PATH` (default: `languages/japanese/data/progress.db`)

## Ejecución local de referencia

```bash
pip install fastapi uvicorn httpx
uvicorn languages.japanese.app.api:app --reload --port 8099
```

Luego abrir `http://localhost:8099/web/`.

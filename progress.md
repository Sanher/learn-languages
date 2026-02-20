Original prompt: puedes añadir un cuadro de respuesta para todos los juegos, como el de quiza de contexto, en corregir de particula ira donde el selector y sus opciones, en lectura rapida kana faltan saltos de linea y deberia ir en el transcript reconocido, en emparejar kanji alrededor de todas las opciones, en completar huecos quita la frase con huecos y ponlo alrededor de kanji arrastra aqui kanji, en pronunciacion guiada alrededor de transcript reconocido, en ordenar frase alrededor de fragmentos y zona de orden final, shadowing con puntuacion alrededor de texto pronunciado.

## 2026-02-16
- Updated web renderers in `languages/japanese/web/app.js` to wrap answer areas with a shared fieldset style (`response-group`) across all requested games.
- Adjusted `kana_speed_round` prompt rendering to preserve line separation and moved recognized transcript input inside the response box.
- Updated `listening_gap_fill` to remove the "Frase con huecos" label and wrap the kanji drag/drop sentence line with a "Kanji arrastra aqui" response box.
- Added shared response-box styling in `languages/japanese/web/styles.css`.
- Validation:
  - `node --check languages/japanese/web/app.js`
  - `python3 -m unittest discover -s tests`

## TODO
- Run a visual check in browser for each game card to confirm spacing/legend text is exactly as desired.

## 2026-02-16 (ajuste de legends)
- Unified all answer fieldset legends to the exact text `Respuesta`.
- Moved game-specific captions inside the fieldset as labels to keep a consistent legend style.
- Tuned response box border/padding for a lighter line feel.

## 2026-02-16 (kana elapsed state)
- Replaced `Tiempo (segundos)` input in `kana_speed_round` with a live display variable.
- Initial value now renders as approximate (`~3.0 (aprox.)`), then switches to exact while recording/stopped.
- Payload still sends `elapsed_seconds` to backend, now sourced from internal UI state.

## 2026-02-16 (kanji drag/drop + significado por nivel)
- Added drag-and-drop in `kanji_match`: learner drags romaji tokens into one drop slot per kanji.
- Added live reveal of approximate Spanish meaning when the romaji is matched to the correct kanji.
- Added advanced/intermediate meaning input (`level >= 2`) with quality evaluation statuses:
  - `incorrecto`
  - `casi_correcto`
  - `correcto`
- Extended backend kanji evaluation to score reading accuracy and meaning quality, preserving legacy payload compatibility.
- Added frontend visual feedback for kanji row correctness and per-symbol meaning status.
- Added extra top padding above `Tiempo (segundos)` in kana speed round.

## 2026-02-16 (pronunciacion guiada: romaji + microfono)
- Extended `pronunciation_match` content model with romaji and approximate literal translation for each Japanese phrase.
- Added level-aware view behavior:
  - level 1-2: show romaji line.
  - level 3: hide romaji line.
- Added translation in evaluation response (`literal_translation`) so UI can show it after completing an attempt.
- Added microphone recording controls for `pronunciation_match` (record/stop + STT transcription into transcript input).
- Added service and UI tests for romaji visibility and translation behavior.

## 2026-02-16 (shadowing: romaji + microfono)
- Added level-aware romanized line for `shadowing_score`:
  - level 1-2: show romaji.
  - level 3: hide romaji.
- Added microphone recording controls for `shadowing_score` (record/stop + STT transcription into `learner_text`).
- Updated UI payload/API wiring so frontend receives `show_romanized_line` and `romanized_line` for shadowing.

## 2026-02-16 (shadowing retirado del flujo activo)
- Removed `shadowing_score` from active daily game pool (`game_engine.GAME_POOL`).
- Removed `ShadowingScoreService` registration in Japanese API startup, so it no longer appears in daily selection or right-side game list.
- Removed shadowing-specific payload/evaluation branches from API to avoid stale references.

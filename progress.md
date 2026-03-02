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

## 2026-03-02 (lesson/game flow UX + secondary ES fallback)
- Updated `languages/japanese/web/app.js` with a guided flow:
  - Added collapsible lesson panel (`Expand lesson` / `Collapse lesson`).
  - Added `Review lesson` action after lesson completion.
  - Auto-collapses lesson after `Complete lesson and start games`.
  - Added daily game block collapse after finishing the 3 required daily games.
  - Added `Review daily games` action from collapsed daily block.
  - Added summary panel after daily completion with score, persistence confirmation, and extra-games hint.
- Updated `listening_gap_fill` UX in `languages/japanese/web/app.js`:
  - On evaluation, correct selected gap options now highlight in green (`gap-correct`).
  - Incorrect selected options highlight in amber (`gap-wrong`).
- Updated styles in `languages/japanese/web/styles.css`:
  - New reusable collapsed/summary panel styles.
  - Visual feedback classes for listening gap dropzones.
- Updated backend translation behavior in `languages/japanese/app/api.py`:
  - Added deterministic Spanish fallback translations for key lesson/game strings and prompt prefixes.
  - Added fallback path when OpenAI translation is unavailable (`no_api_key` or provider failure), with HA-friendly logs:
    - `translation_fallback_used ... reason=no_api_key`
    - `translation_fallback_used ... reason=openai_empty_or_failed`
- Validation executed:
  - `node --check languages/japanese/web/app.js`
  - `python3 -m py_compile languages/japanese/app/api.py`
  - `python3 -m unittest tests.test_sentence_order_service tests.test_listening_gap_fill_service tests.test_mora_romanization_service tests.test_grammar_particle_fix_service tests.test_context_quiz_service tests.test_kanji_match_service tests.test_pronunciation_match_service`
- Validation limitation in this local shell:
  - API-level test modules that import FastAPI app fail here due missing `python-multipart` package.

## 2026-03-02 (secondary translation availability message)
- Removed deterministic local fallback for secondary Spanish translations in `languages/japanese/app/api.py`; secondary lines now depend on OpenAI translation responses again.
- Extended `translation_preferences` payload with `secondary_translation_provider_available` to expose provider readiness to UI.
- Added UI message under secondary translation selector:
  - `"<Language> is not available right now."` when secondary translation is selected but unavailable.
- Added payload inspection in `languages/japanese/web/app.js` to detect missing secondary lines in responses and show/hide the warning status.
- Added topbar status element in `languages/japanese/web/index.html` and warning style in `languages/japanese/web/styles.css`.
- Added API contract assertions in `tests/test_api_english_contract.py` for `secondary_translation_provider_available`.

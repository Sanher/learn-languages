const currentLanguageEl = document.getElementById('current-language');
const currentLevelEl = document.getElementById('current-level');
const todayScoreEl = document.getElementById('today-score');
const gameZoneEl = document.getElementById('game-zone');
const gamesSidebarEl = document.getElementById('games-sidebar');
const changeLanguageBtn = document.getElementById('change-language-btn');
const changeLevelBtn = document.getElementById('change-level-btn');
const LANGUAGE_ALIASES = {
  ja: 'Japanese',
};

let availableLanguages = ['ja'];
let currentLanguage = 'ja';
let currentLevel = 1;
let todayLevel = 1;
let todayLevelOverride = null;
let selectedGame = null;
let availableGameCards = [];
let todayScoreTotal = 0;
let todayScoreCount = 0;
const retryCounters = new Map();
const ttsAudioCache = new Map();
let activeAudio = null;
let activeRecorder = null;
let activeRecorderStream = null;
let recorderChunks = [];
let recordingStartedAtMs = 0;
const KANA_DEFAULT_ELAPSED_SECONDS = 3.0;
let kanaElapsedSeconds = KANA_DEFAULT_ELAPSED_SECONDS;
let kanaElapsedApproximate = true;
let kanaElapsedTicker = null;
const PRONUNCIATION_DEFAULT_AUDIO_SECONDS = 2.0;
let pronunciationElapsedSeconds = PRONUNCIATION_DEFAULT_AUDIO_SECONDS;
const SHADOWING_DEFAULT_AUDIO_SECONDS = 2.0;
let shadowingElapsedSeconds = SHADOWING_DEFAULT_AUDIO_SECONDS;

function apiUrl(path) {
  const cleanPath = String(path || '').replace(/^\/+/, '');
  const pathname = window.location.pathname || '/';
  const webIdx = pathname.indexOf('/web/');
  let basePrefix = pathname;

  if (webIdx >= 0) {
    basePrefix = `${pathname.slice(0, webIdx)}/`;
  } else if (pathname.endsWith('/')) {
    basePrefix = pathname;
  } else {
    const lastSlash = pathname.lastIndexOf('/');
    basePrefix = lastSlash >= 0 ? pathname.slice(0, lastSlash + 1) : '/';
  }

  const normalizedBase = basePrefix.endsWith('/') ? basePrefix : `${basePrefix}/`;
  return `${normalizedBase}${cleanPath}`;
}

function escapeHtml(value) {
  return String(value || '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function languageLabel(code) {
  return LANGUAGE_ALIASES[String(code || '').toLowerCase()] || code;
}

function resolveLanguageCode(input) {
  const normalized = String(input || '').trim().toLowerCase();
  if (!normalized) return '';
  if (availableLanguages.includes(normalized)) return normalized;
  const aliasMatch = Object.entries(LANGUAGE_ALIASES).find((entry) => entry[1].toLowerCase() === normalized);
  return aliasMatch ? aliasMatch[0] : normalized;
}

function updateTopbar() {
  currentLanguageEl.textContent = languageLabel(currentLanguage);
  currentLevelEl.textContent = String(todayLevel);
  if (changeLanguageBtn) {
    changeLanguageBtn.hidden = availableLanguages.length <= 1;
  }
  const score = todayScoreCount > 0 ? Math.round(todayScoreTotal / todayScoreCount) : 0;
  if (todayScoreEl) {
    todayScoreEl.textContent = `Today's score: ${score}`;
  }
}

function stopKanaElapsedTicker() {
  if (kanaElapsedTicker) {
    window.clearInterval(kanaElapsedTicker);
    kanaElapsedTicker = null;
  }
}

function formatKanaElapsed(seconds, approximate) {
  const normalized = Number.isFinite(seconds) ? Math.max(0.1, seconds) : KANA_DEFAULT_ELAPSED_SECONDS;
  const text = normalized.toFixed(1);
  return approximate ? `~${text} (approx.)` : `${text}`;
}

function setKanaElapsed(seconds, approximate) {
  kanaElapsedSeconds = Number.isFinite(seconds) ? Math.max(0.1, seconds) : KANA_DEFAULT_ELAPSED_SECONDS;
  kanaElapsedApproximate = Boolean(approximate);
  const valueEl = document.getElementById('kana-elapsed-value');
  if (valueEl) {
    valueEl.textContent = formatKanaElapsed(kanaElapsedSeconds, kanaElapsedApproximate);
  }
}

function startKanaElapsedTicker() {
  stopKanaElapsedTicker();
  kanaElapsedTicker = window.setInterval(() => {
    if (!recordingStartedAtMs) return;
    const liveSeconds = Math.max(0.1, (Date.now() - recordingStartedAtMs) / 1000);
    setKanaElapsed(liveSeconds, false);
  }, 100);
}

function renderSingleGame(game) {
  if (!game) {
    gameZoneEl.classList.remove('hidden');
    gameZoneEl.innerHTML = '<p class="muted">No game available for today.</p>';
    return;
  }

  const payload = game.payload || {};
  const gameType = game.game_type;
  const displayName = game.display_name || gameType;
  let promptHtml = `<p class="prompt">${escapeHtml(game.prompt || '')}</p>`;
  if (gameType !== 'kana_speed_round') {
    stopKanaElapsedTicker();
  }

  let controls = '';
  if (gameType === 'grammar_particle_fix') {
    const enriched = payload.options_enriched || [];
    const options = (enriched.length > 0 ? enriched : (payload.options || []).map((opt) => ({ particle: opt, label: opt })))
      .map((opt) => `<option value="${escapeHtml(opt.particle)}">${escapeHtml(opt.label || opt.particle)}</option>`)
      .join('');
    const promptLines = String(game.prompt || '')
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean)
      .filter((line) => !/^Options:/i.test(line));
    promptHtml = `
      <div class="prompt game-meta">
        ${promptLines.map((line) => `<p class="game-meta-line">${escapeHtml(line)}</p>`).join('')}
      </div>
    `;
    controls = `
      <fieldset class="response-group">
        <legend>Answer</legend>
        <div class="inline-select-field">
          <label for="grammar-particle-select">Particle options:</label>
          <select id="grammar-particle-select" data-k="selected_particle">${options}</select>
        </div>
      </fieldset>
    `;
  } else if (gameType === 'context_quiz') {
    const options = (payload.options || [])
      .map((opt, idx) => {
        const checked = idx === 0 ? 'checked' : '';
        const romaji = opt.romaji ? ` (${escapeHtml(opt.romaji)})` : '';
        return `
          <label class="radio-option">
            <input type="radio" name="context-option" value="${escapeHtml(opt.id)}" ${checked} />
            <span>${escapeHtml(opt.text)}${romaji}</span>
          </label>
        `;
      })
      .join('');
    controls = `
      <fieldset class="response-group context-group">
        <legend>Answer</legend>
        ${options}
      </fieldset>
    `;
  } else if (gameType === 'sentence_order') {
    const fallbackTokens = extractSentenceOrderTokensFromPrompt(game.prompt || '');
    const sourceTokens = (payload.tokens_scrambled && payload.tokens_scrambled.length > 0)
      ? payload.tokens_scrambled
      : fallbackTokens;
    const orderedTokens = Array.isArray(payload.ordered_tokens) ? payload.ordered_tokens : [];
    const items = sourceTokens.map((token, index) => ({
      id: `frag-${index}`,
      token,
    }));
    const dndItems = items
      .map(
        (item) => `
      <div class="sentence-token dnd-token" draggable="true" data-token-id="${escapeHtml(item.id)}" data-token-text="${escapeHtml(item.token)}">
        ${escapeHtml(item.token)}
      </div>`
      )
      .join('');
    const slotItems = items
      .map(
        (_, index) => `
          <span
            class="sentence-order-slot dnd-zone"
            data-single-slot="true"
            data-slot-index="${index}"
            data-bank-selector="#sentence-sourcezone"
            data-expected-token="${escapeHtml(orderedTokens[index] || '')}"
            data-placeholder="Slot ${index + 1}"
          ></span>
        `
      )
      .join('');

    controls = `
      <fieldset class="response-group">
        <legend>Answer</legend>
        <label>Available fragments</label>
        <div id="sentence-sourcezone" class="sentence-dropzone dnd-zone">${dndItems}</div>
        <label>Final order zone</label>
        <div id="sentence-dropzone" class="sentence-order-target">${slotItems}</div>
      </fieldset>
    `;
  } else if (gameType === 'listening_gap_fill') {
    const tokens = payload.tokens || [];
    const gapPositions = payload.gap_positions || [];
    const gaps = new Set(gapPositions);
    const gapIndexByPosition = new Map(gapPositions.map((position, index) => [position, index]));
    const phraseSlots = tokens
      .map((token, position) => {
        if (!gaps.has(position)) {
          return `<span class="gap-static-token">${escapeHtml(token)}</span>`;
        }
        const gapIndex = Number(gapIndexByPosition.get(position));
        return `<span class="gap-dropzone dnd-zone" data-single-slot="true" data-gap-index="${gapIndex}" data-placeholder="Gap ${gapIndex + 1}"></span>`;
      })
      .join('');
    const options = payload.options || [];
    const optionTokens = options
      .map(
        (option, idx) => `
          <div class="gap-option-token dnd-token" draggable="true" data-token-id="gap-option-${idx}" data-token-text="${escapeHtml(option)}">
            <span class="gap-option-index">${idx + 1}</span>
            <span class="gap-option-text">${escapeHtml(option)}</span>
          </div>
        `
      )
      .join('');
    const fallbackInputs = gapPositions
      .map(
        (pos, idx) => `
          <input data-k="gap_token_${idx}" placeholder="Gap value ${idx + 1}" />
        `
      )
      .join('');
    const promptLines = String(game.prompt || '')
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean)
      .filter((line) => !/^Fill the gaps:/i.test(line))
      .filter((line) => !/^Options:/i.test(line));
    promptHtml = `
      <div class="prompt listening-meta">
        ${promptLines.map((line) => `<p class="listening-line">${escapeHtml(line)}</p>`).join('')}
      </div>
    `;
    controls = `
      <div class="listening-controls">
        <label>Available fragments</label>
        <div id="gap-options-bank" class="sentence-dropzone gap-options-bank dnd-zone" data-placeholder="Available options">
          ${optionTokens}
        </div>
        <fieldset class="response-group">
          <legend>Answer</legend>
          <label>Drag here</label>
          <div class="gap-phrase-line">${phraseSlots}</div>
        </fieldset>
        ${
          options.length === 0
            ? `
              <div class="gap-inputs">
                ${fallbackInputs}
              </div>
            `
            : ""
        }
      </div>
    `;
  } else if (gameType === 'kanji_match') {
    const pairs = payload.pairs || [];
    const requireMeaningInput = Boolean(payload.require_meaning_input || Number(game.level || 1) >= 2);
    const readingBankTokens = seededShuffle(
      pairs.map((pair, index) => ({ pair, index })),
      `${game.activity_id || game.game_type}-kanji-reading-bank`
    )
      .map(
        ({ pair, index }) => `
          <div
            class="kanji-reading-token dnd-token"
            draggable="true"
            data-token-id="kanji-reading-${index}"
            data-token-text="${escapeHtml(pair.reading_romaji || '')}"
            data-reading-symbol="${escapeHtml(pair.symbol)}"
          >
            ${escapeHtml(pair.reading_romaji || '')}
          </div>
        `
      )
      .join('');
    const rows = pairs
      .map((pair) => {
        const meaningInput = requireMeaningInput
          ? `
            <div class="kanji-meaning-answer">
              <input data-k="kanji-meaning:${escapeHtml(pair.symbol)}" placeholder="approximate meaning" />
              <small class="kanji-meaning-status muted" data-meaning-status-for="${escapeHtml(pair.symbol)}"></small>
            </div>
          `
          : "";
        return `
          <div
            class="kanji-match-row ${requireMeaningInput ? 'with-meaning-input' : ''}"
            data-symbol="${escapeHtml(pair.symbol)}"
            data-expected-reading="${escapeHtml(pair.reading_romaji || '')}"
            data-meaning="${escapeHtml(pair.meaning || '')}"
          >
            <span class="kanji-symbol">${escapeHtml(pair.symbol)}</span>
            <span
              class="kanji-reading-dropzone dnd-zone"
              data-single-slot="true"
              data-symbol="${escapeHtml(pair.symbol)}"
              data-bank-selector="#kanji-reading-bank"
              data-placeholder="Drop romaji"
            ></span>
            <span class="kanji-meaning-preview" data-meaning-preview-for="${escapeHtml(pair.symbol)}"></span>
            ${meaningInput}
          </div>
        `;
      })
      .join('');
    controls = `
      <fieldset class="response-group">
        <legend>Answer</legend>
        <div class="kanji-match-controls">
          <label>Available romanized readings</label>
          <div id="kanji-reading-bank" class="sentence-dropzone kanji-reading-bank dnd-zone" data-placeholder="Drag romaji to kanji">
            ${readingBankTokens}
          </div>
          <div class="kanji-match-list">${rows}</div>
        </div>
      </fieldset>
    `;
  } else if (gameType === 'kana_speed_round') {
    const expectedText = payload.expected_text || extractKanaSequenceFromPrompt(game.prompt || '');
    setKanaElapsed(KANA_DEFAULT_ELAPSED_SECONDS, true);
    const promptLines = String(game.prompt || '')
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean);
    promptHtml = `
      <div class="prompt game-meta">
        ${promptLines.map((line) => `<p class="game-meta-line">${escapeHtml(line)}</p>`).join('')}
      </div>
    `;
    controls = `
      <p><strong>Target sequence:</strong> ${escapeHtml(expectedText)}</p>
      <input data-k="expected_text" type="hidden" value="${escapeHtml(expectedText)}" />
      <div class="audio-actions">
        <button id="kana-play-audio-btn" type="button" class="ghost-btn">Play audio (TTS)</button>
        <button id="kana-record-btn" type="button" class="ghost-btn">Record</button>
        <button id="kana-stop-record-btn" type="button" class="ghost-btn" disabled>Stop</button>
      </div>
      <small id="kana-record-status" class="muted kana-status-line">Microphone inactive.</small>
      <fieldset class="response-group">
        <legend>Answer</legend>
        <label>Recognized transcript (STT)</label>
        <input data-k="recognized_text" placeholder="あ い う え お" />
      </fieldset>
      <div class="kana-elapsed-line" aria-live="polite">
        <span class="kana-elapsed-label">Time (seconds)</span>
        <strong id="kana-elapsed-value" class="kana-elapsed-value">${escapeHtml(formatKanaElapsed(kanaElapsedSeconds, kanaElapsedApproximate))}</strong>
      </div>
    `;
  } else if (gameType === 'pronunciation_match') {
    const expectedText = payload.expected_text || game.prompt || '';
    pronunciationElapsedSeconds = PRONUNCIATION_DEFAULT_AUDIO_SECONDS;
    const promptLines = [`Target sentence: ${expectedText}`];
    if (payload.show_romanized_line && payload.romanized_line) {
      promptLines.push(`Romanized: ${payload.romanized_line}`);
    }
    promptHtml = `
      <div class="prompt game-meta">
        ${promptLines.map((line) => `<p class="game-meta-line">${escapeHtml(line)}</p>`).join('')}
      </div>
    `;
    controls = `
      <div class="audio-actions">
        <button id="pronunciation-record-btn" type="button" class="ghost-btn">Record</button>
        <button id="pronunciation-stop-record-btn" type="button" class="ghost-btn" disabled>Stop</button>
      </div>
      <small id="pronunciation-record-status" class="muted kana-status-line">Microphone inactive.</small>
      <fieldset class="response-group">
        <legend>Answer</legend>
        <label>Recognized transcript</label>
        <input data-k="recognized_text" placeholder="recognized text" />
      </fieldset>
    `;
  } else if (gameType === 'shadowing_score') {
    const expectedText = payload.expected_text || game.prompt || '';
    shadowingElapsedSeconds = SHADOWING_DEFAULT_AUDIO_SECONDS;
    const promptLines = [`Target sentence: ${expectedText}`];
    if (payload.show_romanized_line && payload.romanized_line) {
      promptLines.push(`Romanized: ${payload.romanized_line}`);
    }
    promptHtml = `
      <div class="prompt game-meta">
        ${promptLines.map((line) => `<p class="game-meta-line">${escapeHtml(line)}</p>`).join('')}
      </div>
    `;
    controls = `
      <div class="audio-actions">
        <button id="shadowing-record-btn" type="button" class="ghost-btn">Record</button>
        <button id="shadowing-stop-record-btn" type="button" class="ghost-btn" disabled>Stop</button>
      </div>
      <small id="shadowing-record-status" class="muted kana-status-line">Microphone inactive.</small>
      <fieldset class="response-group">
        <legend>Answer</legend>
        <label>Pronounced text (with punctuation)</label>
        <input data-k="learner_text" placeholder="pronounced text" />
      </fieldset>
    `;
  } else {
    controls = '<p class="muted">Game renderer not implemented.</p>';
  }

  const evaluateLabel = (gameType === 'pronunciation_match' || gameType === 'shadowing_score' || gameType === 'kana_speed_round')
    ? 'Evaluate audio'
    : 'Evaluate';

  gameZoneEl.classList.remove('hidden');
  gameZoneEl.innerHTML = `
    <h2>${escapeHtml(displayName)}</h2>
    ${promptHtml}
    ${controls}
    <div class="actions">
      <button id="evaluate-btn">${evaluateLabel}</button>
      <button id="retry-btn" class="ghost-btn">Retry</button>
    </div>
    <div id="game-result" class="result"></div>
  `;
}

function renderSidebar(games) {
  if (!gamesSidebarEl) return;
  const list = (games || [])
    .map((game) => {
      const active = selectedGame && selectedGame.game_type === game.game_type ? 'active-game' : '';
      return `<button class="sidebar-game ${active}" data-action="pick-game" data-game="${escapeHtml(game.game_type)}">${escapeHtml(game.display_name || game.game_type)}</button>`;
    })
    .join('');

  gamesSidebarEl.innerHTML = `
    <h3>Available games</h3>
    <p class="muted">Select one to try it.</p>
    <div class="sidebar-list">${list || '<p class="muted">No games available.</p>'}</div>
  `;
}

function parseTokenList(value, separator) {
  if (!value || !value.trim()) return [];
  if (separator === ',') {
    return value.split(',').map((s) => s.trim()).filter(Boolean);
  }
  return value.split(/\s+/).map((s) => s.trim()).filter(Boolean);
}

function seededShuffle(items, seedText) {
  const clone = [...items];
  let seed = 0;
  const raw = String(seedText || 'seed');
  for (let i = 0; i < raw.length; i += 1) {
    seed = ((seed << 5) - seed) + raw.charCodeAt(i);
    seed |= 0;
  }
  const next = () => {
    seed = (seed * 1664525 + 1013904223) >>> 0;
    return seed / 0x100000000;
  };
  for (let i = clone.length - 1; i > 0; i -= 1) {
    const j = Math.floor(next() * (i + 1));
    [clone[i], clone[j]] = [clone[j], clone[i]];
  }
  return clone;
}

function extractSentenceOrderTokensFromPrompt(prompt) {
  const text = String(prompt || '');
  if (!text) return [];

  const lines = text.split(/\r?\n/);
  const targetLine = lines.find((line) => /Order tokens:/i.test(line));
  if (!targetLine) return [];

  const raw = targetLine.split(':').slice(1).join(':').trim();
  if (!raw) return [];

  return raw
    .split('|')
    .map((token) => token.trim())
    .filter(Boolean);
}

function extractKanaSequenceFromPrompt(prompt) {
  const text = String(prompt || '');
  if (!text) return '';

  const lines = text.split(/\r?\n/);
  const targetLine = lines.find((line) => /^Read fast/i.test(line.trim()));
  if (!targetLine) return text.trim();

  return targetLine.split(':').slice(1).join(':').trim() || text.trim();
}

function collectPayload(game) {
  const payload = { item_id: game.activity_id };
  const fields = gameZoneEl.querySelectorAll('[data-k]');

  fields.forEach((field) => {
    const key = field.getAttribute('data-k');
    if (!key) return;
    if (game.game_type === 'kanji_match' && key.startsWith('kanji-meaning:')) {
      if (!payload.learner_meanings) payload.learner_meanings = {};
      const symbol = key.slice('kanji-meaning:'.length);
      payload.learner_meanings[symbol] = field.value.trim();
      return;
    }
    payload[key] = field.value;
  });

  if (game.game_type === 'kanji_match') {
    const dropzones = Array.from(gameZoneEl.querySelectorAll('.kanji-reading-dropzone[data-symbol]'));
    payload.learner_readings = {};
    dropzones.forEach((dropzone) => {
      const symbol = String(dropzone.dataset.symbol || '').trim();
      if (!symbol) return;
      const token = dropzone.querySelector('.dnd-token');
      payload.learner_readings[symbol] = token ? String(token.dataset.tokenText || token.textContent || '').trim() : '';
    });
    payload.learner_meanings = payload.learner_meanings || {};
    payload.learner_matches = payload.learner_meanings;
  }

  if (game.game_type === 'sentence_order') {
    const slots = Array.from(gameZoneEl.querySelectorAll('.sentence-order-slot[data-slot-index]'))
      .sort((a, b) => Number(a.dataset.slotIndex || 0) - Number(b.dataset.slotIndex || 0));
    const ordered = (slots.length > 0 ? slots : Array.from(gameZoneEl.querySelectorAll('#sentence-dropzone .sentence-token')))
      .map((el) => {
        if (el.classList.contains('sentence-order-slot')) {
          const token = el.querySelector('.sentence-token');
          return token ? (token.dataset.tokenText || '') : '';
        }
        return el.dataset.tokenText || '';
      });
    payload.ordered_tokens_by_user = ordered;
  }
  if (game.game_type === 'context_quiz') {
    const checked = gameZoneEl.querySelector('input[name="context-option"]:checked');
    payload.selected_option_id = checked ? checked.value : '';
  }
  if (game.game_type === 'listening_gap_fill') {
    const dropzones = Array.from(gameZoneEl.querySelectorAll('.gap-dropzone[data-gap-index]'))
      .sort((a, b) => Number(a.dataset.gapIndex || 0) - Number(b.dataset.gapIndex || 0));
    if (dropzones.length > 0) {
      payload.user_gap_tokens = dropzones.map((dropzone) => {
        const token = dropzone.querySelector('.dnd-token');
        return token ? String(token.dataset.tokenText || token.textContent || '').trim() : '';
      });
    } else {
      const gapInputs = Array.from(gameZoneEl.querySelectorAll('[data-k^="gap_token_"]'));
      payload.user_gap_tokens = gapInputs.map((input) => String(input.value || '').trim());
    }
  }
  if (game.game_type === 'kana_speed_round') {
    const expectedText = payload.expected_text || game.payload?.expected_text || extractKanaSequenceFromPrompt(game.prompt || '');
    payload.expected_text = expectedText;
    payload.sequence_expected = parseTokenList(expectedText, ' ');
    payload.recognized_text = String(payload.recognized_text || '').trim();
    payload.sequence_read = parseTokenList(payload.recognized_text, ' ');
    payload.elapsed_seconds = kanaElapsedSeconds;
    payload.audio_duration_seconds = payload.elapsed_seconds;
    payload.speech_seconds = payload.elapsed_seconds;
    payload.pause_seconds = 0.2;
    payload.pitch_track_hz = [150.0, 149.0, 151.0];
  }
  if (game.game_type === 'pronunciation_match') {
    payload.expected_text = game.payload?.expected_text || game.prompt;
    payload.audio_duration_seconds = pronunciationElapsedSeconds;
    payload.speech_seconds = pronunciationElapsedSeconds;
    payload.pause_seconds = 0.2;
    payload.pitch_track_hz = [150.0, 151.0, 149.0];
  }
  if (game.game_type === 'shadowing_score') {
    payload.expected_text = game.payload?.expected_text || game.prompt;
    payload.audio_duration_seconds = shadowingElapsedSeconds;
    payload.pause_seconds = 0.2;
  }

  return payload;
}

function kanjiRowBySymbol(symbol) {
  const rows = Array.from(gameZoneEl.querySelectorAll('.kanji-match-row[data-symbol]'));
  return rows.find((row) => row.dataset.symbol === symbol) || null;
}

function setTokenLocked(token, locked) {
  if (!token) return;
  token.dataset.locked = locked ? 'true' : 'false';
  token.draggable = !locked;
  token.classList.toggle('dnd-token-locked', locked);
}

function setSingleSlotLocked(zone, locked) {
  if (!zone) return;
  zone.dataset.locked = locked ? 'true' : 'false';
  zone.classList.toggle('locked', locked);
}

function syncSentenceOrderLocks() {
  if (!selectedGame || selectedGame.game_type !== 'sentence_order') return;
  const slots = Array.from(gameZoneEl.querySelectorAll('.sentence-order-slot[data-slot-index]'));
  slots.forEach((slot) => {
    const expectedToken = String(slot.dataset.expectedToken || '').trim();
    const token = slot.querySelector('.dnd-token');
    if (!token || !expectedToken) {
      setSingleSlotLocked(slot, false);
      slot.classList.remove('sentence-slot-correct');
      if (token) setTokenLocked(token, false);
      return;
    }
    const tokenText = String(token.dataset.tokenText || token.textContent || '').trim();
    const isCorrect = tokenText === expectedToken;
    setSingleSlotLocked(slot, isCorrect);
    setTokenLocked(token, isCorrect);
    slot.classList.toggle('sentence-slot-correct', isCorrect);
  });
}

function syncKanjiReadingPreview() {
  if (!selectedGame || selectedGame.game_type !== 'kanji_match') return;
  const rows = Array.from(gameZoneEl.querySelectorAll('.kanji-match-row[data-symbol]'));
  rows.forEach((row) => {
    const expectedReading = String(row.dataset.expectedReading || '').trim();
    const meaning = String(row.dataset.meaning || '').trim();
    const token = row.querySelector('.kanji-reading-dropzone .dnd-token');
    const learnerReading = token ? String(token.dataset.tokenText || token.textContent || '').trim() : '';
    const isMatch = learnerReading && learnerReading === expectedReading;
    const preview = row.querySelector('[data-meaning-preview-for]');
    if (preview) {
      preview.textContent = isMatch ? meaning : '';
    }
    const zone = row.querySelector('.kanji-reading-dropzone');
    if (zone) {
      setSingleSlotLocked(zone, Boolean(isMatch));
      zone.classList.toggle('kanji-slot-correct', Boolean(isMatch));
    }
    if (token) {
      setTokenLocked(token, Boolean(isMatch));
    }
    row.classList.toggle('kanji-reading-ok', Boolean(isMatch));
    row.classList.toggle('kanji-reading-miss', Boolean(learnerReading) && !isMatch);
    row.classList.remove('kanji-eval-correct', 'kanji-eval-wrong');
    const statusEl = row.querySelector('[data-meaning-status-for]');
    if (statusEl) {
      statusEl.textContent = '';
      statusEl.classList.remove('status-correct', 'status-almost', 'status-incorrect');
    }
    if (!learnerReading) {
      row.classList.remove('kanji-reading-miss');
    }
  });
}

function applyKanjiEvaluationFeedback(data) {
  if (!selectedGame || selectedGame.game_type !== 'kanji_match') return;
  const readingResults = Array.isArray(data.reading_results) ? data.reading_results : [];
  const meaningResults = Array.isArray(data.meaning_results) ? data.meaning_results : [];

  readingResults.forEach((result) => {
    const symbol = String(result.symbol || '');
    const row = kanjiRowBySymbol(symbol);
    if (!row) return;
    const isCorrect = Boolean(result.is_correct);
    const zone = row.querySelector('.kanji-reading-dropzone');
    const token = row.querySelector('.kanji-reading-dropzone .dnd-token');
    if (zone) {
      setSingleSlotLocked(zone, isCorrect);
      zone.classList.toggle('kanji-slot-correct', isCorrect);
    }
    if (token) {
      setTokenLocked(token, isCorrect);
    }
    row.classList.toggle('kanji-eval-correct', isCorrect);
    row.classList.toggle('kanji-eval-wrong', !isCorrect);
  });

  meaningResults.forEach((result) => {
    const symbol = String(result.symbol || '');
    const status = String(result.status || '');
    const statusEl = gameZoneEl.querySelector(`[data-meaning-status-for="${symbol}"]`);
    if (!statusEl) return;
    statusEl.classList.remove('status-correct', 'status-almost', 'status-incorrect');
    if (status === 'correct') {
      statusEl.textContent = 'Meaning: correct';
      statusEl.classList.add('status-correct');
      return;
    }
    if (status === 'almost_correct') {
      statusEl.textContent = 'Meaning: almost correct';
      statusEl.classList.add('status-almost');
      return;
    }
    statusEl.textContent = 'Meaning: incorrect';
    statusEl.classList.add('status-incorrect');
  });
}

function renderMismatchesHtml(mismatches) {
  if (!Array.isArray(mismatches) || mismatches.length === 0) return '';
  const rows = mismatches
    .map((item) => {
      const position = Number(item.position || 0);
      const expected = String(item.expected || '').trim() || '∅';
      const recognized = String(item.recognized || '').trim() || '∅';
      return `<li>#${position} expected: <strong>${escapeHtml(expected)}</strong> / recognized: <strong>${escapeHtml(recognized)}</strong></li>`;
    })
    .join('');
  return `<div class="result-block"><p><strong>Mismatches</strong></p><ul class="result-list">${rows}</ul></div>`;
}

function renderWordFeedbackHtml(wordFeedback) {
  if (!Array.isArray(wordFeedback) || wordFeedback.length === 0) return '';
  const rows = wordFeedback
    .map((item) => `<li><strong>${escapeHtml(item.word || '')}</strong>: ${escapeHtml(item.issue || '')}. ${escapeHtml(item.hint || '')}</li>`)
    .join('');
  return `<div class="result-block"><p><strong>Word feedback</strong></p><ul class="result-list">${rows}</ul></div>`;
}

function renderEvaluation(data) {
  const resultEl = document.getElementById('game-result');
  if (!resultEl) return;

  const alerts = Array.isArray(data.alerts) ? data.alerts : [];
  const alertsHtml = alerts.map((alert) => `<p class="alert">${escapeHtml(alert)}</p>`).join('');
  const scoreHtml = data.score != null ? `<p><strong>Score:</strong> ${escapeHtml(data.score)}</p>` : '';
  const feedbackHtml = data.feedback ? `<p><strong>Feedback:</strong> ${escapeHtml(data.feedback)}</p>` : '';
  const translationHtml = data.literal_translation
    ? `<p><strong>Literal translation:</strong> ${escapeHtml(data.literal_translation)}</p>`
    : '';
  const readingAccuracyHtml = data.reading_accuracy != null
    ? `<p><strong>Reading:</strong> ${escapeHtml(Math.round(Number(data.reading_accuracy) * 100))}%</p>`
    : '';
  const meaningAccuracyHtml = data.meaning_accuracy != null
    ? `<p><strong>Meaning:</strong> ${escapeHtml(Math.round(Number(data.meaning_accuracy) * 100))}%</p>`
    : '';
  const pronunciationSummaryHtml = (data.is_match != null)
    ? `<p><strong>Match:</strong> ${data.is_match ? 'Yes' : 'No'}${data.match_threshold != null ? ` (target ${Math.round(Number(data.match_threshold) * 100)}%)` : ''}</p>`
    : '';
  const kanaRomanizedHtml = data.expected_romaji || data.recognized_romaji
    ? `
      <div class="result-block">
        <p><strong>Expected (romanized):</strong> ${escapeHtml(data.expected_romaji || '-')}</p>
        <p><strong>Recognized (romanized):</strong> ${escapeHtml(data.recognized_romaji || '-')}</p>
        <p><strong>Expected translation:</strong> ${escapeHtml(data.expected_translation || '-')}</p>
        <p><strong>Recognized translation:</strong> ${escapeHtml(data.recognized_translation || '-')}</p>
      </div>
    `
    : '';
  const mismatchHtml = renderMismatchesHtml(data.sequence_mismatches);
  const wordFeedbackHtml = renderWordFeedbackHtml(data.word_feedback);
  const nextStepHtml = data.next_step ? `<p><strong>Next step:</strong> ${escapeHtml(data.next_step)}</p>` : '';

  resultEl.innerHTML = `
    ${alertsHtml}
    ${scoreHtml}
    ${pronunciationSummaryHtml}
    ${readingAccuracyHtml}
    ${meaningAccuracyHtml}
    ${feedbackHtml}
    ${translationHtml}
    ${kanaRomanizedHtml}
    ${mismatchHtml}
    ${wordFeedbackHtml}
    ${nextStepHtml}
  `;
  applyKanjiEvaluationFeedback(data);
}

async function evaluateSelectedGame(isRetry) {
  if (!selectedGame) return;
  const key = `${selectedGame.game_type}:${selectedGame.activity_id}`;
  const currentRetry = retryCounters.get(key) || 0;
  const nextRetry = isRetry ? currentRetry + 1 : currentRetry;
  retryCounters.set(key, nextRetry);

  const payload = collectPayload(selectedGame);
  const res = await fetch(apiUrl('api/games/evaluate'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      game_type: selectedGame.game_type,
      language: selectedGame.language || currentLanguage,
      level: todayLevel,
      retry_count: nextRetry,
      payload,
    }),
  });
  const data = await res.json();
  if (typeof data.score === 'number') {
    todayScoreTotal += data.score;
    todayScoreCount += 1;
    updateTopbar();
  }
  renderEvaluation(data);
}

async function playKanaAudio(game) {
  if (!game || game.game_type !== 'kana_speed_round') return;
  const text = game.payload?.tts_text || game.payload?.expected_text || extractKanaSequenceFromPrompt(game.prompt || '');
  if (!text) return;

  const cacheKey = `${game.language || currentLanguage}:${text}`;
  let audioDataUrl = ttsAudioCache.get(cacheKey);
  if (!audioDataUrl) {
    const res = await fetch(apiUrl('api/audio/tts'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        text,
        language: game.language || currentLanguage,
      }),
    });
    const data = await res.json();
    if (!res.ok || !data.audio_data_url) {
      const resultEl = document.getElementById('game-result');
      if (resultEl) {
        resultEl.innerHTML = `<p class="alert">${escapeHtml(data.error || 'Could not generate TTS audio')}</p>`;
      }
      return;
    }
    audioDataUrl = data.audio_data_url;
    ttsAudioCache.set(cacheKey, audioDataUrl);
  }

  if (activeAudio) {
    activeAudio.pause();
    activeAudio.currentTime = 0;
  }
  activeAudio = new Audio(audioDataUrl);
  await activeAudio.play();
}

function setKanaRecordStatus(message, isError = false) {
  const statusEl = document.getElementById('kana-record-status');
  if (!statusEl) return;
  statusEl.textContent = message;
  statusEl.classList.toggle('alert', Boolean(isError));
}

function updateKanaRecordButtons(isRecording) {
  const recordBtn = document.getElementById('kana-record-btn');
  const stopBtn = document.getElementById('kana-stop-record-btn');
  if (recordBtn) recordBtn.disabled = isRecording;
  if (stopBtn) stopBtn.disabled = !isRecording;
}

function cleanupRecorder() {
  if (activeRecorderStream) {
    activeRecorderStream.getTracks().forEach((track) => track.stop());
  }
  activeRecorder = null;
  activeRecorderStream = null;
  recorderChunks = [];
  recordingStartedAtMs = 0;
}

async function transcribeKanaRecording(blob, durationSeconds) {
  if (!selectedGame || selectedGame.game_type !== 'kana_speed_round') return;

  const formData = new FormData();
  formData.append('language', selectedGame.language || currentLanguage);
  formData.append('audio_file', blob, `kana-${Date.now()}.webm`);

  const res = await fetch(apiUrl('api/audio/stt'), {
    method: 'POST',
    body: formData,
  });
  const data = await res.json();
  if (!res.ok || !data.transcript) {
    setKanaRecordStatus(data.error || 'Audio transcription failed.', true);
    return;
  }

  const transcriptInput = gameZoneEl.querySelector('input[data-k="recognized_text"]');
  if (transcriptInput) {
    transcriptInput.value = data.transcript;
  }
  setKanaElapsed(durationSeconds, false);
  setKanaRecordStatus(`Transcript ready (${durationSeconds.toFixed(1)}s).`);
}

async function startKanaRecording() {
  if (!selectedGame || selectedGame.game_type !== 'kana_speed_round') return;
  if (activeRecorder) return;

  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    setKanaRecordStatus('This browser does not support microphone access.', true);
    return;
  }
  if (typeof MediaRecorder === 'undefined') {
    setKanaRecordStatus('MediaRecorder is not available in this browser.', true);
    return;
  }

  try {
    activeRecorderStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const candidates = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg;codecs=opus'];
    const mimeType = candidates.find((candidate) => typeof MediaRecorder.isTypeSupported === 'function' && MediaRecorder.isTypeSupported(candidate));
    activeRecorder = mimeType ? new MediaRecorder(activeRecorderStream, { mimeType }) : new MediaRecorder(activeRecorderStream);
    recorderChunks = [];
    recordingStartedAtMs = Date.now();
    setKanaElapsed(0.1, false);
    startKanaElapsedTicker();

    activeRecorder.addEventListener('dataavailable', (event) => {
      if (event.data && event.data.size > 0) {
        recorderChunks.push(event.data);
      }
    });
    activeRecorder.addEventListener('stop', async () => {
      try {
        const durationSeconds = Math.max(0.1, (Date.now() - recordingStartedAtMs) / 1000);
        setKanaElapsed(durationSeconds, false);
        const blobType = (recorderChunks[0] && recorderChunks[0].type) || activeRecorder.mimeType || 'audio/webm';
        const blob = new Blob(recorderChunks, { type: blobType });
        await transcribeKanaRecording(blob, durationSeconds);
      } finally {
        stopKanaElapsedTicker();
        cleanupRecorder();
        updateKanaRecordButtons(false);
      }
    });

    activeRecorder.start();
    updateKanaRecordButtons(true);
    setKanaRecordStatus('Recording... press Stop to transcribe.');
  } catch (error) {
    stopKanaElapsedTicker();
    cleanupRecorder();
    updateKanaRecordButtons(false);
    setKanaRecordStatus('Could not open microphone (check permissions).', true);
  }
}

function stopKanaRecording() {
  if (!activeRecorder) return;
  setKanaRecordStatus('Processing audio...');
  activeRecorder.stop();
}

function setPronunciationRecordStatus(message, isError = false) {
  const statusEl = document.getElementById('pronunciation-record-status');
  if (!statusEl) return;
  statusEl.textContent = message;
  statusEl.classList.toggle('alert', Boolean(isError));
}

function updatePronunciationRecordButtons(isRecording) {
  const recordBtn = document.getElementById('pronunciation-record-btn');
  const stopBtn = document.getElementById('pronunciation-stop-record-btn');
  if (recordBtn) recordBtn.disabled = isRecording;
  if (stopBtn) stopBtn.disabled = !isRecording;
}

async function transcribePronunciationRecording(blob, durationSeconds) {
  if (!selectedGame || selectedGame.game_type !== 'pronunciation_match') return;

  const formData = new FormData();
  formData.append('language', selectedGame.language || currentLanguage);
  formData.append('audio_file', blob, `pronunciation-${Date.now()}.webm`);

  const res = await fetch(apiUrl('api/audio/stt'), {
    method: 'POST',
    body: formData,
  });
  const data = await res.json();
  if (!res.ok || !data.transcript) {
    setPronunciationRecordStatus(data.error || 'Audio transcription failed.', true);
    return;
  }

  const transcriptInput = gameZoneEl.querySelector('input[data-k="recognized_text"]');
  if (transcriptInput) {
    transcriptInput.value = data.transcript;
  }
  pronunciationElapsedSeconds = durationSeconds;
  setPronunciationRecordStatus(`Transcript ready (${durationSeconds.toFixed(1)}s).`);
}

async function startPronunciationRecording() {
  if (!selectedGame || selectedGame.game_type !== 'pronunciation_match') return;
  if (activeRecorder) return;

  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    setPronunciationRecordStatus('This browser does not support microphone access.', true);
    return;
  }
  if (typeof MediaRecorder === 'undefined') {
    setPronunciationRecordStatus('MediaRecorder is not available in this browser.', true);
    return;
  }

  try {
    activeRecorderStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const candidates = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg;codecs=opus'];
    const mimeType = candidates.find((candidate) => typeof MediaRecorder.isTypeSupported === 'function' && MediaRecorder.isTypeSupported(candidate));
    activeRecorder = mimeType ? new MediaRecorder(activeRecorderStream, { mimeType }) : new MediaRecorder(activeRecorderStream);
    recorderChunks = [];
    recordingStartedAtMs = Date.now();
    pronunciationElapsedSeconds = 0.1;

    activeRecorder.addEventListener('dataavailable', (event) => {
      if (event.data && event.data.size > 0) {
        recorderChunks.push(event.data);
      }
    });
    activeRecorder.addEventListener('stop', async () => {
      try {
        const durationSeconds = Math.max(0.1, (Date.now() - recordingStartedAtMs) / 1000);
        pronunciationElapsedSeconds = durationSeconds;
        const blobType = (recorderChunks[0] && recorderChunks[0].type) || activeRecorder.mimeType || 'audio/webm';
        const blob = new Blob(recorderChunks, { type: blobType });
        await transcribePronunciationRecording(blob, durationSeconds);
      } finally {
        cleanupRecorder();
        updatePronunciationRecordButtons(false);
      }
    });

    activeRecorder.start();
    updatePronunciationRecordButtons(true);
    setPronunciationRecordStatus('Recording... press Stop to transcribe.');
  } catch (error) {
    cleanupRecorder();
    updatePronunciationRecordButtons(false);
    setPronunciationRecordStatus('Could not open microphone (check permissions).', true);
  }
}

function stopPronunciationRecording() {
  if (!activeRecorder) return;
  setPronunciationRecordStatus('Processing audio...');
  activeRecorder.stop();
}

function setShadowingRecordStatus(message, isError = false) {
  const statusEl = document.getElementById('shadowing-record-status');
  if (!statusEl) return;
  statusEl.textContent = message;
  statusEl.classList.toggle('alert', Boolean(isError));
}

function updateShadowingRecordButtons(isRecording) {
  const recordBtn = document.getElementById('shadowing-record-btn');
  const stopBtn = document.getElementById('shadowing-stop-record-btn');
  if (recordBtn) recordBtn.disabled = isRecording;
  if (stopBtn) stopBtn.disabled = !isRecording;
}

async function transcribeShadowingRecording(blob, durationSeconds) {
  if (!selectedGame || selectedGame.game_type !== 'shadowing_score') return;

  const formData = new FormData();
  formData.append('language', selectedGame.language || currentLanguage);
  formData.append('audio_file', blob, `shadowing-${Date.now()}.webm`);

  const res = await fetch(apiUrl('api/audio/stt'), {
    method: 'POST',
    body: formData,
  });
  const data = await res.json();
  if (!res.ok || !data.transcript) {
    setShadowingRecordStatus(data.error || 'Audio transcription failed.', true);
    return;
  }

  const learnerInput = gameZoneEl.querySelector('input[data-k="learner_text"]');
  if (learnerInput) {
    learnerInput.value = data.transcript;
  }
  shadowingElapsedSeconds = durationSeconds;
  setShadowingRecordStatus(`Transcript ready (${durationSeconds.toFixed(1)}s).`);
}

async function startShadowingRecording() {
  if (!selectedGame || selectedGame.game_type !== 'shadowing_score') return;
  if (activeRecorder) return;

  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    setShadowingRecordStatus('This browser does not support microphone access.', true);
    return;
  }
  if (typeof MediaRecorder === 'undefined') {
    setShadowingRecordStatus('MediaRecorder is not available in this browser.', true);
    return;
  }

  try {
    activeRecorderStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const candidates = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg;codecs=opus'];
    const mimeType = candidates.find((candidate) => typeof MediaRecorder.isTypeSupported === 'function' && MediaRecorder.isTypeSupported(candidate));
    activeRecorder = mimeType ? new MediaRecorder(activeRecorderStream, { mimeType }) : new MediaRecorder(activeRecorderStream);
    recorderChunks = [];
    recordingStartedAtMs = Date.now();
    shadowingElapsedSeconds = 0.1;

    activeRecorder.addEventListener('dataavailable', (event) => {
      if (event.data && event.data.size > 0) {
        recorderChunks.push(event.data);
      }
    });
    activeRecorder.addEventListener('stop', async () => {
      try {
        const durationSeconds = Math.max(0.1, (Date.now() - recordingStartedAtMs) / 1000);
        shadowingElapsedSeconds = durationSeconds;
        const blobType = (recorderChunks[0] && recorderChunks[0].type) || activeRecorder.mimeType || 'audio/webm';
        const blob = new Blob(recorderChunks, { type: blobType });
        await transcribeShadowingRecording(blob, durationSeconds);
      } finally {
        cleanupRecorder();
        updateShadowingRecordButtons(false);
      }
    });

    activeRecorder.start();
    updateShadowingRecordButtons(true);
    setShadowingRecordStatus('Recording... press Stop to transcribe.');
  } catch (error) {
    cleanupRecorder();
    updateShadowingRecordButtons(false);
    setShadowingRecordStatus('Could not open microphone (check permissions).', true);
  }
}

function stopShadowingRecording() {
  if (!activeRecorder) return;
  setShadowingRecordStatus('Processing audio...');
  activeRecorder.stop();
}

function wireGameActions() {
  const evaluateBtn = document.getElementById('evaluate-btn');
  const retryBtn = document.getElementById('retry-btn');
  const kanaPlayBtn = document.getElementById('kana-play-audio-btn');
  const kanaRecordBtn = document.getElementById('kana-record-btn');
  const kanaStopRecordBtn = document.getElementById('kana-stop-record-btn');
  const pronunciationRecordBtn = document.getElementById('pronunciation-record-btn');
  const pronunciationStopRecordBtn = document.getElementById('pronunciation-stop-record-btn');
  const shadowingRecordBtn = document.getElementById('shadowing-record-btn');
  const shadowingStopRecordBtn = document.getElementById('shadowing-stop-record-btn');
  evaluateBtn?.addEventListener('click', () => evaluateSelectedGame(false));
  retryBtn?.addEventListener('click', () => evaluateSelectedGame(true));
  kanaPlayBtn?.addEventListener('click', () => playKanaAudio(selectedGame));
  kanaRecordBtn?.addEventListener('click', startKanaRecording);
  kanaStopRecordBtn?.addEventListener('click', stopKanaRecording);
  pronunciationRecordBtn?.addEventListener('click', startPronunciationRecording);
  pronunciationStopRecordBtn?.addEventListener('click', stopPronunciationRecording);
  shadowingRecordBtn?.addEventListener('click', startShadowingRecording);
  shadowingStopRecordBtn?.addEventListener('click', stopShadowingRecording);
  initDragAndDropComponents();
  syncKanjiReadingPreview();
  syncSentenceOrderLocks();
}

function initDragAndDropComponents() {
  const zones = Array.from(gameZoneEl.querySelectorAll('.dnd-zone'));
  if (zones.length === 0) return;

  const tokens = gameZoneEl.querySelectorAll('.dnd-token');
  tokens.forEach((token) => {
    token.addEventListener('dragstart', (event) => {
      if (token.dataset.locked === 'true') {
        event.preventDefault();
        return;
      }
      token.classList.add('dragging');
    });
    token.addEventListener('dragend', () => {
      token.classList.remove('dragging');
      if (selectedGame && selectedGame.game_type === 'kanji_match') {
        window.setTimeout(syncKanjiReadingPreview, 0);
      }
      if (selectedGame && selectedGame.game_type === 'sentence_order') {
        window.setTimeout(syncSentenceOrderLocks, 0);
      }
    });
  });

  zones.forEach((zone) => {
    zone.addEventListener('dragover', (event) => {
      event.preventDefault();
      const dragging = gameZoneEl.querySelector('.dnd-token.dragging');
      if (!dragging) return;
      const singleSlot = zone.dataset.singleSlot === 'true';
      if (singleSlot) {
        if (zone.dataset.locked === 'true') return;
        return;
      }

      const after = getDragAfterElement(zone, event.clientY);
      if (!after) {
        zone.appendChild(dragging);
      } else {
        zone.insertBefore(dragging, after);
      }
    });

    zone.addEventListener('drop', (event) => {
      event.preventDefault();
      const dragging = gameZoneEl.querySelector('.dnd-token.dragging');
      if (!dragging) return;
      const singleSlot = zone.dataset.singleSlot === 'true';
      if (singleSlot) {
        if (zone.dataset.locked === 'true') return;
        const current = zone.querySelector('.dnd-token:not(.dragging)');
        if (current && current !== dragging) {
          const bankSelector = zone.dataset.bankSelector || '#gap-options-bank';
          const bank = gameZoneEl.querySelector(bankSelector);
          if (bank) {
            bank.appendChild(current);
          }
        }
        zone.appendChild(dragging);
        if (selectedGame && selectedGame.game_type === 'kanji_match') {
          window.setTimeout(syncKanjiReadingPreview, 0);
        }
        if (selectedGame && selectedGame.game_type === 'sentence_order') {
          window.setTimeout(syncSentenceOrderLocks, 0);
        }
        return;
      }

      const after = getDragAfterElement(zone, event.clientY);
      if (!after) {
        zone.appendChild(dragging);
      } else {
        zone.insertBefore(dragging, after);
      }
      if (selectedGame && selectedGame.game_type === 'sentence_order') {
        window.setTimeout(syncSentenceOrderLocks, 0);
      }
    });
  });
}

function getDragAfterElement(container, y) {
  const draggableElements = [...container.querySelectorAll('.dnd-token:not(.dragging)')];

  return draggableElements.reduce(
    (closest, child) => {
      const box = child.getBoundingClientRect();
      const offset = y - box.top - box.height / 2;
      if (offset < 0 && offset > closest.offset) {
        return { offset, element: child };
      }
      return closest;
    },
    { offset: Number.NEGATIVE_INFINITY, element: null }
  ).element;
}

async function loadDailyGame() {
  const body = {};
  if (todayLevelOverride != null) {
    body.level_override_today = todayLevelOverride;
  }

  const res = await fetch(apiUrl('api/games/daily'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const data = await res.json();

  availableLanguages = data.available_languages || ['ja'];
  currentLanguage = data.language || 'ja';
  currentLevel = Number(data.current_level || 1);
  todayLevel = Number(data.today_level || currentLevel);
  selectedGame = data.selected_game || null;
  availableGameCards = data.all_games || data.available_games || (selectedGame ? [selectedGame] : []);

  if (todayLevel === currentLevel) {
    todayLevelOverride = null;
  }

  retryCounters.clear();
  updateTopbar();
  renderSidebar(availableGameCards);
  renderSingleGame(selectedGame);
  wireGameActions();
}

async function changeLanguage() {
  const options = availableLanguages.map((code) => `${languageLabel(code)} (${code})`).join(', ');
  const value = prompt(`Language (${options})`, currentLanguage);
  if (!value) return;
  const language = resolveLanguageCode(value);
  if (!availableLanguages.includes(language)) return;

  await fetch(apiUrl('api/ui/language'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ language }),
  });

  todayLevelOverride = null;
  await loadDailyGame();
}

async function changeLevelForToday() {
  const value = prompt('Level for today (1, 2, 3). Leave empty to return to base level.', String(todayLevel));
  if (value == null) return;
  const trimmed = value.trim();
  if (!trimmed) {
    todayLevelOverride = null;
    await loadDailyGame();
    return;
  }

  const parsed = Number(trimmed);
  if (![1, 2, 3].includes(parsed)) return;
  todayLevelOverride = parsed;
  await loadDailyGame();
}

changeLanguageBtn?.addEventListener('click', changeLanguage);
changeLevelBtn?.addEventListener('click', changeLevelForToday);
gamesSidebarEl?.addEventListener('click', (event) => {
  const target = event.target;
  if (!target || !target.dataset || target.dataset.action !== 'pick-game') return;
  const gameType = target.dataset.game;
  const found = availableGameCards.find((g) => g.game_type === gameType);
  if (!found) return;
  selectedGame = found;
  retryCounters.clear();
  renderSidebar(availableGameCards);
  renderSingleGame(selectedGame);
  wireGameActions();
});

loadDailyGame();

const currentLanguageEl = document.getElementById('current-language');
const currentLevelEl = document.getElementById('current-level');
const todayScoreEl = document.getElementById('today-score');
const gameZoneEl = document.getElementById('game-zone');
const gamesSidebarEl = document.getElementById('games-sidebar');
const changeLanguageBtn = document.getElementById('change-language-btn');
const secondaryTranslationSelectEl = document.getElementById('secondary-translation-select');
const LANGUAGE_ALIASES = {
  ja: 'Japanese',
};

let availableLanguages = ['ja'];
let learnerId = 'ha_default_user';
let currentLanguage = 'ja';
let currentLevel = 1;
let todayLevel = 1;
let selectedGame = null;
let availableGameCards = [];
let dailyGameCards = [];
let extraGameCards = [];
let dailyTopic = null;
let dailyLesson = null;
let dailyProgress = null;
let translationPreferences = {
  primary_translation_language: 'en',
  secondary_translation_language: null,
  available_secondary_translation_languages: [{ code: 'es', label: 'Español' }],
};
let closedTopics = [];
let closedTopicsVisible = false;
let isReviewMode = false;
const retryCounters = new Map();
const extraGameCardsByType = new Map();
const extraLoadedCards = new Map();
const sentenceOrderPenaltyByAttempt = new Map();
const ttsAudioCache = new Map();
const ttsPlayCounters = new Map();
const ttsWarningShownByGame = new Set();
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

function normalizeSecondaryLanguage(value) {
  const normalized = String(value || '').trim().toLowerCase();
  if (!normalized || normalized === 'off' || normalized === 'none' || normalized === 'null') {
    return null;
  }
  return normalized;
}

function setTranslationPreferences(preferences) {
  const payload = preferences && typeof preferences === 'object' ? preferences : {};
  const available = Array.isArray(payload.available_secondary_translation_languages)
    ? payload.available_secondary_translation_languages
      .filter((entry) => entry && entry.code && entry.label)
      .map((entry) => ({ code: String(entry.code).toLowerCase(), label: String(entry.label) }))
    : [];
  translationPreferences = {
    primary_translation_language: 'en',
    secondary_translation_language: normalizeSecondaryLanguage(payload.secondary_translation_language),
    available_secondary_translation_languages: available.length > 0
      ? available
      : [{ code: 'es', label: 'Español' }],
  };
}

function secondaryTranslationLabel(code) {
  const normalized = normalizeSecondaryLanguage(code);
  if (!normalized) return 'Off';
  const match = translationPreferences.available_secondary_translation_languages
    .find((entry) => String(entry.code || '').toLowerCase() === normalized);
  return match ? match.label : normalized.toUpperCase();
}

function renderSecondaryTranslationSelector() {
  if (!secondaryTranslationSelectEl) return;
  const selected = normalizeSecondaryLanguage(translationPreferences.secondary_translation_language) || '';
  const options = [
    '<option value="">Off</option>',
    ...translationPreferences.available_secondary_translation_languages
      .map((entry) => `<option value="${escapeHtml(entry.code)}">${escapeHtml(entry.label)}</option>`),
  ].join('');
  secondaryTranslationSelectEl.innerHTML = options;
  secondaryTranslationSelectEl.value = selected;
}

// Shared renderer for all EN/secondary translation bundles returned by the API.
function translationBundleForField(record, field) {
  const bundle = record && record[`${field}_translations`];
  if (bundle && typeof bundle === 'object' && !Array.isArray(bundle)) {
    return bundle;
  }
  return {
    en: record && typeof record[field] === 'string' ? record[field] : '',
    secondary_lang: normalizeSecondaryLanguage(translationPreferences.secondary_translation_language),
    secondary: null,
  };
}

function multilineHtml(value) {
  return escapeHtml(value).replaceAll('\n', '<br />');
}

function renderBilingualValue(bundle, { showEnglish = true, multiline = false } = {}) {
  if (!bundle || typeof bundle !== 'object') return '';
  const enText = String(bundle.en || '').trim();
  const secondaryLang = normalizeSecondaryLanguage(bundle.secondary_lang);
  const secondaryText = String(bundle.secondary || '').trim();
  const parts = [];
  if (showEnglish && enText) {
    parts.push(`<span class="translation-primary-line">${multiline ? multilineHtml(enText) : escapeHtml(enText)}</span>`);
  }
  if (secondaryLang && secondaryText) {
    const secondaryLabel = secondaryTranslationLabel(secondaryLang);
    const secondaryBody = multiline ? multilineHtml(secondaryText) : escapeHtml(secondaryText);
    parts.push(`<span class="translation-secondary-line">${escapeHtml(secondaryLabel)}: ${secondaryBody}</span>`);
  }
  return parts.join('<br />');
}

function renderTranslatedField(record, field, {
  label = '',
  className = '',
  tag = 'p',
  showEnglish = true,
  multiline = false,
} = {}) {
  const bundle = translationBundleForField(record, field);
  const html = renderBilingualValue(bundle, { showEnglish, multiline });
  if (!html) return '';
  const classes = className ? ` class="${escapeHtml(className)}"` : '';
  const labelHtml = label ? `<strong>${escapeHtml(label)}:</strong> ` : '';
  return `<${tag}${classes}>${labelHtml}${html}</${tag}>`;
}

function renderTranslatedList(record, field) {
  const values = Array.isArray(record && record[field]) ? record[field] : [];
  const bundles = Array.isArray(record && record[`${field}_translations`]) ? record[`${field}_translations`] : [];
  return values
    .map((value, index) => {
      const bundle = bundles[index] && typeof bundles[index] === 'object'
        ? bundles[index]
        : { en: value, secondary_lang: normalizeSecondaryLanguage(translationPreferences.secondary_translation_language), secondary: null };
      const rendered = renderBilingualValue(bundle, { showEnglish: true, multiline: false });
      return rendered ? `<li>${rendered}</li>` : '';
    })
    .filter(Boolean)
    .join('');
}

function updateTopbar() {
  currentLanguageEl.textContent = languageLabel(currentLanguage);
  currentLevelEl.textContent = String(currentLevel);
  if (changeLanguageBtn) {
    changeLanguageBtn.hidden = availableLanguages.length <= 1;
  }
  renderSecondaryTranslationSelector();
  const score = Number((dailyProgress && dailyProgress.daily_score) || 0);
  const scoreMax = Number((dailyProgress && dailyProgress.daily_score_max) || 300);
  if (todayScoreEl) {
    todayScoreEl.textContent = `Today's score: ${score}/${scoreMax}`;
  }
}

function gameAttemptKey(game) {
  if (!game) return '';
  return `${game.game_type || ''}:${game.activity_id || ''}:${game.language || ''}`;
}

function appendResultAlert(message) {
  const resultEl = document.getElementById('game-result');
  if (!resultEl || !message) return;
  resultEl.innerHTML = `<p class="alert">${escapeHtml(message)}</p>${resultEl.innerHTML}`;
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

function isLessonCompleted() {
  if (isReviewMode) return true;
  return Boolean(dailyProgress && dailyProgress.lesson_completed);
}

function areExtrasUnlocked() {
  if (isReviewMode) return true;
  return Boolean(dailyProgress && dailyProgress.extras_unlocked);
}

function refreshAvailableGameCards() {
  availableGameCards = areExtrasUnlocked()
    ? [...dailyGameCards, ...extraGameCards]
    : [...dailyGameCards];
}

function nextPendingDailyGame() {
  const completed = new Set((dailyProgress && dailyProgress.completed_daily_games) || []);
  const pending = dailyGameCards.find((card) => !completed.has(card.game_type));
  return pending || null;
}

function renderLessonPanel() {
  if (!dailyLesson) return '';

  if (isReviewMode) {
    const reviewTopicHtml = renderTranslatedField(dailyTopic, 'title', {
      label: 'Topic',
      className: 'muted',
    });
    const reviewTopicDescriptionHtml = renderTranslatedField(dailyTopic, 'description', {
      className: 'muted',
      multiline: true,
    });
    return `
      <section class="lesson-card">
        <h2>Review mode</h2>
        ${reviewTopicHtml || `<p class="muted"><strong>Topic:</strong> ${escapeHtml((dailyTopic && dailyTopic.title) || dailyLesson.topic_title || '')}</p>`}
        ${reviewTopicDescriptionHtml}
        <p class="muted">Practice this learned topic. Review attempts do not modify daily score or progression.</p>
        <div class="lesson-progress-actions">
          <button id="exit-review-btn" class="ghost-btn" type="button">Back to today's topic</button>
        </div>
      </section>
    `;
  }

  const points = renderTranslatedList(dailyLesson, 'theory_points');
  const completedCount = Number((dailyProgress && dailyProgress.daily_games_completed_count) || 0);
  const totalCount = Number((dailyProgress && dailyProgress.daily_games_total) || dailyGameCards.length || 3);
  const lessonDone = isLessonCompleted();
  const lessonButton = lessonDone
    ? '<button id="complete-lesson-btn" type="button" class="ghost-btn" disabled>Lesson completed</button>'
    : '<button id="complete-lesson-btn" type="button" class="ghost-btn">Complete lesson and start games</button>';
  const unlockLine = areExtrasUnlocked()
    ? '<p class="muted">Extra games for this topic are unlocked.</p>'
    : '<p class="muted">Finish lesson + 3 daily games to unlock extra topic games.</p>';
  const topicDays = Number((dailyProgress && dailyProgress.topic_days_count) || 0);
  const targetScore = Number((dailyProgress && dailyProgress.topic_day_target_score) || 150);
  const targetReached = Boolean(dailyProgress && dailyProgress.topic_day_target_reached);
  const highScoreDays = Number((dailyProgress && dailyProgress.high_score_days_over_240) || 0);
  const retention = (dailyProgress && dailyProgress.retention_ratio_percent);
  const failures = (dailyProgress && dailyProgress.topic_failure_totals) || {};
  const failureSummary = Object.keys(failures).length > 0
    ? Object.entries(failures).map(([game, count]) => `${game}: ${count}`).join(' | ')
    : 'No failures registered yet.';
  const weeklyDue = Boolean(dailyProgress && dailyProgress.weekly_exam_due);
  const weeklyExamUnlocked = weeklyDue && lessonDone && completedCount >= totalCount;
  const weeklyButtonLabel = weeklyExamUnlocked ? 'Take weekly mini-exam' : 'Weekly mini-exam locked';
  const weeklyDisabled = weeklyExamUnlocked ? '' : 'disabled';
  const readyTo2 = Boolean(dailyProgress && dailyProgress.ready_to_level_2);
  const readyTo3 = Boolean(dailyProgress && dailyProgress.ready_to_level_3);
  const levelExamReady = readyTo2 || readyTo3;
  const levelExamLabel = readyTo2 ? 'Take level exam (1 -> 2)' : (readyTo3 ? 'Take level exam (2 -> 3)' : 'Level exam locked');
  const levelExamDisabled = (levelExamReady && lessonDone && completedCount >= totalCount) ? '' : 'disabled';
  const closedTopicsCount = Number((dailyProgress && dailyProgress.closed_topics_count) || 0);
  const lessonTitleHtml = renderTranslatedField(dailyLesson, 'title', { tag: 'h2' }) || '<h2>Daily lesson</h2>';
  const topicTitleHtml = renderTranslatedField(dailyTopic, 'title', {
    label: 'Topic',
    className: 'muted',
  });
  const topicDescriptionHtml = renderTranslatedField(dailyTopic, 'description', {
    className: 'muted',
    multiline: true,
  });
  const closedTopicsHtml = closedTopicsVisible
    ? `
      <div class="lesson-closed-topics">
        ${
          closedTopics.length === 0
            ? '<p class="muted">No learned topics yet.</p>'
            : `
              <ul class="lesson-closed-list">
                ${closedTopics.map((topic) => `
                  <li class="lesson-closed-item">
                    <span>${escapeHtml(topic.topic_title || topic.topic_key)} · ${escapeHtml(topic.closed_day_iso || '')} · level ${escapeHtml(topic.closed_level || '')}</span>
                    <button
                      type="button"
                      class="ghost-btn closed-topic-review-btn"
                      data-topic-key="${escapeHtml(topic.topic_key || '')}"
                    >
                      Review topic
                    </button>
                  </li>
                `).join('')}
              </ul>
            `
        }
      </div>
    `
    : '';

  return `
    <section class="lesson-card">
      ${lessonTitleHtml}
      ${topicTitleHtml || `<p class="muted"><strong>Topic:</strong> ${escapeHtml((dailyTopic && dailyTopic.title) || dailyLesson.topic_title || '')}</p>`}
      ${topicDescriptionHtml}
      ${renderTranslatedField(dailyLesson, 'objective', { className: 'muted' })}
      ${points ? `<ul class="lesson-points">${points}</ul>` : ''}
      <div class="lesson-example">
        <p><strong>Example:</strong> ${escapeHtml(dailyLesson.example_script || '')}</p>
        <p><strong>Romanized:</strong> ${escapeHtml(dailyLesson.example_romanized || '')}</p>
        ${renderTranslatedField(dailyLesson, 'example_literal_translation', { label: 'Literal' })}
      </div>
      <div class="lesson-actions">
        ${lessonButton}
      </div>
      <p class="muted">Daily progress: ${completedCount}/${totalCount} games completed.</p>
      <p class="muted">Days on this topic: ${topicDays}.</p>
      <p class="muted">Target score for this day: ${targetScore}/300 (${targetReached ? 'reached' : 'pending'}).</p>
      <p class="muted">High-score days (>240): ${highScoreDays}.</p>
      <p class="muted">Retention (vs previous days): ${retention == null ? 'n/a' : `${retention}%`}.</p>
      <p class="muted">Failures by game: ${escapeHtml(failureSummary)}</p>
      ${unlockLine}
      <div class="lesson-progress-actions">
        <button id="weekly-exam-btn" class="ghost-btn" type="button" ${weeklyDisabled}>${weeklyButtonLabel}</button>
        <button id="level-exam-btn" class="ghost-btn" type="button" ${levelExamDisabled}>${levelExamLabel}</button>
        <button id="closed-topics-btn" class="ghost-btn" type="button">
          ${closedTopicsVisible ? 'Hide learned topics' : `Show learned topics (${closedTopicsCount})`}
        </button>
      </div>
      ${closedTopicsHtml}
    </section>
  `;
}

function sentenceOrderState(game) {
  if (!game) return null;
  const key = gameAttemptKey(game);
  if (!key) return null;
  if (!sentenceOrderPenaltyByAttempt.has(key)) {
    sentenceOrderPenaltyByAttempt.set(key, {
      penalty: 0,
      wrongBySlot: {},
      autoEvaluated: false,
    });
  }
  return sentenceOrderPenaltyByAttempt.get(key);
}

function sentenceOrderPenaltyForGame(game) {
  const state = sentenceOrderState(game);
  return state ? Number(state.penalty || 0) : 0;
}

function updateSentenceOrderStatusLine() {
  if (!selectedGame || selectedGame.game_type !== 'sentence_order') return;
  const statusEl = document.getElementById('sentence-order-status');
  if (!statusEl) return;
  const penalty = sentenceOrderPenaltyForGame(selectedGame);
  const score = Math.max(0, 100 - penalty);
  statusEl.textContent = `Current penalty: -${penalty}. Potential score: ${score}/100`;
}

function renderSingleGame(game) {
  const lessonHtml = renderLessonPanel();
  if (!isLessonCompleted()) {
    gameZoneEl.classList.remove('hidden');
    gameZoneEl.innerHTML = `
      ${lessonHtml}
      <section class="game-card-locked">
        <p class="muted">Complete the lesson to unlock today's 3 topic games.</p>
      </section>
    `;
    return;
  }

  if (!game) {
    gameZoneEl.classList.remove('hidden');
    gameZoneEl.innerHTML = `
      ${lessonHtml}
      <section class="game-card-locked">
        <p class="muted">No game available for today.</p>
      </section>
    `;
    return;
  }

  const payload = game.payload || {};
  const gameType = game.game_type;
  const displayName = game.display_name || gameType;
  let promptHtml = renderTranslatedField(game, 'prompt', { className: 'prompt', multiline: true });
  let promptIncludesTranslation = true;
  if (game.ai_generated_prompt) {
    promptHtml = `
      <div class="prompt game-meta">
        ${renderTranslatedField(game, 'ai_generated_prompt', { label: 'AI prompt', className: 'game-meta-line' })}
        ${renderTranslatedField(game, 'prompt', { className: 'game-meta-line', multiline: true })}
      </div>
    `;
    promptIncludesTranslation = true;
  }
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
    promptIncludesTranslation = false;
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
        <small id="sentence-order-status" class="muted">Place all fragments to get your final score.</small>
      </fieldset>
    `;
  } else if (gameType === 'mora_romanization') {
    // The backend controls assistance mode per level: beginner exposes mora guides.
    const numericLevel = Number(game.level || 1);
    const fallbackMode = numericLevel <= 1 ? 'beginner' : (numericLevel === 2 ? 'intermediate' : 'advanced');
    const mode = payload.mode || fallbackMode;
    const moraKanaLine = Array.isArray(payload.mora_kana_tokens) ? payload.mora_kana_tokens.join(' | ') : '';
    const moraRomajiLine = Array.isArray(payload.mora_romaji_tokens) ? payload.mora_romaji_tokens.join(' ') : '';
    const japaneseText = payload.japanese_text || '';
    const metaLines = [];
    if (mode === 'beginner' || mode === 'intermediate') {
      if (moraKanaLine) metaLines.push(`Mora (kana): ${moraKanaLine}`);
      if (moraRomajiLine) metaLines.push(`Mora (romaji): ${moraRomajiLine}`);
    } else if (japaneseText) {
      metaLines.push(`Japanese text: ${japaneseText}`);
    }
    const inputPlaceholder = mode === 'beginner'
      ? ' placeholder="watashi wa gakusei desu"'
      : '';
    promptHtml = `
      <div class="prompt game-meta">
        ${metaLines.map((line) => `<p class="game-meta-line">${escapeHtml(line)}</p>`).join('')}
      </div>
    `;
    promptIncludesTranslation = false;
    controls = `
      <fieldset class="response-group">
        <legend>Answer</legend>
        <label>Romanized words</label>
        <input data-k="user_romanized_text"${inputPlaceholder} />
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
    promptIncludesTranslation = false;
    const listenButton = payload.tts_text
      ? `
        <div class="audio-actions">
          <button id="listening-play-audio-btn" type="button" class="ghost-btn">Play full sentence (TTS)</button>
        </div>
      `
      : '';
    controls = `
      <div class="listening-controls">
        ${listenButton}
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
    promptIncludesTranslation = false;
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
    promptIncludesTranslation = false;
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
  } else {
    controls = '<p class="muted">Game renderer not implemented.</p>';
  }

  const evaluateLabel = (gameType === 'pronunciation_match' || gameType === 'kana_speed_round')
    ? 'Evaluate audio'
    : 'Evaluate';
  const showEvaluateButton = gameType !== 'sentence_order';
  const promptSecondaryHtml = promptIncludesTranslation
    ? ''
    : renderTranslatedField(game, 'prompt', {
      className: 'prompt prompt-secondary',
      showEnglish: false,
      multiline: true,
    });

  gameZoneEl.classList.remove('hidden');
  gameZoneEl.innerHTML = `
    ${lessonHtml}
    <section class="game-card">
      <h2>${escapeHtml(displayName)}</h2>
      ${promptHtml}
      ${promptSecondaryHtml}
      ${controls}
      <div class="actions">
        ${showEvaluateButton ? `<button id="evaluate-btn">${evaluateLabel}</button>` : ''}
        <button id="retry-btn" class="ghost-btn">Retry</button>
      </div>
      <div id="game-result" class="result"></div>
    </section>
  `;
}

function renderSidebar(games) {
  if (!gamesSidebarEl) return;
  const sidebarTopicLine = renderTranslatedField(dailyTopic, 'title', { className: 'muted' })
    || `<p class="muted">${escapeHtml((dailyTopic && dailyTopic.title) || (dailyLesson && dailyLesson.topic_title) || 'Daily topic')}</p>`;
  const sidebarTopicDescriptionLine = renderTranslatedField(dailyTopic, 'description', {
    className: 'muted',
    multiline: true,
  });
  if (isReviewMode) {
    const reviewList = (dailyGameCards || [])
      .map((game) => {
        const active = selectedGame && selectedGame.game_type === game.game_type ? 'active-game' : '';
        return `
          <button class="sidebar-game ${active}" data-action="pick-game" data-game="${escapeHtml(game.game_type)}">
            ${escapeHtml(game.display_name || game.game_type)}
          </button>
        `;
      })
      .join('');
    gamesSidebarEl.innerHTML = `
      <h3>Topic review</h3>
      ${sidebarTopicLine}
      ${sidebarTopicDescriptionLine || ''}
      <div class="sidebar-list">${reviewList || '<p class="muted">No review games available.</p>'}</div>
    `;
    return;
  }
  const lessonDone = isLessonCompleted();
  const extrasUnlocked = areExtrasUnlocked();
  const dailyList = (dailyGameCards || [])
    .map((game) => {
      const active = selectedGame && selectedGame.game_type === game.game_type ? 'active-game' : '';
      const done = (dailyProgress && dailyProgress.completed_daily_games || []).includes(game.game_type);
      const doneTag = done ? ' <span class="done-tag">Done</span>' : '';
      const disabled = lessonDone ? '' : 'disabled';
      return `
        <button class="sidebar-game ${active}" data-action="pick-game" data-game="${escapeHtml(game.game_type)}" ${disabled}>
          ${escapeHtml(game.display_name || game.game_type)}${doneTag}
        </button>
      `;
    })
    .join('');

  const extraList = (extraGameCards || [])
    .map((game) => {
      const active = selectedGame && selectedGame.game_type === game.game_type ? 'active-game' : '';
      const disabled = extrasUnlocked ? '' : 'disabled';
      return `
        <button class="sidebar-game ${active}" data-action="pick-game" data-game="${escapeHtml(game.game_type)}" ${disabled}>
          ${escapeHtml(game.display_name || game.game_type)}
        </button>
      `;
    })
    .join('');

  const extraSection = extraGameCards.length === 0
    ? ''
    : `
      <h4>Extra topic games</h4>
      ${extrasUnlocked ? '' : '<p class="muted">Locked until lesson + 3 daily games.</p>'}
      <div class="sidebar-list">${extraList}</div>
    `;

  gamesSidebarEl.innerHTML = `
    <h3>Topic flow</h3>
    ${sidebarTopicLine}
    ${sidebarTopicDescriptionLine || ''}
    <h4>Daily games</h4>
    <div class="sidebar-list">${dailyList || '<p class="muted">No games available.</p>'}</div>
    ${extraSection}
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
    payload.sentence_order_penalty = sentenceOrderPenaltyForGame(game);
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
  const state = sentenceOrderState(selectedGame);
  if (!state) return;
  const slots = Array.from(gameZoneEl.querySelectorAll('.sentence-order-slot[data-slot-index]'));
  let allFilled = slots.length > 0;
  let allCorrect = slots.length > 0;
  slots.forEach((slot) => {
    const expectedToken = String(slot.dataset.expectedToken || '').trim();
    const token = slot.querySelector('.dnd-token');
    const slotIndex = String(slot.dataset.slotIndex || '');
    if (!token || !expectedToken) {
      allFilled = false;
      allCorrect = false;
      setSingleSlotLocked(slot, false);
      slot.classList.remove('sentence-slot-correct');
      state.wrongBySlot[slotIndex] = '';
      if (token) setTokenLocked(token, false);
      return;
    }
    const tokenText = String(token.dataset.tokenText || token.textContent || '').trim();
    const isCorrect = tokenText === expectedToken;
    if (!isCorrect) {
      allCorrect = false;
      const wrongSignature = `${slotIndex}:${tokenText}`;
      if (state.wrongBySlot[slotIndex] !== wrongSignature) {
        state.penalty = Math.min(100, Number(state.penalty || 0) + 10);
        state.wrongBySlot[slotIndex] = wrongSignature;
      }
    } else {
      state.wrongBySlot[slotIndex] = '';
    }
    setSingleSlotLocked(slot, isCorrect);
    setTokenLocked(token, isCorrect);
    slot.classList.toggle('sentence-slot-correct', isCorrect);
  });
  sentenceOrderPenaltyByAttempt.set(gameAttemptKey(selectedGame), state);
  updateSentenceOrderStatusLine();
  if (allFilled && allCorrect && !state.autoEvaluated) {
    state.autoEvaluated = true;
    sentenceOrderPenaltyByAttempt.set(gameAttemptKey(selectedGame), state);
    evaluateSelectedGame(false);
  }
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
  const scoreHtml = data.score != null ? `<p class="result-line"><strong>Score:</strong> ${escapeHtml(data.score)}</p>` : '';
  const feedbackHtml = renderTranslatedField(data, 'feedback', {
    label: 'Feedback',
    className: 'result-line',
    multiline: true,
  });
  const translationHtml = renderTranslatedField(data, 'literal_translation', {
    label: 'Literal translation',
    className: 'result-line',
    multiline: true,
  });
  const readingAccuracyHtml = data.reading_accuracy != null
    ? `<p class="result-line"><strong>Reading:</strong> ${escapeHtml(Math.round(Number(data.reading_accuracy) * 100))}%</p>`
    : '';
  const meaningAccuracyHtml = data.meaning_accuracy != null
    ? `<p class="result-line"><strong>Meaning:</strong> ${escapeHtml(Math.round(Number(data.meaning_accuracy) * 100))}%</p>`
    : '';
  const romanizationAccuracyHtml = data.romanization_accuracy != null
    ? `<p class="result-line"><strong>Romanization:</strong> ${escapeHtml(Math.round(Number(data.romanization_accuracy) * 100))}%</p>`
    : '';
  const segmentationAccuracyHtml = data.segmentation_accuracy != null
    ? `<p class="result-line"><strong>Segmentation:</strong> ${escapeHtml(Math.round(Number(data.segmentation_accuracy) * 100))}%</p>`
    : '';
  const kanjiMoraHtml = data.kanji_mora_line
    ? `<div class="result-block"><p><strong>Kanji (mora):</strong> ${escapeHtml(data.kanji_mora_line)}</p></div>`
    : '';
  const pronunciationSummaryHtml = (data.is_match != null)
    ? `<p class="result-line"><strong>Match:</strong> ${data.is_match ? 'Yes' : 'No'}${data.match_threshold != null ? ` (target ${Math.round(Number(data.match_threshold) * 100)}%)` : ''}</p>`
    : '';
  const kanaRomanizedHtml = data.expected_romaji || data.recognized_romaji
    ? `
      <div class="result-block">
        <p class="result-line"><strong>Expected (romanized):</strong> ${escapeHtml(data.expected_romaji || '-')}</p>
        <p class="result-line"><strong>Recognized (romanized):</strong> ${escapeHtml(data.recognized_romaji || '-')}</p>
        ${renderTranslatedField(data, 'expected_translation', { label: 'Expected translation', className: 'result-line' })}
        ${renderTranslatedField(data, 'recognized_translation', { label: 'Recognized translation', className: 'result-line' })}
      </div>
    `
    : '';
  const mismatchHtml = renderMismatchesHtml(data.sequence_mismatches);
  const wordFeedbackHtml = renderWordFeedbackHtml(data.word_feedback);
  const nextStepHtml = renderTranslatedField(data, 'next_step', {
    label: 'Next step',
    className: 'result-line',
    multiline: true,
  });

  resultEl.innerHTML = `
    ${alertsHtml}
    ${scoreHtml}
    ${pronunciationSummaryHtml}
    ${readingAccuracyHtml}
    ${meaningAccuracyHtml}
    ${romanizationAccuracyHtml}
    ${segmentationAccuracyHtml}
    ${feedbackHtml}
    ${translationHtml}
    ${kanjiMoraHtml}
    ${kanaRomanizedHtml}
    ${mismatchHtml}
    ${wordFeedbackHtml}
    ${nextStepHtml}
  `;
  applyKanjiEvaluationFeedback(data);
}

async function evaluateSelectedGame(isRetry) {
  if (!selectedGame) return;
  if (!isLessonCompleted()) return;
  const key = `${selectedGame.game_type}:${selectedGame.activity_id}`;
  const currentRetry = retryCounters.get(key) || 0;
  const nextRetry = isRetry ? currentRetry + 1 : currentRetry;
  retryCounters.set(key, nextRetry);

  const payload = collectPayload(selectedGame);
  const res = await fetch(apiUrl('api/games/evaluate'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      learner_id: learnerId,
      game_type: selectedGame.game_type,
      language: selectedGame.language || currentLanguage,
      // Use card level first to avoid backend item lookup mismatches in review/extra flows.
      level: Number(selectedGame.level || todayLevel || currentLevel || 1),
      retry_count: nextRetry,
      review_mode: isReviewMode,
      payload,
    }),
  });
  const data = await res.json();
  if (!isReviewMode && data.daily_progress) {
    dailyProgress = data.daily_progress;
    refreshAvailableGameCards();
    renderSidebar(availableGameCards);
  }
  updateTopbar();
  renderEvaluation(data);
}

function resolveTtsText(game) {
  if (!game) return '';
  if (game.payload?.tts_text) return String(game.payload.tts_text);
  if (game.game_type === 'kana_speed_round') {
    return game.payload?.expected_text || extractKanaSequenceFromPrompt(game.prompt || '');
  }
  return '';
}

async function playTtsAudio(game) {
  if (!game) return;
  const text = resolveTtsText(game);
  if (!text) return;
  const gameKey = gameAttemptKey(game);
  const currentPlays = ttsPlayCounters.get(gameKey) || 0;
  const playCount = currentPlays + 1;
  ttsPlayCounters.set(gameKey, playCount);

  const cacheKey = `${game.language || currentLanguage}:${text}`;
  let audioDataUrl = ttsAudioCache.get(cacheKey);
  if (!audioDataUrl) {
    const res = await fetch(apiUrl('api/audio/tts'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        text,
        language: game.language || currentLanguage,
        play_count: playCount,
      }),
    });
    const data = await res.json();
    if (data.warning && gameKey && !ttsWarningShownByGame.has(gameKey)) {
      appendResultAlert(data.warning);
      ttsWarningShownByGame.add(gameKey);
    }
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
  if (playCount > 3 && gameKey && !ttsWarningShownByGame.has(gameKey)) {
    appendResultAlert('Warning: repeated TTS playback may increase token usage.');
    ttsWarningShownByGame.add(gameKey);
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

async function completeDailyLesson() {
  if (isReviewMode) return;
  if (!dailyLesson || isLessonCompleted()) return;

  const res = await fetch(apiUrl('api/games/lesson/complete'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      learner_id: learnerId,
      language: currentLanguage,
      topic_key: dailyLesson.topic_key || (dailyTopic && dailyTopic.topic_key) || '',
    }),
  });
  const data = await res.json();
  if (!res.ok || data.error) {
    window.alert(data.error || 'Could not mark lesson as completed.');
    return;
  }

  if (data.daily_progress) {
    dailyProgress = data.daily_progress;
  }
  refreshAvailableGameCards();
  selectedGame = nextPendingDailyGame() || availableGameCards[0] || null;
  updateTopbar();
  renderSidebar(availableGameCards);
  renderSingleGame(selectedGame);
  wireGameActions();
}

async function loadClosedTopics() {
  const res = await fetch(apiUrl('api/topics/closed'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      learner_id: learnerId,
      language: currentLanguage,
    }),
  });
  const data = await res.json();
  if (!res.ok || data.error) {
    window.alert(data.error || 'Could not load learned topics.');
    return false;
  }
  closedTopics = Array.isArray(data.closed_topics) ? data.closed_topics : [];
  return true;
}

async function toggleClosedTopics() {
  if (!closedTopicsVisible) {
    const ok = await loadClosedTopics();
    if (!ok) return;
    closedTopicsVisible = true;
  } else {
    closedTopicsVisible = false;
  }
  renderSingleGame(selectedGame);
  wireGameActions();
}

async function startTopicReview(topicKey) {
  const normalizedTopic = String(topicKey || '').trim();
  if (!normalizedTopic) return;

  const res = await fetch(apiUrl('api/topics/review'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      learner_id: learnerId,
      language: currentLanguage,
      topic_key: normalizedTopic,
    }),
  });
  const data = await res.json();
  if (!res.ok || data.error) {
    window.alert(data.error || 'Could not start topic review.');
    return;
  }

  isReviewMode = true;
  closedTopicsVisible = false;
  dailyTopic = data.topic || dailyTopic;
  dailyLesson = data.lesson || dailyLesson;
  dailyGameCards = Array.isArray(data.review_games) ? data.review_games : [];
  extraGameCards = [];
  extraGameCardsByType.clear();
  extraLoadedCards.clear();
  availableGameCards = [...dailyGameCards];
  selectedGame = data.selected_game || dailyGameCards[0] || null;
  retryCounters.clear();
  sentenceOrderPenaltyByAttempt.clear();
  updateTopbar();
  renderSidebar(availableGameCards);
  renderSingleGame(selectedGame);
  wireGameActions();
}

async function exitReviewMode() {
  if (!isReviewMode) return;
  isReviewMode = false;
  await loadDailyGame();
}

function parseMoraRomajiFromPrompt(prompt) {
  const lines = String(prompt || '').split(/\r?\n/);
  const target = lines.find((line) => /^Mora \(romaji\):/i.test(line.trim()));
  if (!target) return [];
  const raw = target.split(':').slice(1).join(':').trim();
  if (!raw) return [];
  return raw.split(/\s+/).map((token) => token.trim()).filter(Boolean);
}

function buildWeeklyExamAnswerPayload(question) {
  const payload = {};
  const source = (question && question.payload) || {};
  const gameType = String((question && question.game_type) || '');
  const itemId = String((question && question.item_id) || source.item_id || '').trim();
  if (itemId) {
    payload.item_id = itemId;
  }

  if (gameType === 'sentence_order') {
    payload.ordered_tokens_by_user = Array.isArray(source.ordered_tokens) ? source.ordered_tokens : [];
    return payload;
  }

  if (gameType === 'listening_gap_fill') {
    const tokens = Array.isArray(source.tokens) ? source.tokens : [];
    const positions = Array.isArray(source.gap_positions) ? source.gap_positions : [];
    payload.user_gap_tokens = positions
      .map((position) => Number(position))
      .filter((position) => Number.isInteger(position) && position >= 0 && position < tokens.length)
      .map((position) => String(tokens[position] || '').trim())
      .filter(Boolean);
    return payload;
  }

  if (gameType === 'mora_romanization') {
    const moraTokens = Array.isArray(source.mora_romaji_tokens) ? source.mora_romaji_tokens : parseMoraRomajiFromPrompt(question?.prompt);
    payload.user_romanized_text = moraTokens.join(' ');
    return payload;
  }

  if (gameType === 'context_quiz') {
    const options = Array.isArray(source.options) ? source.options : [];
    const firstOption = options.find((opt) => opt && typeof opt.id === 'string');
    payload.selected_option_id = firstOption ? firstOption.id : '';
    return payload;
  }

  if (gameType === 'grammar_particle_fix') {
    const options = Array.isArray(source.options) ? source.options : [];
    payload.selected_particle = options.length > 0 ? String(options[0]) : '';
    return payload;
  }

  if (gameType === 'kanji_match') {
    const pairs = Array.isArray(source.pairs) ? source.pairs : [];
    const learnerReadings = {};
    const learnerMeanings = {};
    pairs.forEach((pair) => {
      const symbol = String((pair && pair.symbol) || '').trim();
      if (!symbol) return;
      learnerReadings[symbol] = String((pair && pair.reading_romaji) || '').trim();
      learnerMeanings[symbol] = String((pair && pair.meaning) || '').trim();
    });
    payload.learner_readings = learnerReadings;
    payload.learner_meanings = learnerMeanings;
    payload.learner_matches = learnerMeanings;
    return payload;
  }

  if (gameType === 'pronunciation_match') {
    const expectedText = String(source.expected_text || question?.prompt || '').trim();
    payload.expected_text = expectedText;
    payload.recognized_text = expectedText;
    payload.audio_duration_seconds = 2.0;
    payload.speech_seconds = 2.0;
    payload.pause_seconds = 0.2;
    payload.pitch_track_hz = [150.0, 151.0, 149.0];
    return payload;
  }

  if (gameType === 'kana_speed_round') {
    const expectedText = String(source.expected_text || '').trim();
    payload.expected_text = expectedText;
    payload.recognized_text = expectedText;
    payload.sequence_expected = parseTokenList(expectedText, ' ');
    payload.sequence_read = parseTokenList(expectedText, ' ');
    payload.elapsed_seconds = KANA_DEFAULT_ELAPSED_SECONDS;
    payload.audio_duration_seconds = KANA_DEFAULT_ELAPSED_SECONDS;
    payload.speech_seconds = KANA_DEFAULT_ELAPSED_SECONDS;
    payload.pause_seconds = 0.2;
    payload.pitch_track_hz = [150.0, 149.0, 151.0];
    return payload;
  }

  return payload;
}

async function takeWeeklyExam() {
  const weeklyExamBtn = document.getElementById('weekly-exam-btn');
  if (weeklyExamBtn) {
    weeklyExamBtn.disabled = true;
  }
  try {
    const topicKey = (dailyTopic && dailyTopic.topic_key) || (dailyLesson && dailyLesson.topic_key) || '';
    const firstRes = await fetch(apiUrl('api/exams/weekly'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        learner_id: learnerId,
        language: currentLanguage,
        topic_key: topicKey,
        mode: 'cumulative',
      }),
    });
    const firstData = await firstRes.json();
    if (!firstRes.ok || firstData.error) {
      window.alert(firstData.error || 'Weekly mini-exam request failed.');
      if (firstData.daily_progress) {
        dailyProgress = firstData.daily_progress;
      }
      return;
    }

    if (firstData.daily_progress) {
      dailyProgress = firstData.daily_progress;
    }

    if (!firstData.requires_answers) {
      window.alert(firstData.feedback || 'Weekly mini-exam completed.');
      return;
    }

    const questions = Array.isArray(firstData.questions) ? firstData.questions : [];
    if (questions.length === 0) {
      window.alert('Weekly mini-exam could not start: no questions generated.');
      return;
    }

    // Cumulative mode: build answer payloads from generated question cards and submit in a second call.
    const answers = questions.map((question) => ({
      question_id: question.question_id,
      payload: buildWeeklyExamAnswerPayload(question),
    }));
    const secondRes = await fetch(apiUrl('api/exams/weekly'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        learner_id: learnerId,
        language: currentLanguage,
        topic_key: topicKey,
        mode: 'cumulative',
        answers,
      }),
    });
    const secondData = await secondRes.json();
    if (!secondRes.ok || secondData.error) {
      window.alert(secondData.error || 'Weekly mini-exam submission failed.');
      if (secondData.daily_progress) {
        dailyProgress = secondData.daily_progress;
      }
      return;
    }
    if (secondData.daily_progress) {
      dailyProgress = secondData.daily_progress;
    }
    window.alert(secondData.feedback || 'Weekly mini-exam completed.');
  } finally {
    updateTopbar();
    renderSingleGame(selectedGame);
    wireGameActions();
  }
}

async function takeLevelExam() {
  const res = await fetch(apiUrl('api/exams/level'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      learner_id: learnerId,
      language: currentLanguage,
    }),
  });
  const data = await res.json();
  if (!res.ok || data.error) {
    window.alert(data.error || 'Level exam request failed.');
  } else {
    window.alert(data.feedback || 'Level exam completed.');
  }
  if (data.daily_progress) {
    dailyProgress = data.daily_progress;
  }
  if (data.promoted) {
    await loadDailyGame();
    return;
  }
  updateTopbar();
  renderSingleGame(selectedGame);
  wireGameActions();
}

async function loadExtraGameCard(gameType) {
  if (isReviewMode) return null;
  if (!gameType) return null;
  if (extraLoadedCards.has(gameType)) {
    return extraLoadedCards.get(gameType);
  }
  const extraMeta = extraGameCardsByType.get(gameType);
  if (!extraMeta) return null;

  const res = await fetch(apiUrl('api/games/extra/load'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      learner_id: learnerId,
      game_type: gameType,
      language: currentLanguage,
      topic_key: (dailyTopic && dailyTopic.topic_key) || (dailyLesson && dailyLesson.topic_key) || '',
    }),
  });
  const data = await res.json();
  if (!res.ok || data.error || !data.card) {
    window.alert(data.error || 'Could not load this extra game.');
    return null;
  }
  if (data.daily_progress) {
    dailyProgress = data.daily_progress;
  }
  extraLoadedCards.set(gameType, data.card);
  updateTopbar();
  return data.card;
}

function wireGameActions() {
  const evaluateBtn = document.getElementById('evaluate-btn');
  const retryBtn = document.getElementById('retry-btn');
  const completeLessonBtn = document.getElementById('complete-lesson-btn');
  const kanaPlayBtn = document.getElementById('kana-play-audio-btn');
  const listeningPlayBtn = document.getElementById('listening-play-audio-btn');
  const kanaRecordBtn = document.getElementById('kana-record-btn');
  const kanaStopRecordBtn = document.getElementById('kana-stop-record-btn');
  const pronunciationRecordBtn = document.getElementById('pronunciation-record-btn');
  const pronunciationStopRecordBtn = document.getElementById('pronunciation-stop-record-btn');
  const weeklyExamBtn = document.getElementById('weekly-exam-btn');
  const levelExamBtn = document.getElementById('level-exam-btn');
  const closedTopicsBtn = document.getElementById('closed-topics-btn');
  const exitReviewBtn = document.getElementById('exit-review-btn');
  const reviewTopicBtns = Array.from(document.querySelectorAll('.closed-topic-review-btn'));
  completeLessonBtn?.addEventListener('click', completeDailyLesson);
  evaluateBtn?.addEventListener('click', () => evaluateSelectedGame(false));
  retryBtn?.addEventListener('click', () => {
    if (selectedGame && selectedGame.game_type === 'sentence_order') {
      sentenceOrderPenaltyByAttempt.delete(gameAttemptKey(selectedGame));
      renderSingleGame(selectedGame);
      wireGameActions();
      return;
    }
    evaluateSelectedGame(true);
  });
  kanaPlayBtn?.addEventListener('click', () => playTtsAudio(selectedGame));
  listeningPlayBtn?.addEventListener('click', () => playTtsAudio(selectedGame));
  kanaRecordBtn?.addEventListener('click', startKanaRecording);
  kanaStopRecordBtn?.addEventListener('click', stopKanaRecording);
  pronunciationRecordBtn?.addEventListener('click', startPronunciationRecording);
  pronunciationStopRecordBtn?.addEventListener('click', stopPronunciationRecording);
  weeklyExamBtn?.addEventListener('click', takeWeeklyExam);
  levelExamBtn?.addEventListener('click', takeLevelExam);
  closedTopicsBtn?.addEventListener('click', toggleClosedTopics);
  exitReviewBtn?.addEventListener('click', exitReviewMode);
  reviewTopicBtns.forEach((btn) => {
    btn.addEventListener('click', () => startTopicReview(btn.dataset.topicKey || ''));
  });
  initDragAndDropComponents();
  syncKanjiReadingPreview();
  syncSentenceOrderLocks();
  updateSentenceOrderStatusLine();
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
  const res = await fetch(apiUrl('api/games/daily'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ learner_id: learnerId }),
  });
  const data = await res.json();

  learnerId = data.learner_id || learnerId;
  availableLanguages = data.available_languages || ['ja'];
  currentLanguage = data.language || 'ja';
  currentLevel = Number(data.current_level || 1);
  todayLevel = Number(data.today_level || currentLevel);
  setTranslationPreferences(data.translation_preferences || {});
  isReviewMode = false;
  dailyTopic = data.topic || null;
  dailyLesson = data.lesson || null;
  dailyProgress = data.daily_progress || null;
  dailyGameCards = data.daily_games || [];
  extraGameCards = data.extra_games || [];
  extraGameCardsByType.clear();
  extraGameCards.forEach((card) => {
    extraGameCardsByType.set(card.game_type, card);
  });
  extraLoadedCards.clear();
  refreshAvailableGameCards();
  selectedGame = data.selected_game || null;
  if (!selectedGame && isLessonCompleted()) {
    selectedGame = nextPendingDailyGame() || availableGameCards[0] || null;
  }
  if (!isLessonCompleted()) {
    selectedGame = null;
  }

  if (data.level_up_blocked) {
    window.alert('Temporary level override is disabled. Use topic review instead.');
  }

  retryCounters.clear();
  sentenceOrderPenaltyByAttempt.clear();
  closedTopicsVisible = false;
  closedTopics = [];
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
    body: JSON.stringify({ learner_id: learnerId, language }),
  });

  await loadDailyGame();
}

async function changeSecondaryTranslation() {
  if (!secondaryTranslationSelectEl) return;
  const selectedValue = normalizeSecondaryLanguage(secondaryTranslationSelectEl.value);
  secondaryTranslationSelectEl.disabled = true;
  try {
    let res;
    let data;
    try {
      res = await fetch(apiUrl('api/ui/secondary-translation'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          learner_id: learnerId,
          secondary_language: selectedValue || 'off',
        }),
      });
      data = await res.json();
    } catch (error) {
      window.alert('Could not reach the server to update translation preference.');
      renderSecondaryTranslationSelector();
      return;
    }
    if (!res.ok || data.error) {
      window.alert(data.error || 'Could not update translation preference.');
      renderSecondaryTranslationSelector();
      return;
    }
    if (data.translation_preferences) {
      setTranslationPreferences(data.translation_preferences);
    }
    await loadDailyGame();
  } finally {
    secondaryTranslationSelectEl.disabled = false;
  }
}

changeLanguageBtn?.addEventListener('click', changeLanguage);
secondaryTranslationSelectEl?.addEventListener('change', changeSecondaryTranslation);
gamesSidebarEl?.addEventListener('click', (event) => {
  const target = event.target;
  if (!target || !target.dataset || target.dataset.action !== 'pick-game') return;
  if (!isLessonCompleted()) return;
  const gameType = target.dataset.game;
  const openSelected = async () => {
    let found = availableGameCards.find((g) => g.game_type === gameType);
    if (!found) return;
    if (found.deferred_load) {
      const loadedCard = await loadExtraGameCard(gameType);
      if (!loadedCard) return;
      found = loadedCard;
      availableGameCards = availableGameCards.map((card) => (
        card.game_type === gameType ? loadedCard : card
      ));
    }
    selectedGame = found;
    retryCounters.clear();
    renderSidebar(availableGameCards);
    renderSingleGame(selectedGame);
    wireGameActions();
  };
  openSelected();
});

loadDailyGame();

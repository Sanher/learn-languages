from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import logging
from random import Random

from language_games.services import (
    GAME_TYPE_CONTEXT_QUIZ,
    GAME_TYPE_GRAMMAR_PARTICLE_FIX,
    GAME_TYPE_LISTENING_GAP_FILL,
    GAME_TYPE_MORA_ROMANIZATION,
    GAME_TYPE_PRONUNCIATION_MATCH,
    GAME_TYPE_SENTENCE_ORDER,
)

logger = logging.getLogger("learn_languages.japanese.topic_flow")
TOPIC_DAILY_ROTATION_COUNT = 4
TOPIC_STAGES = ("basic", "intermediate", "advanced")
# These competency tags are language-agnostic gates for rank progression.
# Each language can then explain how those competencies show up in its own grammar.
RANK_COMPETENCIES: dict[str, tuple[str, ...]] = {
    "basic": (
        "identity",
        "basic_sentence_roles",
        "time_and_routine",
        "basic_questions",
        "everyday_actions",
    ),
    "intermediate": (
        "past_negative",
        "linking_actions",
        "modality",
        "register_control",
        "reasons_experiences",
    ),
    "advanced": (
        "conditionals",
        "subordination",
        "voice_and_valency",
        "discourse_connectors",
        "formal_register",
    ),
}
# Guidance stays language-specific so OpenAI can generate topic sequences that still
# respect the shared competency contract while sounding natural for the target language.
LANGUAGE_COMPETENCY_GUIDANCE: dict[str, dict[str, str]] = {
    "ja": {
        "identity": "Self-introduction, identity statements, and simple copula patterns in Japanese.",
        "basic_sentence_roles": "Core sentence roles in Japanese, especially topic/subject/object marking and SOV order.",
        "time_and_routine": "Talking about today, tomorrow, dates, and routine actions in Japanese.",
        "basic_questions": "Forming and answering simple Japanese questions.",
        "everyday_actions": "Using common daily Japanese verbs in short statements.",
        "past_negative": "Past, negative, and past-negative forms in Japanese.",
        "linking_actions": "Connecting actions in Japanese, including te-form style chaining.",
        "modality": "Ability, intention, permission, obligation, or related modality in Japanese.",
        "register_control": "Handling plain versus polite Japanese register appropriately.",
        "reasons_experiences": "Explaining reasons and basic experiences in Japanese.",
        "conditionals": "Conditional and hypothetical patterns in Japanese.",
        "subordination": "Relative clauses, embedded statements, and other subordinate structures in Japanese.",
        "voice_and_valency": "Passive, causative, and transitive/intransitive patterns in Japanese.",
        "discourse_connectors": "Connecting and contrasting ideas across longer Japanese discourse.",
        "formal_register": "Formal or socially appropriate Japanese phrasing.",
    }
}


@dataclass(frozen=True)
class LessonDefinition:
    title: str
    objective: str
    theory_points: tuple[str, ...]
    example_script: str
    example_romanized: str
    example_literal_translation: str


@dataclass(frozen=True)
class TopicGamePlan:
    game_type: str
    activity_ids_by_level: dict[int, str]

    def activity_id_for_level(self, level: int) -> str:
        keys = sorted(self.activity_ids_by_level.keys())
        if not keys:
            raise ValueError(f"No activity ids configured for game_type={self.game_type}")
        normalized_level = min(max(level, keys[0]), keys[-1])
        return self.activity_ids_by_level[normalized_level]


@dataclass(frozen=True)
class TopicDefinition:
    topic_key: str
    language: str
    title: str
    description: str
    lessons_by_level: dict[int, LessonDefinition]
    daily_games: tuple[TopicGamePlan, ...]
    extra_games: tuple[TopicGamePlan, ...]
    stage: str = "basic"
    covers: tuple[str, ...] = ()

    def lesson_for_level(self, level: int) -> LessonDefinition:
        keys = sorted(self.lessons_by_level.keys())
        if not keys:
            raise ValueError(f"No lessons configured for topic={self.topic_key}")
        normalized_level = min(max(level, keys[0]), keys[-1])
        return self.lessons_by_level[normalized_level]

    def daily_plan_for_level(self, level: int) -> list[tuple[str, str]]:
        return [(item.game_type, item.activity_id_for_level(level)) for item in self.daily_games]

    def daily_pool_for_level(self, level: int) -> list[tuple[str, str]]:
        pool: list[tuple[str, str]] = []
        seen: set[str] = set()
        for item in (*self.daily_games, *self.extra_games):
            if item.game_type in seen:
                continue
            seen.add(item.game_type)
            pool.append((item.game_type, item.activity_id_for_level(level)))
        return pool

    def daily_plan_for_day(self, level: int, learner_id: str, target_day: date) -> list[tuple[str, str]]:
        pool = self.daily_pool_for_level(level)
        if not pool:
            return []

        ordered = pool.copy()
        # Keep the pool order stable per learner/topic while rotating the visible daily set each day.
        seed = f"{self.topic_key}:{self.language}:{learner_id}:{level}"
        Random(seed).shuffle(ordered)
        daily_count = min(max(1, TOPIC_DAILY_ROTATION_COUNT), len(ordered))
        # Rotate in blocks so consecutive days feel materially different even with a small pool.
        offset = (target_day.toordinal() * daily_count) % len(ordered)
        return [ordered[(offset + idx) % len(ordered)] for idx in range(daily_count)]

    def extra_plan_for_level(self, level: int) -> list[tuple[str, str]]:
        return [(item.game_type, item.activity_id_for_level(level)) for item in self.extra_games]


JA_TOPIC_IDENTITY_AND_PLANS = TopicDefinition(
    topic_key="identity_and_plans",
    language="ja",
    title="Identity and Daily Plans",
    description="Build sentences about who you are, what happens today, and plans for tomorrow.",
    lessons_by_level={
        1: LessonDefinition(
            title="Topic marker basics",
            objective="Introduce yourself with simple topic + noun + copula sentence patterns.",
            theory_points=(
                "Use `wa` to mark the topic of the sentence.",
                "Use simple noun statements like `X wa Y desu`.",
                "Keep a stable order: topic first, core information next.",
            ),
            example_script="私は学生です。",
            example_romanized="watashi wa gakusei desu",
            example_literal_translation="I topic student am",
        ),
        2: LessonDefinition(
            title="Today and routine context",
            objective="Describe today-focused statements with clearer noun and verb anchors.",
            theory_points=(
                "Time words like `kyou` help frame the sentence context.",
                "Topic and subject markers may coexist (`wa`, `ga`).",
                "Keep action/result segments grouped to avoid order mistakes.",
            ),
            example_script="今日は仕事があります。",
            example_romanized="kyou wa shigoto ga arimasu",
            example_literal_translation="today topic work subject exists",
        ),
        3: LessonDefinition(
            title="Multi-part plan statements",
            objective="Build longer statements with time, companion, object, and action order.",
            theory_points=(
                "Put time context early to anchor the sentence.",
                "Use connectors and particles to bind roles clearly.",
                "Check final verb placement to keep the sentence natural.",
            ),
            example_script="明日友達と映画を見ます。",
            example_romanized="ashita tomodachi to eiga o mimasu",
            example_literal_translation="tomorrow friend with movie object watch",
        ),
    },
    daily_games=(
        TopicGamePlan(
            game_type=GAME_TYPE_SENTENCE_ORDER,
            activity_ids_by_level={
                1: "ja-sentence-order-1-1",
                2: "ja-sentence-order-2-1",
                3: "ja-sentence-order-3-1",
            },
        ),
        TopicGamePlan(
            game_type=GAME_TYPE_LISTENING_GAP_FILL,
            activity_ids_by_level={
                1: "ja-gap-1-1",
                2: "ja-gap-2-1",
                3: "ja-gap-3-1",
            },
        ),
        TopicGamePlan(
            game_type=GAME_TYPE_MORA_ROMANIZATION,
            activity_ids_by_level={
                1: "ja-mora-romanization-1-1",
                2: "ja-mora-romanization-2-1",
                3: "ja-mora-romanization-3-1",
            },
        ),
    ),
    extra_games=(
        TopicGamePlan(
            game_type=GAME_TYPE_GRAMMAR_PARTICLE_FIX,
            activity_ids_by_level={
                1: "ja-particle-1-1",
                2: "ja-particle-2-1",
                3: "ja-particle-3-1",
            },
        ),
        TopicGamePlan(
            game_type=GAME_TYPE_CONTEXT_QUIZ,
            activity_ids_by_level={
                1: "ja-context-1-1",
                2: "ja-context-2-1",
                3: "ja-context-3-1",
            },
        ),
        TopicGamePlan(
            game_type=GAME_TYPE_PRONUNCIATION_MATCH,
            activity_ids_by_level={
                1: "ja-pronunciation-1-1",
                2: "ja-pronunciation-2-1",
                3: "ja-pronunciation-3-1",
            },
        ),
    ),
    stage="basic",
    covers=(
        "identity",
        "basic_sentence_roles",
        "time_and_routine",
        "basic_questions",
        "everyday_actions",
    ),
)

TOPICS_BY_LANGUAGE: dict[str, tuple[TopicDefinition, ...]] = {
    "ja": (JA_TOPIC_IDENTITY_AND_PLANS,),
}


def normalize_topic_stage(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in TOPIC_STAGES else "basic"


def required_competencies_for_stage(stage: str) -> tuple[str, ...]:
    return RANK_COMPETENCIES.get(normalize_topic_stage(stage), ())


def all_competency_tags() -> tuple[str, ...]:
    tags: list[str] = []
    seen: set[str] = set()
    for values in RANK_COMPETENCIES.values():
        for value in values:
            if value in seen:
                continue
            seen.add(value)
            tags.append(value)
    return tuple(tags)


def language_competency_guidance(language: str) -> dict[str, str]:
    normalized_language = str(language or "").strip().lower()
    return dict(LANGUAGE_COMPETENCY_GUIDANCE.get(normalized_language, {}))


def normalize_topic_covers(raw: object, *, stage: str) -> tuple[str, ...]:
    if isinstance(raw, str):
        candidates = [chunk.strip() for chunk in raw.split(",")]
    elif isinstance(raw, (list, tuple, set)):
        candidates = [str(item or "").strip() for item in raw]
    else:
        candidates = []

    allowed = set(all_competency_tags())
    normalized: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        if not candidate or candidate not in allowed or candidate in seen:
            continue
        seen.add(candidate)
        normalized.append(candidate)
    if normalized:
        return tuple(normalized)
    return tuple()


def topic_for_day(learner_id: str, language: str, target_day: date) -> TopicDefinition:
    topics = TOPICS_BY_LANGUAGE.get(language, ())
    if not topics:
        logger.warning("topic_for_day_missing language=%s learner_id=%s", language, learner_id)
        raise ValueError(f"No topic definitions configured for language={language}")
    if len(topics) == 1:
        logger.debug(
            "topic_for_day_single language=%s learner_id=%s day=%s topic=%s",
            language,
            learner_id,
            target_day.isoformat(),
            topics[0].topic_key,
        )
        return topics[0]

    # Deterministic daily selection avoids topic drift on page reloads.
    seed = f"{learner_id}:{language}:{target_day.isoformat()}"
    rnd = Random(seed)
    selected = topics[rnd.randrange(len(topics))]
    logger.info(
        "topic_for_day_selected language=%s learner_id=%s day=%s topic=%s",
        language,
        learner_id,
        target_day.isoformat(),
        selected.topic_key,
    )
    return selected

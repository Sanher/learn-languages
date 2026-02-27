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

    def lesson_for_level(self, level: int) -> LessonDefinition:
        keys = sorted(self.lessons_by_level.keys())
        if not keys:
            raise ValueError(f"No lessons configured for topic={self.topic_key}")
        normalized_level = min(max(level, keys[0]), keys[-1])
        return self.lessons_by_level[normalized_level]

    def daily_plan_for_level(self, level: int) -> list[tuple[str, str]]:
        return [(item.game_type, item.activity_id_for_level(level)) for item in self.daily_games]

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
)

TOPICS_BY_LANGUAGE: dict[str, tuple[TopicDefinition, ...]] = {
    "ja": (JA_TOPIC_IDENTITY_AND_PLANS,),
}


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

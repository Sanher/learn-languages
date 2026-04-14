from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

from .focus_items import (
    FOCUS_ITEM_TYPE_EXPRESSION,
    FOCUS_ITEM_TYPE_KANJI,
    FOCUS_ITEM_TYPE_PARTICLE,
    FOCUS_ITEM_TYPE_WORD,
    FocusItem,
    normalize_focus_item_type,
)

logger = logging.getLogger("learn_languages.japanese.focus_item_catalog")
STAGE_ORDER = {"basic": 0, "intermediate": 1, "advanced": 2}


@dataclass(frozen=True)
class FocusItemSeed:
    item_type: str
    script: str
    reading_kana: str | None = None
    reading_romanized: str | None = None
    meaning_en: str | None = None
    function: str | None = None
    mandatory: bool = False
    exam_relevant: bool = False
    suggested_priority: int = 50
    covers_competencies: tuple[str, ...] = ()
    stage_min: str = "basic"
    stage_max: str | None = None
    level_hint: int | None = None
    example_script: str | None = None
    example_romanized: str | None = None
    example_literal_translation: str | None = None

    def to_focus_item(self, *, source: str = "catalog") -> FocusItem:
        normalized_type = normalize_focus_item_type(self.item_type)
        item_id = f"{normalized_type}-{self.script}"
        return FocusItem(
            item_id=item_id,
            item_type=normalized_type,
            script=self.script,
            reading_kana=self.reading_kana,
            reading_romanized=self.reading_romanized,
            meaning_en=self.meaning_en,
            function=self.function,
            example_script=self.example_script,
            example_romanized=self.example_romanized,
            example_literal_translation=self.example_literal_translation,
            level_hint=self.level_hint,
            is_core=self.mandatory,
            is_exam_relevant=self.exam_relevant,
            covers_competencies=self.covers_competencies,
            source=source,
        )


IDENTITY_AND_PLANS_SEEDS: tuple[FocusItemSeed, ...] = (
    FocusItemSeed(
        item_type=FOCUS_ITEM_TYPE_PARTICLE,
        script="は",
        reading_kana="は",
        reading_romanized="wa",
        function="Marks the topic of the sentence.",
        mandatory=True,
        exam_relevant=True,
        suggested_priority=100,
        covers_competencies=("identity", "basic_sentence_roles"),
        stage_min="basic",
        example_script="私は学生です。",
        example_romanized="watashi wa gakusei desu",
        example_literal_translation="I topic student am",
    ),
    FocusItemSeed(
        item_type=FOCUS_ITEM_TYPE_PARTICLE,
        script="に",
        reading_kana="に",
        reading_romanized="ni",
        function="Marks destination, time, or indirect target depending on context.",
        mandatory=True,
        exam_relevant=True,
        suggested_priority=95,
        covers_competencies=("basic_sentence_roles", "time_and_routine"),
        stage_min="basic",
        example_script="私は駅に行きます。",
        example_romanized="watashi wa eki ni ikimasu",
        example_literal_translation="I topic station to go",
    ),
    FocusItemSeed(
        item_type=FOCUS_ITEM_TYPE_KANJI,
        script="私",
        reading_kana="わたし",
        reading_romanized="watashi",
        meaning_en="I / me",
        mandatory=True,
        exam_relevant=True,
        suggested_priority=92,
        covers_competencies=("identity",),
        stage_min="basic",
        example_script="私は学生です。",
        example_romanized="watashi wa gakusei desu",
        example_literal_translation="I topic student am",
    ),
    FocusItemSeed(
        item_type=FOCUS_ITEM_TYPE_WORD,
        script="学生",
        reading_kana="がくせい",
        reading_romanized="gakusei",
        meaning_en="student",
        mandatory=True,
        exam_relevant=False,
        suggested_priority=86,
        covers_competencies=("identity",),
        stage_min="basic",
        example_script="私は学生です。",
        example_romanized="watashi wa gakusei desu",
        example_literal_translation="I topic student am",
    ),
    FocusItemSeed(
        item_type=FOCUS_ITEM_TYPE_WORD,
        script="毎日",
        reading_kana="まいにち",
        reading_romanized="mainichi",
        meaning_en="every day",
        mandatory=False,
        exam_relevant=True,
        suggested_priority=88,
        covers_competencies=("time_and_routine", "everyday_actions"),
        stage_min="basic",
        example_script="毎日日本語を勉強します。",
        example_romanized="mainichi nihongo o benkyou shimasu",
        example_literal_translation="every day Japanese object study",
    ),
    FocusItemSeed(
        item_type=FOCUS_ITEM_TYPE_WORD,
        script="今日",
        reading_kana="きょう",
        reading_romanized="kyou",
        meaning_en="today",
        mandatory=False,
        exam_relevant=True,
        suggested_priority=84,
        covers_competencies=("time_and_routine",),
        stage_min="basic",
        example_script="今日は仕事があります。",
        example_romanized="kyou wa shigoto ga arimasu",
        example_literal_translation="today topic work subject exists",
    ),
    FocusItemSeed(
        item_type=FOCUS_ITEM_TYPE_WORD,
        script="明日",
        reading_kana="あした",
        reading_romanized="ashita",
        meaning_en="tomorrow",
        mandatory=False,
        exam_relevant=True,
        suggested_priority=82,
        covers_competencies=("time_and_routine",),
        stage_min="basic",
        example_script="明日友達と映画を見ます。",
        example_romanized="ashita tomodachi to eiga o mimasu",
        example_literal_translation="tomorrow friend with movie object watch",
    ),
    FocusItemSeed(
        item_type=FOCUS_ITEM_TYPE_PARTICLE,
        script="を",
        reading_kana="を",
        reading_romanized="o",
        function="Marks the direct object of an action.",
        mandatory=False,
        exam_relevant=True,
        suggested_priority=80,
        covers_competencies=("basic_sentence_roles", "everyday_actions"),
        stage_min="basic",
        example_script="寿司を食べます。",
        example_romanized="sushi o tabemasu",
        example_literal_translation="sushi object eat",
    ),
    FocusItemSeed(
        item_type=FOCUS_ITEM_TYPE_WORD,
        script="行きます",
        reading_kana="いきます",
        reading_romanized="ikimasu",
        meaning_en="go",
        mandatory=False,
        exam_relevant=False,
        suggested_priority=74,
        covers_competencies=("everyday_actions",),
        stage_min="basic",
        example_script="私は駅に行きます。",
        example_romanized="watashi wa eki ni ikimasu",
        example_literal_translation="I topic station to go",
    ),
    FocusItemSeed(
        item_type=FOCUS_ITEM_TYPE_EXPRESSION,
        script="よろしくお願いします",
        reading_kana="よろしくおねがいします",
        reading_romanized="yoroshiku onegaishimasu",
        meaning_en="Please treat me kindly.",
        mandatory=False,
        exam_relevant=False,
        suggested_priority=60,
        covers_competencies=("identity", "register_control"),
        stage_min="intermediate",
        example_script="はじめまして。よろしくお願いします。",
        example_romanized="hajimemashite. yoroshiku onegaishimasu.",
        example_literal_translation="nice to meet you. please treat me favorably.",
    ),
)

EVERYDAY_VERBS_SEEDS: tuple[FocusItemSeed, ...] = (
    FocusItemSeed(
        item_type=FOCUS_ITEM_TYPE_PARTICLE,
        script="を",
        reading_kana="を",
        reading_romanized="o",
        function="Marks the direct object of an action.",
        mandatory=True,
        exam_relevant=True,
        suggested_priority=100,
        covers_competencies=("basic_sentence_roles", "everyday_actions"),
        stage_min="basic",
        example_script="寿司を食べます。",
        example_romanized="sushi o tabemasu",
        example_literal_translation="sushi object eat",
    ),
    FocusItemSeed(
        item_type=FOCUS_ITEM_TYPE_WORD,
        script="食べます",
        reading_kana="たべます",
        reading_romanized="tabemasu",
        meaning_en="eat",
        mandatory=True,
        exam_relevant=True,
        suggested_priority=96,
        covers_competencies=("everyday_actions",),
        stage_min="basic",
        example_script="今日は寿司を食べます。",
        example_romanized="kyou wa sushi o tabemasu",
        example_literal_translation="today topic sushi object eat",
    ),
    FocusItemSeed(
        item_type=FOCUS_ITEM_TYPE_WORD,
        script="行きます",
        reading_kana="いきます",
        reading_romanized="ikimasu",
        meaning_en="go",
        mandatory=True,
        exam_relevant=True,
        suggested_priority=94,
        covers_competencies=("everyday_actions",),
        stage_min="basic",
        example_script="駅に行きます。",
        example_romanized="eki ni ikimasu",
        example_literal_translation="station to go",
    ),
    FocusItemSeed(
        item_type=FOCUS_ITEM_TYPE_WORD,
        script="見ます",
        reading_kana="みます",
        reading_romanized="mimasu",
        meaning_en="watch / see",
        mandatory=False,
        exam_relevant=True,
        suggested_priority=88,
        covers_competencies=("everyday_actions",),
        stage_min="basic",
        example_script="明日友達と映画を見ます。",
        example_romanized="ashita tomodachi to eiga o mimasu",
        example_literal_translation="tomorrow friend with movie object watch",
    ),
    FocusItemSeed(
        item_type=FOCUS_ITEM_TYPE_WORD,
        script="勉強します",
        reading_kana="べんきょうします",
        reading_romanized="benkyou shimasu",
        meaning_en="study",
        mandatory=False,
        exam_relevant=True,
        suggested_priority=86,
        covers_competencies=("everyday_actions",),
        stage_min="basic",
        example_script="毎日日本語を勉強します。",
        example_romanized="mainichi nihongo o benkyou shimasu",
        example_literal_translation="every day Japanese object study",
    ),
    FocusItemSeed(
        item_type=FOCUS_ITEM_TYPE_WORD,
        script="毎日",
        reading_kana="まいにち",
        reading_romanized="mainichi",
        meaning_en="every day",
        mandatory=False,
        exam_relevant=True,
        suggested_priority=84,
        covers_competencies=("time_and_routine", "everyday_actions"),
        stage_min="basic",
        example_script="毎日日本語を勉強します。",
        example_romanized="mainichi nihongo o benkyou shimasu",
        example_literal_translation="every day Japanese object study",
    ),
    FocusItemSeed(
        item_type=FOCUS_ITEM_TYPE_WORD,
        script="日本語",
        reading_kana="にほんご",
        reading_romanized="nihongo",
        meaning_en="Japanese language",
        mandatory=False,
        exam_relevant=False,
        suggested_priority=74,
        covers_competencies=("everyday_actions",),
        stage_min="basic",
        example_script="毎日日本語を勉強します。",
        example_romanized="mainichi nihongo o benkyou shimasu",
        example_literal_translation="every day Japanese object study",
    ),
)

ASKING_QUESTIONS_SEEDS: tuple[FocusItemSeed, ...] = (
    FocusItemSeed(
        item_type=FOCUS_ITEM_TYPE_PARTICLE,
        script="か",
        reading_kana="か",
        reading_romanized="ka",
        function="Turns a polite statement into a question.",
        mandatory=True,
        exam_relevant=True,
        suggested_priority=100,
        covers_competencies=("basic_questions",),
        stage_min="basic",
        example_script="駅はどこですか。",
        example_romanized="eki wa doko desu ka",
        example_literal_translation="station topic where is question",
    ),
    FocusItemSeed(
        item_type=FOCUS_ITEM_TYPE_WORD,
        script="どこ",
        reading_kana="どこ",
        reading_romanized="doko",
        meaning_en="where",
        mandatory=True,
        exam_relevant=True,
        suggested_priority=96,
        covers_competencies=("basic_questions",),
        stage_min="basic",
        example_script="駅はどこですか。",
        example_romanized="eki wa doko desu ka",
        example_literal_translation="station topic where is question",
    ),
    FocusItemSeed(
        item_type=FOCUS_ITEM_TYPE_WORD,
        script="何",
        reading_kana="なに",
        reading_romanized="nani",
        meaning_en="what",
        mandatory=True,
        exam_relevant=True,
        suggested_priority=94,
        covers_competencies=("basic_questions",),
        stage_min="basic",
        example_script="これは何ですか。",
        example_romanized="kore wa nani desu ka",
        example_literal_translation="this topic what is question",
    ),
    FocusItemSeed(
        item_type=FOCUS_ITEM_TYPE_WORD,
        script="ですか",
        reading_kana="ですか",
        reading_romanized="desu ka",
        meaning_en="is it?",
        mandatory=False,
        exam_relevant=True,
        suggested_priority=88,
        covers_competencies=("basic_questions",),
        stage_min="basic",
        example_script="これは何ですか。",
        example_romanized="kore wa nani desu ka",
        example_literal_translation="this topic what is question",
    ),
    FocusItemSeed(
        item_type=FOCUS_ITEM_TYPE_PARTICLE,
        script="は",
        reading_kana="は",
        reading_romanized="wa",
        function="Marks the topic you are asking about.",
        mandatory=False,
        exam_relevant=True,
        suggested_priority=84,
        covers_competencies=("identity", "basic_questions", "basic_sentence_roles"),
        stage_min="basic",
        example_script="駅はどこですか。",
        example_romanized="eki wa doko desu ka",
        example_literal_translation="station topic where is question",
    ),
    FocusItemSeed(
        item_type=FOCUS_ITEM_TYPE_WORD,
        script="駅",
        reading_kana="えき",
        reading_romanized="eki",
        meaning_en="station",
        mandatory=False,
        exam_relevant=False,
        suggested_priority=72,
        covers_competencies=("basic_questions", "identity"),
        stage_min="basic",
        example_script="駅はどこですか。",
        example_romanized="eki wa doko desu ka",
        example_literal_translation="station topic where is question",
    ),
)

DAILY_ROUTINES_SEEDS: tuple[FocusItemSeed, ...] = (
    FocusItemSeed(
        item_type=FOCUS_ITEM_TYPE_WORD,
        script="毎日",
        reading_kana="まいにち",
        reading_romanized="mainichi",
        meaning_en="every day",
        mandatory=True,
        exam_relevant=True,
        suggested_priority=100,
        covers_competencies=("time_and_routine", "everyday_actions"),
        stage_min="basic",
        example_script="毎日日本語を勉強します。",
        example_romanized="mainichi nihongo o benkyou shimasu",
        example_literal_translation="every day Japanese object study",
    ),
    FocusItemSeed(
        item_type=FOCUS_ITEM_TYPE_WORD,
        script="今日",
        reading_kana="きょう",
        reading_romanized="kyou",
        meaning_en="today",
        mandatory=True,
        exam_relevant=True,
        suggested_priority=96,
        covers_competencies=("time_and_routine",),
        stage_min="basic",
        example_script="今日は寿司を食べます。",
        example_romanized="kyou wa sushi o tabemasu",
        example_literal_translation="today topic sushi object eat",
    ),
    FocusItemSeed(
        item_type=FOCUS_ITEM_TYPE_WORD,
        script="明日",
        reading_kana="あした",
        reading_romanized="ashita",
        meaning_en="tomorrow",
        mandatory=True,
        exam_relevant=True,
        suggested_priority=94,
        covers_competencies=("time_and_routine",),
        stage_min="basic",
        example_script="明日友達と映画を見ます。",
        example_romanized="ashita tomodachi to eiga o mimasu",
        example_literal_translation="tomorrow friend with movie object watch",
    ),
    FocusItemSeed(
        item_type=FOCUS_ITEM_TYPE_WORD,
        script="勉強します",
        reading_kana="べんきょうします",
        reading_romanized="benkyou shimasu",
        meaning_en="study",
        mandatory=False,
        exam_relevant=True,
        suggested_priority=88,
        covers_competencies=("everyday_actions",),
        stage_min="basic",
        example_script="毎日日本語を勉強します。",
        example_romanized="mainichi nihongo o benkyou shimasu",
        example_literal_translation="every day Japanese object study",
    ),
    FocusItemSeed(
        item_type=FOCUS_ITEM_TYPE_WORD,
        script="食べます",
        reading_kana="たべます",
        reading_romanized="tabemasu",
        meaning_en="eat",
        mandatory=False,
        exam_relevant=False,
        suggested_priority=86,
        covers_competencies=("everyday_actions",),
        stage_min="basic",
        example_script="今日は寿司を食べます。",
        example_romanized="kyou wa sushi o tabemasu",
        example_literal_translation="today topic sushi object eat",
    ),
    FocusItemSeed(
        item_type=FOCUS_ITEM_TYPE_WORD,
        script="行きます",
        reading_kana="いきます",
        reading_romanized="ikimasu",
        meaning_en="go",
        mandatory=False,
        exam_relevant=False,
        suggested_priority=82,
        covers_competencies=("everyday_actions",),
        stage_min="basic",
        example_script="駅に行きます。",
        example_romanized="eki ni ikimasu",
        example_literal_translation="station to go",
    ),
)

BASIC_GREETINGS_SEEDS: tuple[FocusItemSeed, ...] = (
    FocusItemSeed(
        item_type=FOCUS_ITEM_TYPE_WORD,
        script="おはようございます",
        reading_kana="おはようございます",
        reading_romanized="ohayou gozaimasu",
        meaning_en="good morning",
        mandatory=True,
        exam_relevant=False,
        suggested_priority=100,
        covers_competencies=("identity",),
        stage_min="basic",
        example_script="おはようございます。",
        example_romanized="ohayou gozaimasu",
        example_literal_translation="good morning",
    ),
    FocusItemSeed(
        item_type=FOCUS_ITEM_TYPE_WORD,
        script="こんにちは",
        reading_kana="こんにちは",
        reading_romanized="konnichiwa",
        meaning_en="hello",
        mandatory=True,
        exam_relevant=False,
        suggested_priority=96,
        covers_competencies=("identity",),
        stage_min="basic",
        example_script="こんにちは。",
        example_romanized="konnichiwa",
        example_literal_translation="hello",
    ),
    FocusItemSeed(
        item_type=FOCUS_ITEM_TYPE_WORD,
        script="はじめまして",
        reading_kana="はじめまして",
        reading_romanized="hajimemashite",
        meaning_en="nice to meet you",
        mandatory=True,
        exam_relevant=True,
        suggested_priority=92,
        covers_competencies=("identity",),
        stage_min="basic",
        example_script="はじめまして。",
        example_romanized="hajimemashite",
        example_literal_translation="nice to meet you",
    ),
    FocusItemSeed(
        item_type=FOCUS_ITEM_TYPE_WORD,
        script="よろしくお願いします",
        reading_kana="よろしくおねがいします",
        reading_romanized="yoroshiku onegaishimasu",
        meaning_en="please treat me kindly",
        mandatory=False,
        exam_relevant=False,
        suggested_priority=84,
        covers_competencies=("identity",),
        stage_min="basic",
        example_script="はじめまして。よろしくお願いします。",
        example_romanized="hajimemashite. yoroshiku onegaishimasu.",
        example_literal_translation="nice to meet you. please treat me favorably.",
    ),
    FocusItemSeed(
        item_type=FOCUS_ITEM_TYPE_PARTICLE,
        script="か",
        reading_kana="か",
        reading_romanized="ka",
        function="Marks a polite question.",
        mandatory=False,
        exam_relevant=True,
        suggested_priority=80,
        covers_competencies=("basic_questions",),
        stage_min="basic",
        example_script="お元気ですか。",
        example_romanized="ogenki desu ka",
        example_literal_translation="are you well question",
    ),
)

PAST_NEGATIVE_PATTERNS_SEEDS: tuple[FocusItemSeed, ...] = (
    FocusItemSeed(
        item_type=FOCUS_ITEM_TYPE_WORD,
        script="昨日",
        reading_kana="きのう",
        reading_romanized="kinou",
        meaning_en="yesterday",
        mandatory=True,
        exam_relevant=True,
        suggested_priority=100,
        covers_competencies=("past_negative", "reasons_experiences"),
        stage_min="intermediate",
        example_script="昨日は学校に行きませんでした。",
        example_romanized="kinou wa gakkou ni ikimasen deshita",
        example_literal_translation="yesterday topic school to did not go",
    ),
    FocusItemSeed(
        item_type=FOCUS_ITEM_TYPE_EXPRESSION,
        script="ませんでした",
        reading_kana="ませんでした",
        reading_romanized="masen deshita",
        meaning_en="did not",
        mandatory=True,
        exam_relevant=True,
        suggested_priority=98,
        covers_competencies=("past_negative",),
        stage_min="intermediate",
        example_script="昨日は学校に行きませんでした。",
        example_romanized="kinou wa gakkou ni ikimasen deshita",
        example_literal_translation="yesterday topic school to did not go",
    ),
    FocusItemSeed(
        item_type=FOCUS_ITEM_TYPE_EXPRESSION,
        script="ません",
        reading_kana="ません",
        reading_romanized="masen",
        meaning_en="do not",
        mandatory=False,
        exam_relevant=True,
        suggested_priority=92,
        covers_competencies=("past_negative",),
        stage_min="intermediate",
        example_script="肉は食べません。",
        example_romanized="niku wa tabemasen",
        example_literal_translation="meat topic do not eat",
    ),
    FocusItemSeed(
        item_type=FOCUS_ITEM_TYPE_EXPRESSION,
        script="行きませんでした",
        reading_kana="いきませんでした",
        reading_romanized="ikimasen deshita",
        meaning_en="did not go",
        mandatory=False,
        exam_relevant=True,
        suggested_priority=90,
        covers_competencies=("past_negative",),
        stage_min="intermediate",
        example_script="昨日は学校に行きませんでした。",
        example_romanized="kinou wa gakkou ni ikimasen deshita",
        example_literal_translation="yesterday topic school to did not go",
    ),
    FocusItemSeed(
        item_type=FOCUS_ITEM_TYPE_EXPRESSION,
        script="食べません",
        reading_kana="たべません",
        reading_romanized="tabemasen",
        meaning_en="do not eat",
        mandatory=False,
        exam_relevant=False,
        suggested_priority=82,
        covers_competencies=("past_negative",),
        stage_min="intermediate",
        example_script="夜は甘い物を食べません。",
        example_romanized="yoru wa amai mono o tabemasen",
        example_literal_translation="night topic sweet things object do not eat",
    ),
)

LINKING_ACTIONS_SEEDS: tuple[FocusItemSeed, ...] = (
    FocusItemSeed(
        item_type=FOCUS_ITEM_TYPE_EXPRESSION,
        script="てから",
        reading_kana="てから",
        reading_romanized="te kara",
        meaning_en="after doing",
        mandatory=True,
        exam_relevant=True,
        suggested_priority=100,
        covers_competencies=("linking_actions",),
        stage_min="intermediate",
        example_script="ご飯を食べてから勉強します。",
        example_romanized="gohan o tabete kara benkyou shimasu",
        example_literal_translation="meal object eat after study",
    ),
    FocusItemSeed(
        item_type=FOCUS_ITEM_TYPE_WORD,
        script="それから",
        reading_kana="それから",
        reading_romanized="sorekara",
        meaning_en="after that / and then",
        mandatory=True,
        exam_relevant=True,
        suggested_priority=96,
        covers_competencies=("linking_actions", "discourse_connectors"),
        stage_min="intermediate",
        example_script="宿題をします。それから寝ます。",
        example_romanized="shukudai o shimasu. sorekara nemasu",
        example_literal_translation="homework object do. after that sleep",
    ),
    FocusItemSeed(
        item_type=FOCUS_ITEM_TYPE_EXPRESSION,
        script="食べて",
        reading_kana="たべて",
        reading_romanized="tabete",
        meaning_en="eat and...",
        mandatory=False,
        exam_relevant=True,
        suggested_priority=90,
        covers_competencies=("linking_actions",),
        stage_min="intermediate",
        example_script="朝ご飯を食べて学校に行きます。",
        example_romanized="asagohan o tabete gakkou ni ikimasu",
        example_literal_translation="breakfast object eat and school to go",
    ),
    FocusItemSeed(
        item_type=FOCUS_ITEM_TYPE_EXPRESSION,
        script="見て",
        reading_kana="みて",
        reading_romanized="mite",
        meaning_en="watch / look and...",
        mandatory=False,
        exam_relevant=False,
        suggested_priority=84,
        covers_competencies=("linking_actions",),
        stage_min="intermediate",
        example_script="映画を見てから帰ります。",
        example_romanized="eiga o mite kara kaerimasu",
        example_literal_translation="movie object watch after return",
    ),
    FocusItemSeed(
        item_type=FOCUS_ITEM_TYPE_EXPRESSION,
        script="ながら",
        reading_kana="ながら",
        reading_romanized="nagara",
        meaning_en="while doing",
        mandatory=False,
        exam_relevant=False,
        suggested_priority=80,
        covers_competencies=("linking_actions",),
        stage_min="intermediate",
        example_script="音楽を聞きながら勉強します。",
        example_romanized="ongaku o kikinagara benkyou shimasu",
        example_literal_translation="music object listen while study",
    ),
)

MODALITY_PATTERNS_SEEDS: tuple[FocusItemSeed, ...] = (
    FocusItemSeed(
        item_type=FOCUS_ITEM_TYPE_WORD,
        script="できます",
        reading_kana="できます",
        reading_romanized="dekimasu",
        meaning_en="can do",
        mandatory=True,
        exam_relevant=True,
        suggested_priority=100,
        covers_competencies=("modality",),
        stage_min="intermediate",
        example_script="日本語で会話ができます。",
        example_romanized="nihongo de kaiwa ga dekimasu",
        example_literal_translation="in Japanese conversation subject can do",
    ),
    FocusItemSeed(
        item_type=FOCUS_ITEM_TYPE_EXPRESSION,
        script="たいです",
        reading_kana="たいです",
        reading_romanized="tai desu",
        meaning_en="want to",
        mandatory=True,
        exam_relevant=True,
        suggested_priority=96,
        covers_competencies=("modality",),
        stage_min="intermediate",
        example_script="日本に行きたいです。",
        example_romanized="nihon ni ikitai desu",
        example_literal_translation="to Japan want to go",
    ),
    FocusItemSeed(
        item_type=FOCUS_ITEM_TYPE_EXPRESSION,
        script="てもいいです",
        reading_kana="てもいいです",
        reading_romanized="temo ii desu",
        meaning_en="may / it is okay to",
        mandatory=True,
        exam_relevant=True,
        suggested_priority=94,
        covers_competencies=("modality",),
        stage_min="intermediate",
        example_script="ここで写真を撮ってもいいです。",
        example_romanized="koko de shashin o totte mo ii desu",
        example_literal_translation="here at photo object take may",
    ),
    FocusItemSeed(
        item_type=FOCUS_ITEM_TYPE_EXPRESSION,
        script="なければなりません",
        reading_kana="なければなりません",
        reading_romanized="nakereba narimasen",
        meaning_en="must",
        mandatory=False,
        exam_relevant=True,
        suggested_priority=90,
        covers_competencies=("modality", "formal_register"),
        stage_min="intermediate",
        example_script="明日は早く起きなければなりません。",
        example_romanized="ashita wa hayaku okinakereba narimasen",
        example_literal_translation="tomorrow topic early must wake up",
    ),
    FocusItemSeed(
        item_type=FOCUS_ITEM_TYPE_EXPRESSION,
        script="ほうがいいです",
        reading_kana="ほうがいいです",
        reading_romanized="hou ga ii desu",
        meaning_en="should",
        mandatory=False,
        exam_relevant=False,
        suggested_priority=82,
        covers_competencies=("modality",),
        stage_min="intermediate",
        example_script="少し休んだほうがいいです。",
        example_romanized="sukoshi yasunda hou ga ii desu",
        example_literal_translation="a little rested side is good",
    ),
)

REGISTER_CONTROL_SEEDS: tuple[FocusItemSeed, ...] = (
    FocusItemSeed(
        item_type=FOCUS_ITEM_TYPE_WORD,
        script="です",
        reading_kana="です",
        reading_romanized="desu",
        meaning_en="polite is / am / are",
        mandatory=True,
        exam_relevant=True,
        suggested_priority=100,
        covers_competencies=("register_control",),
        stage_min="intermediate",
        example_script="こちらは静かです。",
        example_romanized="kochira wa shizuka desu",
        example_literal_translation="this place topic quiet is",
    ),
    FocusItemSeed(
        item_type=FOCUS_ITEM_TYPE_WORD,
        script="だ",
        reading_kana="だ",
        reading_romanized="da",
        meaning_en="plain is / am / are",
        mandatory=True,
        exam_relevant=True,
        suggested_priority=96,
        covers_competencies=("register_control",),
        stage_min="intermediate",
        example_script="ここは静かだ。",
        example_romanized="koko wa shizuka da",
        example_literal_translation="here topic quiet is",
    ),
    FocusItemSeed(
        item_type=FOCUS_ITEM_TYPE_WORD,
        script="ます",
        reading_kana="ます",
        reading_romanized="masu",
        meaning_en="polite verb ending",
        mandatory=False,
        exam_relevant=True,
        suggested_priority=90,
        covers_competencies=("register_control",),
        stage_min="intermediate",
        example_script="毎日日本語を勉強します。",
        example_romanized="mainichi nihongo o benkyou shimasu",
        example_literal_translation="every day Japanese object study",
    ),
    FocusItemSeed(
        item_type=FOCUS_ITEM_TYPE_EXPRESSION,
        script="と思います",
        reading_kana="とおもいます",
        reading_romanized="to omoimasu",
        meaning_en="I think",
        mandatory=False,
        exam_relevant=False,
        suggested_priority=86,
        covers_competencies=("register_control", "reasons_experiences"),
        stage_min="intermediate",
        example_script="明日は忙しいと思います。",
        example_romanized="ashita wa isogashii to omoimasu",
        example_literal_translation="tomorrow topic busy I think",
    ),
    FocusItemSeed(
        item_type=FOCUS_ITEM_TYPE_EXPRESSION,
        script="お願いします",
        reading_kana="おねがいします",
        reading_romanized="onegaishimasu",
        meaning_en="please",
        mandatory=False,
        exam_relevant=False,
        suggested_priority=80,
        covers_competencies=("register_control", "formal_register"),
        stage_min="intermediate",
        example_script="確認をお願いします。",
        example_romanized="kakunin o onegaishimasu",
        example_literal_translation="confirmation object please",
    ),
)

REASONS_AND_EXPERIENCES_SEEDS: tuple[FocusItemSeed, ...] = (
    FocusItemSeed(
        item_type=FOCUS_ITEM_TYPE_PARTICLE,
        script="から",
        reading_kana="から",
        reading_romanized="kara",
        function="Gives a direct reason: because.",
        mandatory=True,
        exam_relevant=True,
        suggested_priority=100,
        covers_competencies=("reasons_experiences",),
        stage_min="intermediate",
        example_script="雨だから行きません。",
        example_romanized="ame da kara ikimasen",
        example_literal_translation="because it is rain do not go",
    ),
    FocusItemSeed(
        item_type=FOCUS_ITEM_TYPE_EXPRESSION,
        script="ので",
        reading_kana="ので",
        reading_romanized="node",
        meaning_en="because / so",
        mandatory=True,
        exam_relevant=True,
        suggested_priority=96,
        covers_competencies=("reasons_experiences", "formal_register"),
        stage_min="intermediate",
        example_script="時間がないので急ぎます。",
        example_romanized="jikan ga nai node isogimasu",
        example_literal_translation="because time does not exist hurry",
    ),
    FocusItemSeed(
        item_type=FOCUS_ITEM_TYPE_WORD,
        script="どうして",
        reading_kana="どうして",
        reading_romanized="doushite",
        meaning_en="why",
        mandatory=False,
        exam_relevant=True,
        suggested_priority=90,
        covers_competencies=("reasons_experiences", "basic_questions"),
        stage_min="intermediate",
        example_script="どうして遅れましたか。",
        example_romanized="doushite okuremashita ka",
        example_literal_translation="why were late question",
    ),
    FocusItemSeed(
        item_type=FOCUS_ITEM_TYPE_EXPRESSION,
        script="ことがあります",
        reading_kana="ことがあります",
        reading_romanized="koto ga arimasu",
        meaning_en="have experienced / sometimes",
        mandatory=True,
        exam_relevant=True,
        suggested_priority=92,
        covers_competencies=("reasons_experiences",),
        stage_min="intermediate",
        example_script="日本に行ったことがあります。",
        example_romanized="nihon ni itta koto ga arimasu",
        example_literal_translation="to Japan went experience exists",
    ),
    FocusItemSeed(
        item_type=FOCUS_ITEM_TYPE_EXPRESSION,
        script="行ったことがあります",
        reading_kana="いったことがあります",
        reading_romanized="itta koto ga arimasu",
        meaning_en="have been / have gone before",
        mandatory=False,
        exam_relevant=False,
        suggested_priority=84,
        covers_competencies=("reasons_experiences",),
        stage_min="intermediate",
        example_script="日本に行ったことがあります。",
        example_romanized="nihon ni itta koto ga arimasu",
        example_literal_translation="to Japan went experience exists",
    ),
)

JA_FOCUS_ITEM_SEEDS_BY_TOPIC: dict[str, tuple[FocusItemSeed, ...]] = {
    "identity_and_plans": IDENTITY_AND_PLANS_SEEDS,
    "everyday_verbs": EVERYDAY_VERBS_SEEDS,
    "asking_questions": ASKING_QUESTIONS_SEEDS,
    "daily_routines": DAILY_ROUTINES_SEEDS,
    "basic_greetings": BASIC_GREETINGS_SEEDS,
    "past_negative_patterns": PAST_NEGATIVE_PATTERNS_SEEDS,
    "linking_actions": LINKING_ACTIONS_SEEDS,
    "modality_patterns": MODALITY_PATTERNS_SEEDS,
    "register_control": REGISTER_CONTROL_SEEDS,
    "reasons_and_experiences": REASONS_AND_EXPERIENCES_SEEDS,
}

FOCUS_ITEM_SEEDS_BY_LANGUAGE: dict[str, dict[str, tuple[FocusItemSeed, ...]]] = {
    "ja": JA_FOCUS_ITEM_SEEDS_BY_TOPIC,
}


def _stage_value(value: str | None) -> int:
    return STAGE_ORDER.get(str(value or "").strip().lower(), 0)


def _seed_allowed_for_stage(seed: FocusItemSeed, stage: str) -> bool:
    current = _stage_value(stage)
    minimum = _stage_value(seed.stage_min)
    if current < minimum:
        return False
    if seed.stage_max is not None and current > _stage_value(seed.stage_max):
        return False
    return True


def _normalized_competencies(covers: tuple[str, ...] | list[str] | None) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in covers or ():
        value = str(item or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return tuple(ordered)


def _topic_competencies(seeds: tuple[FocusItemSeed, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for seed in seeds:
        for competency in seed.covers_competencies:
            if competency in seen:
                continue
            seen.add(competency)
            ordered.append(competency)
    return tuple(ordered)


def _seeds_from_competencies(*, language: str, covers: tuple[str, ...]) -> tuple[FocusItemSeed, ...]:
    requested = set(_normalized_competencies(covers))
    if not requested:
        return ()

    topic_map = FOCUS_ITEM_SEEDS_BY_LANGUAGE.get(language, {})
    scored_topics: list[tuple[int, int, int, str]] = []
    for topic_key, seeds in topic_map.items():
        topic_covers = set(_topic_competencies(seeds))
        overlap = len(requested & topic_covers)
        if overlap <= 0:
            continue
        missing = len(requested - topic_covers)
        extra = len(topic_covers - requested)
        scored_topics.append((-overlap, missing, extra, topic_key))

    if not scored_topics:
        return ()

    scored_topics.sort()
    merged: list[FocusItemSeed] = []
    seen_scripts: set[str] = set()
    covered: set[str] = set()
    for _neg_overlap, _missing, _extra, topic_key in scored_topics:
        seeds = topic_map.get(topic_key, ())
        for seed in seeds:
            if seed.script in seen_scripts:
                continue
            if requested and not (requested & set(seed.covers_competencies)):
                continue
            merged.append(seed)
            seen_scripts.add(seed.script)
            covered.update(seed.covers_competencies)
        if requested.issubset(covered):
            break

    logger.info(
        "focus_item_catalog_competency_fallback language=%s requested=%s topics=%s items=%s",
        language,
        ",".join(sorted(requested)),
        ",".join(topic_key for _a, _b, _c, topic_key in scored_topics[:3]),
        len(merged),
    )
    return tuple(merged)


def focus_item_seeds_for_topic(
    *,
    language: str,
    topic_key: str,
    covers: tuple[str, ...] | list[str] | None = None,
) -> tuple[FocusItemSeed, ...]:
    direct = FOCUS_ITEM_SEEDS_BY_LANGUAGE.get(language, {}).get(topic_key, ())
    if direct:
        return direct
    return _seeds_from_competencies(language=language, covers=_normalized_competencies(covers))


def select_focus_item_seeds_for_topic(
    *,
    language: str,
    topic_key: str,
    stage: str,
    covers: tuple[str, ...] | list[str] | None = None,
    max_items: int = 6,
) -> tuple[list[FocusItemSeed], list[FocusItemSeed], list[FocusItemSeed]]:
    seeds = [
        seed
        for seed in focus_item_seeds_for_topic(language=language, topic_key=topic_key, covers=covers)
        if _seed_allowed_for_stage(seed, stage)
    ]
    mandatory = [seed for seed in seeds if seed.mandatory]
    suggested_candidates = [seed for seed in seeds if not seed.mandatory]
    suggested_candidates.sort(key=lambda seed: (-seed.suggested_priority, seed.script))

    selected: list[FocusItemSeed] = list(mandatory)
    seen_scripts = {seed.script for seed in selected}
    for seed in suggested_candidates:
        if len(selected) >= max_items:
            break
        if seed.script in seen_scripts:
            continue
        selected.append(seed)
        seen_scripts.add(seed.script)
    return selected, mandatory, suggested_candidates


def build_fallback_focus_items_for_topic(
    *,
    language: str,
    topic_key: str,
    stage: str,
    covers: tuple[str, ...] | list[str] | None = None,
    max_items: int = 6,
) -> list[dict[str, Any]]:
    selected, _mandatory, _suggested = select_focus_item_seeds_for_topic(
        language=language,
        topic_key=topic_key,
        stage=stage,
        covers=covers,
        max_items=max_items,
    )
    return [seed.to_focus_item().to_payload() for seed in selected]

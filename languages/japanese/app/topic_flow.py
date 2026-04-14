from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
import logging
from random import Random

from .focus_items import FocusItem
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
    focus_items_by_level: dict[int, tuple[FocusItem, ...]] = field(default_factory=dict)

    def lesson_for_level(self, level: int) -> LessonDefinition:
        keys = sorted(self.lessons_by_level.keys())
        if not keys:
            raise ValueError(f"No lessons configured for topic={self.topic_key}")
        normalized_level = min(max(level, keys[0]), keys[-1])
        return self.lessons_by_level[normalized_level]

    def daily_plan_for_level(self, level: int) -> list[tuple[str, str]]:
        return [(item.game_type, item.activity_id_for_level(level)) for item in self.daily_games]

    def focus_items_for_level(self, level: int) -> tuple[FocusItem, ...]:
        keys = sorted(self.focus_items_by_level.keys())
        if not keys:
            return ()
        normalized_level = min(max(level, keys[0]), keys[-1])
        return self.focus_items_by_level.get(normalized_level, ())

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


JA_STANDARD_DAILY_GAMES: tuple[TopicGamePlan, ...] = (
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
)

JA_STANDARD_EXTRA_GAMES: tuple[TopicGamePlan, ...] = (
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
)


def _lesson(
    *,
    title: str,
    objective: str,
    theory_points: tuple[str, ...],
    example_script: str,
    example_romanized: str,
    example_literal_translation: str,
) -> LessonDefinition:
    return LessonDefinition(
        title=title,
        objective=objective,
        theory_points=theory_points,
        example_script=example_script,
        example_romanized=example_romanized,
        example_literal_translation=example_literal_translation,
    )


def _ja_topic(
    *,
    topic_key: str,
    title: str,
    description: str,
    stage: str,
    covers: tuple[str, ...],
    lessons_by_level: dict[int, LessonDefinition],
) -> TopicDefinition:
    return TopicDefinition(
        topic_key=topic_key,
        language="ja",
        title=title,
        description=description,
        lessons_by_level=lessons_by_level,
        daily_games=JA_STANDARD_DAILY_GAMES,
        extra_games=JA_STANDARD_EXTRA_GAMES,
        stage=stage,
        covers=covers,
    )


JA_TOPIC_IDENTITY_AND_PLANS = _ja_topic(
    topic_key="identity_and_plans",
    title="Identity and Daily Plans",
    description="Build sentences about who you are, what happens today, and plans for tomorrow.",
    stage="basic",
    covers=(
        "identity",
        "basic_sentence_roles",
        "time_and_routine",
        "basic_questions",
        "everyday_actions",
    ),
    lessons_by_level={
        1: _lesson(
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
        2: _lesson(
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
        3: _lesson(
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
)

JA_TOPIC_EVERYDAY_VERBS = _ja_topic(
    topic_key="everyday_verbs",
    title="Everyday Verbs",
    description="Practice common actions like eating, going, watching, and studying with short Japanese sentences.",
    stage="basic",
    covers=("everyday_actions", "basic_sentence_roles", "time_and_routine"),
    lessons_by_level={
        1: _lesson(
            title="Core action verbs",
            objective="Recognize common polite-form verbs and the object marker used with them.",
            theory_points=(
                "Japanese action sentences often end with the verb.",
                "Use `o` to mark the direct object before the action.",
                "Keep the action word stable so sentence order stays readable.",
            ),
            example_script="今日は寿司を食べます。",
            example_romanized="kyou wa sushi o tabemasu",
            example_literal_translation="today topic sushi object eat",
        ),
        2: _lesson(
            title="Verb choices in routine statements",
            objective="Swap in different daily verbs while keeping particle order clear.",
            theory_points=(
                "Reuse familiar particles while changing the action verb.",
                "Time words help a short sentence sound more anchored.",
                "Notice how polite verbs often share the `-masu` ending.",
            ),
            example_script="毎日日本語を勉強します。",
            example_romanized="mainichi nihongo o benkyou shimasu",
            example_literal_translation="every day Japanese object study",
        ),
        3: _lesson(
            title="Action chains with destinations and objects",
            objective="Handle longer action statements that mix destinations, objects, and time words.",
            theory_points=(
                "Keep time and destination cues before the final verb.",
                "Object and destination markers help separate roles clearly.",
                "Read the full sentence once before deciding the final action.",
            ),
            example_script="明日駅に行って映画を見ます。",
            example_romanized="ashita eki ni itte eiga o mimasu",
            example_literal_translation="tomorrow station to go and movie object watch",
        ),
    },
)

JA_TOPIC_ASKING_QUESTIONS = _ja_topic(
    topic_key="asking_questions",
    title="Asking Questions",
    description="Form and understand simple Japanese questions with question markers and basic question words.",
    stage="basic",
    covers=("basic_questions", "identity", "basic_sentence_roles"),
    lessons_by_level={
        1: _lesson(
            title="Question marker basics",
            objective="Turn a polite statement into a simple Japanese question.",
            theory_points=(
                "Add `ka` to turn a polite statement into a question.",
                "Question words like `doko` and `nani` anchor the missing information.",
                "Keep the topic early so the listener knows what the question is about.",
            ),
            example_script="駅はどこですか。",
            example_romanized="eki wa doko desu ka",
            example_literal_translation="station topic where is question",
        ),
        2: _lesson(
            title="Short information questions",
            objective="Ask simple what and where questions without changing the core sentence frame.",
            theory_points=(
                "The topic marker still works inside questions.",
                "Question words replace the information you want to know.",
                "The polite question ending keeps the sentence easy to recognize.",
            ),
            example_script="これは何ですか。",
            example_romanized="kore wa nani desu ka",
            example_literal_translation="this topic what is question",
        ),
        3: _lesson(
            title="Question prompts in short exchanges",
            objective="Recognize the same question frame across small dialogue-style sentences.",
            theory_points=(
                "Repeated question frames help you focus on the changing keyword.",
                "Keep track of whether the question asks about a place, thing, or person.",
                "A stable polite ending makes short exchanges easier to parse.",
            ),
            example_script="先生はどこですか。",
            example_romanized="sensei wa doko desu ka",
            example_literal_translation="teacher topic where is question",
        ),
    },
)

JA_TOPIC_DAILY_ROUTINES = _ja_topic(
    topic_key="daily_routines",
    title="Daily Routines",
    description="Talk about repeated actions, today, and tomorrow with familiar routine vocabulary.",
    stage="basic",
    covers=("time_and_routine", "everyday_actions"),
    lessons_by_level={
        1: _lesson(
            title="Time words for routines",
            objective="Use common time anchors such as today, tomorrow, and every day.",
            theory_points=(
                "Time words usually appear early to frame the sentence.",
                "Routine vocabulary helps the listener expect a familiar action.",
                "Short routine statements are easier when time and action stay in a fixed order.",
            ),
            example_script="毎日日本語を勉強します。",
            example_romanized="mainichi nihongo o benkyou shimasu",
            example_literal_translation="every day Japanese object study",
        ),
        2: _lesson(
            title="Today versus tomorrow",
            objective="Contrast actions that happen today with ones planned for tomorrow.",
            theory_points=(
                "A small time change can shift the whole meaning of the sentence.",
                "Keep the action phrase stable while swapping the time word.",
                "Repeated routine patterns make it easier to notice the time anchor.",
            ),
            example_script="今日は寿司を食べます。",
            example_romanized="kyou wa sushi o tabemasu",
            example_literal_translation="today topic sushi object eat",
        ),
        3: _lesson(
            title="Routine statements with plans",
            objective="Mix habits and tomorrow plans while keeping the sentence easy to follow.",
            theory_points=(
                "Daily actions and one-time plans can share the same basic sentence frame.",
                "Time words help you switch between habit and plan quickly.",
                "Read the time phrase first before choosing the rest of the sentence.",
            ),
            example_script="明日友達と映画を見ます。",
            example_romanized="ashita tomodachi to eiga o mimasu",
            example_literal_translation="tomorrow friend with movie object watch",
        ),
    },
)

JA_TOPIC_BASIC_GREETINGS = _ja_topic(
    topic_key="basic_greetings",
    title="Basic Greetings",
    description="Handle common greetings and first-meeting phrases with confident, polite Japanese.",
    stage="basic",
    covers=("identity", "basic_questions"),
    lessons_by_level={
        1: _lesson(
            title="Polite greetings",
            objective="Recognize core greetings used in daily polite Japanese.",
            theory_points=(
                "Many greetings work as fixed chunks that should sound natural as a whole.",
                "A full greeting can matter more than translating each part literally.",
                "Repetition helps these chunks become automatic.",
            ),
            example_script="おはようございます。",
            example_romanized="ohayou gozaimasu",
            example_literal_translation="good morning",
        ),
        2: _lesson(
            title="First-meeting phrases",
            objective="Use simple expressions for introductions and polite first contact.",
            theory_points=(
                "Some useful Japanese phrases are best learned as complete expressions.",
                "Keep the rhythm of the full phrase instead of splitting it too early.",
                "These chunks often appear together in short self-introduction exchanges.",
            ),
            example_script="はじめまして。よろしくお願いします。",
            example_romanized="hajimemashite. yoroshiku onegaishimasu.",
            example_literal_translation="nice to meet you. please treat me favorably.",
        ),
        3: _lesson(
            title="Greeting exchanges with polite questions",
            objective="Move from one-line greetings into short, polite exchanges.",
            theory_points=(
                "A greeting can be followed by a very short polite question.",
                "Question markers stay useful even in social opening phrases.",
                "Keep each sentence compact so the exchange stays easy to understand.",
            ),
            example_script="お元気ですか。",
            example_romanized="ogenki desu ka",
            example_literal_translation="are you well question",
        ),
    },
)

JA_TOPIC_PAST_NEGATIVE_PATTERNS = _ja_topic(
    topic_key="past_negative_patterns",
    title="Past and Negative Patterns",
    description="Describe what did not happen and contrast present negative with past negative forms.",
    stage="intermediate",
    covers=("past_negative", "reasons_experiences"),
    lessons_by_level={
        1: _lesson(
            title="Past negative form anchors",
            objective="Recognize past negative endings in short factual statements.",
            theory_points=(
                "Past negative forms often bundle tense and negation into one chunk.",
                "Time words like `kinou` help confirm that the sentence is about the past.",
                "Treat the negative ending as a meaningful pattern, not as isolated syllables.",
            ),
            example_script="昨日は学校に行きませんでした。",
            example_romanized="kinou wa gakkou ni ikimasen deshita",
            example_literal_translation="yesterday topic school to did not go",
        ),
        2: _lesson(
            title="Present negative versus past negative",
            objective="Tell apart what someone does not do from what they did not do.",
            theory_points=(
                "Japanese negative forms shift meaning when you change only the ending.",
                "The surrounding sentence can stay almost the same while the time changes.",
                "Read the final chunk carefully before deciding whether the action is present or past.",
            ),
            example_script="肉は食べません。",
            example_romanized="niku wa tabemasen",
            example_literal_translation="meat topic do not eat",
        ),
        3: _lesson(
            title="Negative patterns inside fuller statements",
            objective="Track time, topic, and negative endings across longer sentences.",
            theory_points=(
                "Longer sentences often keep the negative meaning near the end.",
                "Use the time phrase to anchor when the negative action happened.",
                "Notice how repeated chunks make advanced negatives easier to decode.",
            ),
            example_script="夜は甘い物を食べません。",
            example_romanized="yoru wa amai mono o tabemasen",
            example_literal_translation="night topic sweet things object do not eat",
        ),
    },
)

JA_TOPIC_LINKING_ACTIONS = _ja_topic(
    topic_key="linking_actions",
    title="Linking Actions",
    description="Connect actions in sequence so Japanese sentences flow beyond a single verb.",
    stage="intermediate",
    covers=("linking_actions", "everyday_actions"),
    lessons_by_level={
        1: _lesson(
            title="Action linking chunks",
            objective="Recognize common connectors used to say one action happens after another.",
            theory_points=(
                "Japanese often links actions with compact connector forms.",
                "The first action sets context for the one that follows.",
                "Reading the link as one chunk makes multi-step sentences easier to decode.",
            ),
            example_script="ご飯を食べてから勉強します。",
            example_romanized="gohan o tabete kara benkyou shimasu",
            example_literal_translation="meal object eat after study",
        ),
        2: _lesson(
            title="Chaining everyday events",
            objective="Follow two-step Japanese routines without losing the order of actions.",
            theory_points=(
                "The connector tells you whether the second action follows immediately or more loosely.",
                "Objects and verbs still keep their own roles inside a chain.",
                "Notice where the final polite verb lands in the sentence.",
            ),
            example_script="朝ご飯を食べて学校に行きます。",
            example_romanized="asagohan o tabete gakkou ni ikimasu",
            example_literal_translation="breakfast object eat and school to go",
        ),
        3: _lesson(
            title="Sequence markers across full routines",
            objective="Read a short chain of actions as a connected timeline.",
            theory_points=(
                "Words like `sorekara` signal a transition to the next step.",
                "A sequence can still be clear even when the actions are short.",
                "Track the action order before translating each verb literally.",
            ),
            example_script="宿題をします。それから寝ます。",
            example_romanized="shukudai o shimasu. sorekara nemasu",
            example_literal_translation="homework object do. after that sleep",
        ),
    },
)

JA_TOPIC_MODALITY_PATTERNS = _ja_topic(
    topic_key="modality_patterns",
    title="Modality Patterns",
    description="Express ability, desire, permission, and obligation in Japanese with stable sentence patterns.",
    stage="intermediate",
    covers=("modality", "register_control"),
    lessons_by_level={
        1: _lesson(
            title="Ability and desire patterns",
            objective="Recognize common patterns for can, want, and similar intentions.",
            theory_points=(
                "Modality often appears as a reusable chunk attached to the end of a phrase.",
                "These patterns change the speaker's stance more than the core action itself.",
                "Keep the action phrase stable so the modal meaning stands out clearly.",
            ),
            example_script="日本に行きたいです。",
            example_romanized="nihon ni ikitai desu",
            example_literal_translation="Japan to want to go",
        ),
        2: _lesson(
            title="Permission and obligation",
            objective="Tell apart what is allowed from what is required.",
            theory_points=(
                "Permission and obligation can sound similar if you only watch the final words.",
                "Read the whole modal chunk before deciding the meaning.",
                "These forms are useful because they stay stable across many verbs.",
            ),
            example_script="ここで写真を撮ってもいいです。",
            example_romanized="koko de shashin o totte mo ii desu",
            example_literal_translation="here at photo object take may be good",
        ),
        3: _lesson(
            title="Advice and stronger stance",
            objective="Handle should and must patterns inside fuller polite statements.",
            theory_points=(
                "Advice sounds softer than obligation even when both patterns come near the end.",
                "Modal chunks often work best when learned as complete expressions.",
                "Use the sentence context to tell whether the speaker is allowing, recommending, or requiring something.",
            ),
            example_script="明日は早く起きなければなりません。",
            example_romanized="ashita wa hayaku okinakereba narimasen",
            example_literal_translation="tomorrow topic early wake must",
        ),
    },
)

JA_TOPIC_REGISTER_CONTROL = _ja_topic(
    topic_key="register_control",
    title="Register Control",
    description="Switch between plain and polite Japanese in ways that fit the situation.",
    stage="intermediate",
    covers=("register_control", "identity"),
    lessons_by_level={
        1: _lesson(
            title="Polite versus plain anchors",
            objective="Notice how polite and plain endings shift the tone of a sentence.",
            theory_points=(
                "Register changes often appear in the final chunk of the sentence.",
                "The same idea can sound more direct or more polite with only a small ending change.",
                "Compare endings before translating the whole sentence.",
            ),
            example_script="こちらは静かです。",
            example_romanized="kochira wa shizuka desu",
            example_literal_translation="this side topic quiet is",
        ),
        2: _lesson(
            title="Plain style inside opinions",
            objective="Recognize plain-style forms when they appear inside longer statements.",
            theory_points=(
                "Japanese can mix polite framing with plain forms inside quoted thoughts.",
                "A plain form does not always mean the whole sentence is informal.",
                "Pay attention to where the quoted or embedded thought begins.",
            ),
            example_script="明日は忙しいと思います。",
            example_romanized="ashita wa isogashii to omoimasu",
            example_literal_translation="tomorrow topic busy I think",
        ),
        3: _lesson(
            title="Polite requests in context",
            objective="Use polite request language without losing the main sentence meaning.",
            theory_points=(
                "Request chunks often travel as set expressions.",
                "A polite request can soften the whole tone of an interaction.",
                "Treat high-frequency polite chunks as reusable language blocks.",
            ),
            example_script="確認をお願いします。",
            example_romanized="kakunin o onegaishimasu",
            example_literal_translation="confirmation object please",
        ),
    },
)

JA_TOPIC_REASONS_AND_EXPERIENCES = _ja_topic(
    topic_key="reasons_and_experiences",
    title="Reasons and Experiences",
    description="Explain why something happens and talk about experiences you have had before.",
    stage="intermediate",
    covers=("reasons_experiences", "basic_questions", "past_negative"),
    lessons_by_level={
        1: _lesson(
            title="Direct reasons",
            objective="Recognize short reason phrases that explain why an action happens or does not happen.",
            theory_points=(
                "Reason markers often come just before the conclusion they support.",
                "Direct and softer reason markers can sound different in tone.",
                "Read the reason chunk first, then connect it to the result.",
            ),
            example_script="雨だから行きません。",
            example_romanized="ame dakara ikimasen",
            example_literal_translation="because it is rain do not go",
        ),
        2: _lesson(
            title="Softer reason framing",
            objective="Differentiate stronger because from a softer explanatory because.",
            theory_points=(
                "Japanese has more than one way to mark a reason.",
                "The reason marker can subtly shift the tone of the sentence.",
                "Keep the reason chunk and the result chunk mentally separated.",
            ),
            example_script="時間がないので急ぎます。",
            example_romanized="jikan ga nai node isogimasu",
            example_literal_translation="time subject not exist because hurry",
        ),
        3: _lesson(
            title="Talking about prior experience",
            objective="Handle patterns that say someone has had an experience before.",
            theory_points=(
                "Experience expressions often work as larger fixed patterns.",
                "These chunks are easier to remember as one unit than as separate words.",
                "Look for the completed-action part before the experience marker.",
            ),
            example_script="日本に行ったことがあります。",
            example_romanized="nihon ni itta koto ga arimasu",
            example_literal_translation="Japan to went experience subject exists",
        ),
    },
)

JA_TOPIC_CONDITIONAL_PATTERNS = _ja_topic(
    topic_key="conditional_patterns",
    title="Conditional Patterns",
    description="Work with if, when, and even-if style Japanese conditionals across short and longer statements.",
    stage="advanced",
    covers=("conditionals", "discourse_connectors"),
    lessons_by_level={
        1: _lesson(
            title="Conditional markers in short clauses",
            objective="Recognize the major Japanese conditional forms as reusable patterns.",
            theory_points=(
                "Japanese conditionals often look similar unless you read the full marker carefully.",
                "Each conditional can carry a slightly different nuance.",
                "Anchor the condition first, then read the result clause.",
            ),
            example_script="時間があったら、連絡してください。",
            example_romanized="jikan ga attara, renraku shite kudasai",
            example_literal_translation="if there is time, please contact me",
        ),
        2: _lesson(
            title="Scenario-based conditionals",
            objective="Compare multiple if-forms inside practical everyday scenarios.",
            theory_points=(
                "The condition can describe a state, not only an action.",
                "Small changes in the conditional marker shift how direct or hypothetical the sentence feels.",
                "Read the left side of the sentence as the setup for the result.",
            ),
            example_script="静かなら、ここで勉強できます。",
            example_romanized="shizuka nara, koko de benkyou dekimasu",
            example_literal_translation="if it is quiet, can study here",
        ),
        3: _lesson(
            title="Concessive meaning",
            objective="Handle even-if style meaning without losing the core result clause.",
            theory_points=(
                "Some conditional-looking forms actually mean even if rather than if.",
                "The result clause can stay firm even when the condition changes.",
                "Check whether the sentence expresses a requirement or a concession.",
            ),
            example_script="遅くても行きます。",
            example_romanized="osokute mo ikimasu",
            example_literal_translation="even if late, go",
        ),
    },
)

JA_TOPIC_SUBORDINATION_PATTERNS = _ja_topic(
    topic_key="subordination_patterns",
    title="Subordination Patterns",
    description="Read embedded actions and subordinate ideas that make Japanese sentences denser and more precise.",
    stage="advanced",
    covers=("subordination", "time_and_routine"),
    lessons_by_level={
        1: _lesson(
            title="Time-linked subordinate phrases",
            objective="Recognize subordinate chunks that anchor when an action happens.",
            theory_points=(
                "Subordinate phrases often appear before the main clause they support.",
                "Time expressions like before, after, and when can work as larger chunks.",
                "Read the subordinate part fully before jumping to the main action.",
            ),
            example_script="寝る前に本を読みます。",
            example_romanized="neru mae ni hon o yomimasu",
            example_literal_translation="before sleeping book object read",
        ),
        2: _lesson(
            title="Nominalized and abstract actions",
            objective="Handle forms that turn actions into abstract things or embedded statements.",
            theory_points=(
                "Japanese can package an action into a noun-like chunk.",
                "These forms often support opinions, rules, or abstract statements.",
                "Treat the embedded action as one unit before reading the rest.",
            ),
            example_script="早く帰ることが大切です。",
            example_romanized="hayaku kaeru koto ga taisetsu desu",
            example_literal_translation="return early thing subject important is",
        ),
        3: _lesson(
            title="In-progress and point-in-time phrases",
            objective="Read advanced subordinate expressions that describe the point or timing of an action.",
            theory_points=(
                "A subordinate chunk can describe the exact point inside an action.",
                "These expressions often feel abstract until you read the entire phrase.",
                "Use the final clause to confirm how the subordinate phrase is functioning.",
            ),
            example_script="ちょうど出かけるところです。",
            example_romanized="choudo dekakeru tokoro desu",
            example_literal_translation="just at the point of going out",
        ),
    },
)

JA_TOPIC_VOICE_AND_VALENCY = _ja_topic(
    topic_key="voice_and_valency",
    title="Voice and Valency",
    description="Tell apart who acts, what changes on its own, and how passive or transitive patterns alter the sentence.",
    stage="advanced",
    covers=("voice_and_valency", "basic_sentence_roles"),
    lessons_by_level={
        1: _lesson(
            title="Transitive and intransitive pairs",
            objective="See how Japanese changes meaning when an action affects something versus happens on its own.",
            theory_points=(
                "Some verb pairs look related but describe different sentence roles.",
                "Particles often help reveal whether the action is transitive or intransitive.",
                "Focus on who acts and what changes in the sentence.",
            ),
            example_script="ドアが開きます。",
            example_romanized="doa ga akimasu",
            example_literal_translation="door subject opens",
        ),
        2: _lesson(
            title="Cause versus change of state",
            objective="Compare verbs that break or open something with verbs that describe becoming broken or open.",
            theory_points=(
                "Valency changes often shift the particle pattern along with the verb.",
                "The same situation can be framed from the actor side or the result side.",
                "Read the verb and particle together rather than in isolation.",
            ),
            example_script="機械が壊れました。",
            example_romanized="kikai ga kowaremashita",
            example_literal_translation="machine subject became broken",
        ),
        3: _lesson(
            title="Passive perspective",
            objective="Recognize passive-style expressions that shift perspective toward what was done.",
            theory_points=(
                "Passive forms often move attention away from the actor.",
                "The sentence perspective changes even if the event itself stays the same.",
                "Watch the passive ending carefully before deciding who did what.",
            ),
            example_script="先生にほめられました。",
            example_romanized="sensei ni homeraremashita",
            example_literal_translation="by teacher was praised",
        ),
    },
)

JA_TOPIC_DISCOURSE_CONNECTORS = _ja_topic(
    topic_key="discourse_connectors",
    title="Discourse Connectors",
    description="Connect ideas across sentences with contrast, consequence, reformulation, and persistence markers.",
    stage="advanced",
    covers=("discourse_connectors", "reasons_experiences"),
    lessons_by_level={
        1: _lesson(
            title="Contrast and consequence",
            objective="Track how Japanese links ideas beyond a single sentence.",
            theory_points=(
                "Connectors shape the relationship between the sentence before and after them.",
                "A connector can show contrast, result, summary, or persistence.",
                "Read the connector first to predict the logic that follows.",
            ),
            example_script="行きたいです。しかし、時間がありません。",
            example_romanized="ikitai desu. shikashi, jikan ga arimasen",
            example_literal_translation="want to go. however, time does not exist",
        ),
        2: _lesson(
            title="Result and reformulation signals",
            objective="Use connectors to explain outcomes and restate ideas clearly.",
            theory_points=(
                "Some connectors point forward to a result.",
                "Others signal that the next sentence reframes the previous one.",
                "These words help you follow logic across multiple clauses.",
            ),
            example_script="電車が遅れました。そのため、会議に遅れました。",
            example_romanized="densha ga okuremashita. sonotame, kaigi ni okuremashita",
            example_literal_translation="the train was delayed. therefore, was late to the meeting",
        ),
        3: _lesson(
            title="Holding a position despite contrast",
            objective="Read connectors that keep an idea going even after a difficulty or contrast appears.",
            theory_points=(
                "Advanced connectors often tell you how to interpret the next sentence before you read it.",
                "Concessive connectors are especially important in longer discourse.",
                "Notice whether the second sentence reverses, supports, or survives the first one.",
            ),
            example_script="難しいです。それでも続けます。",
            example_romanized="muzukashii desu. soredemo tsuzukemasu",
            example_literal_translation="it is difficult. even so continue",
        ),
    },
)

JA_TOPIC_FORMAL_REGISTER_PATTERNS = _ja_topic(
    topic_key="formal_register_patterns",
    title="Formal Register Patterns",
    description="Handle advanced polite and formal Japanese phrases used in professional or service-style contexts.",
    stage="advanced",
    covers=("formal_register", "register_control"),
    lessons_by_level={
        1: _lesson(
            title="Formal existence and service phrasing",
            objective="Recognize formal alternatives to standard polite Japanese.",
            theory_points=(
                "Formal Japanese often uses specialized set phrases instead of simple polite equivalents.",
                "These expressions are best learned as full chunks.",
                "The goal is not only correctness but also appropriate social tone.",
            ),
            example_script="ご不明な点がございます。",
            example_romanized="gofumei na ten ga gozaimasu",
            example_literal_translation="there are unclear points",
        ),
        2: _lesson(
            title="Humble action language",
            objective="Read formal phrases that present the speaker's actions in a humble way.",
            theory_points=(
                "Formal register can shift the relationship between speaker and listener.",
                "A humble form often replaces a simpler everyday verb.",
                "Read these patterns as social signals as much as grammatical ones.",
            ),
            example_script="こちらで確認いたします。",
            example_romanized="kochira de kakunin itashimasu",
            example_literal_translation="we will humbly confirm here",
        ),
        3: _lesson(
            title="High-formality requests",
            objective="Handle polite requests and apologies used in formal service or workplace settings.",
            theory_points=(
                "Formal requests often layer several fixed expressions together.",
                "The sentence may be long, but the key chunks repeat across contexts.",
                "Treat the request frame as one reusable social pattern.",
            ),
            example_script="恐れ入りますが、もう一度お願いいたします。",
            example_romanized="osoreirimasu ga, mou ichido onegai itashimasu",
            example_literal_translation="I am sorry to trouble you, but please once more",
        ),
    },
)

# The static roadmap is intentionally broad so the app can keep progressing across
# all stages even when topic generation is unavailable.
TOPICS_BY_LANGUAGE: dict[str, tuple[TopicDefinition, ...]] = {
    "ja": (
        JA_TOPIC_IDENTITY_AND_PLANS,
        JA_TOPIC_EVERYDAY_VERBS,
        JA_TOPIC_ASKING_QUESTIONS,
        JA_TOPIC_DAILY_ROUTINES,
        JA_TOPIC_BASIC_GREETINGS,
        JA_TOPIC_PAST_NEGATIVE_PATTERNS,
        JA_TOPIC_LINKING_ACTIONS,
        JA_TOPIC_MODALITY_PATTERNS,
        JA_TOPIC_REGISTER_CONTROL,
        JA_TOPIC_REASONS_AND_EXPERIENCES,
        JA_TOPIC_CONDITIONAL_PATTERNS,
        JA_TOPIC_SUBORDINATION_PATTERNS,
        JA_TOPIC_VOICE_AND_VALENCY,
        JA_TOPIC_DISCOURSE_CONNECTORS,
        JA_TOPIC_FORMAL_REGISTER_PATTERNS,
    ),
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

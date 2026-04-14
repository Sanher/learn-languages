import unittest

from languages.japanese.app.focus_item_catalog import (
    build_fallback_focus_items_for_topic,
    select_focus_item_seeds_for_topic,
)


class FocusItemCatalogTests(unittest.TestCase):
    def test_identity_and_plans_catalog_returns_core_items_first(self) -> None:
        selected, mandatory, suggested = select_focus_item_seeds_for_topic(
            language="ja",
            topic_key="identity_and_plans",
            stage="basic",
            max_items=6,
        )

        self.assertGreaterEqual(len(mandatory), 4)
        self.assertTrue(suggested)
        self.assertTrue(any(seed.script == "は" for seed in mandatory))
        self.assertTrue(any(seed.script == "私" for seed in mandatory))
        self.assertEqual([seed.script for seed in selected[: len(mandatory)]], [seed.script for seed in mandatory])

    def test_identity_and_plans_basic_catalog_hides_expression(self) -> None:
        payload = build_fallback_focus_items_for_topic(
            language="ja",
            topic_key="identity_and_plans",
            stage="basic",
            max_items=8,
        )

        self.assertFalse(any(item["item_type"] == "expression" for item in payload))
        self.assertTrue(any(item["is_core"] for item in payload))
        self.assertTrue(any(item["is_exam_relevant"] for item in payload))

    def test_identity_and_plans_intermediate_catalog_allows_expression(self) -> None:
        payload = build_fallback_focus_items_for_topic(
            language="ja",
            topic_key="identity_and_plans",
            stage="intermediate",
            max_items=12,
        )

        self.assertTrue(any(item["item_type"] == "expression" for item in payload))

    def test_everyday_verbs_basic_catalog_focuses_on_routine_actions(self) -> None:
        payload = build_fallback_focus_items_for_topic(
            language="ja",
            topic_key="everyday_verbs",
            stage="basic",
            max_items=8,
        )

        scripts = {item["script"] for item in payload}
        self.assertIn("食べます", scripts)
        self.assertIn("行きます", scripts)
        self.assertIn("を", scripts)

    def test_asking_questions_basic_catalog_includes_question_markers(self) -> None:
        payload = build_fallback_focus_items_for_topic(
            language="ja",
            topic_key="asking_questions",
            stage="basic",
            max_items=8,
        )

        scripts = {item["script"] for item in payload}
        self.assertIn("か", scripts)
        self.assertIn("どこ", scripts)
        self.assertIn("何", scripts)

    def test_daily_routines_basic_catalog_highlights_time_words(self) -> None:
        payload = build_fallback_focus_items_for_topic(
            language="ja",
            topic_key="daily_routines",
            stage="basic",
            max_items=8,
        )

        scripts = {item["script"] for item in payload}
        self.assertIn("毎日", scripts)
        self.assertIn("今日", scripts)
        self.assertIn("明日", scripts)

    def test_basic_greetings_basic_catalog_uses_lexical_chunks(self) -> None:
        payload = build_fallback_focus_items_for_topic(
            language="ja",
            topic_key="basic_greetings",
            stage="basic",
            max_items=8,
        )

        scripts = {item["script"] for item in payload}
        self.assertIn("おはようございます", scripts)
        self.assertIn("はじめまして", scripts)
        self.assertFalse(any(item["item_type"] == "expression" for item in payload))

    def test_unknown_basic_topic_can_fallback_by_competency_coverage(self) -> None:
        payload = build_fallback_focus_items_for_topic(
            language="ja",
            topic_key="unknown_basic_topic",
            stage="basic",
            covers=("identity", "basic_questions"),
            max_items=8,
        )

        scripts = {item["script"] for item in payload}
        self.assertTrue(payload)
        self.assertTrue({"か", "どこ"} & scripts)
        self.assertTrue(any(item["is_exam_relevant"] for item in payload))

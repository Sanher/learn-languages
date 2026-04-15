import unittest

from languages.japanese.app.focus_items import (
    FOCUS_ITEM_TYPE_EXPRESSION,
    FOCUS_ITEM_TYPE_KANJI,
    FOCUS_ITEM_TYPE_PARTICLE,
    focus_item_type_allowed_for_stage,
    merge_focus_item_payloads,
    normalize_focus_item,
    normalize_focus_items,
)


class FocusItemTests(unittest.TestCase):
    def test_normalize_focus_item_accepts_particle_with_function_only(self) -> None:
        item = normalize_focus_item(
            {
                "item_type": FOCUS_ITEM_TYPE_PARTICLE,
                "script": "に",
                "reading_kana": "に",
                "reading_romanized": "ni",
                "function": "Marks destination or time depending on context.",
            }
        )

        self.assertIsNotNone(item)
        assert item is not None
        self.assertEqual(item.item_type, FOCUS_ITEM_TYPE_PARTICLE)
        self.assertIsNone(item.meaning_en)
        self.assertEqual(item.function, "Marks destination or time depending on context.")

    def test_normalize_focus_item_rejects_items_without_meaning_or_function(self) -> None:
        item = normalize_focus_item(
            {
                "item_type": FOCUS_ITEM_TYPE_KANJI,
                "script": "私",
                "reading_kana": "わたし",
            }
        )
        self.assertIsNone(item)

    def test_normalize_focus_items_filters_expression_out_of_basic_stage(self) -> None:
        items = normalize_focus_items(
            [
                {
                    "item_type": FOCUS_ITEM_TYPE_EXPRESSION,
                    "script": "よろしくお願いします",
                    "reading_kana": "よろしくおねがいします",
                    "reading_romanized": "yoroshiku onegaishimasu",
                    "meaning_en": "Please treat me kindly.",
                }
            ],
            stage="basic",
        )
        self.assertEqual(items, [])

    def test_normalize_focus_items_keeps_expression_for_intermediate(self) -> None:
        items = normalize_focus_items(
            [
                {
                    "item_type": FOCUS_ITEM_TYPE_EXPRESSION,
                    "script": "よろしくお願いします",
                    "reading_kana": "よろしくおねがいします",
                    "reading_romanized": "yoroshiku onegaishimasu",
                    "meaning_en": "Please treat me kindly.",
                }
            ],
            stage="intermediate",
        )
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["item_type"], FOCUS_ITEM_TYPE_EXPRESSION)

    def test_focus_item_type_allowed_for_stage_matches_rank_policy(self) -> None:
        self.assertFalse(focus_item_type_allowed_for_stage(FOCUS_ITEM_TYPE_EXPRESSION, "basic"))
        self.assertTrue(focus_item_type_allowed_for_stage(FOCUS_ITEM_TYPE_EXPRESSION, "intermediate"))
        self.assertTrue(focus_item_type_allowed_for_stage(FOCUS_ITEM_TYPE_KANJI, "basic"))

    def test_merge_focus_item_payloads_keeps_catalog_structure_and_adds_optional_fields(self) -> None:
        merged = merge_focus_item_payloads(
            [
                {
                    "item_id": "particle-は",
                    "item_type": FOCUS_ITEM_TYPE_PARTICLE,
                    "script": "は",
                    "reading_kana": "は",
                    "reading_romanized": "wa",
                    "function": "Marks the topic of the sentence.",
                    "is_core": True,
                    "is_exam_relevant": True,
                    "covers_competencies": ["identity"],
                    "source": "catalog",
                }
            ],
            [
                {
                    "item_id": "particle-は",
                    "item_type": FOCUS_ITEM_TYPE_PARTICLE,
                    "script": "は",
                    "meaning_secondary": "Marca el tema de la oración.",
                    "example_script": "私は学生です。",
                    "example_secondary_translation": "Soy estudiante.",
                    "example_romanized": "watashi wa gakusei desu",
                    "example_literal_translation": "I topic student am",
                }
            ],
            stage="basic",
        )

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["function"], "Marks the topic of the sentence.")
        self.assertEqual(merged[0]["meaning_secondary"], "Marca el tema de la oración.")
        self.assertEqual(merged[0]["example_script"], "私は学生です。")
        self.assertEqual(merged[0]["example_secondary_translation"], "Soy estudiante.")
        self.assertTrue(merged[0]["is_core"])
        self.assertTrue(merged[0]["is_exam_relevant"])
        self.assertEqual(merged[0]["source"], "catalog+openai")

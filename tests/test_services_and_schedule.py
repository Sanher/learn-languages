from datetime import date, datetime
import unittest

from language_games.orchestrator import GamesOrchestrator
from language_games.policy import language_for_date
from language_games.scheduling import LanguageScheduleConfig, NotificationRule
from language_games.services import GameActivity, GameServiceRegistry, InMemoryGameService


class ServicesAndScheduleTests(unittest.TestCase):
    def test_language_policy_is_configurable(self) -> None:
        custom = LanguageScheduleConfig(
            default_language="en",
            language_by_weekday={0: "ja", 1: "ja", 2: "ja", 3: "ja", 4: "ja", 5: "en", 6: "en"},
            notifications_by_language={},
        )
        self.assertEqual(language_for_date(date(2026, 2, 12), config=custom), "ja")  # Thursday
        self.assertEqual(language_for_date(date(2026, 2, 14), config=custom), "en")  # Saturday

    def test_notifications_by_day_and_time(self) -> None:
        config = LanguageScheduleConfig(
            default_language="ja",
            language_by_weekday={},
            notifications_by_language={
                "ja": [NotificationRule(weekday=0, hour=8, minute=0)],
                "en": [NotificationRule(weekday=5, hour=10, minute=30)],
            },
        )

        monday_target = datetime(2026, 2, 16, 8, 0)
        saturday_target = datetime(2026, 2, 14, 10, 30)

        self.assertEqual(config.pending_notifications(monday_target), ["ja"])
        self.assertEqual(config.pending_notifications(saturday_target), ["en"])

    def test_registry_returns_language_specific_activities(self) -> None:
        registry = GameServiceRegistry()
        registry.register(
            InMemoryGameService(
                game_type="vocab_match",
                activities_by_language={
                    "ja": [
                        GameActivity(
                            activity_id="ja-vocab-1",
                            language="ja",
                            game_type="vocab_match",
                            prompt="Relaciona hiragana con su lectura.",
                            level=1,
                        )
                    ],
                    "en": [
                        GameActivity(
                            activity_id="en-vocab-1",
                            language="en",
                            game_type="vocab_match",
                            prompt="Match words with definitions.",
                            level=1,
                        )
                    ],
                },
            )
        )

        config = LanguageScheduleConfig(
            default_language="en",
            language_by_weekday={0: "ja", 1: "ja", 2: "ja", 3: "ja", 4: "ja", 5: "en", 6: "en"},
            notifications_by_language={},
        )
        orchestrator = GamesOrchestrator(registry=registry, schedule_config=config)

        friday = datetime(2026, 2, 13, 12, 0)
        saturday = datetime(2026, 2, 14, 12, 0)

        friday_result = orchestrator.daily_games(friday, game_types=["vocab_match"], level=1)
        saturday_result = orchestrator.daily_games(saturday, game_types=["vocab_match"], level=1)

        self.assertEqual(friday_result.language, "ja")
        self.assertEqual(friday_result.activities["vocab_match"].activity_id, "ja-vocab-1")
        self.assertEqual(saturday_result.language, "en")
        self.assertEqual(saturday_result.activities["vocab_match"].activity_id, "en-vocab-1")


if __name__ == "__main__":
    unittest.main()

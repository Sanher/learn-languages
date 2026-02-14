from datetime import date
from pprint import pprint

from language_games.pronunciation import PronunciationRequest, run_pronunciation_activity


if __name__ == "__main__":
    request = PronunciationRequest(
        expected_text="おはよう ございます",
        recognized_text="おはよう ございます",
        audio_duration_seconds=2.9,
        speech_seconds=2.2,
        pause_seconds=0.5,
        pitch_track_hz=[170, 176, 181, 177, 169],
    )

    result = run_pronunciation_activity(request=request, current_date=date.today())
    pprint(result)

from pipeline.text_extractor import _parse_vision_response


def test_vision_response_extracts_english_dialogue_and_russian_visual_description():
    raw = """TEXT:
I will protect this village.
Are you ready?

VISUAL:
Высокий парень в плаще закрывает собой испуганную девушку; позади них горит дом."""
    dialogue, description = _parse_vision_response(raw)
    assert dialogue == "I will protect this village.\nAre you ready?"
    assert "парень в плаще" in description
    assert "горит дом" in description


def test_vision_response_keeps_visual_description_when_no_dialogue():
    raw = """TEXT:
NONE
VISUAL:
Воин поднимает меч перед огромным чудовищем."""
    dialogue, description = _parse_vision_response(raw)
    assert dialogue == ""
    assert "поднимает меч" in description


def test_vision_response_ignores_non_latin_dialogue_but_keeps_scene_description():
    raw = """TEXT:
こんにちは
VISUAL:
Девушка стоит у окна и смотрит на ночной город."""
    dialogue, description = _parse_vision_response(raw)
    assert dialogue == ""
    assert "ночной город" in description

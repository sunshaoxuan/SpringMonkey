import pytest

from activate_flare import configured_cron
import activate_flare


WEATHER = "0 7 * * * root helper --name weather-report-jst-0700 --channel-id 123 --command env OPENCLAW_WEATHER_IMAGE_MODEL_CANDIDATES=openai/gpt-image-2 python3 weather.py\n"


def test_model_switch_preserves_schedule_destination_and_other_jobs():
    other = "0 9 * * * root helper --name news-report --command python3 news.py\n"
    source = "SHELL=/bin/bash\n" + WEATHER + other
    changed = configured_cron(source)
    assert changed == source.replace("=openai/gpt-image-2 ", "=openai/gpt-image-2.5-flare ")
    assert configured_cron(changed) == changed


@pytest.mark.parametrize("source", ["", "# " + WEATHER, WEATHER + WEATHER, WEATHER.replace("OPENCLAW_WEATHER_IMAGE_MODEL_CANDIDATES", "OTHER")])
def test_missing_ambiguous_or_unrecognized_configuration_is_rejected(source):
    with pytest.raises(ValueError):
        configured_cron(source)


def test_activation_backs_up_original_and_is_idempotent(tmp_path, monkeypatch):
    path = tmp_path / "cron"
    path.write_text(WEATHER, encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["activate_flare", "--path", str(path)])
    assert activate_flare.main() == 0
    assert path.read_text(encoding="utf-8") == configured_cron(WEATHER)
    backup = path.with_name(path.name + ".pre-flare-20260915.bak")
    assert backup.read_text(encoding="utf-8") == WEATHER
    assert activate_flare.main() == 0
    assert backup.read_text(encoding="utf-8") == WEATHER

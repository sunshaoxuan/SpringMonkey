from pathlib import Path

import pytest

from repair_delivery_gate import repaired_source


SOURCE = '''from pathlib import Path
def should_deliver_public(name, message):
    if name.startswith("weather-report-"):
        path = Path(message.removeprefix("MEDIA:"))
        return path.is_file() and path.name.endswith("_image2.png") and path.stat().st_size >= 100000
    return True
'''


def test_repair_accepts_actual_output_and_preserves_quality_gate(tmp_path: Path):
    source = repaired_source(SOURCE)
    scope = {}
    exec(source, scope)
    check = scope["should_deliver_public"]
    image = tmp_path / "weather_model.png"
    image.write_bytes(b"x" * 100000)
    assert check("weather-report-jst-0700", "MEDIA:" + str(image))
    image.write_bytes(b"x")
    assert not check("weather-report-jst-0700", "MEDIA:" + str(image))
    assert check("other-job", "unchanged")
    assert repaired_source(source) == source


def test_repair_rejects_unrecognized_gate():
    with pytest.raises(ValueError):
        repaired_source(SOURCE.replace("_image2.png", "_unknown.png"))

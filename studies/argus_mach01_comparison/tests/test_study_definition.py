import json
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]


def test_low_speed_definition_is_fixed_cl() -> None:
    config = json.loads(
        (PROJECT / "config" / "study_config.json").read_text(encoding="utf-8")
    )
    assert config["mach"] == 0.1
    assert 0.4 < config["target_CL"] < 0.7
    assert "fixed-CL" in config["definition"]


def test_concept_regions_are_explicit() -> None:
    config = json.loads(
        (PROJECT / "config" / "study_config.json").read_text(encoding="utf-8")
    )
    assert config["concept_regions"]["trailing_edge"] == [0.6, 1.0]
    assert config["concept_regions"]["twist"] == [0.6, 1.0]
    assert config["concept_regions"]["conventional_hinged"] == [0.71, 0.97]



import pytest

from music2midi.generate.prompts import build_user_prompt
from music2midi.generate.styles import STYLES, detect_style, get_style, list_styles


def test_registry_populated_and_unique():
    presets = list_styles()
    assert len(presets) >= 24
    ids = [p.id for p in presets]
    assert len(ids) == len(set(ids)), "duplicate style ids"


def test_every_preset_is_well_formed():
    for p in list_styles():
        assert p.instruments, f"{p.id} has no instruments"
        assert p.tempo[0] < p.tempo[1], f"{p.id} tempo range invalid"
        assert p.tempo[0] <= p.default_tempo <= p.tempo[1]
        for _, gm in (*p.instruments, p.bass):
            assert 0 <= gm <= 127, f"{p.id} GM program out of range"
        assert all(c.startswith("#") and len(c) == 7 for c in p.palette)


def test_get_style_by_id_and_alias():
    assert get_style("russian_folk").id == "russian_folk"
    assert get_style("balalaika").id == "russian_folk"
    assert get_style("EDM").id == "edm_house"


def test_get_style_unknown_lists_catalog():
    with pytest.raises(KeyError, match="russian_folk"):
        get_style("does-not-exist")


@pytest.mark.parametrize(
    "text,expected",
    [
        ("nhạc dân ca nga buồn", "russian_folk"),
        ("a relaxing lofi beat to study", "lofi"),
        ("nhạc có âm hưởng không gian, chậm rãi", "space_ambient"),
        ("nhạc cổ Trung Quốc với guzheng", "chinese_classical"),
        ("epic cinematic trailer music", "epic_cinematic"),
        ("một bản tango kịch tính", "tango"),
    ],
)
def test_detect_style_from_prompt(text, expected):
    preset = detect_style(text)
    assert preset is not None and preset.id == expected


def test_detect_style_word_boundary_avoids_false_positive():
    # 'nga' must not fire inside unrelated Vietnamese words like 'ngang'.
    assert detect_style("một giai điệu đi ngang nhẹ nhàng") is None


def test_prompt_block_contains_key_fields():
    block = STYLES["chinese_classical"].prompt_block()
    assert "pentatonic" in block.lower()
    assert "GM program 73" in block  # Dizi flute
    assert "Tempo" in block


def test_build_user_prompt_includes_style():
    block = build_user_prompt("buồn", bars=16, style=STYLES["flamenco"])
    assert "Phrygian" in block
    assert "Andalusian" in block

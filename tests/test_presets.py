from presets import PRESETS, get_preset


def test_two_presets_exist():
    assert set(PRESETS.keys()) == {"qq", "wechat"}


def test_qq_preset_values():
    p = get_preset("qq")
    assert p.max_bytes == 5 * 1024 * 1024
    assert p.max_edge == 480
    assert p.fps == 15
    assert p.suffix == "_qq"
    assert p.edge_ladder[0] == 480
    assert p.fps_ladder[0] == 15
    assert len(p.edge_ladder) >= 2 and len(p.fps_ladder) >= 2


def test_wechat_preset_values():
    p = get_preset("wechat")
    assert p.max_bytes == 1 * 1024 * 1024
    assert p.max_edge == 300
    assert p.fps == 12
    assert p.suffix == "_wechat"


def test_unknown_preset_raises():
    import pytest
    with pytest.raises(KeyError):
        get_preset("telegram")

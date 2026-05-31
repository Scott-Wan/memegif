import os
from pathlib import Path

import pytest

import converter
from presets import get_preset

SAMPLE = Path(__file__).parent.parent / "assets" / "sample.mp4"
requires_sample = pytest.mark.skipif(
    not SAMPLE.exists(), reason="缺少 assets/sample.mp4 测试素材"
)


def test_find_ffmpeg_returns_executable():
    exe = converter.find_ffmpeg()
    assert exe  # 非空
    import subprocess
    out = subprocess.run([exe, "-version"], capture_output=True, text=True)
    assert out.returncode == 0
    assert "ffmpeg version" in out.stdout


@requires_sample
def test_probe_duration_positive():
    dur = converter.probe_duration(str(SAMPLE))
    assert isinstance(dur, float)
    assert dur > 0


@requires_sample
def test_convert_once_produces_looping_gif(tmp_path):
    out = tmp_path / "once.gif"
    size = converter.convert_once(
        video_path=str(SAMPLE),
        start=0.0,
        end=2.0,
        max_edge=240,
        fps=10,
        out_path=str(out),
    )
    assert out.exists()
    assert size == out.stat().st_size
    assert size > 0
    head = out.read_bytes()[:6]
    assert head in (b"GIF87a", b"GIF89a")
    w, h = converter.gif_dimensions(str(out))
    assert max(w, h) <= 240


@requires_sample
def test_convert_qq_under_limit(tmp_path):
    out = tmp_path / "qq.gif"
    result = converter.convert(
        video_path=str(SAMPLE), start=0.0, end=3.0,
        preset=get_preset("qq"), out_path=str(out),
    )
    assert out.exists()
    assert result.size_bytes <= 5 * 1024 * 1024
    w, h = converter.gif_dimensions(str(out))
    assert max(w, h) <= 480


@requires_sample
def test_convert_wechat_under_strict_limit(tmp_path):
    out = tmp_path / "wechat.gif"
    result = converter.convert(
        video_path=str(SAMPLE), start=0.0, end=3.0,
        preset=get_preset("wechat"), out_path=str(out),
    )
    assert out.exists()
    assert result.size_bytes <= 1 * 1024 * 1024
    w, h = converter.gif_dimensions(str(out))
    assert max(w, h) <= 300


@requires_sample
def test_convert_reports_final_params(tmp_path):
    out = tmp_path / "r.gif"
    result = converter.convert(
        video_path=str(SAMPLE), start=0.0, end=3.0,
        preset=get_preset("wechat"), out_path=str(out),
    )
    assert result.max_edge in get_preset("wechat").edge_ladder
    assert result.fps in get_preset("wechat").fps_ladder
    assert result.out_path == str(out)


def test_default_output_path_adds_suffix():
    p = converter.default_output_path("D:/clips/cat.mp4", get_preset("qq"))
    assert p.replace("\\", "/") == "D:/clips/cat_qq.gif"
    p2 = converter.default_output_path("D:/clips/cat.mp4", get_preset("wechat"))
    assert p2.replace("\\", "/") == "D:/clips/cat_wechat.gif"

import json
import os
import subprocess
from pathlib import Path
from unittest.mock import ANY

import pytest

import converter
from presets import get_preset

SAMPLE = Path(__file__).parent.parent / "assets" / "sample.mp4"
requires_sample = pytest.mark.skipif(
    not SAMPLE.exists(), reason="缺少 assets/sample.mp4 测试素材"
)


@pytest.fixture
def animated_gif(tmp_path):
    gif_path = tmp_path / "animated.gif"
    ffmpeg = converter.find_ffmpeg()
    cmd = [
        ffmpeg,
        "-y",
        "-f",
        "lavfi",
        "-i",
        "testsrc2=size=160x90:rate=12",
        "-t",
        "1",
        str(gif_path),
    ]
    subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    assert gif_path.exists()
    assert gif_path.stat().st_size > 0
    return gif_path


def test_find_ffmpeg_returns_executable():
    exe = converter.find_ffmpeg()
    assert exe  # 非空
    out = subprocess.run([exe, "-version"], capture_output=True, text=True)
    assert out.returncode == 0
    assert "ffmpeg version" in out.stdout


@requires_sample
def test_probe_duration_positive():
    dur = converter.probe_duration(str(SAMPLE))
    assert isinstance(dur, float)
    assert dur > 0


def test_probe_dimensions_returns_first_stream_size(monkeypatch):
    class DummyCompletedProcess:
        stdout = json.dumps({
            "streams": [
                {"width": 320, "height": 240},
                {"width": 640, "height": 480},
            ]
        })

    def fake_run(cmd, capture_output, text, encoding, errors, check):
        return DummyCompletedProcess()

    monkeypatch.setattr(converter.subprocess, "run", fake_run)

    assert converter.probe_dimensions("demo.mp4") == (320, 240)


def test_probe_dimensions_raises_when_no_valid_stream(monkeypatch):
    class DummyCompletedProcess:
        stdout = json.dumps({"streams": [{"width": 0, "height": 720}, {}]})

    def fake_run(cmd, capture_output, text, encoding, errors, check):
        return DummyCompletedProcess()

    monkeypatch.setattr(converter.subprocess, "run", fake_run)

    with pytest.raises(ValueError, match="无法确定画面尺寸"):
        converter.probe_dimensions("demo.mp4")


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


def test_parse_fps_normal():
    assert converter._parse_fps("30000/1001") == pytest.approx(29.97, abs=0.01)
    assert converter._parse_fps("25/1") == 25.0


def test_parse_fps_zero_falls_back_to_avg():
    assert converter._parse_fps("0/0", "24/1") == 24.0


def test_parse_fps_all_invalid_defaults_25():
    assert converter._parse_fps("0/0", "0/0") == 25.0
    assert converter._parse_fps("", None) == 25.0


@requires_sample
def test_probe_fps_positive():
    fps = converter.probe_fps(str(SAMPLE))
    assert isinstance(fps, float)
    assert fps > 0


def test_to_float_parses_valid_and_rejects_na():
    assert converter._to_float("3.5") == 3.5
    assert converter._to_float("2") == 2.0
    # 'N/A'、None、0、负数均视为无效（GIF 缺时长时常见）
    assert converter._to_float("N/A") is None
    assert converter._to_float(None) is None
    assert converter._to_float("0") is None
    assert converter._to_float("-1") is None


def test_build_vf_no_crop():
    vf = converter._build_vf(None, 12, 300)
    assert vf.startswith("fps=12,scale=")
    assert "crop=" not in vf
    assert "flags=lanczos" in vf


def test_build_vf_with_crop_puts_crop_first():
    vf = converter._build_vf({"w": 200, "h": 100, "x": 10, "y": 20}, 15, 480)
    assert vf.startswith("crop=200:100:10:20,")
    assert ",fps=15," in vf
    assert vf.index("crop=") < vf.index("fps=") < vf.index("scale=")


@requires_sample
def test_convert_once_with_crop_changes_dimensions(tmp_path):
    out = tmp_path / "cropped.gif"
    converter.convert_once(
        video_path=str(SAMPLE), start=0.0, end=1.0,
        max_edge=240, fps=10, out_path=str(out),
        crop={"w": 120, "h": 120, "x": 0, "y": 0},
    )
    w, h = converter.gif_dimensions(str(out))
    assert w == h  # 1:1 裁切后等比缩放仍为正方形


def test_create_gif_preview_returns_non_empty_mp4(animated_gif, tmp_path):
    out = tmp_path / "preview.mp4"
    result = converter.create_gif_preview(str(animated_gif), str(out))

    assert result == str(out)
    assert out.exists()
    assert out.stat().st_size > 0

    width, height = converter.probe_dimensions(str(out))
    assert max(width, height) <= 640
    assert width / height == pytest.approx(160 / 90, rel=0.05)

    duration = converter.probe_duration(str(out))
    assert duration == pytest.approx(1.0, abs=0.15)


def test_create_gif_preview_raises_when_source_missing(tmp_path):
    missing = tmp_path / "missing.gif"
    out = tmp_path / "preview.mp4"

    with pytest.raises(FileNotFoundError):
        converter.create_gif_preview(str(missing), str(out))


def test_create_gif_preview_builds_expected_ffmpeg_command(monkeypatch, tmp_path):
    source = tmp_path / "source.gif"
    source.write_bytes(b"GIF89a")
    out = tmp_path / "nested" / "preview.mp4"

    calls = []

    class DummyCompletedProcess:
        stdout = ""

    def fake_run(cmd, capture_output, text, encoding, errors, check):
        calls.append({
            "cmd": cmd,
            "capture_output": capture_output,
            "text": text,
            "encoding": encoding,
            "errors": errors,
            "check": check,
        })
        temp_out = Path(cmd[-1])
        temp_out.parent.mkdir(parents=True, exist_ok=True)
        temp_out.write_bytes(b"mp4")
        return DummyCompletedProcess()

    monkeypatch.setattr(converter, "find_ffmpeg", lambda: "ffmpeg-bin")
    monkeypatch.setattr(converter.subprocess, "run", fake_run)

    result = converter.create_gif_preview(str(source), str(out))

    assert result == str(out)
    assert out.exists()
    assert out.parent.exists()
    assert len(calls) == 1
    recorded = calls[0]
    assert recorded == {
        "cmd": ANY,
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "check": True,
    }

    cmd = recorded["cmd"]
    assert cmd[:4] == ["ffmpeg-bin", "-y", "-i", str(source)]
    assert "-an" in cmd
    assert "-vf" in cmd
    vf = cmd[cmd.index("-vf") + 1]
    assert "fps=12" in vf
    assert "scale=" in vf
    assert "format=yuv420p" in vf
    assert "flags=lanczos" in vf
    assert cmd[cmd.index("-c:v") + 1] == "libx264"
    assert cmd[cmd.index("-preset") + 1] == "veryfast"
    assert cmd[cmd.index("-crf") + 1] == "26"
    assert cmd[cmd.index("-pix_fmt") + 1] == "yuv420p"
    assert cmd[cmd.index("-movflags") + 1] == "+faststart"
    assert Path(cmd[-1]).suffix == ".mp4"
    assert Path(cmd[-1]).parent == out.parent
    assert Path(cmd[-1]) != out


def test_create_gif_preview_cleans_partial_file_when_ffmpeg_fails(monkeypatch, tmp_path):
    source = tmp_path / "source.gif"
    source.write_bytes(b"GIF89a")
    out = tmp_path / "preview.mp4"

    def fake_run(cmd, capture_output, text, encoding, errors, check):
        temp_out = Path(cmd[-1])
        temp_out.parent.mkdir(parents=True, exist_ok=True)
        temp_out.write_bytes(b"partial-mp4-bytes")
        raise subprocess.CalledProcessError(returncode=1, cmd=cmd)

    monkeypatch.setattr(converter.subprocess, "run", fake_run)

    with pytest.raises(subprocess.CalledProcessError):
        converter.create_gif_preview(str(source), str(out))

    assert not out.exists()
    assert list(tmp_path.glob("*.mp4")) == []


def test_create_gif_preview_keeps_existing_output_when_ffmpeg_fails(monkeypatch, tmp_path):
    source = tmp_path / "source.gif"
    source.write_bytes(b"GIF89a")
    out = tmp_path / "preview.mp4"
    out.write_bytes(b"old-preview")

    def fake_run(cmd, capture_output, text, encoding, errors, check):
        temp_out = Path(cmd[-1])
        temp_out.parent.mkdir(parents=True, exist_ok=True)
        temp_out.write_bytes(b"partial-mp4-bytes")
        raise subprocess.CalledProcessError(returncode=1, cmd=cmd)

    monkeypatch.setattr(converter.subprocess, "run", fake_run)

    with pytest.raises(subprocess.CalledProcessError):
        converter.create_gif_preview(str(source), str(out))

    assert out.read_bytes() == b"old-preview"
    assert list(tmp_path.glob("*.tmp-*.mp4")) == []

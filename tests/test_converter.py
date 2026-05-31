import os
from pathlib import Path

import pytest

import converter

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

"""核心转换逻辑：定位 ffmpeg、探测视频、两步调色板转 GIF、体积回退。"""
import json
import shutil
import subprocess
from pathlib import Path


def find_ffmpeg() -> str:
    """定位 ffmpeg 可执行文件。优先 PATH，其次常见 WinGet 安装目录。"""
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    import glob
    base = Path.home() / "AppData/Local/Microsoft/WinGet/Packages"
    matches = glob.glob(str(base / "Gyan.FFmpeg*" / "**" / "ffmpeg.exe"), recursive=True)
    if matches:
        return matches[0]
    raise FileNotFoundError("未找到 ffmpeg，请确认已安装并在 PATH 中")


def _ffprobe() -> str:
    """ffprobe 与 ffmpeg 同目录。"""
    ff = Path(find_ffmpeg())
    probe = ff.with_name("ffprobe.exe")
    return str(probe) if probe.exists() else "ffprobe"


def probe_duration(video_path: str) -> float:
    """返回视频时长（秒）。"""
    cmd = [
        _ffprobe(), "-v", "error",
        "-show_entries", "format=duration",
        "-of", "json", video_path,
    ]
    out = subprocess.run(cmd, capture_output=True, text=True, check=True)
    data = json.loads(out.stdout)
    return float(data["format"]["duration"])

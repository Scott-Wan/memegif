"""核心转换逻辑：定位 ffmpeg、探测视频、两步调色板转 GIF、体积回退。"""
import json
import shutil
import subprocess
from dataclasses import dataclass
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


def gif_dimensions(gif_path: str) -> tuple:
    """返回 GIF 的 (宽, 高) 像素。"""
    cmd = [
        _ffprobe(), "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "json", gif_path,
    ]
    out = subprocess.run(cmd, capture_output=True, text=True, check=True)
    s = json.loads(out.stdout)["streams"][0]
    return int(s["width"]), int(s["height"])


def convert_once(video_path: str, start: float, end: float,
                 max_edge: int, fps: int, out_path: str) -> int:
    """用两步调色板把 [start,end] 片段转成循环 GIF，返回输出字节数。

    - 缩放：最长边缩到 max_edge，另一边按比例（保持宽高比，宽高取偶数）。
    - palettegen/paletteuse：生成专属 256 色调色板，提升清晰度。
    - -loop 0：无限循环。
    """
    ff = find_ffmpeg()
    duration = max(0.001, end - start)
    vf = (
        f"fps={fps},"
        f"scale=if(gt(iw\\,ih)\\,{max_edge}\\,-2):if(gt(iw\\,ih)\\,-2\\,{max_edge}):flags=lanczos"
    )
    palette = str(Path(out_path).with_suffix(".palette.png"))
    gen = [
        ff, "-y", "-ss", f"{start}", "-t", f"{duration}", "-i", video_path,
        "-vf", f"{vf},palettegen=stats_mode=diff",
        palette,
    ]
    subprocess.run(gen, capture_output=True, text=True, check=True)
    use = [
        ff, "-y", "-ss", f"{start}", "-t", f"{duration}", "-i", video_path,
        "-i", palette,
        "-lavfi", f"{vf}[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=3",
        "-loop", "0",
        out_path,
    ]
    subprocess.run(use, capture_output=True, text=True, check=True)
    Path(palette).unlink(missing_ok=True)
    return Path(out_path).stat().st_size


@dataclass
class ConvertResult:
    out_path: str
    size_bytes: int
    max_edge: int
    fps: int
    within_limit: bool   # 是否成功压到上限内


def convert(video_path: str, start: float, end: float, preset, out_path: str) -> "ConvertResult":
    """按预设转换并自动回退到体积达标。

    回退策略：帧率为外层、分辨率为内层。对每个 fps，先逐级降分辨率；
    某帧率下所有分辨率都超限，再降到下一档帧率。
    每个 (edge, fps) 组合转一次、测体积，第一个达标的即返回。
    全部尝试仍超限则返回最后一次（最小）结果并标记 within_limit=False。
    """
    last = None
    for fps in preset.fps_ladder:
        for edge in preset.edge_ladder:
            size = convert_once(video_path, start, end, edge, fps, out_path)
            last = ConvertResult(out_path, size, edge, fps, size <= preset.max_bytes)
            if last.within_limit:
                return last
    return last


def default_output_path(video_path: str, preset) -> str:
    """源视频同目录，文件名加预设后缀，扩展名改为 .gif。"""
    p = Path(video_path)
    return str(p.with_name(p.stem + preset.suffix + ".gif"))

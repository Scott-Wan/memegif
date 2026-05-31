"""核心转换逻辑：定位 ffmpeg、探测视频、两步调色板转 GIF、体积回退。"""
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


def _bundled_bin_dir() -> Path | None:
    """返回随程序捆绑的 ffmpeg 所在目录（bin/），找不到返回 None。

    - 打包成 exe 后（PyInstaller）：资源在 sys._MEIPASS / exe 同目录的 bin。
    - 源码运行：项目根目录下的 bin。
    """
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", os.path.dirname(sys.executable)))
    else:
        base = Path(__file__).resolve().parent
    cand = base / "bin"
    return cand if cand.is_dir() else None


def find_ffmpeg() -> str:
    """定位 ffmpeg 可执行文件。优先捆绑版，其次 PATH，再次 WinGet 安装目录。"""
    bundled = _bundled_bin_dir()
    if bundled:
        exe = bundled / "ffmpeg.exe"
        if exe.exists():
            return str(exe)
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


def _parse_fps(r_frame_rate: str, avg_frame_rate: str | None = None) -> float:
    """把 ffprobe 的 'num/den' 帧率串解析为浮点 fps。

    无效（'0/0'、空、除零、解析失败）时先试 avg_frame_rate，再不行回退 25.0。
    """
    def _one(s):
        if not s or "/" not in s:
            return None
        num, den = s.split("/", 1)
        try:
            num, den = float(num), float(den)
        except ValueError:
            return None
        if den == 0 or num == 0:
            return None
        return num / den
    return _one(r_frame_rate) or _one(avg_frame_rate) or 25.0


def probe_fps(video_path: str) -> float:
    """探测视频真实帧率（每秒帧数）。读不到时回退 25.0。"""
    cmd = [
        _ffprobe(), "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=r_frame_rate,avg_frame_rate",
        "-of", "json", video_path,
    ]
    out = subprocess.run(cmd, capture_output=True, text=True, check=True)
    streams = json.loads(out.stdout).get("streams") or [{}]
    s = streams[0]
    return _parse_fps(s.get("r_frame_rate", ""), s.get("avg_frame_rate", ""))


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


def _build_vf(crop, fps, max_edge) -> str:
    """构建 ffmpeg -vf 滤镜串。

    crop 为 {'w','h','x','y'}（视频真实像素）或 None。
    顺序：crop（先裁）-> fps -> scale（最长边缩到 max_edge，保持宽高比、取偶数）。
    不裁切时与原行为完全一致。
    """
    scale = (
        f"scale=if(gt(iw\\,ih)\\,{max_edge}\\,-2):"
        f"if(gt(iw\\,ih)\\,-2\\,{max_edge}):flags=lanczos"
    )
    parts = []
    if crop:
        parts.append(
            f"crop={int(crop['w'])}:{int(crop['h'])}:{int(crop['x'])}:{int(crop['y'])}"
        )
    parts.append(f"fps={fps}")
    parts.append(scale)
    return ",".join(parts)


def convert_once(video_path: str, start: float, end: float,
                 max_edge: int, fps: int, out_path: str, crop=None) -> int:
    """用两步调色板把 [start,end] 片段转成循环 GIF，返回输出字节数。

    - crop：{'w','h','x','y'} 真实像素裁切区域，None 表示不裁。
    - 缩放：最长边缩到 max_edge，另一边按比例（保持宽高比，宽高取偶数）。
    - palettegen/paletteuse：生成专属 256 色调色板，提升清晰度。
    - -loop 0：无限循环。
    """
    ff = find_ffmpeg()
    duration = max(0.001, end - start)
    vf = _build_vf(crop, fps, max_edge)
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


def convert(video_path: str, start: float, end: float, preset, out_path: str,
            crop=None) -> "ConvertResult":
    """按预设转换并自动回退到体积达标。crop 透传给每次转换（裁切区域不随回退变化）。

    回退策略：帧率为外层、分辨率为内层。对每个 fps，先逐级降分辨率；
    某帧率下所有分辨率都超限，再降到下一档帧率。
    每个 (edge, fps) 组合转一次、测体积，第一个达标的即返回。
    全部尝试仍超限则返回最后一次（最小）结果并标记 within_limit=False。
    """
    last = None
    for fps in preset.fps_ladder:
        for edge in preset.edge_ladder:
            size = convert_once(video_path, start, end, edge, fps, out_path, crop=crop)
            last = ConvertResult(out_path, size, edge, fps, size <= preset.max_bytes)
            if last.within_limit:
                return last
    return last


def unique_path(path: str) -> str:
    """若 path 已存在，则在主名后追加 _1、_2… 直到不冲突，返回可用路径。"""
    p = Path(path)
    if not p.exists():
        return str(p)
    stem, suffix, parent = p.stem, p.suffix, p.parent
    n = 1
    while True:
        cand = parent / f"{stem}_{n}{suffix}"
        if not cand.exists():
            return str(cand)
        n += 1


def default_output_path(video_path: str, preset) -> str:
    """源视频同目录，文件名加预设后缀，扩展名改为 .gif。

    若同名 GIF 已存在（同一视频多次转换），自动追加序号，避免覆盖之前的成品。
    """
    p = Path(video_path)
    out = p.parent / f"{p.stem}{preset.suffix}.gif"
    return unique_path(str(out))

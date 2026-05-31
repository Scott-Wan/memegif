# 视频转 GIF 表情包小工具 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 做一个 pywebview 桌面小工具，把视频拖入窗口、可视化选取一段，转成循环播放、尽量清晰、体积达标（QQ ≤5MB / 微信 ≤1MB）的 GIF。

**Architecture:** 内核是纯函数式的 `converter.py`（输入视频路径+起止+预设，输出 gif 路径+体积），底层调系统已装的 ffmpeg，用两步调色板保证清晰、体积超限时自动逐级回退。窗口用 pywebview 渲染 `web/` 下的 HTML/CSS/JS 前端，前端通过 `js_api` 桥接调后端。深色背景 + 陶土橙强调的视觉风格，纯手写 CSS、内联 SVG，零额外 UI 依赖。

**Tech Stack:** Python 3.12（项目本地 venv，位于 `F:\gifmaker\venv`）、pywebview、系统 ffmpeg、pytest；前端 HTML/CSS/JS。

参考 spec：`docs/superpowers/specs/2026-05-31-video-to-gif-design.md`

---

## File Structure

| 文件 | 职责 |
|------|------|
| `requirements.txt` | 声明 pip 依赖（pywebview, pytest） |
| `presets.py` | QQ / 微信 两套预设参数（体积上限、最大边、起始帧率、回退梯度、输出后缀） |
| `converter.py` | 核心：定位 ffmpeg、两步调色板转 GIF、体积超限自动回退；纯函数，可单测 |
| `app.py` | 入口：创建 pywebview 窗口，定义 `Api` 类（选文件、获取视频信息、转换）暴露给前端 |
| `web/index.html` | 界面结构：拖入区、video 预览、双滑块时间轴、预设按钮、状态栏 |
| `web/style.css` | 深色橙色视觉风格，纯手写 |
| `web/main.js` | 前端交互：拖拽/选择、选段滑块、调 `pywebview.api`、刷新状态 |
| `tests/test_presets.py` | 预设结构校验 |
| `tests/test_converter.py` | 用 `assets/sample.mp4` 验证体积达标、尺寸约束、回退逻辑 |
| `assets/sample.mp4` | 测试素材（从 `F:\格式转换` 拷入；不进版本库） |
| `README.md` | 运行说明 |

执行顺序：先内核（presets → converter，可纯命令行 TDD），再前端与入口（app + web），最后文档。这样核心逻辑在没有 GUI 的情况下就能被测试验证。

---

## Task 0: 环境与测试素材准备

**Files:**
- Create: `requirements.txt`
- Create: `assets/sample.mp4`（拷贝，不提交）

- [ ] **Step 1: 创建项目本地虚拟环境（装在 F 盘，不碰 C 盘全局）**

Run:
```powershell
& "C:\Users\PC\AppData\Local\Programs\Python\Python312\python.exe" -m venv F:\gifmaker\venv
```
Expected: 生成 `F:\gifmaker\venv\` 目录，无报错。

- [ ] **Step 2: 写 requirements.txt**

`requirements.txt`:
```
pywebview==5.*
pytest==8.*
```

- [ ] **Step 3: 在 venv 内安装依赖**

Run:
```powershell
F:\gifmaker\venv\Scripts\python.exe -m pip install -r F:\gifmaker\requirements.txt
```
Expected: pywebview、pytest 及其依赖安装成功（装进 venv，不影响全局）。

- [ ] **Step 4: 验证 pywebview 可导入、ffmpeg 可调用**

Run:
```powershell
F:\gifmaker\venv\Scripts\python.exe -c "import webview; print('webview ok')"
ffmpeg -version
```
Expected: 打印 `webview ok`；ffmpeg 打印版本号。

- [ ] **Step 5: 拷贝测试素材**

Run:
```powershell
Copy-Item "F:\格式转换\u8LSRvsL_LCreszP..MP4" "F:\gifmaker\assets\sample.mp4"
```
Expected: `F:\gifmaker\assets\sample.mp4` 存在（`.gitignore` 已排除 `assets/*.mp4`，不会进库）。

- [ ] **Step 6: Commit**

```powershell
git -C F:\gifmaker add requirements.txt
git -C F:\gifmaker commit -m "chore: 添加依赖声明与本地venv"
```

---

## Task 1: 预设参数 presets.py

**Files:**
- Create: `presets.py`
- Test: `tests/test_presets.py`

- [ ] **Step 1: 写失败测试**

`tests/test_presets.py`:
```python
from presets import PRESETS, get_preset


def test_two_presets_exist():
    assert set(PRESETS.keys()) == {"qq", "wechat"}


def test_qq_preset_values():
    p = get_preset("qq")
    assert p.max_bytes == 5 * 1024 * 1024
    assert p.max_edge == 480
    assert p.fps == 15
    assert p.suffix == "_qq"
    # 回退梯度：分辨率与帧率都需给出，且首项等于起始值
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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `F:\gifmaker\venv\Scripts\python.exe -m pytest tests/test_presets.py -v`
（在 `F:\gifmaker` 目录下执行，使 `presets` 可被导入）
Expected: FAIL，`ModuleNotFoundError: No module named 'presets'`

- [ ] **Step 3: 写最小实现**

`presets.py`:
```python
"""转换预设：定义不同平台的目标体积、尺寸、帧率与回退梯度。"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Preset:
    name: str            # 显示名
    max_bytes: int       # 体积上限（字节）
    max_edge: int        # 起始最大边（像素）
    fps: int             # 起始帧率
    suffix: str          # 输出文件名后缀
    edge_ladder: tuple   # 分辨率回退梯度（从大到小）
    fps_ladder: tuple    # 帧率回退梯度（从大到小）


PRESETS = {
    "qq": Preset(
        name="QQ",
        max_bytes=5 * 1024 * 1024,
        max_edge=480,
        fps=15,
        suffix="_qq",
        edge_ladder=(480, 400, 320, 256),
        fps_ladder=(15, 12, 10),
    ),
    "wechat": Preset(
        name="微信表情",
        max_bytes=1 * 1024 * 1024,
        max_edge=300,
        fps=12,
        suffix="_wechat",
        edge_ladder=(300, 256, 200, 160),
        fps_ladder=(12, 10, 8),
    ),
}


def get_preset(key: str) -> Preset:
    """按 key 取预设，未知 key 抛 KeyError。"""
    return PRESETS[key]
```

- [ ] **Step 4: 运行测试确认通过**

Run: `F:\gifmaker\venv\Scripts\python.exe -m pytest tests/test_presets.py -v`
Expected: PASS（4 passed）

- [ ] **Step 5: Commit**

```powershell
git -C F:\gifmaker add presets.py tests/test_presets.py
git -C F:\gifmaker commit -m "feat: 添加QQ/微信转换预设"
```

---

## Task 2: ffmpeg 定位与视频信息探测

**Files:**
- Create: `converter.py`
- Test: `tests/test_converter.py`

- [ ] **Step 1: 写失败测试（ffmpeg 定位 + 时长探测）**

`tests/test_converter.py`:
```python
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
    # 应能执行 -version
    import subprocess
    out = subprocess.run([exe, "-version"], capture_output=True, text=True)
    assert out.returncode == 0
    assert "ffmpeg version" in out.stdout


@requires_sample
def test_probe_duration_positive():
    dur = converter.probe_duration(str(SAMPLE))
    assert isinstance(dur, float)
    assert dur > 0
```

- [ ] **Step 2: 运行确认失败**

Run: `F:\gifmaker\venv\Scripts\python.exe -m pytest tests/test_converter.py -v`
Expected: FAIL，`AttributeError: module 'converter' has no attribute 'find_ffmpeg'`（或 import 失败）

- [ ] **Step 3: 写最小实现**

`converter.py`（创建文件，先放定位与探测部分）:
```python
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
    # WinGet 安装的常见位置兜底
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
```

- [ ] **Step 4: 运行确认通过**

Run: `F:\gifmaker\venv\Scripts\python.exe -m pytest tests/test_converter.py -v`
Expected: PASS（test_find_ffmpeg PASS；test_probe_duration PASS 或在无素材时 SKIP）

- [ ] **Step 5: Commit**

```powershell
git -C F:\gifmaker add converter.py tests/test_converter.py
git -C F:\gifmaker commit -m "feat: 添加ffmpeg定位与视频时长探测"
```

---

## Task 3: 单次两步调色板转换（一档参数）

**Files:**
- Modify: `converter.py`
- Test: `tests/test_converter.py`

- [ ] **Step 1: 追加失败测试（按指定边长/帧率转一版 GIF）**

在 `tests/test_converter.py` 末尾追加：
```python
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
    # GIF 头部魔数
    head = out.read_bytes()[:6]
    assert head in (b"GIF87a", b"GIF89a")
    # 最长边不超过请求值（允许等于）
    w, h = converter.gif_dimensions(str(out))
    assert max(w, h) <= 240
```

- [ ] **Step 2: 运行确认失败**

Run: `F:\gifmaker\venv\Scripts\python.exe -m pytest tests/test_converter.py::test_convert_once_produces_looping_gif -v`
Expected: FAIL，`AttributeError: ... 'convert_once'`

- [ ] **Step 3: 实现 convert_once 与 gif_dimensions**

在 `converter.py` 末尾追加：
```python
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
    # 缩放滤镜：长边=max_edge，短边自适应且为偶数；fps 抽帧
    vf = (
        f"fps={fps},"
        f"scale=if(gt(iw\\,ih)\\,{max_edge}\\,-2):if(gt(iw\\,ih)\\,-2\\,{max_edge}):flags=lanczos"
    )
    palette = str(Path(out_path).with_suffix(".palette.png"))
    # 第一步：生成调色板
    gen = [
        ff, "-y", "-ss", f"{start}", "-t", f"{duration}", "-i", video_path,
        "-vf", f"{vf},palettegen=stats_mode=diff",
        palette,
    ]
    subprocess.run(gen, capture_output=True, text=True, check=True)
    # 第二步：应用调色板
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
```

- [ ] **Step 4: 运行确认通过**

Run: `F:\gifmaker\venv\Scripts\python.exe -m pytest tests/test_converter.py::test_convert_once_produces_looping_gif -v`
Expected: PASS

- [ ] **Step 5: Commit**

```powershell
git -C F:\gifmaker add converter.py tests/test_converter.py
git -C F:\gifmaker commit -m "feat: 实现两步调色板单档GIF转换"
```

---

## Task 4: 体积自动回退主函数 convert

**Files:**
- Modify: `converter.py`
- Test: `tests/test_converter.py`

- [ ] **Step 1: 追加失败测试（达标 + 回退）**

在 `tests/test_converter.py` 末尾追加：
```python
from presets import get_preset


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
    # 结果对象应报告最终使用的边长/帧率，便于状态栏显示
    assert result.max_edge in get_preset("wechat").edge_ladder
    assert result.fps in get_preset("wechat").fps_ladder
    assert result.out_path == str(out)
```

- [ ] **Step 2: 运行确认失败**

Run: `F:\gifmaker\venv\Scripts\python.exe -m pytest tests/test_converter.py -k convert_ -v`
Expected: FAIL，`AttributeError: ... 'convert'`

- [ ] **Step 3: 实现 convert + 结果数据类**

在 `converter.py` 顶部 import 区补 `from dataclasses import dataclass`，并在文件末尾追加：
```python
@dataclass
class ConvertResult:
    out_path: str
    size_bytes: int
    max_edge: int
    fps: int
    within_limit: bool   # 是否成功压到上限内


def convert(video_path: str, start: float, end: float, preset, out_path: str) -> "ConvertResult":
    """按预设转换并自动回退到体积达标。

    回退策略：先逐级降分辨率（edge_ladder），仍超限再逐级降帧率（fps_ladder）。
    每个 (edge, fps) 组合转一次、测体积，第一个达标的即返回。
    全部尝试仍超限则返回最后一次（最小）结果并标记 within_limit=False。
    """
    last = None
    # 帧率为外层、分辨率为内层：优先牺牲分辨率保流畅；流畅档不行再降帧率
    for fps in preset.fps_ladder:
        for edge in preset.edge_ladder:
            size = convert_once(video_path, start, end, edge, fps, out_path)
            last = ConvertResult(out_path, size, edge, fps, size <= preset.max_bytes)
            if last.within_limit:
                return last
    return last
```

- [ ] **Step 4: 运行确认通过**

Run: `F:\gifmaker\venv\Scripts\python.exe -m pytest tests/test_converter.py -v`
Expected: PASS（全部通过；无素材时相关用例 SKIP）

- [ ] **Step 5: Commit**

```powershell
git -C F:\gifmaker add converter.py tests/test_converter.py
git -C F:\gifmaker commit -m "feat: 实现体积自动回退转换主函数"
```

---

## Task 5: 输出路径辅助 + 后端 Api 类

**Files:**
- Modify: `converter.py`（加 `default_output_path`）
- Create: `app.py`
- Test: `tests/test_converter.py`

- [ ] **Step 1: 追加失败测试（默认输出路径规则）**

在 `tests/test_converter.py` 末尾追加：
```python
def test_default_output_path_adds_suffix():
    p = converter.default_output_path("D:/clips/cat.mp4", get_preset("qq"))
    assert p.replace("\\", "/") == "D:/clips/cat_qq.gif"
    p2 = converter.default_output_path("D:/clips/cat.mp4", get_preset("wechat"))
    assert p2.replace("\\", "/") == "D:/clips/cat_wechat.gif"
```

- [ ] **Step 2: 运行确认失败**

Run: `F:\gifmaker\venv\Scripts\python.exe -m pytest tests/test_converter.py::test_default_output_path_adds_suffix -v`
Expected: FAIL，`AttributeError: ... 'default_output_path'`

- [ ] **Step 3: 实现 default_output_path**

在 `converter.py` 末尾追加：
```python
def default_output_path(video_path: str, preset) -> str:
    """源视频同目录，文件名加预设后缀，扩展名改为 .gif。"""
    p = Path(video_path)
    return str(p.with_name(p.stem + preset.suffix + ".gif"))
```

- [ ] **Step 4: 运行确认通过**

Run: `F:\gifmaker\venv\Scripts\python.exe -m pytest tests/test_converter.py::test_default_output_path_adds_suffix -v`
Expected: PASS

- [ ] **Step 5: 写 app.py（后端 Api + 窗口入口）**

`app.py`:
```python
"""pywebview 入口：创建窗口，暴露 Api 给前端调用。"""
import os
import webview

import converter
from presets import get_preset


class Api:
    """前端通过 pywebview.api.<方法> 调用。所有方法返回可 JSON 序列化的 dict。"""

    def __init__(self):
        self._window = None

    def set_window(self, window):
        self._window = window

    def choose_file(self):
        """弹原生文件对话框选视频，返回 {path, duration} 或 {error}。"""
        result = self._window.create_file_dialog(
            webview.OPEN_DIALOG,
            file_types=("视频文件 (*.mp4;*.mov;*.mkv;*.avi;*.webm;*.flv)", "所有文件 (*.*)"),
        )
        if not result:
            return {"cancelled": True}
        path = result[0]
        return self.load_video(path)

    def load_video(self, path):
        """探测视频时长，返回 {path, duration} 或 {error}。"""
        try:
            duration = converter.probe_duration(path)
            return {"path": path, "duration": duration}
        except Exception as e:
            return {"error": f"无法读取视频：{e}"}

    def video_src(self, path):
        """返回前端 <video> 可加载的本地文件 URL。"""
        return {"url": "file:///" + path.replace("\\", "/")}

    def convert(self, path, start, end, preset_key):
        """执行转换，返回 {out_path, size_mb, max_edge, fps, within_limit} 或 {error}。"""
        try:
            preset = get_preset(preset_key)
            out_path = converter.default_output_path(path, preset)
            r = converter.convert(path, float(start), float(end), preset, out_path)
            return {
                "out_path": r.out_path,
                "size_mb": round(r.size_bytes / 1024 / 1024, 2),
                "max_edge": r.max_edge,
                "fps": r.fps,
                "within_limit": r.within_limit,
                "limit_mb": round(preset.max_bytes / 1024 / 1024, 2),
            }
        except Exception as e:
            return {"error": f"转换失败：{e}"}


def main():
    api = Api()
    here = os.path.dirname(os.path.abspath(__file__))
    window = webview.create_window(
        title="GIF Maker · 视频转表情包",
        url=os.path.join(here, "web", "index.html"),
        js_api=api,
        width=720, height=640, min_size=(560, 520),
        background_color="#1C1B1A",
    )
    api.set_window(window)
    webview.start()


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Commit**

```powershell
git -C F:\gifmaker add converter.py app.py tests/test_converter.py
git -C F:\gifmaker commit -m "feat: 添加输出路径规则与pywebview后端Api"
```

---

## Task 6: 前端界面结构 index.html

**Files:**
- Create: `web/index.html`

- [ ] **Step 1: 写 index.html**

`web/index.html`:
```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>GIF Maker</title>
  <link rel="stylesheet" href="style.css" />
</head>
<body>
  <header class="topbar">
    <span class="logo" aria-hidden="true">
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
        <rect x="2" y="4" width="20" height="16" rx="4" fill="#D97757"/>
        <path d="M9 9l6 3-6 3V9z" fill="#1C1B1A"/>
      </svg>
    </span>
    <h1>GIF Maker</h1>
    <span class="subtitle">视频转表情包</span>
  </header>

  <main>
    <!-- 拖入 / 选择 区 -->
    <section id="dropzone" class="dropzone">
      <svg class="drop-icon" width="40" height="40" viewBox="0 0 24 24" fill="none">
        <path d="M12 16V4m0 0L8 8m4-4l4 4" stroke="#D97757" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
        <path d="M4 16v2a2 2 0 002 2h12a2 2 0 002-2v-2" stroke="#9B9B9B" stroke-width="2" stroke-linecap="round"/>
      </svg>
      <p class="drop-text">把视频拖到这里</p>
      <p class="drop-hint">或</p>
      <button id="choose-btn" class="btn-secondary">选择文件</button>
    </section>

    <!-- 编辑区（载入后显示） -->
    <section id="editor" class="editor hidden">
      <div class="video-wrap">
        <video id="video" preload="metadata"></video>
      </div>

      <div class="timeline">
        <div class="range-labels">
          <span id="start-label">0.0s</span>
          <span id="dur-label">时长 0.0s</span>
          <span id="end-label">0.0s</span>
        </div>
        <div class="dual-slider" id="dual-slider">
          <div class="track"></div>
          <div class="range-fill" id="range-fill"></div>
          <input type="range" id="start-range" min="0" max="100" step="0.1" value="0" />
          <input type="range" id="end-range" min="0" max="100" step="0.1" value="100" />
        </div>
      </div>

      <div class="presets">
        <button class="btn-primary" data-preset="qq">转为 QQ 表情 · ≤5MB</button>
        <button class="btn-primary alt" data-preset="wechat">转为 微信表情 · ≤1MB</button>
      </div>
    </section>

    <!-- 状态栏 -->
    <footer id="status" class="status">拖入视频开始</footer>
  </main>

  <script src="main.js"></script>
</body>
</html>
```

- [ ] **Step 2: Commit**

```powershell
git -C F:\gifmaker add web/index.html
git -C F:\gifmaker commit -m "feat: 前端界面结构"
```

---

## Task 7: 视觉风格 style.css（深色 + 陶土橙）

**Files:**
- Create: `web/style.css`

- [ ] **Step 1: 写 style.css**

`web/style.css`:
```css
/* 深色背景 + 陶土橙强调，参考 Claude 配色 */
:root {
  --bg: #1C1B1A;
  --panel: #262422;
  --panel-2: #2F2C29;
  --accent: #D97757;
  --accent-hover: #E68A6C;
  --text: #ECECEC;
  --text-dim: #9B9B9B;
  --border: #3A3633;
  --ok: #6FBF73;
  --err: #E0625A;
}

* { box-sizing: border-box; margin: 0; padding: 0; }

body {
  font-family: "Segoe UI", "Microsoft YaHei", system-ui, sans-serif;
  background: var(--bg);
  color: var(--text);
  height: 100vh;
  display: flex;
  flex-direction: column;
  user-select: none;
}

.topbar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 14px 20px;
  border-bottom: 1px solid var(--border);
}
.topbar h1 { font-size: 16px; font-weight: 600; }
.topbar .subtitle { color: var(--text-dim); font-size: 12px; margin-left: 4px; }
.logo { display: inline-flex; }

main {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 20px;
  overflow: auto;
}

.hidden { display: none !important; }

/* 拖入区 */
.dropzone {
  flex: 1;
  min-height: 220px;
  border: 2px dashed var(--border);
  border-radius: 16px;
  background: var(--panel);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  transition: border-color .15s, background .15s;
}
.dropzone.dragover {
  border-color: var(--accent);
  background: rgba(217, 119, 87, 0.08);
}
.drop-text { font-size: 15px; }
.drop-hint { color: var(--text-dim); font-size: 12px; }

/* 按钮 */
.btn-primary, .btn-secondary {
  font-size: 14px;
  border: none;
  border-radius: 10px;
  padding: 10px 18px;
  cursor: pointer;
  transition: background .15s, transform .05s;
}
.btn-primary:active, .btn-secondary:active { transform: scale(0.98); }
.btn-primary {
  background: var(--accent);
  color: #1C1B1A;
  font-weight: 600;
}
.btn-primary:hover { background: var(--accent-hover); }
.btn-primary.alt { background: var(--panel-2); color: var(--text); border: 1px solid var(--accent); }
.btn-primary.alt:hover { background: rgba(217,119,87,0.15); }
.btn-secondary {
  background: var(--panel-2);
  color: var(--text);
  border: 1px solid var(--border);
}
.btn-secondary:hover { border-color: var(--accent); color: var(--accent); }

/* 编辑区 */
.editor { display: flex; flex-direction: column; gap: 16px; }
.video-wrap {
  background: #000;
  border-radius: 12px;
  overflow: hidden;
  display: flex;
  justify-content: center;
  max-height: 320px;
}
.video-wrap video { max-width: 100%; max-height: 320px; }

/* 双滑块时间轴 */
.timeline { display: flex; flex-direction: column; gap: 8px; }
.range-labels {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: var(--text-dim);
}
.range-labels #dur-label { color: var(--accent); }

.dual-slider { position: relative; height: 28px; }
.dual-slider .track {
  position: absolute; top: 12px; left: 0; right: 0; height: 4px;
  background: var(--border); border-radius: 2px;
}
.dual-slider .range-fill {
  position: absolute; top: 12px; height: 4px;
  background: var(--accent); border-radius: 2px;
}
.dual-slider input[type="range"] {
  position: absolute; top: 0; left: 0; width: 100%;
  margin: 0; background: none; pointer-events: none;
  -webkit-appearance: none; appearance: none; height: 28px;
}
.dual-slider input[type="range"]::-webkit-slider-thumb {
  -webkit-appearance: none; appearance: none;
  width: 16px; height: 16px; border-radius: 50%;
  background: var(--accent); border: 2px solid var(--bg);
  cursor: pointer; pointer-events: auto;
  box-shadow: 0 0 0 1px var(--accent);
}

/* 预设按钮区 */
.presets { display: flex; gap: 12px; }
.presets .btn-primary { flex: 1; }

/* 状态栏 */
.status {
  font-size: 13px;
  color: var(--text-dim);
  padding: 12px 14px;
  background: var(--panel);
  border-radius: 10px;
  border: 1px solid var(--border);
  word-break: break-all;
}
.status.busy { color: var(--accent); }
.status.ok { color: var(--ok); border-color: var(--ok); }
.status.err { color: var(--err); border-color: var(--err); }
```

- [ ] **Step 2: Commit**

```powershell
git -C F:\gifmaker add web/style.css
git -C F:\gifmaker commit -m "feat: 深色橙色视觉样式"
```

---

## Task 8: 前端交互 main.js

**Files:**
- Create: `web/main.js`

- [ ] **Step 1: 写 main.js**

`web/main.js`:
```javascript
// 前端交互：导入视频、可视化选段、调用后端转换、刷新状态。

let state = { path: null, duration: 0 };

const $ = (id) => document.getElementById(id);
const dropzone = $("dropzone");
const editor = $("editor");
const video = $("video");
const statusEl = $("status");
const startRange = $("start-range");
const endRange = $("end-range");
const rangeFill = $("range-fill");

// 等待 pywebview 注入 api
function whenReady(fn) {
  if (window.pywebview && window.pywebview.api) fn();
  else window.addEventListener("pywebviewready", fn);
}

function setStatus(text, cls) {
  statusEl.textContent = text;
  statusEl.className = "status" + (cls ? " " + cls : "");
}

// ---- 载入视频后初始化编辑区 ----
async function onVideoLoaded(info) {
  if (info.error) { setStatus(info.error, "err"); return; }
  if (info.cancelled) return;
  state.path = info.path;
  state.duration = info.duration;

  const srcRes = await window.pywebview.api.video_src(info.path);
  video.src = srcRes.url;

  // 滑块以「百分比」为单位，0~100 映射到 0~duration
  startRange.value = 0;
  endRange.value = 100;
  updateRangeUI();

  dropzone.classList.add("hidden");
  editor.classList.remove("hidden");
  setStatus("拖动两端滑块选取片段，然后选择目标平台", null);
}

// 百分比 -> 秒
const pctToSec = (pct) => (pct / 100) * state.duration;

function updateRangeUI() {
  let s = parseFloat(startRange.value);
  let e = parseFloat(endRange.value);
  if (s > e) { [s, e] = [e, s]; }       // 防止越界
  const startSec = pctToSec(s);
  const endSec = pctToSec(e);
  $("start-label").textContent = startSec.toFixed(1) + "s";
  $("end-label").textContent = endSec.toFixed(1) + "s";
  $("dur-label").textContent = "时长 " + (endSec - startSec).toFixed(1) + "s";
  rangeFill.style.left = s + "%";
  rangeFill.style.width = (e - s) + "%";
}

// 拖动起始滑块时让预览跳到该帧
startRange.addEventListener("input", () => { updateRangeUI(); seekPreview(startRange); });
endRange.addEventListener("input", () => { updateRangeUI(); seekPreview(endRange); });

function seekPreview(which) {
  const pct = parseFloat(which.value);
  if (!isNaN(pct) && state.duration) video.currentTime = pctToSec(pct);
}

// ---- 转换 ----
async function doConvert(presetKey) {
  if (!state.path) return;
  let s = pctToSec(parseFloat(startRange.value));
  let e = pctToSec(parseFloat(endRange.value));
  if (s > e) [s, e] = [e, s];
  if (e - s < 0.1) { setStatus("选中片段太短，请拉开两端滑块", "err"); return; }

  setStatus("正在转换…可能需要几秒", "busy");
  const r = await window.pywebview.api.convert(state.path, s, e, presetKey);
  if (r.error) { setStatus(r.error, "err"); return; }
  if (r.within_limit) {
    setStatus(
      `✅ 完成：${r.out_path}\n${r.size_mb}MB · 最长边 ${r.max_edge}px · ${r.fps}fps`,
      "ok"
    );
  } else {
    setStatus(
      `⚠ 已尽力压到 ${r.size_mb}MB（上限 ${r.limit_mb}MB）仍超出，建议再缩短片段。\n${r.out_path}`,
      "err"
    );
  }
}

// ---- 事件绑定 ----
whenReady(() => {
  $("choose-btn").addEventListener("click", async () => {
    setStatus("选择视频文件…", "busy");
    const info = await window.pywebview.api.choose_file();
    onVideoLoaded(info);
  });

  document.querySelectorAll("[data-preset]").forEach((btn) => {
    btn.addEventListener("click", () => doConvert(btn.dataset.preset));
  });

  // 拖拽：高亮 + 释放后取路径。pywebview 中 drop 的文件路径在 file.path 上（多数平台可用）。
  ["dragenter", "dragover"].forEach((ev) =>
    dropzone.addEventListener(ev, (e) => { e.preventDefault(); dropzone.classList.add("dragover"); })
  );
  ["dragleave", "drop"].forEach((ev) =>
    dropzone.addEventListener(ev, (e) => { e.preventDefault(); dropzone.classList.remove("dragover"); })
  );
  dropzone.addEventListener("drop", async (e) => {
    const f = e.dataTransfer.files[0];
    if (f && f.path) {
      setStatus("载入中…", "busy");
      const info = await window.pywebview.api.load_video(f.path);
      onVideoLoaded(info);
    } else {
      // 拿不到绝对路径时，引导用按钮
      setStatus("拖拽未能识别路径，请点「选择文件」", "err");
    }
  });
});
```

- [ ] **Step 2: Commit**

```powershell
git -C F:\gifmaker add web/main.js
git -C F:\gifmaker commit -m "feat: 前端选段与转换交互"
```

---

## Task 9: 手动验收 + README + 推送

**Files:**
- Create: `README.md`

- [ ] **Step 1: 跑全部单测**

Run: `F:\gifmaker\venv\Scripts\python.exe -m pytest -v`（在 `F:\gifmaker` 下）
Expected: 全部 PASS（有素材时 converter 用例全过）。

- [ ] **Step 2: 启动应用手动验收**

Run: `F:\gifmaker\venv\Scripts\python.exe F:\gifmaker\app.py`
手动检查清单：
1. 窗口打开，深色背景 + 橙色 logo/按钮，无报错。
2. 点「选择文件」选 `assets/sample.mp4` → 出现视频预览。
3. 拖动两端滑块，时长标签实时更新，预览画面随滑块跳帧。
4. 点「转为 QQ 表情」→ 状态栏显示进行中→成功，给出路径/体积/参数。
5. 到输出目录确认 GIF 能循环播放、清晰度可接受。
6. 点「转为 微信表情」→ 输出体积 ≤1MB。
7. （可选）把一个视频文件拖进窗口，确认拖拽路径能识别；不能识别时给出引导提示。

- [ ] **Step 3: 写 README.md**

`README.md`:
```markdown
# GIF Maker · 视频转表情包

把视频拖入窗口，可视化选取一段，转成循环播放、尽量清晰、体积达标的 GIF。
主用途 QQ 表情（≤5MB），同时支持微信表情（≤1MB / ≤300px）。

## 运行

需要系统已安装 ffmpeg（含 ffprobe）并在 PATH 中。

```powershell
# 首次：创建本地虚拟环境并安装依赖
python -m venv venv
venv\Scripts\python.exe -m pip install -r requirements.txt

# 启动
venv\Scripts\python.exe app.py
```

## 测试

```powershell
venv\Scripts\python.exe -m pytest -v
```
（需要 `assets/sample.mp4` 测试素材，缺失时相关用例会自动跳过。）

## 技术

Python + pywebview 窗口，HTML/CSS/JS 前端，底层调 ffmpeg 两步调色板转换，
体积超限自动逐级回退（先降分辨率、再降帧率）。
```

- [ ] **Step 4: Commit 并推送**

```powershell
git -C F:\gifmaker add README.md
git -C F:\gifmaker commit -m "docs: 添加README"
git -C F:\gifmaker push
```

---

## Self-Review 记录

- **Spec 覆盖**：导入(Task5/8)、可视化选段(Task6/7/8)、QQ/微信预设(Task1)、两步调色板(Task3)、体积回退(Task4)、同目录后缀输出(Task5)、错误处理(Api+main.js)、深色橙色视觉(Task7)、测试策略(Task1-5)、技术风险（拖拽兜底按钮，Task5/8）均有对应任务。
- **占位符**：无 TODO/TBD；每个代码步骤含完整代码。
- **类型一致**：`Preset` 字段（max_bytes/max_edge/fps/suffix/edge_ladder/fps_ladder）、`ConvertResult` 字段（out_path/size_bytes/max_edge/fps/within_limit）、`convert/convert_once/default_output_path/gif_dimensions/probe_duration/find_ffmpeg` 命名在各任务间一致。
- **已知遗留**：拖拽取绝对路径依赖 pywebview 平台行为，已用「选择文件」按钮兜底（spec 第 8 节风险）。

# GIF 选段循环预览 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将导入的 GIF 一次性转换为轻量 MP4 预览，使起止时间变化后播放窗口能实时、连续地循环所选片段，同时保持最终 GIF 导出质量和普通视频行为不变。

**Architecture:** `converter.py` 只负责媒体探测和轻量预览文件生成；`app.py` 管理本次运行的临时目录、缓存、并发保护及本地 HTTP URL；前端通过独立的纯 JavaScript 区间判断模块控制 `<video>` seek 和循环，并在预览失败时降级为现有 `<img>`。源文件类型与实际预览元素分开记录，裁切坐标始终按源媒体宽高计算。

**Tech Stack:** Python 3.12、pytest、ffmpeg/ffprobe、pywebview、原生 JavaScript、Node.js 内置 `node:test`、HTML5 `<video>`

---

## 实施前约束

- 已批准设计：`docs/superpowers/specs/2026-07-23-gif-range-preview-design.md`。
- 当前工作区存在未跟踪的 `.claude/`，实施时不得加入提交或改动范围。
- 按项目规则，除非用户另行明确授权，否则本计划不执行 `git commit`；每个任务结束时仅运行 `git diff --check` 和 `git status --short` 作为检查点。
- 不新增 npm 或 Python 运行时依赖。
- 不改变 `converter.convert()`、体积回退、预设和最终输出命名。

## 文件结构与职责

### 修改

- `converter.py`
  - 提供通用源媒体宽高探测；
  - 生成 640px / 24fps 上限的 H.264 轻量 MP4 预览。
- `app.py`
  - `load_video()` 返回源宽高；
  - `Api` 管理预览临时目录、缓存和生成锁；
  - 暴露 `prepare_gif_preview()`；
  - 窗口关闭时清理临时目录。
- `web/main.js`
  - 分离 `kind` 与 `previewMode`；
  - 使用轻量 MP4 预览 GIF；
  - 处理导入竞态、区间重播和失败降级；
  - 使用源宽高换算裁切坐标。
- `web/index.html`
  - 在 `main.js` 前加载纯区间逻辑脚本。
- `README.md`
  - 更新 GIF 预览能力说明。
- `tests/test_converter.py`
  - 覆盖通用尺寸探测和轻量 MP4 生成。

### 新建

- `web/range-preview.js`
  - 不依赖 DOM 的区间播放判断和异步请求有效性判断。
- `tests/test_range_preview.js`
  - 使用 Node 内置测试框架测试前端纯逻辑。
- `tests/test_app.py`
  - 测试 GIF 预览 API 的缓存、失效、并发、校验和清理。

---

### Task 1: 为媒体元数据增加源宽高

**Files:**
- Modify: `converter.py:140-150`
- Modify: `app.py:137-146`
- Test: `tests/test_converter.py`
- Test: `tests/test_app.py`

- [ ] **Step 1: 在转换层写尺寸探测失败测试**

在 `tests/test_converter.py` 增加：

```python
def test_probe_dimensions_reads_first_video_stream(monkeypatch):
    class Result:
        stdout = '{"streams":[{"width":320,"height":180}]}'

    monkeypatch.setattr(converter.subprocess, "run", lambda *args, **kwargs: Result())

    assert converter.probe_dimensions("demo.gif") == (320, 180)


def test_probe_dimensions_rejects_missing_stream(monkeypatch):
    class Result:
        stdout = '{"streams":[]}'

    monkeypatch.setattr(converter.subprocess, "run", lambda *args, **kwargs: Result())

    with pytest.raises(ValueError, match="无法确定画面尺寸"):
        converter.probe_dimensions("broken.gif")
```

- [ ] **Step 2: 运行定向测试并确认失败**

Run:

```powershell
venv\Scripts\python.exe -m pytest tests/test_converter.py::test_probe_dimensions_reads_first_video_stream tests/test_converter.py::test_probe_dimensions_rejects_missing_stream -v
```

Expected: 两项均因 `converter.probe_dimensions` 不存在而 `FAIL`。

- [ ] **Step 3: 实现通用尺寸探测并保留兼容包装**

在 `converter.py` 用以下实现替换现有 `gif_dimensions()`：

```python
def probe_dimensions(video_path: str) -> tuple[int, int]:
    """返回首个视频流的原始宽高。"""
    cmd = [
        _ffprobe(), "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "json", video_path,
    ]
    out = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8",
        errors="replace", check=True,
    )
    streams = json.loads(out.stdout).get("streams") or []
    if not streams:
        raise ValueError("无法确定画面尺寸")
    width = int(streams[0].get("width") or 0)
    height = int(streams[0].get("height") or 0)
    if width <= 0 or height <= 0:
        raise ValueError("无法确定画面尺寸")
    return width, height


def gif_dimensions(gif_path: str) -> tuple[int, int]:
    """兼容旧调用：返回 GIF 的宽高。"""
    return probe_dimensions(gif_path)
```

- [ ] **Step 4: 运行尺寸探测测试**

Run:

```powershell
venv\Scripts\python.exe -m pytest tests/test_converter.py -v
```

Expected: `tests/test_converter.py` 全部 `PASS`，仅缺失素材的既有测试允许显示 `SKIPPED`。

- [ ] **Step 5: 写 `load_video()` 返回源宽高的失败测试**

新建 `tests/test_app.py`，先加入：

```python
from pathlib import Path
from unittest.mock import Mock

import app


def test_load_video_returns_source_dimensions(monkeypatch, tmp_path):
    source = tmp_path / "source.gif"
    source.write_bytes(b"GIF89a")
    monkeypatch.setattr(app.converter, "probe_duration", lambda path: 2.5)
    monkeypatch.setattr(app.converter, "probe_fps", lambda path: 12.0)
    monkeypatch.setattr(app.converter, "probe_dimensions", lambda path: (320, 180))
    api = app.Api(4321, preview_root=tmp_path / "preview")

    try:
        result = api.load_video(str(source))
    finally:
        api.cleanup()

    assert result == {
        "path": str(source),
        "duration": 2.5,
        "fps": 12.0,
        "width": 320,
        "height": 180,
        "kind": "gif",
    }
```

此测试提前使用后续 `Api(..., preview_root=...)` 接口；当前失败是预期的。

- [ ] **Step 6: 运行 API 定向测试并确认失败**

Run:

```powershell
venv\Scripts\python.exe -m pytest tests/test_app.py::test_load_video_returns_source_dimensions -v
```

Expected: `FAIL`，原因是 `Api.__init__()` 尚不接受 `preview_root` 或返回值缺少 `width/height`。

- [ ] **Step 7: 先扩展 `Api` 构造函数和 `load_video()` 的最小接口**

在 `app.py` 顶部增加：

```python
import tempfile
from pathlib import Path
```

将 `Api.__init__()` 扩展为：

```python
def __init__(self, video_port, preview_root=None):
    self._window = None
    self._video_port = video_port
    self._preview_temp = None
    if preview_root is None:
        self._preview_temp = tempfile.TemporaryDirectory(prefix="memegif-preview-")
        self._preview_root = Path(self._preview_temp.name)
    else:
        self._preview_root = Path(preview_root)
        self._preview_root.mkdir(parents=True, exist_ok=True)


def cleanup(self, *_):
    """清理本次运行创建的预览目录。"""
    if self._preview_temp is not None:
        self._preview_temp.cleanup()
        self._preview_temp = None
```

在 `load_video()` 中探测并返回宽高：

```python
duration = converter.probe_duration(path)
fps = converter.probe_fps(path)
width, height = converter.probe_dimensions(path)
kind = "gif" if os.path.splitext(path)[1].lower() == ".gif" else "video"
return {
    "path": path,
    "duration": duration,
    "fps": fps,
    "width": width,
    "height": height,
    "kind": kind,
}
```

- [ ] **Step 8: 运行 Task 1 测试并记录检查点**

Run:

```powershell
venv\Scripts\python.exe -m pytest tests/test_converter.py tests/test_app.py::test_load_video_returns_source_dimensions -v
git diff --check
git status --short
```

Expected: 测试全部 `PASS`；`git diff --check` 无输出；状态只包含计划内文件和既有 `.claude/`。

---

### Task 2: 生成轻量 H.264 GIF 预览

**Files:**
- Modify: `converter.py`（在 `convert_once()` 前新增函数）
- Modify: `tests/test_converter.py`

- [ ] **Step 1: 增加测试用动态 GIF fixture**

在 `tests/test_converter.py` 增加：

```python
@pytest.fixture
def animated_gif(tmp_path):
    out = tmp_path / "animated.gif"
    cmd = [
        converter.find_ffmpeg(), "-y",
        "-f", "lavfi", "-i", "testsrc2=size=160x90:rate=12:duration=1",
        "-vf", "format=rgb24",
        str(out),
    ]
    import subprocess
    subprocess.run(cmd, capture_output=True, check=True)
    return out
```

- [ ] **Step 2: 写预览生成失败测试**

继续增加：

```python
def test_create_gif_preview_produces_bounded_mp4(animated_gif, tmp_path):
    out = tmp_path / "preview.mp4"

    result = converter.create_gif_preview(str(animated_gif), str(out))

    assert result == str(out)
    assert out.exists()
    assert out.stat().st_size > 0
    width, height = converter.probe_dimensions(str(out))
    assert max(width, height) <= 640
    assert width / height == pytest.approx(160 / 90, rel=0.03)
    assert converter.probe_duration(str(out)) == pytest.approx(1.0, abs=0.15)


def test_create_gif_preview_builds_h264_faststart_command(monkeypatch, tmp_path):
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        Path(cmd[-1]).write_bytes(b"mp4")
        return type("Result", (), {})()

    monkeypatch.setattr(converter, "find_ffmpeg", lambda: "ffmpeg")
    monkeypatch.setattr(converter.subprocess, "run", fake_run)
    source = tmp_path / "source.gif"
    source.write_bytes(b"GIF89a")
    out = tmp_path / "preview.mp4"

    converter.create_gif_preview(str(source), str(out))

    cmd = captured["cmd"]
    assert cmd[cmd.index("-c:v") + 1] == "libx264"
    assert cmd[cmd.index("-pix_fmt") + 1] == "yuv420p"
    assert cmd[cmd.index("-movflags") + 1] == "+faststart"
    assert "fps=12" in cmd[cmd.index("-vf") + 1]
    assert "scale=" in cmd[cmd.index("-vf") + 1]
```

- [ ] **Step 3: 运行测试并确认失败**

Run:

```powershell
venv\Scripts\python.exe -m pytest tests/test_converter.py::test_create_gif_preview_produces_bounded_mp4 tests/test_converter.py::test_create_gif_preview_builds_h264_faststart_command -v
```

Expected: `FAIL`，原因是 `converter.create_gif_preview` 不存在。

- [ ] **Step 4: 实现轻量预览生成函数**

在 `converter.py` 的 `convert_once()` 前增加：

```python
def create_gif_preview(gif_path: str, out_path: str) -> str:
    """把 GIF 一次性转成适合 WebView2 seek 的轻量 MP4。"""
    source = Path(gif_path)
    if not source.is_file():
        raise FileNotFoundError(f"GIF 文件不存在：{gif_path}")
    target = Path(out_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    vf = (
        "fps=12,"
        "scale='if(gt(iw,ih),min(640,iw),-2)':"
        "'if(gt(iw,ih),-2,min(640,ih))':flags=lanczos,"
        "format=yuv420p"
    )
    cmd = [
        find_ffmpeg(), "-y", "-i", str(source),
        "-an", "-vf", vf,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "26",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        str(target),
    ]
    subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8",
        errors="replace", check=True,
    )
    if not target.is_file() or target.stat().st_size <= 0:
        raise RuntimeError("GIF 预览文件生成失败")
    return str(target)
```

该预览固定使用 12fps，满足设计中的“最高 24fps”约束，并减少首次导入转码开销。

- [ ] **Step 5: 运行预览生成测试**

Run:

```powershell
venv\Scripts\python.exe -m pytest tests/test_converter.py -v
```

Expected: 全部 `PASS` 或既有素材测试 `SKIPPED`；生成的 MP4 尺寸比例与时长断言通过。

- [ ] **Step 6: 验证实际编码和像素格式**

Run:

```powershell
$gif = Join-Path $env:TEMP "memegif-plan-test.gif"; $mp4 = Join-Path $env:TEMP "memegif-plan-test.mp4"; & (venv\Scripts\python.exe -c "import converter,subprocess; f=converter.find_ffmpeg(); subprocess.run([f,'-y','-f','lavfi','-i','testsrc2=size=160x90:rate=12:duration=1',r'$gif'],check=True,capture_output=True); converter.create_gif_preview(r'$gif',r'$mp4')"); ffprobe -v error -select_streams v:0 -show_entries stream=codec_name,pix_fmt,width,height -of json $mp4; Remove-Item $gif,$mp4 -Force
```

Expected: JSON 中包含 `"codec_name": "h264"`、`"pix_fmt": "yuv420p"`，宽高不超过 640。

- [ ] **Step 7: 记录检查点**

Run:

```powershell
git diff --check
git status --short
```

Expected: 无空白错误，只有计划内改动及既有 `.claude/`。

---

### Task 3: 实现预览缓存、并发保护和清理

**Files:**
- Modify: `app.py:6-11,116-168,207-255`
- Modify: `tests/test_app.py`

- [ ] **Step 1: 写成功、复用和缓存失效测试**

在 `tests/test_app.py` 增加导入：

```python
import os
import threading
import time
```

增加测试：

```python
def test_prepare_gif_preview_generates_once_and_returns_url(monkeypatch, tmp_path):
    source = tmp_path / "source.gif"
    source.write_bytes(b"GIF89a-source")
    calls = []

    def fake_create(source_path, out_path):
        calls.append((source_path, out_path))
        Path(out_path).write_bytes(b"mp4-preview")
        return out_path

    monkeypatch.setattr(app.converter, "create_gif_preview", fake_create)
    api = app.Api(4321, preview_root=tmp_path / "preview")

    try:
        first = api.prepare_gif_preview(str(source))
        second = api.prepare_gif_preview(str(source))
    finally:
        api.cleanup()

    assert first == second
    assert first["url"].startswith("http://127.0.0.1:4321/video?id=")
    assert len(calls) == 1


def test_prepare_gif_preview_invalidates_changed_source(monkeypatch, tmp_path):
    source = tmp_path / "source.gif"
    source.write_bytes(b"first")
    calls = []

    def fake_create(source_path, out_path):
        calls.append(out_path)
        Path(out_path).write_bytes(b"mp4")
        return out_path

    monkeypatch.setattr(app.converter, "create_gif_preview", fake_create)
    api = app.Api(4321, preview_root=tmp_path / "preview")

    try:
        first = api.prepare_gif_preview(str(source))
        source.write_bytes(b"second-version")
        os.utime(source, ns=(source.stat().st_atime_ns, source.stat().st_mtime_ns + 1_000_000))
        second = api.prepare_gif_preview(str(source))
    finally:
        api.cleanup()

    assert first["url"] != second["url"]
    assert len(calls) == 2
```

- [ ] **Step 2: 写校验、异常和清理测试**

继续增加：

```python
def test_prepare_gif_preview_rejects_non_gif(tmp_path):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    api = app.Api(4321, preview_root=tmp_path / "preview")

    try:
        result = api.prepare_gif_preview(str(source))
    finally:
        api.cleanup()

    assert result == {"error": "只能为 GIF 生成片段预览"}


def test_prepare_gif_preview_returns_readable_error(monkeypatch, tmp_path):
    source = tmp_path / "source.gif"
    source.write_bytes(b"GIF89a")
    monkeypatch.setattr(
        app.converter, "create_gif_preview",
        Mock(side_effect=RuntimeError("编码器不可用")),
    )
    api = app.Api(4321, preview_root=tmp_path / "preview")

    try:
        result = api.prepare_gif_preview(str(source))
    finally:
        api.cleanup()

    assert result == {"error": "无法生成 GIF 片段预览：编码器不可用"}


def test_cleanup_removes_owned_temporary_directory():
    api = app.Api(4321)
    root = api._preview_root
    (root / "preview.mp4").write_bytes(b"mp4")

    api.cleanup()

    assert not root.exists()
```

- [ ] **Step 3: 写并发只生成一次的测试**

继续增加：

```python
def test_prepare_gif_preview_serializes_same_source(monkeypatch, tmp_path):
    source = tmp_path / "source.gif"
    source.write_bytes(b"GIF89a")
    calls = 0
    calls_lock = threading.Lock()

    def fake_create(source_path, out_path):
        nonlocal calls
        with calls_lock:
            calls += 1
        time.sleep(0.05)
        Path(out_path).write_bytes(b"mp4")
        return out_path

    monkeypatch.setattr(app.converter, "create_gif_preview", fake_create)
    api = app.Api(4321, preview_root=tmp_path / "preview")
    results = []

    try:
        threads = [
            threading.Thread(
                target=lambda: results.append(api.prepare_gif_preview(str(source)))
            )
            for _ in range(2)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
    finally:
        api.cleanup()

    assert calls == 1
    assert len(results) == 2
    assert results[0] == results[1]
```

- [ ] **Step 4: 运行 API 测试并确认失败**

Run:

```powershell
venv\Scripts\python.exe -m pytest tests/test_app.py -v
```

Expected: 新测试因 `prepare_gif_preview()` 不存在而 `FAIL`；Task 1 的元数据测试仍 `PASS`。

- [ ] **Step 5: 实现缓存键、锁和预览 API**

在 `app.py` 增加：

```python
import hashlib
```

在 `Api.__init__()` 末尾增加：

```python
self._preview_cache = {}
self._preview_lock = threading.Lock()
```

在 `Api` 中增加：

```python
def _preview_key(self, path):
    resolved = os.path.normcase(os.path.abspath(path))
    stat = os.stat(resolved)
    return resolved, stat.st_size, stat.st_mtime_ns


def prepare_gif_preview(self, path):
    """准备可 seek 的轻量 MP4，返回本地媒体 URL。"""
    try:
        if os.path.splitext(path)[1].lower() != ".gif":
            return {"error": "只能为 GIF 生成片段预览"}
        if not os.path.isfile(path):
            return {"error": "GIF 文件不存在"}
        key = self._preview_key(path)
        with self._preview_lock:
            cached = self._preview_cache.get(key)
            if cached and Path(cached).is_file():
                out_path = cached
            else:
                digest = hashlib.sha256(repr(key).encode("utf-8")).hexdigest()[:20]
                out_path = str(self._preview_root / f"{digest}.mp4")
                converter.create_gif_preview(path, out_path)
                self._preview_cache[key] = out_path
            vid = _register_video(out_path)
        return {"url": f"http://127.0.0.1:{self._video_port}/video?id={vid}"}
    except Exception as e:
        return {"error": f"无法生成 GIF 片段预览：{e}"}
```

说明：锁覆盖生成过程，以最小实现保证同源并发不会重复启动 ffmpeg；当前桌面应用一次只操作一个文件，不需要引入更复杂的 per-key future。

- [ ] **Step 6: 让重复调用复用 URL，而不仅是文件**

Step 5 的测试要求相同调用返回相同 URL。将缓存值改为同时保存 `out_path` 和 `url`：

```python
cached = self._preview_cache.get(key)
if cached and Path(cached["path"]).is_file():
    return {"url": cached["url"]}

digest = hashlib.sha256(repr(key).encode("utf-8")).hexdigest()[:20]
out_path = str(self._preview_root / f"{digest}.mp4")
converter.create_gif_preview(path, out_path)
vid = _register_video(out_path)
url = f"http://127.0.0.1:{self._video_port}/video?id={vid}"
self._preview_cache[key] = {"path": out_path, "url": url}
return {"url": url}
```

整个缓存查找、生成、注册和写缓存仍位于 `with self._preview_lock:` 内；异常处理位于锁外层。

- [ ] **Step 7: 绑定窗口关闭清理**

在 `main()` 中 `window.events.loaded += _register_dnd` 后增加：

```python
window.events.closed += api.cleanup
```

同时让 `cleanup()` 幂等，并清空缓存：

```python
def cleanup(self, *_):
    """清理本次运行创建的预览目录。"""
    self._preview_cache.clear()
    if self._preview_temp is not None:
        self._preview_temp.cleanup()
        self._preview_temp = None
```

- [ ] **Step 8: 运行 API 和全量 Python 测试**

Run:

```powershell
venv\Scripts\python.exe -m pytest tests/test_app.py -v
venv\Scripts\python.exe -m pytest -v
```

Expected: 所有测试 `PASS`；只有明确标记为缺素材的测试允许 `SKIPPED`。

- [ ] **Step 9: 记录检查点**

Run:

```powershell
git diff --check
git status --short
```

Expected: 无空白错误；不出现临时 MP4 或 palette 文件。

---

### Task 4: 提取并测试前端区间播放纯逻辑

**Files:**
- Create: `web/range-preview.js`
- Create: `tests/test_range_preview.js`
- Modify: `web/index.html:84`

- [ ] **Step 1: 写区间动作和请求有效性测试**

新建 `tests/test_range_preview.js`：

```javascript
const test = require("node:test");
const assert = require("node:assert/strict");
const {
  playbackAction,
  isCurrentPreviewRequest,
} = require("../web/range-preview.js");

test("播放位置在所选区间内时不跳转", () => {
  assert.deepEqual(playbackAction(1.5, 1, 2), {
    pause: false,
    seekTo: null,
  });
});

test("播放到终点附近时回到起点", () => {
  assert.deepEqual(playbackAction(1.97, 1, 2), {
    pause: false,
    seekTo: 1,
  });
});

test("播放位置落在起点前时回到起点", () => {
  assert.deepEqual(playbackAction(0.5, 1, 2), {
    pause: false,
    seekTo: 1,
  });
});

test("过短区间暂停并停在起点", () => {
  assert.deepEqual(playbackAction(1.03, 1, 1.05), {
    pause: true,
    seekTo: 1,
  });
});

test("只有请求编号和路径都匹配时才接受异步响应", () => {
  assert.equal(isCurrentPreviewRequest(3, 3, "a.gif", "a.gif"), true);
  assert.equal(isCurrentPreviewRequest(2, 3, "a.gif", "a.gif"), false);
  assert.equal(isCurrentPreviewRequest(3, 3, "old.gif", "a.gif"), false);
});
```

- [ ] **Step 2: 运行 Node 测试并确认失败**

Run:

```powershell
node --test tests/test_range_preview.js
```

Expected: `FAIL`，提示找不到 `web/range-preview.js`。

- [ ] **Step 3: 实现无 DOM 依赖的纯逻辑模块**

新建 `web/range-preview.js`：

```javascript
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.RangePreview = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  const MIN_RANGE_SECONDS = 0.1;
  const END_EPSILON_SECONDS = 0.04;

  function playbackAction(currentTime, startSec, endSec) {
    if (endSec - startSec < MIN_RANGE_SECONDS) {
      return { pause: true, seekTo: startSec };
    }
    if (
      currentTime < startSec - END_EPSILON_SECONDS ||
      currentTime >= endSec - END_EPSILON_SECONDS
    ) {
      return { pause: false, seekTo: startSec };
    }
    return { pause: false, seekTo: null };
  }

  function isCurrentPreviewRequest(requestId, activeId, requestPath, activePath) {
    return requestId === activeId && requestPath === activePath;
  }

  return {
    MIN_RANGE_SECONDS,
    playbackAction,
    isCurrentPreviewRequest,
  };
});
```

- [ ] **Step 4: 运行 Node 测试**

Run:

```powershell
node --test tests/test_range_preview.js
```

Expected: 5 项测试全部 `PASS`。

- [ ] **Step 5: 在页面中先加载纯逻辑模块**

将 `web/index.html` 底部脚本改为：

```html
<script src="range-preview.js"></script>
<script src="main.js"></script>
```

- [ ] **Step 6: 检查 JavaScript 语法与检查点**

Run:

```powershell
node --check web/range-preview.js
node --test tests/test_range_preview.js
git diff --check
```

Expected: 命令全部成功，无输出错误。

---

### Task 5: 将 GIF 预览切换为可 seek 的轻量视频

**Files:**
- Modify: `web/main.js:3-36,85-169,172-192,240-253,327-350`
- Test: `tests/test_range_preview.js`

- [ ] **Step 1: 扩展前端状态并分离源类型与预览模式**

将 `state` 改为：

```javascript
let state = {
  path: null,
  duration: 0,
  fps: 25,
  sourceWidth: 0,
  sourceHeight: 0,
  startSec: 0,
  endSec: 0,
  cropOn: false,
  kind: "video",
  previewMode: "video",
  loadRequestId: 0,
};
```

将媒体抽象改为：

```javascript
function mediaEl() {
  return state.previewMode === "gif-image" ? gifImg : video;
}

function sourceMediaSize() {
  if (state.sourceWidth && state.sourceHeight) {
    return { w: state.sourceWidth, h: state.sourceHeight };
  }
  return state.previewMode === "gif-image"
    ? { w: gifImg.naturalWidth, h: gifImg.naturalHeight }
    : { w: video.videoWidth, h: video.videoHeight };
}

function seekTo(sec) {
  if (state.previewMode !== "video") return;
  try { video.currentTime = sec; } catch (e) {}
}
```

- [ ] **Step 2: 增加播放辅助函数**

在 `seekTo()` 后增加：

```javascript
function playVideo() {
  if (state.previewMode !== "video") return;
  const pending = video.play();
  if (pending && pending.catch) pending.catch(() => {});
}

function restartSelectedPreview(seekToEndForVideo = false) {
  if (state.kind === "gif" && state.previewMode === "video") {
    seekTo(state.startSec);
    playVideo();
    return;
  }
  seekTo(seekToEndForVideo ? state.endSec : state.startSec);
}

function applyGifRangeLoop() {
  if (state.kind !== "gif" || state.previewMode !== "video") return;
  const action = RangePreview.playbackAction(
    video.currentTime,
    state.startSec,
    state.endSec,
  );
  if (action.pause) video.pause();
  if (action.seekTo !== null) seekTo(action.seekTo);
  if (!action.pause && action.seekTo !== null) playVideo();
}
```

- [ ] **Step 3: 增加 GIF `<img>` 降级函数**

在 `onVideoLoaded()` 前增加：

```javascript
async function fallbackToGifImage(path, requestId, message) {
  const gifRes = await window.pywebview.api.gif_data_url(path);
  if (!RangePreview.isCurrentPreviewRequest(
    requestId, state.loadRequestId, path, state.path,
  )) return;

  video.pause();
  video.removeAttribute("src");
  video.load();
  video.classList.add("hidden");
  state.previewMode = "gif-image";
  gifImg.classList.remove("hidden");

  if (gifRes.error) {
    setStatus(gifRes.error + "，最终转换仍会按所选时间生效", "err");
    return;
  }
  gifImg.src = gifRes.url;
  setStatus(message, "err");
  if (state.cropOn) layoutCropOverlay();
}
```

- [ ] **Step 4: 重写 GIF 导入分支并加入请求竞态保护**

在 `onVideoLoaded(info)` 成功校验后先写入：

```javascript
const requestId = ++state.loadRequestId;
state.path = info.path;
state.duration = info.duration;
state.fps = info.fps || 25;
state.sourceWidth = info.width || 0;
state.sourceHeight = info.height || 0;
state.kind = info.kind === "gif" ? "gif" : "video";
state.previewMode = "video";
```

在异步媒体请求前完成公共初始化，避免用户在等待期间操作旧区间：

```javascript
disableCrop();
editor.classList.toggle("has-hours", showHours());
setRange(0, state.duration);
dropzone.classList.add("hidden");
editor.classList.remove("hidden");
```

用以下流程替换原 GIF 分支：

```javascript
if (state.kind === "gif") {
  gifImg.classList.add("hidden");
  gifImg.removeAttribute("src");
  video.classList.remove("hidden");
  video.removeAttribute("src");
  video.load();
  state.previewMode = "video";
  setStatus("正在准备 GIF 片段预览…", "busy");

  const preview = await window.pywebview.api.prepare_gif_preview(info.path);
  if (!RangePreview.isCurrentPreviewRequest(
    requestId, state.loadRequestId, info.path, state.path,
  )) return;

  if (preview.error) {
    await fallbackToGifImage(
      info.path,
      requestId,
      "无法生成选段预览，最终转换仍会按所选时间生效",
    );
    return;
  }

  video.addEventListener("loadeddata", () => {
    if (!RangePreview.isCurrentPreviewRequest(
      requestId, state.loadRequestId, info.path, state.path,
    )) return;
    seekTo(state.startSec);
    playVideo();
    if (state.cropOn) layoutCropOverlay();
    setStatus("拖动滑块或输入时间，预览将循环播放所选片段", null);
  }, { once: true });
  video.addEventListener("error", () => {
    if (!RangePreview.isCurrentPreviewRequest(
      requestId, state.loadRequestId, info.path, state.path,
    )) return;
    fallbackToGifImage(
      info.path,
      requestId,
      "GIF 片段预览加载失败，最终转换仍会按所选时间生效",
    );
  }, { once: true });
  video.src = preview.url;
  video.load();
} else {
  // 保留现有普通视频分支，只补 state.previewMode = "video" 和请求有效性判断。
}
```

删除 `onVideoLoaded()` 末尾重复的 `disableCrop()`、`setRange()`、编辑器显隐操作和会覆盖“正在准备”状态的通用 `setStatus()`。普通视频分支继续显示现有操作提示。

- [ ] **Step 5: 在重置流程中使旧请求失效**

将 `resetToDropzone()` 开头改为：

```javascript
function resetToDropzone() {
  state.loadRequestId += 1;
  try { video.pause(); } catch (e) {}
```

并在状态清理处增加：

```javascript
state.sourceWidth = 0;
state.sourceHeight = 0;
state.previewMode = "video";
```

- [ ] **Step 6: 修改滑块和数字输入后的预览动作**

改为：

```javascript
startRange.addEventListener("input", () => {
  const s = (parseFloat(startRange.value) / 100) * state.duration;
  setRange(s, state.endSec);
  restartSelectedPreview(false);
});

endRange.addEventListener("input", () => {
  const e = (parseFloat(endRange.value) / 100) * state.duration;
  setRange(state.startSec, e);
  restartSelectedPreview(true);
});
```

在 `bindTimeGroup()` 中把最后一行改为：

```javascript
restartSelectedPreview(seekToEnd);
```

这样 GIF 无论修改哪一端都从最终起点开始播放，普通视频继续保持“改起点看起点、改终点看终点”的既有行为。

- [ ] **Step 7: 绑定区间循环事件**

在 `whenReady()` 中增加一次性事件绑定：

```javascript
video.addEventListener("timeupdate", applyGifRangeLoop);
```

区间变更后的立即跳转由 `restartSelectedPreview()` 负责，持续播放的终点约束由 `timeupdate` 负责；不监听 `seeking`，避免在 seek 过程中递归设置 `currentTime`。

- [ ] **Step 8: 修正裁切坐标使用源媒体尺寸**

在 `currentCropPixels()` 中将：

```javascript
const { w: natW, h: natH } = mediaSize();
```

替换为：

```javascript
const { w: natW, h: natH } = sourceMediaSize();
```

`layoutCropOverlay()` 仍使用实际 `mediaEl().getBoundingClientRect()`，因此轻量 MP4 负责布局，源宽高只负责输出坐标换算。

- [ ] **Step 9: 增加透明预览的显式限制说明**

轻量 MP4 不保留 alpha；透明区域使用 `.video-wrap` 已有的黑色背景语义进行预览，最终导出始终读取源 GIF 并保留现有透明处理结果。本任务不增加额外 alpha 合成滤镜，因为它不影响时间选段正确性，并会扩大本次修复范围。

- [ ] **Step 10: 运行前端静态和纯逻辑测试**

Run:

```powershell
node --check web/range-preview.js
node --check web/main.js
node --test tests/test_range_preview.js
```

Expected: 语法检查成功，5 项 Node 测试全部 `PASS`。

- [ ] **Step 11: 运行全量自动化测试和检查点**

Run:

```powershell
venv\Scripts\python.exe -m pytest -v
node --test tests/test_range_preview.js
git diff --check
git status --short
```

Expected: Python 和 Node 测试通过；状态只包含计划内文件、设计/计划文档和既有 `.claude/`。

---

### Task 6: 更新文档并进行真实应用验收

**Files:**
- Modify: `README.md:10`
- Verify: `app.py`, `converter.py`, `web/main.js`, `web/range-preview.js`

- [ ] **Step 1: 更新 README 的 GIF 预览说明**

将 README 第 10 行替换为：

```markdown
支持的导入格式：mp4 / mov / mkv / avi / webm / flv，以及 **GIF**。导入 GIF 后会生成一次轻量视频预览；调整起止时间时，窗口会实时循环播放所选片段，裁切和最终转换仍直接使用原始 GIF 并按所选区间精确生效。
```

- [ ] **Step 2: 运行全部自动化验证**

Run:

```powershell
venv\Scripts\python.exe -m pytest -v
node --check web/range-preview.js
node --check web/main.js
node --test tests/test_range_preview.js
git diff --check
```

Expected: 所有测试和语法检查成功；`git diff --check` 无输出。

- [ ] **Step 3: 启动实际应用**

Run:

```powershell
venv\Scripts\python.exe app.py
```

Expected: MemeGIF 桌面窗口打开，控制台无 traceback。此命令需保持运行直至完成下面的手动验收。

- [ ] **Step 4: 验收 GIF 实时区间循环**

使用至少 2 秒、不同时间画面明显不同的 GIF：

1. 导入后出现“正在准备 GIF 片段预览…”；
2. 准备完成后自动播放；
3. 把起点拖到约 25%，画面从新起点开始；
4. 把终点拖到约 60%，播放到终点后回到起点；
5. 连续拖动两端时不触发新的 ffmpeg 转换，也不恢复完整 GIF；
6. 修改数字时间输入，行为与滑块一致；
7. 所选片段短于 0.1 秒时播放器不发生高频闪烁或卡死。

Expected: 播放窗口始终只循环最终所选区间。

- [ ] **Step 5: 验收裁切坐标和最终导出**

1. 对 GIF 开启裁切，选择一个容易辨认的局部区域；
2. 设置非零起点和短于完整时长的终点；
3. 转为 QQ 表情；
4. 打开产物，检查时长约等于 `end-start`，画面区域与裁切框一致；
5. 确认产物不是由 640px/24fps 预览直接生成，而是遵循 QQ 预设和原始源文件。

Expected: 时间和裁切均准确，最终导出链路无变化。

- [ ] **Step 6: 验收普通视频回归**

导入 `assets/sample.mp4`：

1. 修改起点时预览跳到起点；
2. 修改终点时预览跳到终点；
3. 裁切框和导出正常；
4. 不显示“准备 GIF 片段预览”。

Expected: 普通视频现有行为不变。

- [ ] **Step 7: 验收失败降级与快速换文件**

失败降级可在开发环境中临时让 `prepare_gif_preview()` 返回 `{"error": "测试失败"}`，只用于验收，验收后必须撤销该临时修改：

1. 导入 GIF 后显示原始 GIF `<img>`；
2. 状态明确说明选段预览失败但最终转换仍有效；
3. 时间选择和最终导出仍成功；
4. 恢复正常代码后，快速连续导入两个文件，第一份的晚到响应不能覆盖第二份。

Expected: 降级可用，异步响应无串文件。

- [ ] **Step 8: 停止应用并确认临时目录清理**

关闭窗口后检查系统临时目录：

```powershell
Get-ChildItem $env:TEMP -Directory -Filter "memegif-preview-*"
```

Expected: 本次正常关闭创建的目录已消失。若存在更早异常退出遗留目录，只记录其时间，不在本任务中删除用户未知文件。

- [ ] **Step 9: 最终审阅改动范围**

Run:

```powershell
git diff --stat
git diff --check
git status --short
```

Expected: 仅包含：

- `converter.py`
- `app.py`
- `web/main.js`
- `web/range-preview.js`
- `web/index.html`
- `tests/test_converter.py`
- `tests/test_app.py`
- `tests/test_range_preview.js`
- `README.md`
- 已批准的设计文档和本计划

不得包含临时 GIF/MP4、palette 文件、缓存、构建产物或 `.claude/` 内容。

---

## 完成定义

只有同时满足以下条件才能宣布修复完成：

- GIF 导入时只生成一次轻量 MP4；
- 起点和终点变化后立即从最终起点播放；
- 播放到终点后稳定回到起点；
- 快速换文件不会显示旧预览；
- 预览失败可降级到原 GIF；
- 裁切坐标使用源 GIF 宽高；
- 最终导出仍读取源 GIF；
- 普通视频行为无回归；
- Python、Node 测试和真实应用验收全部通过；
- 工作区无意外文件，且未在未经授权时创建提交。

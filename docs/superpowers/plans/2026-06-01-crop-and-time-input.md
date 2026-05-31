# 画面裁切 + 智能时间输入 + PNG 图标 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 MemeGIF 增加画面裁切、按 智:分:秒:帧 精确输入时间，并把内嵌 SVG 图案换成应用 PNG，全程保持深色 + 陶土橙风格。

**Architecture:** 后端在现有 ffmpeg 滤镜链前插入 `crop` 滤镜（抽出纯函数 `_build_vf` 便于单测），并新增 `probe_fps` 探测真实帧率。前端把"以滑块百分比为真相"重构为"以起点秒/终点秒为真相"，滑块、数字输入框、预览三者由它派生联动；裁切框为纯 HTML/CSS/JS 叠层，转换时把显示坐标换算成视频真实像素传给后端。

**Tech Stack:** Python 3.12 + pywebview + ffmpeg/ffprobe；前端原生 HTML/CSS/JS；pytest（仅后端纯逻辑可单测，前端走手动验收）。

约定：所有命令在 `F:\memegif` 下执行；测试命令统一用 `venv\Scripts\python.exe -m pytest`。

---

## 文件结构

- `converter.py`（改）：新增 `_parse_fps`、`probe_fps`、`_build_vf`；`convert_once`/`convert` 加 `crop` 参数。
- `app.py`（改）：`load_video` 返回 `fps`；`convert` API 加 `crop` 参数透传。
- `tests/test_converter.py`（改）：新增 `_parse_fps`、`_build_vf` 单测，带 crop 的转换用例。
- `web/logo.png`（新）：从 `assets/icon/MemeGIF-icon-transparent.png` 拷入。
- `web/index.html`（改）：SVG→PNG、时间输入行、裁切按钮/裁切框/正方形开关 DOM。
- `web/main.js`（改）：状态重构、时间联动、裁切框拖拽缩放与坐标换算。
- `web/style.css`（改）：时间输入框、裁切框/手柄/遮罩、PNG logo 样式（沿用现有 CSS 变量）。

---

## Task 1：探测真实帧率（`_parse_fps` + `probe_fps`）

**Files:**
- Modify: `converter.py`（在 `probe_duration` 之后新增）
- Test: `tests/test_converter.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_converter.py` 末尾追加：

```python
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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `venv\Scripts\python.exe -m pytest tests/test_converter.py::test_parse_fps_normal -v`
Expected: FAIL（`AttributeError: module 'converter' has no attribute '_parse_fps'`）

- [ ] **Step 3: 实现**

在 `converter.py` 的 `probe_duration` 函数之后插入：

```python
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
```

- [ ] **Step 4: 运行测试确认通过**

Run: `venv\Scripts\python.exe -m pytest tests/test_converter.py -k "fps" -v`
Expected: PASS（`test_probe_fps_positive` 若缺 sample.mp4 则 skip）

- [ ] **Step 5: 提交**

```bash
git add converter.py tests/test_converter.py
git commit -m "feat: 探测视频真实帧率 probe_fps（带回退）"
```

---

## Task 2：裁切滤镜（`_build_vf` 纯函数 + `convert_once`/`convert` 加 crop）

**Files:**
- Modify: `converter.py`（`convert_once`、`convert`）
- Test: `tests/test_converter.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_converter.py` 末尾追加：

```python
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
    # 裁出一块明确的矩形（源至少 64x64 才有意义，sample 一般足够大）
    converter.convert_once(
        video_path=str(SAMPLE), start=0.0, end=1.0,
        max_edge=240, fps=10, out_path=str(out),
        crop={"w": 120, "h": 120, "x": 0, "y": 0},
    )
    w, h = converter.gif_dimensions(str(out))
    assert w == h  # 1:1 裁切后等比缩放仍为正方形
```

- [ ] **Step 2: 运行测试确认失败**

Run: `venv\Scripts\python.exe -m pytest tests/test_converter.py::test_build_vf_no_crop -v`
Expected: FAIL（`AttributeError: ... '_build_vf'`）

- [ ] **Step 3: 实现**

在 `converter.py` 中，把 `convert_once` 上方加入 `_build_vf`，并改写 `convert_once`、`convert`。

新增纯函数（放在 `convert_once` 之前）：

```python
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
```

把 `convert_once` 的签名和 vf 构造改为：

```python
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
```

把 `convert` 的签名和循环内调用改为透传 crop：

```python
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
```

- [ ] **Step 4: 运行测试确认通过**

Run: `venv\Scripts\python.exe -m pytest tests/test_converter.py -v`
Expected: PASS（全部既有用例 + 新增 `_build_vf` 用例通过；带 sample 的用例若无素材则 skip）

- [ ] **Step 5: 提交**

```bash
git add converter.py tests/test_converter.py
git commit -m "feat: ffmpeg 裁切滤镜，convert 支持 crop 参数"
```

---

## Task 3：后端 API 透传（`load_video` 返回 fps，`convert` 加 crop）

**Files:**
- Modify: `app.py`（`Api.load_video`、`Api.convert`）

说明：这部分是 pywebview 桥接，无单测；改完用 Python 直接调用验证 `load_video`，`convert` 在 Task 8 端到端验收。

- [ ] **Step 1: 修改 `load_video`**

把 `app.py` 中 `load_video` 改为：

```python
    def load_video(self, path):
        """探测视频时长与帧率，返回 {path, duration, fps} 或 {error}。"""
        try:
            duration = converter.probe_duration(path)
            fps = converter.probe_fps(path)
            return {"path": path, "duration": duration, "fps": fps}
        except Exception as e:
            return {"error": f"无法读取视频：{e}"}
```

- [ ] **Step 2: 修改 `convert`**

把 `app.py` 中 `convert` 方法签名与调用改为：

```python
    def convert(self, path, start, end, preset_key, crop=None):
        """执行转换，返回 {out_path, size_mb, max_edge, fps, within_limit} 或 {error}。

        crop 为 {'w','h','x','y'} 真实像素裁切区域，或 None 表示不裁切。
        """
        try:
            preset = get_preset(preset_key)
            out_path = converter.default_output_path(path, preset)
            r = converter.convert(path, float(start), float(end), preset, out_path, crop=crop)
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
```

- [ ] **Step 3: 验证 `load_video` 返回 fps**

Run（需有 sample.mp4，否则跳过此步、Task 8 再验）：
```bash
venv\Scripts\python.exe -c "import converter,app; a=app.Api(0); print(a.load_video(r'assets/sample.mp4'))"
```
Expected: 打印含 `'fps'` 键且为正数的 dict。

- [ ] **Step 4: 提交**

```bash
git add app.py
git commit -m "feat: load_video 返回 fps，convert API 支持 crop"
```

---

## Task 4：PNG logo 替换内嵌 SVG

**Files:**
- Create: `web/logo.png`（从 `assets/icon/MemeGIF-icon-transparent.png` 拷入）
- Modify: `web/index.html`（顶栏 logo、拖放区图标）
- Modify: `web/style.css`（logo 尺寸）

- [ ] **Step 1: 拷入 PNG**

Run:
```bash
cp assets/icon/MemeGIF-icon-transparent.png web/logo.png
```
Expected: `web/logo.png` 存在。

- [ ] **Step 2: 替换顶栏 logo（index.html）**

把 `web/index.html` 顶栏的 `<span class="logo">…</span>`（含内嵌 `<svg>`）整块替换为：

```html
    <span class="logo" aria-hidden="true">
      <img src="logo.png" alt="MemeGIF" class="logo-img" />
    </span>
```

- [ ] **Step 3: 替换拖放区图标（index.html）**

把 `web/index.html` 拖放区里的 `<svg class="drop-icon" …>…</svg>` 整块替换为：

```html
      <img src="logo.png" alt="" class="drop-icon-img" />
```

- [ ] **Step 4: 加 logo 样式（style.css）**

在 `web/style.css` 的 `.logo { display: inline-flex; }` 之后追加：

```css
.logo-img { width: 24px; height: 24px; object-fit: contain; display: block; }
.drop-icon-img { width: 56px; height: 56px; object-fit: contain; opacity: .95; }
```

- [ ] **Step 5: 手动验收**

Run: `venv\Scripts\python.exe app.py`
Expected: 顶栏左侧和拖放区中央都显示应用 PNG 图标（透明底融入深色背景），布局未错位；深色橙风格不变。关闭窗口。

- [ ] **Step 6: 提交**

```bash
git add web/logo.png web/index.html web/style.css
git commit -m "feat: 顶栏与拖放区改用应用 PNG 图标"
```

---

## Task 5：时间输入行 + 裁切控件 DOM（index.html）

**Files:**
- Modify: `web/index.html`（editor 区）

- [ ] **Step 1: 替换时间标签行为数字输入行**

把 `web/index.html` 中整个 `<div class="range-labels">…</div>`（含 start-label/dur-label/end-label）替换为：

```html
        <div class="time-row" id="time-row">
          <label class="time-group">
            <span class="time-tag">起点</span>
            <span class="hours-only"><input class="tnum" id="start-h" type="number" min="0" value="0" />:</span>
            <input class="tnum" id="start-m" type="number" min="0" value="00" />:
            <input class="tnum" id="start-s" type="number" min="0" max="59" value="00" />:
            <input class="tnum" id="start-f" type="number" min="0" value="00" />
          </label>
          <span id="dur-label" class="dur-mid">时长 0.0s</span>
          <label class="time-group">
            <span class="time-tag">终点</span>
            <span class="hours-only"><input class="tnum" id="end-h" type="number" min="0" value="0" />:</span>
            <input class="tnum" id="end-m" type="number" min="0" value="00" />:
            <input class="tnum" id="end-s" type="number" min="0" max="59" value="00" />:
            <input class="tnum" id="end-f" type="number" min="0" value="00" />
          </label>
        </div>
```

（保留其后的 `<div class="dual-slider" …>` 不动。）

- [ ] **Step 2: 把裁切框叠层加进视频区**

把 `web/index.html` 中 `<div class="video-wrap">…</div>` 整块替换为：

```html
      <div class="video-wrap">
        <video id="video" preload="auto" muted playsinline></video>
        <div id="crop-overlay" class="crop-overlay hidden">
          <div id="crop-box" class="crop-box">
            <span class="crop-handle nw" data-h="nw"></span>
            <span class="crop-handle ne" data-h="ne"></span>
            <span class="crop-handle sw" data-h="sw"></span>
            <span class="crop-handle se" data-h="se"></span>
          </div>
        </div>
      </div>
```

- [ ] **Step 3: 在预设按钮上方加裁切工具行**

在 `web/index.html` 中 `<div class="presets">` 这一行之前插入：

```html
      <div class="crop-bar">
        <button id="crop-btn" class="btn-secondary">✂ 裁切</button>
        <label id="square-wrap" class="square-wrap hidden">
          <input type="checkbox" id="square-toggle" /> 锁定正方形
        </label>
      </div>
```

- [ ] **Step 4: 手动验收（仅结构）**

Run: `venv\Scripts\python.exe app.py`
Expected: 拖入视频后能看到「起点/终点」数字框行、「✂ 裁切」按钮（裁切框暂不响应，下个 Task 接逻辑）。关闭窗口。

- [ ] **Step 5: 提交**

```bash
git add web/index.html
git commit -m "feat: 时间输入行与裁切控件 DOM 结构"
```

---

## Task 6：前端逻辑重构 —— 秒为真相、时间联动、裁切（main.js）

**Files:**
- Modify: `web/main.js`（整体重写）

说明：状态模型从"滑块百分比"改为"起点秒/终点秒"，因此整体替换 `main.js`。下方为完整文件内容。

- [ ] **Step 1: 用以下完整内容覆盖 `web/main.js`**

```javascript
// 前端交互：导入视频、可视化选段（滑块 + 数字框双向联动）、画面裁切、调用后端转换。

let state = { path: null, duration: 0, fps: 25, startSec: 0, endSec: 0, cropOn: false };

const $ = (id) => document.getElementById(id);
const dropzone = $("dropzone");
const editor = $("editor");
const video = $("video");
const statusEl = $("status");
const startRange = $("start-range");
const endRange = $("end-range");
const rangeFill = $("range-fill");
const overlay = $("crop-overlay");
const cropBox = $("crop-box");

// 裁切框（显示像素，相对 overlay 左上角）
let cropRect = null;

function whenReady(fn) {
  if (window.pywebview && window.pywebview.api) fn();
  else window.addEventListener("pywebviewready", fn);
}

function setStatus(text, cls) {
  statusEl.textContent = text;
  statusEl.className = "status" + (cls ? " " + cls : "");
}

const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
const showHours = () => state.duration >= 3600;

// ---- 时间 <-> 帧/分/秒 换算 ----
function secToParts(sec) {
  const fps = Math.round(state.fps || 25);
  let whole = Math.floor(sec);
  let frame = Math.round((sec - whole) * (state.fps || 25));
  if (frame >= fps) { frame = 0; whole += 1; } // 帧进位
  return {
    h: Math.floor(whole / 3600),
    m: Math.floor((whole % 3600) / 60),
    s: whole % 60,
    f: frame,
  };
}

function partsToSec(h, m, s, f) {
  return h * 3600 + m * 60 + s + f / (state.fps || 25);
}

function fillTimeInputs(prefix, sec) {
  const p = secToParts(sec);
  if (showHours()) $(prefix + "-h").value = p.h;
  $(prefix + "-m").value = String(p.m).padStart(2, "0");
  $(prefix + "-s").value = String(p.s).padStart(2, "0");
  $(prefix + "-f").value = String(p.f).padStart(2, "0");
}

function readTime(prefix) {
  const h = showHours() ? (parseInt($(prefix + "-h").value, 10) || 0) : 0;
  const m = parseInt($(prefix + "-m").value, 10) || 0;
  const s = parseInt($(prefix + "-s").value, 10) || 0;
  const f = parseInt($(prefix + "-f").value, 10) || 0;
  return partsToSec(h, m, s, f);
}

// ---- 选段唯一真相：startSec / endSec ----
function setRange(startSec, endSec) {
  startSec = clamp(startSec, 0, state.duration);
  endSec = clamp(endSec, 0, state.duration);
  if (startSec > endSec) [startSec, endSec] = [endSec, startSec];
  state.startSec = startSec;
  state.endSec = endSec;
  syncUI();
}

function syncUI() {
  const sp = state.duration ? (state.startSec / state.duration) * 100 : 0;
  const ep = state.duration ? (state.endSec / state.duration) * 100 : 100;
  startRange.value = sp;
  endRange.value = ep;
  rangeFill.style.left = sp + "%";
  rangeFill.style.width = (ep - sp) + "%";
  fillTimeInputs("start", state.startSec);
  fillTimeInputs("end", state.endSec);
  $("dur-label").textContent = "时长 " + (state.endSec - state.startSec).toFixed(1) + "s";
}

async function onVideoLoaded(info) {
  if (info.error) { setStatus(info.error, "err"); return; }
  if (info.cancelled) return;
  state.path = info.path;
  state.duration = info.duration;
  state.fps = info.fps || 25;

  const srcRes = await window.pywebview.api.video_src(info.path);
  video.src = srcRes.url;
  video.load();
  video.addEventListener("loadeddata", () => {
    try { video.currentTime = 0.04; } catch (e) {}
  }, { once: true });
  video.addEventListener("error", () => {
    setStatus("视频预览加载失败，但仍可直接选段后转换", "err");
  }, { once: true });

  disableCrop();                 // 新视频默认不裁切
  editor.classList.toggle("has-hours", showHours());
  setRange(0, state.duration);   // 默认全选

  dropzone.classList.add("hidden");
  editor.classList.remove("hidden");
  const hint = (!info.fps) ? "（未能探测帧率，按 25fps 估算）" : "";
  setStatus("拖动滑块或输入时间选段，可点「裁切」框选画面" + hint, null);
}

function resetToDropzone() {
  try { video.pause(); } catch (e) {}
  video.removeAttribute("src");
  video.load();
  state.path = null;
  state.duration = 0;
  disableCrop();
  editor.classList.add("hidden");
  dropzone.classList.remove("hidden");
  setStatus("拖入视频开始", null);
}

// ---- 滑块联动 ----
startRange.addEventListener("input", () => {
  const s = (parseFloat(startRange.value) / 100) * state.duration;
  setRange(s, state.endSec);
  try { video.currentTime = state.startSec; } catch (e) {}
});
endRange.addEventListener("input", () => {
  const e = (parseFloat(endRange.value) / 100) * state.duration;
  setRange(state.startSec, e);
  try { video.currentTime = state.endSec; } catch (e) {}
});

// ---- 数字框联动 ----
function bindTimeGroup(prefix, seekToEnd) {
  ["-h", "-m", "-s", "-f"].forEach((suf) => {
    const el = $(prefix + suf);
    if (el) el.addEventListener("change", () => {
      setRange(readTime("start"), readTime("end"));
      try { video.currentTime = seekToEnd ? state.endSec : state.startSec; } catch (e) {}
    });
  });
}

// ---- 裁切 ----
function squareLock() { return $("square-toggle").checked; }

function layoutCropOverlay() {
  const wrap = video.parentElement;
  const vr = video.getBoundingClientRect();
  const wr = wrap.getBoundingClientRect();
  overlay.style.left = (vr.left - wr.left) + "px";
  overlay.style.top = (vr.top - wr.top) + "px";
  overlay.style.width = vr.width + "px";
  overlay.style.height = vr.height + "px";
}

function applyCropRect() {
  if (!cropRect) return;
  cropBox.style.left = cropRect.x + "px";
  cropBox.style.top = cropRect.y + "px";
  cropBox.style.width = cropRect.w + "px";
  cropBox.style.height = cropRect.h + "px";
}

function enableCrop() {
  state.cropOn = true;
  $("crop-btn").classList.add("active");
  $("square-wrap").classList.remove("hidden");
  layoutCropOverlay();
  const W = overlay.clientWidth, H = overlay.clientHeight;
  let bw = W * 0.8, bh = H * 0.8;
  if (squareLock()) { const m = Math.min(bw, bh); bw = m; bh = m; }
  cropRect = { x: (W - bw) / 2, y: (H - bh) / 2, w: bw, h: bh };
  applyCropRect();
  overlay.classList.remove("hidden");
}

function disableCrop() {
  state.cropOn = false;
  cropRect = null;
  $("crop-btn").classList.remove("active");
  $("square-wrap").classList.add("hidden");
  overlay.classList.add("hidden");
}

// 把显示像素裁切框换算成视频真实像素，并取偶数、钳制边界
function currentCropPixels() {
  if (!state.cropOn || !cropRect) return null;
  const dispW = overlay.clientWidth, dispH = overlay.clientHeight;
  if (!dispW || !dispH || !video.videoWidth) return null;
  const sx = video.videoWidth / dispW;
  const sy = video.videoHeight / dispH;
  const even = (n) => n - (n % 2);
  let x = clamp(Math.round(cropRect.x * sx), 0, video.videoWidth - 2);
  let y = clamp(Math.round(cropRect.y * sy), 0, video.videoHeight - 2);
  let w = even(clamp(Math.round(cropRect.w * sx), 2, video.videoWidth - x));
  let h = even(clamp(Math.round(cropRect.h * sy), 2, video.videoHeight - y));
  return { w, h, x, y };
}

// 拖动 / 缩放裁切框（pointer 事件）
let drag = null;
function onPointerDown(e) {
  if (!state.cropOn) return;
  const handle = e.target.dataset ? e.target.dataset.h : null;
  drag = {
    mode: handle || "move",
    sx: e.clientX, sy: e.clientY,
    orig: { ...cropRect },
  };
  e.preventDefault();
  window.addEventListener("pointermove", onPointerMove);
  window.addEventListener("pointerup", onPointerUp);
}

function onPointerMove(e) {
  if (!drag) return;
  const W = overlay.clientWidth, H = overlay.clientHeight;
  const dx = e.clientX - drag.sx, dy = e.clientY - drag.sy;
  let { x, y, w, h } = drag.orig;
  if (drag.mode === "move") {
    x = clamp(x + dx, 0, W - w);
    y = clamp(y + dy, 0, H - h);
  } else {
    // 四角缩放：根据手柄决定哪条边动
    const east = drag.mode.includes("e");
    const south = drag.mode.includes("s");
    if (east) w = clamp(w + dx, 20, W - x);
    else { const nx = clamp(x + dx, 0, x + w - 20); w = w + (x - nx); x = nx; }
    if (south) h = clamp(h + dy, 20, H - y);
    else { const ny = clamp(y + dy, 0, y + h - 20); h = h + (y - ny); y = ny; }
    if (squareLock()) {
      const m = Math.min(w, h);
      // 以动点为基准保持正方形
      if (!east) x = x + (w - m);
      if (!south) y = y + (h - m);
      w = m; h = m;
    }
  }
  cropRect = { x, y, w, h };
  applyCropRect();
}

function onPointerUp() {
  drag = null;
  window.removeEventListener("pointermove", onPointerMove);
  window.removeEventListener("pointerup", onPointerUp);
}

// ---- 转换 ----
async function doConvert(presetKey) {
  if (!state.path) return;
  const s = state.startSec, e = state.endSec;
  if (e - s < 0.1) { setStatus("选中片段太短，请拉开两端或修改时间", "err"); return; }

  setStatus("正在转换…可能需要几秒", "busy");
  const crop = currentCropPixels();
  const r = await window.pywebview.api.convert(state.path, s, e, presetKey, crop);
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

whenReady(() => {
  $("choose-btn").addEventListener("click", async () => {
    setStatus("选择视频文件…", "busy");
    const info = await window.pywebview.api.choose_file();
    onVideoLoaded(info);
  });

  $("reset-btn").addEventListener("click", resetToDropzone);

  bindTimeGroup("start", false);
  bindTimeGroup("end", true);

  $("crop-btn").addEventListener("click", () => {
    if (state.cropOn) disableCrop(); else enableCrop();
  });
  $("square-toggle").addEventListener("change", () => {
    if (state.cropOn) { enableCrop(); } // 重新按当前约束布置
  });
  cropBox.addEventListener("pointerdown", onPointerDown);
  window.addEventListener("resize", () => { if (state.cropOn) layoutCropOverlay(); });

  document.querySelectorAll("[data-preset]").forEach((btn) => {
    btn.addEventListener("click", () => doConvert(btn.dataset.preset));
  });

  // 拖放视觉反馈绑在整个窗口（真正落地由后端原生拖放处理）
  ["dragenter", "dragover"].forEach((ev) =>
    document.body.addEventListener(ev, (e) => {
      e.preventDefault();
      if (!dropzone.classList.contains("hidden")) dropzone.classList.add("dragover");
    })
  );
  ["dragleave", "drop"].forEach((ev) =>
    document.body.addEventListener(ev, (e) => {
      e.preventDefault();
      dropzone.classList.remove("dragover");
    })
  );
  document.body.addEventListener("drop", (e) => {
    if (e.dataTransfer.files && e.dataTransfer.files.length) {
      setStatus("载入拖入的视频…", "busy");
    }
  });
});
```

- [ ] **Step 2: 提交（样式在下个 Task，先存逻辑）**

```bash
git add web/main.js
git commit -m "feat: 选段以秒为真相，数字框双向联动 + 裁切框拖拽缩放"
```

---

## Task 7：新增控件样式（style.css，深色橙风格）

**Files:**
- Modify: `web/style.css`

- [ ] **Step 1: 追加样式**

在 `web/style.css` 末尾追加：

```css
/* 视频区相对定位，供裁切叠层对齐 */
.video-wrap { position: relative; }

/* 时间数字输入行 */
.time-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  font-size: 12px;
  color: var(--text-dim);
}
.time-group { display: inline-flex; align-items: center; gap: 2px; }
.time-tag { color: var(--text-dim); margin-right: 4px; }
.dur-mid { color: var(--accent); }
.tnum {
  width: 30px;
  text-align: center;
  font-size: 13px;
  color: var(--text);
  background: var(--panel-2);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 3px 2px;
  -moz-appearance: textfield;
}
.tnum::-webkit-outer-spin-button,
.tnum::-webkit-inner-spin-button { -webkit-appearance: none; margin: 0; }
.tnum:focus { outline: none; border-color: var(--accent); }
/* 小时位默认隐藏，视频超 1 小时时由 .has-hours 显示 */
.hours-only { display: none; }
.has-hours .hours-only { display: inline-flex; align-items: center; gap: 2px; }

/* 裁切工具行 */
.crop-bar { display: flex; align-items: center; gap: 12px; }
.square-wrap { font-size: 13px; color: var(--text-dim); cursor: pointer; user-select: none; }
.square-wrap input { accent-color: var(--accent); }
#crop-btn.active { border-color: var(--accent); color: var(--accent); }

/* 裁切叠层与框 */
.crop-overlay { position: absolute; pointer-events: none; }
.crop-box {
  position: absolute;
  pointer-events: auto;
  border: 1px solid var(--accent);
  box-shadow: 0 0 0 9999px rgba(0, 0, 0, 0.5);   /* 框外压暗遮罩 */
  cursor: move;
  box-sizing: border-box;
}
.crop-handle {
  position: absolute;
  width: 12px; height: 12px;
  background: var(--accent);
  border: 2px solid var(--bg);
  border-radius: 50%;
  pointer-events: auto;
}
.crop-handle.nw { left: -6px; top: -6px; cursor: nwse-resize; }
.crop-handle.ne { right: -6px; top: -6px; cursor: nesw-resize; }
.crop-handle.sw { left: -6px; bottom: -6px; cursor: nesw-resize; }
.crop-handle.se { right: -6px; bottom: -6px; cursor: nwse-resize; }
```

- [ ] **Step 2: 手动验收**

Run: `venv\Scripts\python.exe app.py`
Expected: 数字框、裁切按钮、裁切框与手柄均为深色背景 + 陶土橙描边/强调，遮罩压暗框外区域，整体与原风格一致。关闭窗口。

- [ ] **Step 3: 提交**

```bash
git add web/style.css
git commit -m "feat: 时间输入框与裁切框样式（深色橙风格）"
```

---

## Task 8：整体验收 + 全量测试 + 重新打包

**Files:** 无新增，验证为主。

- [ ] **Step 1: 跑全部后端测试**

Run: `venv\Scripts\python.exe -m pytest -v`
Expected: 全绿（无 sample.mp4 的用例 skip）。

- [ ] **Step 2: 端到端手动验收**

Run: `venv\Scripts\python.exe app.py`
逐项确认：
1. 拖入视频，数字框显示 分:秒:帧；改任一框 → 滑块与预览跟随。
2. 拖滑块 → 数字框跟随刷新。
3. 点「✂ 裁切」→ 出现居中裁切框 + 框外压暗；拖动框、拉四角正常；勾「锁定正方形」框变 1:1。
4. 选一段 + 裁切后转 QQ：输出 GIF 画面为裁切区域，尺寸符合预期，体积达标。
5. 再按「✂ 裁切」取消 → 框消失；不裁切再转一次，行为同旧版。
6. 找一个时长 > 1 小时的视频（或临时改判断验证）确认出现小时框。
7. 全程深色橙风格、PNG 图标显示正常。

- [ ] **Step 3: 重新打包 exe**

Run:
```bash
venv\Scripts\python.exe -m PyInstaller memegif.spec --noconfirm --clean
```
Expected: 生成 `dist\MemeGIF\MemeGIF.exe`；双击运行，重复 Step 2 关键项（数字框、裁切、转换、图标）在打包版同样正常。

- [ ] **Step 4: 提交（若打包产物不入库则仅确认无源码遗漏）**

```bash
git add -A
git commit -m "chore: 裁切与时间输入功能联调通过"
```

- [ ] **Step 5: 收尾确认**

确认事项：所有新功能可用、原有行为未破坏、深色橙风格保持、PNG 图标生效。如需发布新版本 Release，另行处理（不在本计划范围）。

---

## 自查（Self-Review）

- **Spec 覆盖**：功能一(时间输入)=Task 1/3/5/6/7；功能二(裁切)=Task 2/3/5/6/7；功能三(PNG+风格)=Task 4/7；测试=Task 1/2/8。无遗漏。
- **占位符**：无 TODO/TBD，所有代码步骤含完整代码。
- **类型/命名一致**：`crop` 统一为 `{'w','h','x','y'}` dict 贯穿 JS→app.py→converter；`_build_vf(crop, fps, max_edge)`、`probe_fps`、`currentCropPixels`、`setRange`、`syncUI` 在定义与调用处名称一致。

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

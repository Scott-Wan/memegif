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

function whenReady(fn) {
  if (window.pywebview && window.pywebview.api) fn();
  else window.addEventListener("pywebviewready", fn);
}

function setStatus(text, cls) {
  statusEl.textContent = text;
  statusEl.className = "status" + (cls ? " " + cls : "");
}

async function onVideoLoaded(info) {
  if (info.error) { setStatus(info.error, "err"); return; }
  if (info.cancelled) return;
  state.path = info.path;
  state.duration = info.duration;

  const srcRes = await window.pywebview.api.video_src(info.path);
  video.src = srcRes.url;

  startRange.value = 0;
  endRange.value = 100;
  updateRangeUI();

  dropzone.classList.add("hidden");
  editor.classList.remove("hidden");
  setStatus("拖动两端滑块选取片段，然后选择目标平台", null);
}

const pctToSec = (pct) => (pct / 100) * state.duration;

function updateRangeUI() {
  let s = parseFloat(startRange.value);
  let e = parseFloat(endRange.value);
  if (s > e) { [s, e] = [e, s]; }
  const startSec = pctToSec(s);
  const endSec = pctToSec(e);
  $("start-label").textContent = startSec.toFixed(1) + "s";
  $("end-label").textContent = endSec.toFixed(1) + "s";
  $("dur-label").textContent = "时长 " + (endSec - startSec).toFixed(1) + "s";
  rangeFill.style.left = s + "%";
  rangeFill.style.width = (e - s) + "%";
}

startRange.addEventListener("input", () => { updateRangeUI(); seekPreview(startRange); });
endRange.addEventListener("input", () => { updateRangeUI(); seekPreview(endRange); });

function seekPreview(which) {
  const pct = parseFloat(which.value);
  if (!isNaN(pct) && state.duration) video.currentTime = pctToSec(pct);
}

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

whenReady(() => {
  $("choose-btn").addEventListener("click", async () => {
    setStatus("选择视频文件…", "busy");
    const info = await window.pywebview.api.choose_file();
    onVideoLoaded(info);
  });

  document.querySelectorAll("[data-preset]").forEach((btn) => {
    btn.addEventListener("click", () => doConvert(btn.dataset.preset));
  });

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
      setStatus("拖拽未能识别路径，请点「选择文件」", "err");
    }
  });
});

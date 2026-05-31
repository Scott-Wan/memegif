# MemeGIF 新功能设计：画面裁切 + 时间精确输入

日期：2026-06-01
状态：已确认，待实现

## 背景

MemeGIF 现有流程：拖入视频 → 双端滑块选取片段 → 选目标平台（QQ ≤5MB / 微信 ≤1MB）→
ffmpeg 两步调色板转 GIF，体积超限自动逐级回退（先降分辨率、再降帧率）。

本次新增两项能力：

1. **画面裁切**：在预览画面上框选一块区域，最终只输出裁切后的画面。
2. **时间精确输入**：除滑块外，支持按 时:分:秒:帧 输入数字精确设定起点/终点。

## 目标与非目标

**目标**
- 裁切框默认自由矩形，可切换"锁定正方形"。
- 裁切按钮为开关式：再次按下取消裁切、恢复整幅画面。
- 时间输入采用"智能"格式：默认 分:秒:帧，视频时长 ≥ 1 小时才显示小时位。
- 数字输入与滑块、预览画面三者双向联动。
- 不裁切 / 不使用数字输入时，原有行为完全不变。
- **保持原有美术风格**：深色背景 + 陶土橙强调（Claude 风格），新增控件沿用现有
  CSS 变量与按钮样式，不引入新配色或新视觉语言。
- **用应用 PNG 图案替换内嵌 SVG**：顶栏 logo 与拖放区图标当前是内嵌 SVG，
  改用应用本身的 PNG 图标（`assets/icon/` 内的图案）。

**非目标**
- 不做旋转、翻转、滤镜等其它画面编辑。
- 不改变现有的体积回退策略与预设档位。
- 不做关键帧级缩略图时间轴（仍沿用单个 `<video>` 预览）。

## 功能一：时间精确输入（智能 时:分:秒:帧）

### 帧率探测
- 现状：`load_video` 只返回 `{path, duration}`。
- 新增 `converter.probe_fps(video_path) -> float`：用 ffprobe 读取
  `stream=r_frame_rate`（形如 `30000/1001`），按 `num/den` 计算得 29.97。
- 健壮性：若 `r_frame_rate` 为 `0/0` 或缺失，回退尝试 `avg_frame_rate`，仍失败则
  默认 25.0，并在前端状态栏提示"未能探测帧率，按 25fps 估算"。
- `load_video` 返回值新增 `fps` 字段。

### 帧 ↔ 秒 换算
- 设某时间 `sec`，整秒部分 `whole = floor(sec)`，秒内帧 `frame = round((sec - whole) * fps)`。
- 反向：用户输入 `(h, m, s, f)` → `sec = h*3600 + m*60 + s + f/fps`。
- 帧框取值范围 `0 ~ ceil(fps)-1`；超出按进位/钳制处理（实现时统一：帧 ≥ fps 则向秒进位）。

### 界面与联动
- 在双端滑块下方新增一行数字输入：

  ```
  起点  [MM]:[SS]:[FF]    终点  [MM]:[SS]:[FF]        （duration < 3600s）
  起点  [HH]:[MM]:[SS]:[FF]    ...                    （duration ≥ 3600s）
  ```

- **唯一真相**改为 `state.startSec` / `state.endSec`（秒，浮点）。
  - 滑块 `input` 事件 → 由百分比算出秒 → 更新 `startSec/endSec` → 刷新数字框、范围条、预览 seek。
  - 数字框 `change` 事件 → 由 (h,m,s,f) 算出秒 → 更新 `startSec/endSec` → 刷新滑块位置、范围条、预览 seek。
  - 这一步顺带把现有 main.js 中"以滑块百分比为真相"的逻辑重构为以秒为真相，
    `pctToSec` 等改为派生函数。
- 校验：`startSec < endSec` 且片段时长 ≥ 0.1s（沿用现有下限）；非法输入还原为上一次合法值。

## 功能二：画面裁切

### 交互
- 编辑区新增 `裁切` 按钮（开关式）。
- 按下 → 视频上浮现裁切框：
  - 默认居中、约占画面 80%。
  - 四角手柄可拉伸；框内可整体拖动；框外区域半透明压暗（遮罩），直观显示保留范围。
  - 旁边出现 `☐ 锁定正方形` 开关：勾选时框始终保持 1:1（拉伸时以较小边为准约束）。
- 再次按下 `裁切` → 框消失、遮罩移除，恢复整幅画面（取消裁切，crop 置空）。

### 坐标换算（显示坐标 → 视频真实像素）
- 预览 `<video>` 无固定宽高、按 `max-width/ max-height` 等比缩放，渲染框与画面内容一致（无信箱黑边），
  故映射比例 `scale = video.videoWidth / displayWidth`。
- 裁切框相对视频渲染框的 `{left, top, w, h}`（显示像素）映射为真实像素：
  - `cx = round(left * scale)`，`cy = round(top * scale)`
  - `cw = round(w * scale)`，`ch = round(h * scale)`
- 取偶数（ffmpeg 缩放/编码要求），并钳制在 `[0, videoWidth/Height]` 内。
- 裁切框状态在转换时读取一次，传给后端。

### 后端滤镜
- 抽出纯函数 `converter._build_vf(crop, fps, max_edge) -> str`：
  - 不裁切（crop 为 None）：`fps={fps},scale=...`（与现状完全一致）。
  - 裁切：`crop={cw}:{ch}:{cx}:{cy},fps={fps},scale=...`（先裁后缩）。
- `convert_once` / `convert` 新增可选参数 `crop`（dict 或 None），透传给 `_build_vf`。
- 体积回退梯度照旧，作用在裁切后画面的最长边上。

## 功能三：界面图标替换与风格约束

### PNG 图标替换
- 现状：`index.html` 顶栏 logo 与拖放区上传图标均为内嵌 SVG。
- 改用应用自带 PNG。素材：`assets/icon/MemeGIF-icon-transparent.png`（透明背景，
  适合叠在深色背景上）。
- 做法：把该 PNG 拷一份到 `web/`（如 `web/logo.png`），`index.html` 用相对路径
  `<img src="logo.png">` 引用——这样源码运行与打包（`datas` 已含 `('web','web')`）
  都能正确加载，不依赖跨目录相对路径。
- 顶栏 logo 用 PNG 替换内嵌 SVG（CSS 控制为约 22–24px）；拖放区图标同样替换为
  PNG（尺寸约 40–56px，保持原布局位置）。

### 风格约束（贯穿全部改动）
- 严格沿用现有 CSS 变量（`--bg/--panel/--accent/--border` 等）与既有按钮类
  （`.btn-primary/.btn-secondary`）。
- 新增控件（数字输入框、裁切按钮、裁切框手柄/遮罩、正方形开关）的配色、圆角、
  间距与现有组件一致，不引入新色板或新视觉语言。
- 验收时对照改动前后，确认整体观感不破坏深色 + 陶土橙风格。

## 受影响文件

- `converter.py`
  - 新增 `probe_fps()`。
  - 新增纯函数 `_build_vf(crop, fps, max_edge)`，`convert_once` 改为调用它。
  - `convert_once` / `convert` 增加 `crop` 参数（默认 None，保持向后兼容）。
- `app.py`
  - `load_video` 返回值增加 `fps`。
  - `convert` API 增加 `crop` 参数，透传给 `converter.convert`。
- `web/index.html`：数字输入行、`裁切` 按钮、裁切框 DOM、`锁定正方形` 开关；
  顶栏与拖放区 SVG 改为 `<img src="logo.png">`。
- `web/logo.png`：从 `assets/icon/MemeGIF-icon-transparent.png` 拷入（新增文件）。
- `web/main.js`：以秒为真相的状态重构、数字框双向联动、裁切框拖拽/缩放/正方形约束、坐标换算。
- `web/style.css`：数字输入框、裁切框手柄、遮罩、按钮、PNG logo 的深色橙风格样式。
- 测试：
  - `_build_vf`：含 crop / 不含 crop 两种情况生成正确滤镜串。
  - `probe_fps`：解析 `30000/1001`、`25/1`、`0/0` 回退等分支（可对解析逻辑做纯单元测试）。

## 测试策略

- Python 单元测试（pytest）：`_build_vf` 字符串断言、帧率解析分支。
- 端到端：保留现有 `assets/sample.mp4` 用例；新增一条带 crop 的转换用例，断言输出 GIF
  宽高与裁切比例相符（素材缺失时自动跳过，沿用现有约定）。
- 手动验收：拖入视频 → 数字框与滑块联动正确 → 开裁切框拉伸/锁方/取消 → 转换输出画面符合裁切。

## 风险与缓解

- **帧率探测失败**：回退 25fps 并提示，不阻断转换。
- **裁切框坐标在缩放/letterbox 下偏移**：依赖"渲染框无黑边"前提；实现时以
  `video.getBoundingClientRect()` 为基准，若后续给视频加了固定尺寸需重新核对映射。
- **数字输入非法值**：统一校验 + 还原上次合法值，避免 NaN 传到后端。

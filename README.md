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

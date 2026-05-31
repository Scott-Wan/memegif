# MemeGIF · 视频转表情包

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

## 打包成 exe（开箱即用）

打包时把 ffmpeg/ffprobe 一起打进程序，生成的 `MemeGIF.exe` 拷到任何 Windows 电脑双击即用，无需另装 ffmpeg。

```powershell
# 1. 安装打包工具
venv\Scripts\python.exe -m pip install pyinstaller

# 2. 准备捆绑的 ffmpeg（bin\ 不进版本库，需手动放入）
mkdir bin
copy <ffmpeg安装目录>\ffmpeg.exe  bin\
copy <ffmpeg安装目录>\ffprobe.exe bin\

# 3. 打包
venv\Scripts\python.exe -m PyInstaller memegif.spec --noconfirm --clean
```

产物在 `dist\MemeGIF\`，整个文件夹即为可分发程序，运行其中的 `MemeGIF.exe` 启动（约 460MB，含 ffmpeg）。

## 技术

Python + pywebview 窗口，HTML/CSS/JS 前端，底层调 ffmpeg 两步调色板转换，
体积超限自动逐级回退（先降分辨率、再降帧率）。

# -*- mode: python ; coding: utf-8 -*-
# PyInstaller 打包配置：把前端资源 web/ 与捆绑的 ffmpeg bin/ 一起打进程序。
# 采用单目录（onedir）模式：启动快，便于和大体积 ffmpeg 共存。

block_cipher = None

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('web', 'web'),                  # 前端 HTML/CSS/JS
        ('bin', 'bin'),                  # 捆绑的 ffmpeg.exe / ffprobe.exe
        ('assets/icon', 'assets/icon'),  # 应用图标（运行期设置任务栏图标用）
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['pytest', 'PyInstaller'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='MemeGIF',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,           # 无控制台窗口（GUI 程序）
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/icon/MemeGIF.ico',   # exe 图标（任务栏/窗口/文件图标）
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='MemeGIF',
)

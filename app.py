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

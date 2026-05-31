"""pywebview 入口：创建窗口，暴露 Api 给前端调用。

视频预览通过一个本地 HTTP 服务提供（支持 Range 请求），
这样 <video> 既能正确加载含中文/特殊字符路径的视频，又能拖动 seek 跳帧。
"""
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

import webview
from webview.dom import DOMEventHandler

import converter
from presets import get_preset

# 本地视频服务注册表：id -> 绝对路径
_registry = {}
_registry_lock = threading.Lock()
_next_id = [0]

# 常见视频扩展名 -> MIME 类型
_MIME = {
    ".mp4": "video/mp4", ".mov": "video/quicktime", ".mkv": "video/x-matroska",
    ".webm": "video/webm", ".avi": "video/x-msvideo", ".flv": "video/x-flv",
}


def _register_video(path):
    """登记一个视频路径，返回其访问 id。"""
    with _registry_lock:
        _next_id[0] += 1
        vid = _next_id[0]
        _registry[vid] = path
    return vid


class _VideoHandler(BaseHTTPRequestHandler):
    """只服务已登记的视频文件，支持 HTTP Range（拖动 seek 必需）。"""

    def log_message(self, *args):
        pass  # 静默，不往控制台打访问日志

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path != "/video":
            self.send_error(404)
            return
        qs = parse_qs(parsed.query)
        try:
            vid = int(qs.get("id", ["0"])[0])
        except ValueError:
            self.send_error(400)
            return
        path = _registry.get(vid)
        if not path or not os.path.isfile(path):
            self.send_error(404)
            return

        file_size = os.path.getsize(path)
        ctype = _MIME.get(os.path.splitext(path)[1].lower(), "application/octet-stream")
        range_header = self.headers.get("Range")

        if range_header and range_header.startswith("bytes="):
            # 解析 "bytes=start-end"
            rng = range_header[len("bytes="):].split("-", 1)
            start = int(rng[0]) if rng[0] else 0
            end = int(rng[1]) if len(rng) > 1 and rng[1] else file_size - 1
            start = max(0, start)
            end = min(end, file_size - 1)
            length = end - start + 1
            self.send_response(206)
            self.send_header("Content-Type", ctype)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
            self.send_header("Content-Length", str(length))
            self.end_headers()
            self._stream(path, start, length)
        else:
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(file_size))
            self.end_headers()
            self._stream(path, 0, file_size)

    def _stream(self, path, start, length):
        """从 start 处读取 length 字节写入响应，分块以省内存。"""
        chunk = 64 * 1024
        with open(path, "rb") as f:
            f.seek(start)
            remaining = length
            while remaining > 0:
                data = f.read(min(chunk, remaining))
                if not data:
                    break
                try:
                    self.wfile.write(data)
                except (ConnectionAbortedError, BrokenPipeError):
                    break  # 前端切换视频/关闭连接，正常中断
                remaining -= len(data)


def _start_video_server():
    """在后台线程启动本地视频服务，返回监听端口。"""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _VideoHandler)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return port


class Api:
    """前端通过 pywebview.api.<方法> 调用。所有方法返回可 JSON 序列化的 dict。"""

    def __init__(self, video_port):
        self._window = None
        self._video_port = video_port

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
        """探测视频时长与帧率，返回 {path, duration, fps} 或 {error}。"""
        try:
            duration = converter.probe_duration(path)
            fps = converter.probe_fps(path)
            return {"path": path, "duration": duration, "fps": fps}
        except Exception as e:
            return {"error": f"无法读取视频：{e}"}

    def video_src(self, path):
        """登记视频并返回 <video> 可加载的本地 HTTP URL（支持 seek）。"""
        vid = _register_video(path)
        return {"url": f"http://127.0.0.1:{self._video_port}/video?id={vid}"}

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


def _push_js(window, expr):
    """安全地在页面里执行一段 JS（拖放回调在后台线程，需经此推回前端）。"""
    try:
        window.evaluate_js(expr)
    except Exception:
        pass


def _resource_dir():
    """资源根目录。打包后指向 PyInstaller 解包目录，源码运行指向本文件目录。"""
    import sys
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def main():
    video_port = _start_video_server()
    api = Api(video_port)
    here = _resource_dir()
    window = webview.create_window(
        title="MemeGIF · 视频转表情包",
        url=os.path.join(here, "web", "index.html"),
        js_api=api,
        width=720, height=640, min_size=(560, 520),
        background_color="#1C1B1A",
    )
    api.set_window(window)

    def _on_drop(e):
        """原生拖放回调：WebView2 会给每个文件注入真实路径 pywebviewFullPath。"""
        try:
            data = e.get("dataTransfer") if isinstance(e, dict) else None
            files = (data or {}).get("files") or []
            path = next((f.get("pywebviewFullPath") for f in files
                         if f.get("pywebviewFullPath")), None)
            if not path:
                _push_js(window, "setStatus('拖入未能识别文件，请点「选择文件」','err')")
                return
            info = api.load_video(path)
            _push_js(window, "onVideoLoaded(" + json.dumps(info, ensure_ascii=False) + ")")
        except Exception as ex:
            _push_js(window, "setStatus(" + json.dumps("拖入失败：" + str(ex)) + ",'err')")

    def _register_dnd():
        """页面加载完成后，把整个窗口注册为原生放置目标。

        绑到 body 而非 #dropzone：导入页和编辑页都能拖入，转换后可直接拖下一个，
        且能拦截 WebView2 把视频文件当链接打开的默认行为（否则会变成打开网页）。
        on() 只收 (event, callback)，要阻止默认行为必须传 DOMEventHandler 包装。
        必须监听 dragover/dragenter 并 preventDefault，浏览器才会把 drop 派发过来。
        """
        try:
            el = window.dom.get_element("body")
            if not el:
                _push_js(window, "setStatus('拖放区未就绪，请用「选择文件」','err')")
                return
            el.on("dragenter", DOMEventHandler(lambda e: None, prevent_default=True))
            el.on("dragover", DOMEventHandler(lambda e: None, prevent_default=True))
            el.on("drop", DOMEventHandler(_on_drop, prevent_default=True))
        except Exception as ex:
            _push_js(window, "setStatus(" + json.dumps("拖放注册失败：" + str(ex)) + ",'err')")

    window.events.loaded += _register_dnd
    webview.start()


if __name__ == "__main__":
    main()

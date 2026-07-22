import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import app


def test_load_video_returns_source_dimensions(monkeypatch, tmp_path):
    source = tmp_path / "source.gif"
    source.write_bytes(b"GIF89a")

    monkeypatch.setattr(app.converter, "probe_duration", lambda path: 2.5)
    monkeypatch.setattr(app.converter, "probe_fps", lambda path: 12.0)
    monkeypatch.setattr(app.converter, "probe_dimensions", lambda path: (320, 180))

    api = app.Api(4321, preview_root=tmp_path / "preview")
    try:
        assert api.load_video(str(source)) == {
            "path": str(source),
            "duration": 2.5,
            "fps": 12.0,
            "width": 320,
            "height": 180,
            "kind": "gif",
        }
    finally:
        api.cleanup()


def test_cleanup_removes_internal_preview_directory_and_is_idempotent():
    api = app.Api(4321)
    preview_root = api._preview_root
    marker = preview_root / "marker.txt"

    assert preview_root.exists()
    marker.write_text("ok", encoding="utf-8")
    assert marker.exists()

    api.cleanup(object())

    assert not preview_root.exists()
    assert api._preview_tmpdir is None
    assert api._preview_cache == {}

    api.cleanup()



def test_cleanup_keeps_explicit_preview_root_and_contents(tmp_path):
    external = tmp_path / "preview"
    sentinel = external / "sentinel.txt"
    api = app.Api(4321, preview_root=external)

    assert external.exists()
    sentinel.write_text("keep", encoding="utf-8")
    assert sentinel.exists()

    api.cleanup(object())

    assert external.exists()
    assert sentinel.exists()

    api.cleanup()

    assert external.exists()
    assert sentinel.exists()


def test_prepare_gif_preview_returns_only_same_origin_url(monkeypatch, tmp_path):
    source = tmp_path / "sample.gif"
    source.write_bytes(b"GIF89a-original")

    created = []

    def fake_create(gif_path, out_path):
        created.append((gif_path, out_path))
        output = tmp_path / out_path
        output.write_bytes(b"mp4-preview")
        return str(output)

    api = app.Api(4321, preview_root=tmp_path / "preview")
    monkeypatch.setattr(app.converter, "create_gif_preview", fake_create)

    try:
        first = api.prepare_gif_preview(str(source))
        second = api.prepare_gif_preview(str(source))

        assert first == second
        assert len(created) == 1
        assert first == {"url": first["url"]}
        assert first["url"].startswith("http://127.0.0.1:4321/video?id=")
    finally:
        api.cleanup()


def test_prepare_gif_preview_regenerates_when_cached_file_is_deleted(monkeypatch, tmp_path):
    source = tmp_path / "sample.gif"
    source.write_bytes(b"GIF89a-v1")

    created = []

    def fake_create(gif_path, out_path):
        created.append(out_path)
        output = tmp_path / out_path
        output.write_bytes(f"preview-{len(created)}".encode("utf-8"))
        return str(output)

    api = app.Api(4321, preview_root=tmp_path / "preview")
    monkeypatch.setattr(app.converter, "create_gif_preview", fake_create)

    try:
        first = api.prepare_gif_preview(str(source))
        cached_path = app.Path(api._preview_cache[api._preview_key(str(source))]["path"])
        cached_path.unlink()

        second = api.prepare_gif_preview(str(source))

        assert first == {"url": first["url"]}
        assert second == {"url": second["url"]}
        assert first["url"] != second["url"]
        assert len(created) == 2
    finally:
        api.cleanup()


def test_prepare_gif_preview_rejects_non_gif_file(tmp_path):
    source = tmp_path / "sample.mp4"
    source.write_bytes(b"not-gif")
    api = app.Api(4321, preview_root=tmp_path / "preview")

    try:
        assert api.prepare_gif_preview(str(source)) == {"error": "只能为 GIF 生成片段预览"}
    finally:
        api.cleanup()


def test_prepare_gif_preview_reports_missing_gif(tmp_path):
    source = tmp_path / "missing.gif"
    api = app.Api(4321, preview_root=tmp_path / "preview")

    try:
        assert api.prepare_gif_preview(str(source)) == {"error": "GIF 文件不存在"}
    finally:
        api.cleanup()


def test_prepare_gif_preview_reports_conversion_error(monkeypatch, tmp_path):
    source = tmp_path / "sample.gif"
    source.write_bytes(b"GIF89a")

    def fake_create(gif_path, out_path):
        raise RuntimeError("ffmpeg failed")

    api = app.Api(4321, preview_root=tmp_path / "preview")
    monkeypatch.setattr(app.converter, "create_gif_preview", fake_create)

    try:
        result = api.prepare_gif_preview(str(source))
        assert result == {"error": "无法生成 GIF 片段预览：ffmpeg failed"}
    finally:
        api.cleanup()


def test_prepare_gif_preview_generates_once_for_same_source_in_two_threads(monkeypatch, tmp_path):
    source = tmp_path / "sample.gif"
    source.write_bytes(b"GIF89a-thread")

    created = []
    gate = threading.Event()
    release = threading.Event()

    def fake_create(gif_path, out_path):
        gate.set()
        assert release.wait(timeout=2)
        created.append(out_path)
        output = tmp_path / out_path
        output.write_bytes(b"mp4-preview-thread")
        return str(output)

    api = app.Api(4321, preview_root=tmp_path / "preview")
    monkeypatch.setattr(app.converter, "create_gif_preview", fake_create)

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            first_future = executor.submit(api.prepare_gif_preview, str(source))
            assert gate.wait(timeout=2)
            second_future = executor.submit(api.prepare_gif_preview, str(source))
            release.set()
            first = first_future.result(timeout=5)
            second = second_future.result(timeout=5)

        assert first == second
        assert len(created) == 1
    finally:
        api.cleanup()

"""Run on a desktop or in Windows CI; core processing has separate tests."""
import os
import sys

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "win32" and not os.environ.get("DISPLAY"),
    reason="GUI needs a desktop display",
)


def test_gui_windows_and_board_settings():
    import tkinter as tk
    from camcal.gui import Application

    for mode in ("calibrate", "undistort"):
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            if sys.platform != "win32" and "display" in str(exc):
                pytest.skip(f"Display is unavailable: {exc}")
            raise
        try:
            app = Application(root, mode)
            root.update()
            assert root.winfo_exists()
            if mode == "calibrate":
                app.fields["type"].set("charuco")
                app.fields["columns"].set("11")
                app.fields["rows"].set("8")
                app.legacy.set(True)
                config = app.get_config()
                assert config.columns == 11 and config.legacy_pattern
                app.fields["type"].set("aprilgrid")
                assert app.get_config().border_bits == 2
        finally:
            root.destroy()


def test_capture_window_save_and_config_change(tmp_path):
    import tkinter as tk
    import queue
    import numpy as np
    from camcal.boards import BoardConfig, Detector
    from camcal.capture import analyze_frame
    from camcal.capture_gui import CaptureApplication
    from camcal.media import read_image
    from test_capture import checker

    class FakeWorker:
        def __init__(self):
            self.events = queue.Queue()
            self.frames = queue.Queue()
            self.stopped = False

        def start(self):
            pass

        def stop(self):
            self.stopped = True

        def configure(self, config, generation):
            self.generation = generation

    try:
        root = tk.Tk()
    except tk.TclError as exc:
        if sys.platform != "win32" and "display" in str(exc):
            pytest.skip(f"Display is unavailable: {exc}")
        raise
    worker = FakeWorker()
    app = CaptureApplication(root, output=tmp_path, worker=worker)
    try:
        root.update()
        raw = checker()
        result = analyze_frame(raw, Detector(BoardConfig()), 0)
        app.accept_frame(result)
        assert app.status.get().startswith("Frame usable")
        assert app.border.cget("background") == "#16833b"
        app.capture()
        saved = list(tmp_path.glob("*.png"))
        assert len(saved) == 1 and np.array_equal(read_image(saved[0]), raw)
        app.overlay.set(False)
        app.render()
        assert app.photo.width() > 1
        app.apply_config(BoardConfig(columns=9, rows=6))
        assert app.current is None
        assert app.status.get().startswith("Frame unusable")
        assert app.border.cget("background") == "#b71c1c"
        app.accept_frame(result)
        assert app.current is None
    finally:
        app.close()
    assert worker.stopped

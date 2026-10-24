import cv2
import numpy as np

from camcal.boards import BoardConfig, Detector
from camcal.capture import (
    CameraWorker,
    analyze_frame,
    discover_cameras,
    draw_preview,
    save_capture,
)
from camcal.media import read_image


def checker():
    image = np.full((550, 700, 3), 255, np.uint8)
    for row in range(8):
        for col in range(11):
            if (row + col) % 2 == 0:
                cv2.rectangle(
                    image,
                    (50 + col * 50, 50 + row * 50),
                    (50 + (col + 1) * 50, 50 + (row + 1) * 50),
                    (0, 0, 0),
                    -1,
                )
    return image


class FakeCamera:
    def __init__(self, readable):
        self.readable = readable
        self.released = False

    def isOpened(self):
        return self.readable is not None

    def read(self):
        return (True, checker()) if self.readable else (False, None)

    def release(self):
        self.released = True


def test_camera_discovery_requires_readable_frame_and_releases():
    cameras = {0: FakeCamera(None), 1: FakeCamera(False), 2: FakeCamera(True)}
    assert discover_cameras(range(3), lambda index: cameras[index]) == [2]
    assert all(camera.released for camera in cameras.values())


def test_detection_status_and_optional_overlay_do_not_modify_raw(tmp_path):
    raw = checker()
    original = raw.copy()
    result = analyze_frame(raw, Detector(BoardConfig()), 7)
    assert result.usable and result.status == "Frame usable" and result.generation == 7
    overlay = draw_preview(result, True)
    assert not np.array_equal(overlay, original)
    assert np.array_equal(draw_preview(result, False), original)
    assert np.array_equal(result.frame, original)
    path = save_capture(result, tmp_path / "日本語")
    assert np.array_equal(read_image(path), original)
    assert save_capture(result, tmp_path / "日本語") != path
    bad = analyze_frame(np.full_like(raw, 255), Detector(BoardConfig()), 7)
    assert not bad.usable and bad.status == "Frame unusable"
    assert save_capture(bad, tmp_path).is_file()


def test_worker_configuration_generation_and_cleanup():
    cameras = []

    def factory(index):
        camera = FakeCamera(True if index == 0 else None)
        cameras.append(camera)
        return camera

    worker = CameraWorker(BoardConfig(), indices=range(2), camera_factory=factory)
    worker.start()
    try:
        event, payload = worker.events.get(timeout=5)
        assert event == "cameras" and payload == [0]
        result = worker.frames.get(timeout=5)
        assert result.generation == 0 and result.usable
        worker.configure(BoardConfig(columns=9, rows=6), 1)
        while True:
            result = worker.frames.get(timeout=5)
            if result.generation == 1:
                break
        assert not result.usable
        worker.select_camera(1, 2)
        while True:
            kind, payload = worker.events.get(timeout=5)
            if kind == "error":
                break
        assert "camera" in payload.lower()
    finally:
        worker.stop()
        worker.join(timeout=5)
    assert not worker.is_alive()
    assert all(camera.released for camera in cameras)


def test_disconnection_does_not_leave_a_capturable_old_frame():
    class DisconnectingCamera(FakeCamera):
        def __init__(self):
            super().__init__(True)
            self.reads = 0

        def read(self):
            self.reads += 1
            return super().read() if self.reads == 1 else (False, None)

    opened = []

    def factory(index):
        camera = DisconnectingCamera()
        opened.append(camera)
        return camera

    worker = CameraWorker(BoardConfig(), indices=[0], camera_factory=factory)
    worker.start()
    try:
        while True:
            kind, payload = worker.events.get(timeout=5)
            if kind == "error":
                break
        assert worker.frames.empty()
    finally:
        worker.stop()
        worker.join(timeout=5)
    assert all(camera.released for camera in opened)


def test_capture_rejects_frame_from_previous_configuration():
    from camcal.capture_gui import CaptureApplication

    app = CaptureApplication.__new__(CaptureApplication)
    app.generation = 1
    app.current = None
    old = analyze_frame(checker(), Detector(BoardConfig()), 0)
    app.accept_frame(old)
    assert app.current is None
    app.current = old
    # With no output field configured, reaching a save would fail instead of returning.
    app.capture()


def test_worker_recovers_from_camera_exception_on_rescan():
    class RaisingCamera(FakeCamera):
        def read(self):
            raise cv2.error("Transient camera failure")

    opened = []

    def factory(index):
        camera = RaisingCamera(True) if len(opened) == 1 else FakeCamera(True)
        opened.append(camera)
        return camera

    worker = CameraWorker(BoardConfig(), indices=[0], camera_factory=factory)
    worker.start()
    try:
        while True:
            kind, payload = worker.events.get(timeout=5)
            if kind == "error":
                break
        worker.rescan(1)
        result = worker.frames.get(timeout=5)
        assert result.usable and result.generation == 1
    finally:
        worker.stop()
        worker.join(timeout=5)
    assert all(camera.released for camera in opened)

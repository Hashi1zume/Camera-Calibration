"""Camera discovery and full-resolution board checks, independent of Tk."""
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
import queue
import sys
import threading

import cv2
import numpy as np

from .boards import BoardConfig, Detector
from .media import write_image


@dataclass
class CheckedFrame:
    frame: np.ndarray
    points: np.ndarray | None
    generation: int

    @property
    def usable(self):
        return self.points is not None

    @property
    def status(self):
        return "Frame usable" if self.usable else "Frame unusable"


def open_camera(index):
    backend = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY
    return cv2.VideoCapture(index, backend)


def discover_cameras(indices, camera_factory=open_camera, stopped=None):
    found = []
    for index in indices:
        if stopped is not None and stopped.is_set():
            break
        camera = camera_factory(index)
        try:
            if camera.isOpened():
                ok, frame = camera.read()
                if ok and frame is not None and frame.size:
                    found.append(index)
        finally:
            camera.release()
    return found


def analyze_frame(frame, detector, generation):
    detected = detector.detect(frame)
    return CheckedFrame(
        frame.copy(), None if detected is None else detected[1], generation
    )


def draw_preview(result, show_corners):
    preview = result.frame.copy()
    if show_corners and result.points is not None:
        radius = max(2, round(min(preview.shape[:2]) / 250))
        for x, y in result.points.reshape(-1, 2):
            center = (round(float(x)), round(float(y)))
            cv2.circle(preview, center, radius + 1, (0, 0, 0), -1, cv2.LINE_AA)
            cv2.circle(preview, center, radius, (0, 255, 0), -1, cv2.LINE_AA)
    return preview


def save_capture(result, directory):
    if not str(directory).strip():
        raise ValueError("Select an image output directory")
    directory = Path(directory).expanduser()
    name = datetime.now().strftime("capture_%Y%m%d_%H%M%S_%f")
    # Exclusive image creation prevents overwriting even if timestamps collide.
    for number in range(1000):
        suffix = "" if number == 0 else f"_{number}"
        target = directory / f"{name}{suffix}.png"
        try:
            write_image(target, result.frame)
            return target
        except FileExistsError:
            continue
    raise FileExistsError("Cannot create a unique capture filename")


class CameraWorker(threading.Thread):
    """One thread owns every VideoCapture; Tk only consumes immutable results."""

    def __init__(self, config, indices=range(10), camera_factory=open_camera):
        super().__init__(daemon=True)
        config.validate()
        self.config = replace(config)
        self.indices = tuple(indices)
        self.camera_factory = camera_factory
        self.commands = queue.Queue()
        self.events = queue.Queue()
        self.frames = queue.Queue(maxsize=1)
        self.stopped = threading.Event()
        self.commands.put(("scan", 0))

    def configure(self, config, generation):
        config.validate()
        self.commands.put(("config", replace(config), generation))

    def select_camera(self, index, generation):
        self.commands.put(("camera", index, generation))

    def rescan(self, generation):
        self.commands.put(("scan", generation))

    def stop(self):
        self.stopped.set()

    def report_error(self, message):
        try:
            self.frames.get_nowait()
        except queue.Empty:
            pass
        self.events.put(("error", message))

    def run(self):
        camera = None
        generation = 0
        try:
            detector = Detector(self.config)
            while not self.stopped.is_set():
                try:
                    while not self.commands.empty():
                        command = self.commands.get_nowait()
                        if command[0] == "config":
                            self.config, generation = command[1:]
                            detector = Detector(self.config)
                        else:
                            if camera is not None:
                                camera.release()
                                camera = None
                            if command[0] == "scan":
                                generation = command[1]
                                indices = discover_cameras(
                                    self.indices, self.camera_factory, self.stopped
                                )
                                self.events.put(("cameras", indices))
                                if not indices:
                                    self.report_error(
                                        "No readable camera found. Connect a camera and select Rescan."
                                    )
                                    continue
                                index = indices[0]
                            else:
                                index, generation = command[1:]
                            if self.stopped.is_set():
                                break
                            camera = self.camera_factory(index)
                            if not camera.isOpened():
                                camera.release()
                                camera = None
                                self.report_error(f"Cannot open camera {index}")
                    if self.stopped.is_set():
                        break
                    if camera is None:
                        self.stopped.wait(0.05)
                        continue
                    ok, frame = camera.read()
                    if not ok or frame is None or not frame.size:
                        camera.release()
                        camera = None
                        self.report_error(
                            "Camera disconnected or frame unavailable. Select Rescan."
                        )
                        continue
                    result = analyze_frame(frame, detector, generation)
                    try:
                        self.frames.get_nowait()
                    except queue.Empty:
                        pass
                    self.frames.put_nowait(result)
                    self.stopped.wait(0.03)
                except (cv2.error, ValueError, OSError) as exc:
                    if camera is not None:
                        camera.release()
                        camera = None
                    self.report_error(f"{exc} Select Rescan to retry.")
                    self.stopped.wait(0.05)
        except Exception as exc:
            self.report_error(str(exc))
        finally:
            if camera is not None:
                camera.release()

"""Pinhole camera parameter validation and image/video correction."""
import json
import math
from pathlib import Path

import cv2
import numpy as np

from .media import IMAGE_EXTS, output_paths, read_image, write_image


def load_parameters(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    try:
        matrix = np.asarray(data["camera_matrix"], dtype=np.float64)
        distortion = np.asarray(data["dist_coeffs"], dtype=np.float64).reshape(-1)
        size = np.asarray(data["image_size"], dtype=np.float64)
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Invalid camera parameter JSON") from exc
    if data.get("camera_model", "pinhole") != "pinhole":
        raise ValueError("Only the OpenCV pinhole model is supported")
    if (
        matrix.shape != (3, 3)
        or not np.isfinite(matrix).all()
        or matrix[0, 0] <= 0
        or matrix[1, 1] <= 0
        or not np.allclose(matrix[2], [0, 0, 1])
        or not np.allclose([matrix[0, 1], matrix[1, 0]], 0)
    ):
        raise ValueError("Invalid camera_matrix")
    if distortion.size not in (4, 5, 8, 12, 14) or not np.isfinite(distortion).all():
        raise ValueError("Invalid dist_coeffs")
    if (
        size.shape != (2,)
        or not np.isfinite(size).all()
        or np.any(size < 1)
        or np.any(size != np.floor(size))
    ):
        raise ValueError("Invalid image_size")
    return matrix, distortion, tuple(map(int, size))


def build_maps(
    matrix, distortion, calibrated_size, size, alpha, scale_intrinsics=False
):
    if not math.isfinite(alpha) or not 0 <= alpha <= 1:
        raise ValueError("alpha must be in [0, 1]")
    matrix = matrix.copy()
    if size != calibrated_size:
        if not scale_intrinsics:
            raise ValueError(
                f"Input resolution {size} differs from calibrated resolution {calibrated_size}"
            )
        matrix[0, :] *= size[0] / calibrated_size[0]
        matrix[1, :] *= size[1] / calibrated_size[1]
    new_matrix, _ = cv2.getOptimalNewCameraMatrix(matrix, distortion, size, alpha)
    return cv2.initUndistortRectifyMap(
        matrix, distortion, None, new_matrix, size, cv2.CV_16SC2
    )


def correct_video(
    source, target, matrix, distortion, calibrated_size, alpha, scale_intrinsics
):
    cap = cv2.VideoCapture(str(source))
    writer = None
    completed = False
    try:
        if not cap.isOpened():
            raise ValueError(f"Cannot open video: {source}")
        fps = cap.get(cv2.CAP_PROP_FPS)
        ok, frame = cap.read()
        if not ok or not math.isfinite(fps) or fps <= 0:
            raise ValueError(f"Cannot read video or invalid FPS: {source}")
        h, w = frame.shape[:2]
        # mp4v silently truncates odd dimensions; reject rather than lose pixels.
        if w % 2 or h % 2:
            raise ValueError(f"Video dimensions must be even for mp4v: {w}x{h}")
        maps = build_maps(
            matrix, distortion, calibrated_size, (w, h), alpha, scale_intrinsics
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        writer = cv2.VideoWriter(
            str(target), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h)
        )
        if not writer.isOpened():
            raise OSError(f"Cannot create video: {target}")
        while ok:
            if frame.shape[1::-1] != (w, h):
                raise ValueError(f"Video resolution changed: {source}")
            writer.write(cv2.remap(frame, *maps, cv2.INTER_LINEAR))
            ok, frame = cap.read()
        completed = True
    finally:
        cap.release()
        if writer is not None:
            writer.release()
            if not completed:
                target.unlink(missing_ok=True)


def undistort(source, output, params, alpha=0.0, scale_intrinsics=False, log=print):
    matrix, distortion, calibrated_size = load_parameters(params)
    pairs = output_paths(source, output)
    if not math.isfinite(alpha) or not 0 <= alpha <= 1:
        raise ValueError("alpha must be in [0, 1]")
    outputs = []
    for index, (path, target) in enumerate(pairs, 1):
        log(f"[{index}/{len(pairs)}] {path}")
        if path.suffix.lower() in IMAGE_EXTS:
            image = read_image(path)
            maps = build_maps(
                matrix,
                distortion,
                calibrated_size,
                image.shape[1::-1],
                alpha,
                scale_intrinsics,
            )
            write_image(target, cv2.remap(image, *maps, cv2.INTER_LINEAR))
        else:
            correct_video(
                path,
                target,
                matrix,
                distortion,
                calibrated_size,
                alpha,
                scale_intrinsics,
            )
        outputs.append(target)
    log(f"Completed: {len(outputs)} files")
    return outputs

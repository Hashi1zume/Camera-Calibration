"""Estimate intrinsics, save parameters and before/after comparisons only."""
import json
from pathlib import Path

import cv2
import numpy as np

from .boards import Detector
from .media import IMAGE_EXTS, check_destination, collect_files, read_image, write_image
from .undistortion import build_maps


def calibrate(
    source, output, config, min_images=10, estimate_tangential=False, log=print
):
    source, output = Path(source).resolve(), Path(output).resolve()
    check_destination(source, output)
    if type(min_images) is not int or min_images < 3:
        raise ValueError("min_images must be an integer >= 3; normally use 10 or more")
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise FileExistsError(
            f"Use a new or empty calibration output directory: {output}"
        )
    detector = Detector(config)
    files = collect_files(source, IMAGE_EXTS)
    objects, points, used, records = [], [], [], []
    size = None
    for i, path in enumerate(files, 1):
        relative = str(path.relative_to(source)) if source.is_dir() else path.name
        record = {"file": relative, "detected": False, "point_count": 0}
        records.append(record)
        try:
            image = read_image(path)
        except (ValueError, OSError, cv2.error) as exc:
            record["reason"] = str(exc)
            log(f"[{i}/{len(files)}] SKIP {relative}: {exc}")
            continue
        if size is None:
            size = image.shape[1::-1]
        if image.shape[1::-1] != size:
            raise ValueError(
                f"Mixed image resolution: {relative}: {image.shape[1::-1]} != {size}"
            )
        detected = detector.detect(image)
        if detected is None:
            record["reason"] = "Insufficient or non-identifiable board points"
        else:
            obj, pts = detected
            objects.append(obj)
            points.append(pts)
            used.append(path)
            record.update(detected=True, point_count=len(pts))
        log(f'[{i}/{len(files)}] {"OK" if detected is not None else "SKIP"} {relative}')
    if len(used) < min_images:
        raise ValueError(
            f"Insufficient usable images: {len(used)}/{len(files)}; need {min_images}. Check board settings and focus."
        )
    flags = 0 if estimate_tangential else cv2.CALIB_ZERO_TANGENT_DIST
    rms, matrix, distortion, rotations, translations = cv2.calibrateCamera(
        objects, points, size, None, None, flags=flags
    )
    if (
        not np.isfinite(matrix).all()
        or not np.isfinite(distortion).all()
        or not np.isfinite(rms)
    ):
        raise ValueError("Calibration returned nonfinite parameters")
    per_image = []
    for obj, pts, rotation, translation in zip(
        objects, points, rotations, translations
    ):
        projected, _ = cv2.projectPoints(obj, rotation, translation, matrix, distortion)
        per_image.append(
            float(np.sqrt(np.mean(np.sum((pts - projected) ** 2, axis=2))))
        )
    result = dict(
        schema_version=1,
        camera_model="pinhole",
        opencv_version=cv2.__version__,
        camera_matrix=matrix.tolist(),
        dist_coeffs=distortion.reshape(-1).tolist(),
        image_size=list(size),
        rms_error=float(rms),
        board=config.to_dict(),
        calibration_flags=int(flags),
        images_used=[r["file"] for r in records if r["detected"]],
        per_image_rms_px=per_image,
        points_per_image=[len(p) for p in points],
        detection_results=records,
    )
    output.mkdir(parents=True, exist_ok=True)
    maps = build_maps(matrix, distortion, size, size, 0.0)
    for path in used:
        image = read_image(path)
        corrected = cv2.remap(image, *maps, cv2.INTER_LINEAR)
        # Full resolution is used for estimation; preview panels are scaled only for display.
        preview_w = min(960, size[0])
        preview_size = (preview_w, max(1, round(size[1] * preview_w / size[0])))
        panels = []
        for frame, label in [(image, "Original"), (corrected, "Undistorted (alpha=0)")]:
            panel = cv2.resize(frame, preview_size)
            cv2.putText(
                panel,
                label,
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 0, 0),
                4,
                cv2.LINE_AA,
            )
            cv2.putText(
                panel,
                label,
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (255, 255, 255),
                1,
                cv2.LINE_AA,
            )
            panels.append(panel)
        relative = path.relative_to(source) if source.is_dir() else Path(path.name)
        target = output / "comparisons" / relative.parent / (relative.name + ".jpg")
        write_image(target, np.hstack(panels))
    with (output / "camera_params.json").open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False, allow_nan=False)
    log(f"Completed: {len(used)}/{len(files)} images; RMS={rms:.6f} px; {output}")
    return result

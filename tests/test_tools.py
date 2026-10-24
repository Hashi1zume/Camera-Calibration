import json
from pathlib import Path
import cv2
import numpy as np
import pytest

from camcal.boards import BoardConfig, Detector
from camcal.calibration import calibrate
from camcal.undistortion import undistort, load_parameters
from camcal.media import output_paths, read_image, write_image


def test_asymmetric_geometry_and_validation():
    cfg = BoardConfig(type="asymmetric_circles", columns=4, rows=5, spacing_mm=10)
    detector = Detector(cfg)
    assert np.allclose(detector.object_points[4], [10, 10, 0])
    assert np.allclose(detector.object_points[3], [60, 0, 0])
    with pytest.raises(ValueError):
        BoardConfig(
            type="charuco", columns=11, rows=8, spacing_mm=20, marker_mm=21
        ).validate()
    with pytest.raises(ValueError):
        BoardConfig(type="checker", columns=0, rows=8, spacing_mm=20).validate()
    with pytest.raises(ValueError):
        BoardConfig(type="aprilgrid", border_bits=3).validate()


def board_image(kind):
    cfg = BoardConfig(type=kind, columns=7, rows=6, spacing_mm=20, marker_mm=14)
    if kind == "asymmetric_circles":
        cfg = BoardConfig(type=kind, columns=4, rows=11, spacing_mm=20)
    if kind == "charuco":
        return cfg, Detector(cfg).board.generateImage((700, 600), marginSize=30)
    if kind == "aprilgrid":
        cfg = BoardConfig(type=kind, columns=3, rows=3, spacing_mm=20, tag_spacing=0.3)
        image = np.full((650, 650), 255, np.uint8)
        dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11)
        for row in range(3):
            for col in range(3):
                marker = cv2.rotate(
                    cv2.aruco.generateImageMarker(
                        dictionary, row * 3 + col, 150, borderBits=2
                    ),
                    cv2.ROTATE_180,
                )
                # Kalibr's IDs increase left-to-right, bottom-to-top.
                y, x = 80 + (2 - row) * 195, 55 + col * 195
                image[y : y + 150, x : x + 150] = marker
        return cfg, image
    image = np.full((700, 900), 255, np.uint8)
    if kind == "checker":
        for row in range(7):
            for col in range(8):
                if (row + col) % 2 == 0:
                    cv2.rectangle(
                        image,
                        (70 + col * 80, 70 + row * 80),
                        (70 + (col + 1) * 80, 70 + (row + 1) * 80),
                        0,
                        -1,
                    )
    else:
        for row in range(cfg.rows):
            for col in range(cfg.columns):
                x = 100 + (col * 80 if kind == "circles" else (2 * col + row % 2) * 50)
                y = 100 + row * (80 if kind == "circles" else 50)
                cv2.circle(image, (x, y), 17, 0, -1)
    return cfg, image


@pytest.mark.parametrize(
    "kind", ["checker", "charuco", "aprilgrid", "circles", "asymmetric_circles"]
)
def test_detect_generated_boards(kind):
    cfg, image = board_image(kind)
    result = Detector(cfg).detect(image)
    assert result is not None
    obj, points = result
    assert len(obj) == len(points) >= 6
    if kind == "aprilgrid":
        # Correct ID-to-world placement must allow a single planar projection.
        homography, _ = cv2.findHomography(obj[:, :2], points.reshape(-1, 2))
        projected = cv2.perspectiveTransform(obj[:, :2].reshape(-1, 1, 2), homography)
        assert np.sqrt(np.mean((projected - points) ** 2)) < 1


def parameters(path):
    path.write_text(
        json.dumps(
            dict(
                camera_matrix=[[100, 0, 32], [0, 100, 24], [0, 0, 1]],
                dist_coeffs=[0, 0, 0, 0, 0],
                image_size=[64, 48],
            )
        ),
        encoding="utf-8",
    )
    return path


def test_recursive_structure_and_no_overwrite(tmp_path):
    source = tmp_path / "input"
    (source / "nested").mkdir(parents=True)
    write_image(source / "nested" / "日本語.png", np.full((48, 64, 3), 120, np.uint8))
    write_image(source / "root.jpg", np.zeros((48, 64, 3), np.uint8))
    params = parameters(tmp_path / "params.json")
    outputs = undistort(source, tmp_path / "output", params)
    assert len(outputs) == 2
    assert (tmp_path / "output" / "input" / "nested" / "日本語.png").is_file()
    assert read_image(outputs[0]).shape == (48, 64, 3)
    with pytest.raises(FileExistsError):
        undistort(source, tmp_path / "output", params)
    with pytest.raises(ValueError):
        undistort(source, source / "output", params)


def test_resolution_and_invalid_parameters(tmp_path):
    params = parameters(tmp_path / "params.json")
    source = tmp_path / "image.png"
    write_image(source, np.zeros((96, 128, 3), np.uint8))
    with pytest.raises(ValueError, match="resolution"):
        undistort(source, tmp_path / "out", params)
    assert undistort(source, tmp_path / "scaled", params, scale_intrinsics=True)
    params.write_text(
        '{"camera_matrix": [[0]], "dist_coeffs": [], "image_size": [0,0]}'
    )
    with pytest.raises(ValueError):
        load_parameters(params)


def test_output_collisions(tmp_path):
    src = tmp_path / "input"
    src.mkdir()
    (src / "same.avi").touch()
    (src / "same.mp4").touch()
    with pytest.raises(ValueError, match="collision"):
        output_paths(src, tmp_path / "out")


def test_video_and_single_file(tmp_path):
    src = tmp_path / "clip.avi"
    writer = cv2.VideoWriter(str(src), cv2.VideoWriter_fourcc(*"MJPG"), 10, (64, 48))
    assert writer.isOpened()
    for value in [20, 80, 140]:
        writer.write(np.full((48, 64, 3), value, np.uint8))
    writer.release()
    outputs = undistort(src, tmp_path / "out", parameters(tmp_path / "params.json"))
    cap = cv2.VideoCapture(str(outputs[0]))
    count = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        assert frame.shape == (48, 64, 3)
        count += 1
    cap.release()
    assert count == 3


@pytest.mark.parametrize(
    "kind", ["checker", "charuco", "aprilgrid", "circles", "asymmetric_circles"]
)
def test_calibration_outputs_only_parameters_and_comparisons(tmp_path, kind):
    cfg, board = board_image(kind)
    source = tmp_path / "images"
    source.mkdir()
    rng = np.random.default_rng(42)
    h, w = board.shape
    for i in range(12):
        rotation, _ = cv2.Rodrigues(rng.uniform(-0.4, 0.4, 3))
        translation = np.array(
            [rng.uniform(-60, 60), rng.uniform(-40, 40), rng.uniform(1000, 1400)]
        )
        matrix = np.array([[900.0, 0, 500], [0, 900.0, 425], [0, 0, 1]])
        # All views must come from one physical camera; arbitrary quadrilaterals do not.
        homography = matrix @ np.column_stack(
            (rotation[:, :2], translation - rotation @ np.array([w / 2, h / 2, 0]))
        )
        image = cv2.warpPerspective(board, homography, (1000, 850), borderValue=255)
        write_image(source / f"{i}.png", image)
    result = calibrate(source, tmp_path / "result", cfg, min_images=10)
    assert len(result["images_used"]) == 12
    assert result["rms_error"] < 3
    assert (tmp_path / "result" / "camera_params.json").is_file()
    assert len(list((tmp_path / "result" / "comparisons").rglob("*.jpg"))) == 12
    assert not (tmp_path / "result" / "undistorted").exists()


def test_cli_config_and_failure(tmp_path):
    from camcal.cli import calibration_main, undistortion_main

    cfg = tmp_path / "board.json"
    cfg.write_text(json.dumps(BoardConfig().to_dict()))
    assert (
        calibration_main(
            [
                str(tmp_path / "missing"),
                "--config",
                str(cfg),
                "--output",
                str(tmp_path / "out"),
            ]
        )
        == 1
    )
    assert (
        undistortion_main(
            [
                str(tmp_path / "missing"),
                "--params",
                str(tmp_path / "missing.json"),
                "--output",
                str(tmp_path / "out"),
            ]
        )
        == 1
    )


def test_asymmetric_invalid_order_is_not_used():
    cfg = BoardConfig(type="asymmetric_circles", columns=7, rows=6, spacing_mm=20)
    image = np.full((700, 900), 255, np.uint8)
    for row in range(6):
        for col in range(7):
            cv2.circle(
                image, (100 + (2 * col + row % 2) * 50, 100 + row * 50), 17, 0, -1
            )
    result = Detector(cfg).detect(image)
    if result is not None:
        objects, points = result
        homography, _ = cv2.findHomography(objects[:, :2], points)
        projected = cv2.perspectiveTransform(
            objects[:, :2].reshape(-1, 1, 2), homography
        )
        assert np.sqrt(np.mean((projected - points) ** 2)) < 1


def test_kalibr_symmetric_corner_squares():
    cfg, image = board_image("aprilgrid")
    for row in range(3):
        for col in range(3):
            x, y = 55 + col * 195, 80 + (2 - row) * 195
            for dx, dy in [(-45, -45), (150, -45), (150, 150), (-45, 150)]:
                cv2.rectangle(
                    image, (x + dx, y + dy), (x + dx + 44, y + dy + 44), 0, -1
                )
    objects, points = Detector(cfg).detect(image)
    assert len(points) == 36
    homography, _ = cv2.findHomography(objects[:, :2], points)
    projected = cv2.perspectiveTransform(objects[:, :2].reshape(-1, 1, 2), homography)
    assert np.sqrt(np.mean((projected - points) ** 2)) < 1

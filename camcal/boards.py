"""Board definitions. All physical distances are millimetres."""
from dataclasses import asdict, dataclass
import math

import cv2
import numpy as np

BOARD_TYPES = ("checker", "charuco", "aprilgrid", "circles", "asymmetric_circles")
DICTIONARIES = tuple(name for name in dir(cv2.aruco) if name.startswith("DICT_"))


@dataclass
class BoardConfig:
    type: str = "checker"
    columns: int = 10
    rows: int = 7
    spacing_mm: float = 20.0
    marker_mm: float = 15.0
    dictionary: str = "DICT_4X4_50"
    legacy_pattern: bool = False
    tag_spacing: float = 0.3
    first_id: int = 0
    border_bits: int = 2

    def validate(self):
        if self.type not in BOARD_TYPES:
            raise ValueError(f"Unknown board type: {self.type}")
        for name in ("columns", "rows"):
            value = getattr(self, name)
            if type(value) is not int or value < 2:
                raise ValueError(f"{name} must be an integer >= 2")
        if not math.isfinite(self.spacing_mm) or self.spacing_mm <= 0:
            raise ValueError("spacing_mm must be positive and finite")
        if type(self.legacy_pattern) is not bool:
            raise ValueError("legacy_pattern must be boolean")
        if self.type == "charuco":
            if (
                not math.isfinite(self.marker_mm)
                or not 0 < self.marker_mm < self.spacing_mm
            ):
                raise ValueError("marker_mm must be smaller than spacing_mm")
            if self.dictionary not in DICTIONARIES:
                raise ValueError(f"Unknown dictionary: {self.dictionary}")
            dictionary = cv2.aruco.getPredefinedDictionary(
                getattr(cv2.aruco, self.dictionary)
            )
            if self.columns * self.rows // 2 > len(dictionary.bytesList):
                raise ValueError("Dictionary has too few markers for this board")
        if self.type == "aprilgrid":
            if type(self.border_bits) is not int or self.border_bits not in (1, 2):
                raise ValueError("border_bits must be 1 or 2")
            if not math.isfinite(self.tag_spacing) or self.tag_spacing <= 0:
                raise ValueError("tag_spacing must be a positive gap/tag-size ratio")
            if type(self.first_id) is not int or self.first_id < 0:
                raise ValueError("first_id must be a nonnegative integer")
            if self.first_id + self.columns * self.rows > 587:
                raise ValueError("AprilGrid IDs exceed the tag36h11 dictionary")
        return self

    def to_dict(self):
        return asdict(self)


class Detector:
    def __init__(self, config: BoardConfig):
        self.config = config.validate()
        self.object_points = np.zeros((config.columns * config.rows, 3), np.float32)
        grid = np.mgrid[: config.columns, : config.rows].T.reshape(-1, 2)
        if config.type == "asymmetric_circles":
            grid[:, 0] = 2 * grid[:, 0] + grid[:, 1] % 2
        self.object_points[:, :2] = grid * config.spacing_mm
        if config.type == "charuco":
            dictionary = cv2.aruco.getPredefinedDictionary(
                getattr(cv2.aruco, config.dictionary)
            )
            self.board = cv2.aruco.CharucoBoard(
                (config.columns, config.rows),
                config.spacing_mm,
                config.marker_mm,
                dictionary,
            )
            self.board.setLegacyPattern(config.legacy_pattern)
            self.detector = cv2.aruco.CharucoDetector(self.board)
        elif config.type == "aprilgrid":
            dictionary = cv2.aruco.getPredefinedDictionary(
                cv2.aruco.DICT_APRILTAG_36h11
            )
            params = cv2.aruco.DetectorParameters()
            params.markerBorderBits = config.border_bits
            params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
            self.detector = cv2.aruco.ArucoDetector(dictionary, params)
        elif config.type in ("circles", "asymmetric_circles"):
            params = cv2.SimpleBlobDetector_Params()
            params.filterByArea = True
            params.minArea = 5
            params.maxArea = 100000
            params.filterByColor = True
            params.blobColor = 0
            params.filterByCircularity = False
            params.filterByConvexity = False
            params.filterByInertia = True
            params.minInertiaRatio = 0.1
            self.blob_detector = cv2.SimpleBlobDetector_create(params)

    def detect(self, image):
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
        cfg = self.config
        if cfg.type == "checker":
            found, points = cv2.findChessboardCorners(gray, (cfg.columns, cfg.rows))
            if not found:
                return None
            points = cv2.cornerSubPix(
                gray,
                points,
                (11, 11),
                (-1, -1),
                (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001),
            )
            objects = self.object_points
        elif cfg.type == "charuco":
            points, ids, _, _ = self.detector.detectBoard(gray)
            if (
                ids is None
                or len(ids) < 6
                or self.board.checkCharucoCornersCollinear(ids)
            ):
                return None
            objects, points = self.board.matchImagePoints(points, ids)
        elif cfg.type == "aprilgrid":
            corners, ids, _ = self.detector.detectMarkers(gray)
            if ids is None:
                return None
            objects, points, seen = [], [], set()
            for marker, marker_id in zip(corners, ids.flatten()):
                index = int(marker_id) - cfg.first_id
                if not 0 <= index < cfg.columns * cfg.rows:
                    continue
                if index in seen:
                    raise ValueError(f"Duplicate AprilGrid ID: {marker_id}")
                seen.add(index)
                row, col = divmod(index, cfg.columns)
                size = cfg.spacing_mm
                x, y = col * size * (1 + cfg.tag_spacing), row * size * (
                    1 + cfg.tag_spacing
                )
                # Kalibr's PDF rotates tag codes by 180 degrees relative to OpenCV.
                objects.extend(
                    [
                        [x + size, y, 0],
                        [x, y, 0],
                        [x, y + size, 0],
                        [x + size, y + size, 0],
                    ]
                )
                points.extend(marker.reshape(4, 2))
            if len(points) < 8:
                return None
        else:
            flag = (
                cv2.CALIB_CB_SYMMETRIC_GRID
                if cfg.type == "circles"
                else cv2.CALIB_CB_ASYMMETRIC_GRID
            )
            found, points = cv2.findCirclesGrid(
                gray,
                (cfg.columns, cfg.rows),
                flags=flag,
                blobDetector=self.blob_detector,
            )
            if not found:
                found, points = cv2.findCirclesGrid(
                    gray,
                    (cfg.columns, cfg.rows),
                    flags=flag | cv2.CALIB_CB_CLUSTERING,
                    blobDetector=self.blob_detector,
                )
            if not found:
                return None
            objects = self.object_points
        objects = np.asarray(objects, np.float32).reshape(-1, 3)
        points = np.asarray(points, np.float32).reshape(-1, 1, 2)
        if cfg.type in ("circles", "asymmetric_circles"):
            # Some OpenCV grid detections report success with row pairs out of order.
            centers = points.reshape(cfg.rows, cfg.columns, 2).mean(axis=1)
            steps = np.diff(centers, axis=0)
            if np.any(steps @ (centers[-1] - centers[0]) <= 0):
                return None
        if (
            len(points) < 6
            or np.linalg.matrix_rank(objects[:, :2] - objects[:, :2].mean(axis=0)) < 2
        ):
            return None
        return objects, points

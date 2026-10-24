"""Small command line interfaces; the GUI calls the same processing functions."""
import argparse
import json
from pathlib import Path
import sys

import cv2

from .boards import BoardConfig
from .calibration import calibrate
from .undistortion import undistort


def calibration_main(argv=None):
    parser = argparse.ArgumentParser(
        description="Calibrate from board images (recursive search)."
    )
    parser.add_argument("input", type=Path, help="Input image directory")
    parser.add_argument(
        "--config", required=True, type=Path, help="Board configuration JSON"
    )
    parser.add_argument(
        "--output", required=True, type=Path, help="New or empty output directory"
    )
    parser.add_argument("--min-images", type=int, default=10)
    parser.add_argument("--estimate-tangential", action="store_true")
    args = parser.parse_args(argv)
    try:
        config = BoardConfig(**json.loads(args.config.read_text(encoding="utf-8")))
        calibrate(
            args.input, args.output, config, args.min_images, args.estimate_tangential
        )
    except (OSError, ValueError, TypeError, cv2.error) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


def undistortion_main(argv=None):
    parser = argparse.ArgumentParser(
        description="Undistort images/videos, preserving recursive directory structure."
    )
    parser.add_argument("input", type=Path, help="Input file or directory")
    parser.add_argument(
        "--params", required=True, type=Path, help="Camera parameter JSON"
    )
    parser.add_argument(
        "--output", required=True, type=Path, help="Output parent directory"
    )
    parser.add_argument(
        "--alpha",
        type=float,
        default=0.0,
        help="0: crop field of view; 1: retain field of view with black borders",
    )
    parser.add_argument(
        "--scale-intrinsics",
        action="store_true",
        help="Only for images resized from the same full sensor view; not cropping or camera mode changes",
    )
    args = parser.parse_args(argv)
    try:
        undistort(
            args.input, args.output, args.params, args.alpha, args.scale_intrinsics
        )
    except (OSError, ValueError, TypeError, cv2.error) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0

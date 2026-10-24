"""Unicode-safe image I/O and deterministic output planning."""
from pathlib import Path

import cv2
import numpy as np

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
VIDEO_EXTS = {".mp4", ".avi", ".mov", ".mkv", ".ts", ".mpg", ".mpeg", ".wmv", ".m4v"}


def read_image(path):
    image = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"Cannot read image: {path}")
    return image


def write_image(path, image):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    ok, encoded = cv2.imencode(path.suffix, image)
    if not ok:
        raise OSError(f"Cannot encode image: {path}")
    with path.open("xb") as stream:
        stream.write(encoded.tobytes())


def collect_files(source, extensions):
    source = Path(source).resolve()
    if source.is_file():
        if source.suffix.lower() not in extensions:
            raise ValueError(f"Unsupported file: {source}")
        return [source]
    if not source.is_dir():
        raise FileNotFoundError(source)
    files = sorted(
        p
        for p in source.rglob("*")
        if p.is_file() and not p.is_symlink() and p.suffix.lower() in extensions
    )
    if not files:
        raise ValueError(f"No supported files found: {source}")
    return files


def check_destination(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if destination == source or source in destination.parents:
        raise ValueError("Output must be outside the input directory/file")


def output_paths(source, output):
    source, output = Path(source).resolve(), Path(output).resolve()
    check_destination(source, output)
    files = collect_files(source, IMAGE_EXTS | VIDEO_EXTS)
    root = output / source.name if source.is_dir() else output
    check_destination(source, root)
    pairs, seen = [], set()
    for path in files:
        relative = path.relative_to(source) if source.is_dir() else Path(path.name)
        if path.suffix.lower() in VIDEO_EXTS:
            relative = relative.with_suffix(".mp4")
        target = root / relative
        key = str(target).casefold()
        if key in seen:
            raise ValueError(f"Output filename collision: {target}")
        seen.add(key)
        if target.exists():
            raise FileExistsError(target)
        pairs.append((path, target))
    return pairs

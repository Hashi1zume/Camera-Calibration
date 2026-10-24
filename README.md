# Camera Calibration

**English** | [日本語](README.ja.md)

Single-camera calibration and image/video undistortion for Ubuntu and Windows 11.
Supported targets: checkerboard, ChArUco, Kalibr-style AprilGrid, symmetric circles, and asymmetric circles.

- **Calibration**: recursively scans an image directory, estimates camera intrinsics and distortion coefficients, and saves a parameter JSON and before/after comparison images. It does not save separate undistorted images.
- **Board capture**: automatically discovers cameras, previews board detection, and saves raw calibration images from a desktop window.
- **Undistortion**: corrects images and videos using a parameter JSON. Accepts a single file or a directory, including all subdirectories.
- Use the CLI on Ubuntu or three dedicated GUI executables on Windows 11. With Python installed, both the CLI and GUI can run on either OS.

The camera model is OpenCV **pinhole with three radial and two tangential distortion coefficients**. Fisheye, stereo, and joint camera/IMU calibration are not supported. Using an AprilGrid target does not run Kalibr itself.

## Project layout

Use the `camera_calibration/` directory containing this README as the public repository root. The existing data and older scripts in its parent directory are not required.

```text
camera_calibration/
├── README.md                    # English documentation
├── README.ja.md                 # Japanese documentation
├── calibrate.py                 # Calibration CLI
├── undistort.py                 # Undistortion CLI
├── capture_gui.py               # Board capture GUI
├── calibration_gui.py           # Calibration GUI
├── undistortion_gui.py          # Undistortion GUI
├── camcal/
│   ├── capture.py               # Camera discovery, detection, and capture
│   ├── capture_gui.py           # Live capture window
│   ├── boards.py                # Board geometry and detection
│   ├── calibration.py           # Estimation and comparison images
│   ├── undistortion.py          # Image/video correction
│   ├── media.py                 # I/O and recursive discovery
│   ├── cli.py
│   └── gui.py
├── configs/                     # Example board configurations
├── scripts/build_windows.ps1    # Windows executable build
├── requirements*.txt
├── tests/                       # Synthetic image/video tests
├── docs/implementation.md
└── .github/workflows/           # Ubuntu tests and Windows build
```

Captured images, videos, and camera-specific parameters are not bundled. Keep local inputs in `data/` and generated files in `outputs/`; both directories are ignored by Git. If you use other locations, check the files tracked by Git before publishing.

## Ubuntu setup

Intended for Ubuntu 22.04 / 24.04 with Python 3.10–3.12. Run these commands in the directory containing this README.

```bash
sudo apt update
sudo apt install python3 python3-venv python3-tk libgl1 libglib2.0-0
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python calibrate.py --help
python undistort.py --help
```

`opencv-contrib-python` includes ChArUco/AprilTag functionality. Do not install `opencv-python` or a headless variant alongside it in the same environment. The GUI requires a desktop display.

```bash
python capture_gui.py
python calibration_gui.py
python undistortion_gui.py
```

## Windows 11 setup and executables

### Using built executables (no Python required)

Extract the Windows build artifact and launch:

- `BoardCapture.exe`: select an output directory and matching board JSON, then use **Capture** to save images.
- `CameraCalibration.exe`: select an image directory and output directory, enter the board type and dimensions, and click **実行** (Run). You can also load a board JSON from `configs/`.
- `CameraUndistortion.exe`: select an input file or directory, a camera parameter JSON, and an output directory, then click **実行** (Run).

The calibration and undistortion GUIs currently use Japanese labels; the capture GUI uses English. Select a directory as the output location, not a filename. Calibration requires a new or empty output directory. Progress and errors appear in the window.

**Executables are not included in the source checkout.** When this directory is published as the repository root on GitHub, the `Test and build Windows applications` workflow builds them on Windows. Download `camera-calibration-windows-x64` from the successful run's Artifacts. To build locally, follow the steps below.

### Building on Windows

Install the official **Python 3.11 x64** distribution with Tcl/Tk included. Run the following in PowerShell:

```powershell
cd C:\path\to\camera_calibration
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
powershell -ExecutionPolicy Bypass -File .\scripts\build_windows.ps1
```

If virtual environment activation is restricted, run `Set-ExecutionPolicy -Scope Process Bypass` for the current PowerShell process.

```text
dist/
├── BoardCapture.exe
├── CameraCalibration.exe
├── CameraUndistortion.exe
├── README.md
├── README.ja.md
├── LICENSE
└── configs/
```

The build uses PyInstaller's one-file mode. Each executable can run independently; distribute `configs/` as well if users need the example settings. Startup may take a while as the application extracts its files. The executables are unsigned.

Build Windows executables on Windows. [PyInstaller builds are specific to the operating system used for the build](https://pyinstaller.org/en/stable/operating-mode.html). Ubuntu tests do not verify the Windows executables.

To run from Python instead, install `requirements.txt` and use the same CLI or GUI commands as on Ubuntu.

## Capturing board images

```bash
python capture_gui.py

# Start with a specific board configuration and save directory
python capture_gui.py --config configs/charuco_11x8_squares_20mm_15mm_legacy.json --output data/charuco
```

The capture window uses English labels. The top toolbar contains the save directory selector and **Capture** button. Choose **Load board JSON...** to load one of the configurations in `configs/` or your own board configuration. The default is a checkerboard with **10 × 7 inner corners**, corresponding to 11 × 8 squares, with 20 mm squares.

- Camera indices **0–9** are probed automatically; the first camera that can deliver an image is selected. Use the **Camera** menu to switch cameras and **Rescan** after connecting a camera. Use `--max-camera-index 20` if higher indices must be searched.
- The preview has a **green border** and **Frame usable** when the configured detector accepts the frame, or a **red border** and **Frame unusable** otherwise. No camera or a disconnected camera also produces the red state.
- **Show corners** switches detection overlays on/off without changing detection or the saved image.
- **Capture** saves exactly the displayed, evaluated frame as a full-resolution, timestamped PNG. Overlays, preview scaling, and border graphics are not included. Existing files are not overwritten.
- Frames marked unusable can also be saved. The calibration command subsequently skips frames it cannot detect; a usable status only means that the configured board points were detected, not that focus, pose diversity, or final calibration accuracy is guaranteed.
- Changing the camera or board settings clears the current frame until a new result is available. Camera reads and detection run outside the GUI thread. Preview speed depends on camera and detection latency.

The camera's default capture resolution is used and displayed in the status line. Keep it consistent with the images/videos you intend to correct. Close other applications using the camera and enable camera access in the OS privacy settings if discovery fails. Some drivers take time to open or release a camera. Camera indices can change after reconnecting devices; they are not persistent device IDs. See [OpenCV VideoCapture](https://docs.opencv.org/4.10.0/d8/dfe/classcv_1_1VideoCapture.html).

After capture, run `calibrate.py` on the selected save directory, using the same board configuration.

### Examples of calibration frames

These examples use **checker detection with 10 × 7 inner corners**. Capture frames in which the required board points are clearly visible.

| Usable frame | Unusable frame |
|---|---|
| ![Green border and Frame usable with 70 detected corners](image/frame_usable.png) | ![Red border and Frame unusable with no detected corners](image/frame_unusable.png) |
| **Usable for calibration:** all 70 required inner corners are detected. The green border and **Frame usable** indicate a successful detection. | **Unusable for this configuration:** part of the board is outside the camera view, so the required corner grid cannot be detected. The red border and **Frame unusable** indicate a failed detection. |

A usable detection does not by itself guarantee calibration accuracy. Also collect sharp images with varied target positions, distances, and tilts. Partial-board acceptance differs for ChArUco and AprilGrid.

## Target characteristics

- **Checkerboard**: easy to print and provides precise corner localization. Generally requires the complete configured inner-corner grid to be visible. Distinguish square counts from inner-corner counts.
- **ChArUco**: combines chessboard corners with ArUco IDs. Correspondences can be identified with partial visibility, making it useful for varied poses. Match the printed dictionary, square counts, marker dimensions, and legacy layout setting.
- **Kalibr / AprilGrid**: uses AprilTag IDs and their four corners. Supports partial visibility and is also commonly used for multi-camera/IMU calibration. This tool performs single-camera calibration only.
- **Symmetric circles**: uses a regular grid of circle centers. Can tolerate some blur, but strong perspective turns circles into ellipses, and symmetry can introduce ambiguity.
- **Asymmetric circles**: uses a staggered arrangement to reduce orientation ambiguity. Its spacing convention differs from the symmetric grid; verify the actual point coordinates.

## Board configuration

All physical dimensions are in **millimetres**. Use the actual square, circle-center, or tag dimensions, rather than the paper width, height, or margins. Disable fit-to-page printing and measure the printed target.

| `type` | `columns` / `rows` | `spacing_mm` |
|---|---|---|
| `checker` | Number of **inner corners** | Square side length |
| `charuco` | Number of **squares** | Square side length |
| `aprilgrid` | Number of tags | Outer side length of the tag's black border |
| `circles` | Number of circle centers | Horizontal/vertical center spacing |
| `asymmetric_circles` | Circles per row / number of rows | `d` in the coordinate formula below |

For asymmetric circles, zero-based column `c` and row `r` have coordinates `x=(2*c+r%2)*d, y=r*d`. Adjacent circles in the same row are `2*d` apart. The row spacing and horizontal offset are `d`; the diagonal neighbor distance is `sqrt(2)*d`.

### Checkerboard example

A board with **11 columns × 8 rows of squares**, each 20 mm wide, has 10 columns × 7 rows of inner corners.

```json
{
  "type": "checker",
  "columns": 10,
  "rows": 7,
  "spacing_mm": 20
}
```

### ChArUco example

```json
{
  "type": "charuco",
  "columns": 11,
  "rows": 8,
  "spacing_mm": 20,
  "marker_mm": 15,
  "dictionary": "DICT_4X4_50",
  "legacy_pattern": true
}
```

`DICT_4X4` alone does not identify a unique dictionary. Specify the one used to print the target, such as `DICT_4X4_50`, `_100`, `_250`, or `_1000`. Some dictionaries share their lower IDs, so images alone may not reveal the original dictionary capacity.

Normally, `legacy_pattern` is `false`. Set it to `true` for even-row layouts compatible with OpenCV versions before 4.6. See the [official legacy-pattern documentation](https://docs.opencv.org/4.10.0/d0/d3c/classcv_1_1aruco_1_1CharucoBoard.html). A mismatched layout can prevent corner extraction even when markers are visible.

### Kalibr AprilGrid example

```json
{
  "type": "aprilgrid",
  "columns": 6,
  "rows": 6,
  "spacing_mm": 20,
  "tag_spacing": 0.3,
  "first_id": 0,
  "border_bits": 2
}
```

`tag_spacing` is the **gap between tags divided by tag width**. This example has a 6 mm gap and a 26 mm pitch. Convert Kalibr YAML settings `tagCols`, `tagRows`, `tagSize` (metres), and `tagSpacing` into this JSON format. Direct YAML loading is not supported.

`border_bits` specifies the black-border thickness in bits. The Kalibr default is **2**; set it to 1 for a target printed with a one-bit border. Tags must use the standard Kalibr orientation, rotated 180 degrees relative to OpenCV-generated markers.

Supported targets use **tag36h11** with ascending IDs and a consistent orientation in the standard Kalibr layout. ID 0 (or `first_id`) is at the bottom left; IDs increase to the right, then continue on the next row above. Custom tag rotations or rearranged IDs are not supported. See [Kalibr targets](https://github.com/ethz-asl/kalibr/wiki/Calibration-targets) and the [coordinate implementation](https://github.com/ethz-asl/kalibr/blob/master/aslam_cv/aslam_cameras_april/src/GridCalibrationTargetAprilgrid.cpp).

## Running calibration

Keep the camera, resolution, focus, and zoom unchanged. Mount the target flat and vary its distance, tilt, and position, including near the image edges. Collect at least 10–30 clear views with varied poses rather than many similar consecutive frames. Avoid motion blur, reflections, and a warped target.

```bash
python calibrate.py data/checker \
  --config configs/checker_11x8_squares_20mm.json \
  --output outputs/checker_run

python calibrate.py data/charuco \
  --config configs/charuco_11x8_squares_20mm_15mm_legacy.json \
  --output outputs/charuco_run
```

In PowerShell, put each command on one line or replace the trailing backslashes with backticks.

- All subdirectories are searched. Supported image formats: JPG/JPEG/PNG/BMP/TIF/TIFF/WebP, with case-insensitive extensions. Symlinked files are excluded.
- At least 10 successfully detected images are required by default. Undetected or unreadable images are skipped with a recorded reason. Mixed image resolutions cause an error.
- Use `--min-images N` to change the minimum (at least 3; normally use 10 or more). ChArUco needs at least six non-collinear corners; AprilGrid needs at least two tags.
- Tangential distortion is fixed to zero by default. Add `--estimate-tangential` to estimate it.
- Use a new or empty output directory for each run. Existing results are not overwritten.

```text
outputs/checker_run/
├── camera_params.json
└── comparisons/
    ├── photo01.jpg.jpg          # Input filename + .jpg
    └── subfolder/
        └── photo02.png.jpg
```

Comparison images show **left: original / right: undistorted (alpha=0)**. Each preview panel is at most 960 pixels wide; estimation uses the original image resolution. Comparisons are generated for successfully detected images. Separate undistorted images and corner overlays are not saved.

`camera_params.json` contains:

- `camera_matrix`: `[[fx,0,cx],[0,fy,cy],[0,0,1]]`, in pixels.
- `dist_coeffs`: `[k1,k2,p1,p2,k3]`.
- `image_size`: `[width,height]`.
- `rms_error`: reprojection RMS across all correspondences, in pixels.
- `per_image_rms_px`, `points_per_image`: RMS and point count for each accepted image.
- `images_used`, `detection_results`: accepted images, detection results for every input, and skip reasons.
- `board`, `calibration_flags`, `opencv_version`: settings needed to reproduce the run.

When point counts vary, the overall RMS is the square root of the point-count-weighted mean of squared per-image RMS values. RMS measures fit to the calibration images; it is not the distortion magnitude or a physical error in millimetres. Also validate straight lines and measured dimensions in unused images.

## Undistorting images and videos

Use the dedicated command when you need separate corrected files.

```bash
# Single image
python undistort.py data/photo.jpg --params outputs/charuco_run/camera_params.json --output outputs/corrected

# Single video
python undistort.py data/movie.mp4 --params outputs/charuco_run/camera_params.json --output outputs/corrected

# Recursively process all images and videos in a directory
python undistort.py data/session --params outputs/charuco_run/camera_params.json --output outputs/corrected
```

Directory input preserves the selected input directory's name and all relative paths:

```text
Input                              Output parent: outputs/corrected
 data/session/                     outputs/corrected/session/
 ├── photo.jpg                     ├── photo.jpg
 ├── camera_a/                     ├── camera_a/
 │   ├── clip.avi                   │   ├── clip.mp4
 │   └── nested/x.png               │   └── nested/x.png
 └── camera_b/clip.mov              └── camera_b/clip.mp4
```

For a single file, the destination is `output_directory/input_filename`. Image extensions are preserved; videos are always converted to `.mp4`. Supported video extensions: MP4/AVI/MOV/MKV/TS/MPG/MPEG/WMV/M4V. Actual codec availability depends on the OpenCV environment.

- Input resolution must match the calibration resolution by default. A mismatch causes an error.
- For a simple resize of the same full field of view, `--scale-intrinsics` scales `fx,fy,cx,cy`. Do not use it for cropping, zoom changes, or sensor-mode changes.
- `--alpha 0` (default) narrows the field of view to reduce black borders; `--alpha 1` retains the field of view with black borders. Output pixel dimensions are preserved, with no additional ROI crop.
- Videos are re-encoded with `mp4v` at the original reported FPS as **constant-frame-rate video without audio**. Audio, variable-frame-rate timestamps, and metadata are not preserved. Odd video dimensions cause an error to avoid silent codec truncation.
- Output inside the input, overwriting existing files, and filename collisions after video conversion (for example, `clip.avi` and `clip.mov`) cause an error. Processing stops on error; files completed before the error remain.
- One run applies the same parameters to every file, even if subdirectories contain multiple cameras. Process different cameras separately.

Parameter JSON files from older scripts are also accepted if they include `camera_matrix`, `dist_coeffs`, and `image_size`. Both one-dimensional and two-dimensional distortion-coefficient arrays are supported.

## Tests

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

Tests cover synthetic detection for all five target types, AprilGrid correspondences, calibration and comparison output, recursive paths, Japanese image filenames, video output, resolution checks, and overwrite/collision prevention. GUI tests are skipped on Ubuntu without an available display and run in Windows CI. Recorded checks and unverified areas are listed in [docs/validation.md](docs/validation.md) (Japanese). Verify real-camera accuracy, Windows GUI interaction, and required video codecs in your own environment as well.

## License

This project is licensed under the [MIT License](LICENSE).

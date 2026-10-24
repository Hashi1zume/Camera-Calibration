# Run on Windows 11 with Python 3.11 x64, from any working directory.
$ErrorActionPreference = 'Stop'
Push-Location (Join-Path $PSScriptRoot '..')
try {
    python -m pip install -r requirements-build.txt
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
    python -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw 'Tests failed' }
    python -m PyInstaller --noconfirm --clean --onefile --windowed --collect-all cv2 --name CameraCalibration calibration_gui.py
    if ($LASTEXITCODE -ne 0) { throw 'Calibration executable build failed' }
    python -m PyInstaller --noconfirm --clean --onefile --windowed --collect-all cv2 --name CameraUndistortion undistortion_gui.py
    if ($LASTEXITCODE -ne 0) { throw 'Undistortion executable build failed' }
    python -m PyInstaller --noconfirm --clean --onefile --windowed --collect-all cv2 --name BoardCapture capture_gui.py
    if ($LASTEXITCODE -ne 0) { throw 'Capture executable build failed' }
    Copy-Item README.md, README.ja.md dist/
    Copy-Item configs dist/ -Recurse -Force
    Write-Host 'Created dist/CameraCalibration.exe, dist/CameraUndistortion.exe and dist/BoardCapture.exe'
} finally {
    Pop-Location
}

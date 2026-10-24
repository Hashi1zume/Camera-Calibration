# 公開用キャリブレーションツールの設計・実装計画

目的: 既存の撮影データを含めず、このディレクトリを独立した公開リポジトリとして利用可能にする。

構成: Python 3.10以上、OpenCV contrib、NumPy。共通ライブラリをCLIとTkinter GUIから呼ぶ。
既存スクリプトの固定設定を持ち込む方法より、ボードJSONによる設定を採用する。
Web UIは不要なサーバー依存が増えるため採用しない。

受け入れ条件:
- checker / charuco / aprilgrid / circles / asymmetric_circles の検出と推定。
- キャリブレーション入力は画像の再帰探索。出力はcamera_params.jsonと比較JPEGのみ。
- 補正入力は画像・動画またはディレクトリ。出力ルート/入力ディレクトリ名/相対パスを維持。
- ファイル衝突、入出力の包含、解像度不一致、破損画像、検出不足を検証。
- GUIで入力・出力・全ボード設定を指定可能。Windowsで2本のexeをビルド可能。
- Ubuntu/Windows 11手順、ボードの特徴、動画の音声非保持、モデルの限界をREADMEに記載。

実装順:
1. ボード幾何・検出と設定検証を実装し、合成画像で5種類を確認する。
2. 推定・比較出力を実装し、既存実画像でも動作確認する。
3. 構造を維持する補正処理を実装し、画像・短い動画・衝突と解像度をテストする。
4. CLI/GUI・設定例・Windowsビルド・CIとREADMEを作成する。
5. 全テスト、実画像CLI、GUI起動を検証する。Windows exeの実行はWindows環境で別途必要。

AprilGridはKalibrのtag36h11・ID昇順・左下原点を対象とする。
このツールはKalibrそのものではなく、OpenCVの単眼pinholeモデルを使用する。
ライセンスは権利者未指定なので勝手に付与しない。公開前に権利者が選択する。

## Board capture GUI (2026-10-24)

- Add `capture_gui.py` / `camcal/capture.py` / `camcal/capture_gui.py`.
- Probe camera indices 0–9 off the Tk thread; select the first readable camera and provide camera selection/rescan.
- Top toolbar: output directory, camera, board configuration JSON, corner overlay checkbox, capture button.
- Reuse `Detector` so all five board types share calibration acceptance rules. Show green `Frame usable` or red `Frame unusable` around the preview.
- A background worker reads and detects full-resolution frames. Keep only the latest processed frame; camera/config changes invalidate old frames before capture can resume.
- Capture the displayed evaluated raw frame as a uniquely named PNG, including frames classified unusable; never save overlay graphics into calibration inputs.
- Add camera-probe, detection/overlay/save, stale-frame and worker cleanup tests; run existing tests and available GUI tests. Real-camera/desktop verification is environment-dependent.
- Document in English and Japanese and include `BoardCapture.exe` in the Windows build and startup checks.

"""Desktop camera capture, with status tied to the displayed raw frame."""
import argparse
import json
from pathlib import Path
import queue
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import cv2

from .boards import BoardConfig, Detector
from .capture import CameraWorker, draw_preview, save_capture


class CaptureApplication:
    def __init__(self, root, config=None, output="", max_camera_index=9, worker=None):
        self.root = root
        self.config = config or BoardConfig()
        self.config.validate()
        self.generation = 0
        self.current = None
        self.photo = None
        self.closed = False
        self.output = tk.StringVar(value=str(output))
        self.camera = tk.StringVar()
        self.overlay = tk.BooleanVar(value=True)
        self.board_label = tk.StringVar()
        self.status = tk.StringVar(value="Frame unusable — Scanning cameras...")
        self.note = tk.StringVar(
            value="Select an output directory and a matching board configuration."
        )
        root.title("Board Capture")
        root.geometry("1080x800")
        root.minsize(780, 550)
        root.protocol("WM_DELETE_WINDOW", self.close)
        outer = ttk.Frame(root, padding=8)
        outer.pack(fill="both", expand=True)
        # The top toolbar remains visible above the scalable preview.
        toolbar = ttk.Frame(outer)
        toolbar.pack(fill="x", pady=(0, 6))
        ttk.Label(toolbar, text="Save to").grid(row=0, column=0, padx=4)
        ttk.Entry(toolbar, textvariable=self.output).grid(
            row=0, column=1, sticky="ew", padx=4
        )
        ttk.Button(toolbar, text="Browse...", command=self.choose_output).grid(
            row=0, column=2, padx=4
        )
        self.capture_button = ttk.Button(
            toolbar, text="Capture", command=self.capture, state="disabled"
        )
        self.capture_button.grid(row=0, column=3, padx=4)
        toolbar.columnconfigure(1, weight=1)
        controls = ttk.Frame(outer)
        controls.pack(fill="x", pady=4)
        ttk.Label(controls, text="Camera").pack(side="left", padx=4)
        self.camera_selector = ttk.Combobox(
            controls, textvariable=self.camera, state="disabled", width=8
        )
        self.camera_selector.pack(side="left", padx=4)
        self.camera_selector.bind("<<ComboboxSelected>>", self.select_camera)
        self.rescan_button = ttk.Button(
            controls, text="Rescan", command=self.rescan, state="disabled"
        )
        self.rescan_button.pack(side="left", padx=4)
        ttk.Button(controls, text="Load board JSON...", command=self.load_board).pack(
            side="left", padx=4
        )
        ttk.Checkbutton(
            controls, text="Show corners", variable=self.overlay, command=self.render
        ).pack(side="left", padx=12)
        ttk.Label(outer, textvariable=self.board_label).pack(anchor="w", padx=4, pady=4)
        # Native title-bar colours are OS-controlled; colour all four preview edges.
        self.border = tk.Frame(outer, background="#b71c1c", padx=6, pady=6)
        self.border.pack(fill="both", expand=True)
        self.preview = tk.Label(
            self.border,
            background="#151515",
            foreground="white",
            text="Waiting for camera...",
            anchor="center",
        )
        self.preview.pack(fill="both", expand=True)
        self.status_label = tk.Label(
            outer,
            textvariable=self.status,
            foreground="#b71c1c",
            font=("TkDefaultFont", 14, "bold"),
        )
        self.status_label.pack(fill="x", pady=6)
        ttk.Label(outer, textvariable=self.note, wraplength=1000).pack(fill="x", padx=4)
        self.preview.bind("<Configure>", lambda _: self.render())
        self.describe_board()
        self.worker = worker or CameraWorker(
            self.config, indices=range(max_camera_index + 1)
        )
        self.worker.start()
        self.poll_id = root.after(40, self.poll)

    def describe_board(self):
        cfg = self.config
        counts = (
            "inner corners"
            if cfg.type == "checker"
            else "squares"
            if cfg.type == "charuco"
            else "tags"
            if cfg.type == "aprilgrid"
            else "circle centers"
        )
        self.board_label.set(
            f"Board: {cfg.type} | {cfg.columns} columns × {cfg.rows} rows ({counts}) | spacing {cfg.spacing_mm:g} mm"
        )

    def choose_output(self):
        path = filedialog.askdirectory(
            title="Select image output directory", mustexist=False
        )
        if path:
            self.output.set(path)

    def invalidate(self, reason):
        self.current = None
        self.photo = None
        self.preview.configure(image="", text=reason)
        self.capture_button.configure(state="disabled")
        self.set_status(False, reason)

    def set_status(self, usable, reason=""):
        color = "#16833b" if usable else "#b71c1c"
        self.border.configure(background=color)
        self.status_label.configure(foreground=color)
        self.status.set(
            ("Frame usable" if usable else "Frame unusable")
            + (f" — {reason}" if reason else "")
        )

    def select_camera(self, _=None):
        self.generation += 1
        self.invalidate("Opening camera...")
        self.worker.select_camera(int(self.camera.get()), self.generation)

    def rescan(self):
        self.generation += 1
        self.invalidate("Scanning cameras...")
        self.camera_selector.configure(state="disabled")
        self.rescan_button.configure(state="disabled")
        self.worker.rescan(self.generation)

    def apply_config(self, config):
        config.validate()
        Detector(
            config
        )  # Report invalid detector settings before replacing the current setup.
        self.config = config
        self.generation += 1
        self.invalidate("Checking new board configuration...")
        self.describe_board()
        self.worker.configure(config, self.generation)

    def load_board(self):
        path = filedialog.askopenfilename(
            title="Select board configuration", filetypes=[("Board JSON", "*.json")]
        )
        if not path:
            return
        try:
            config = BoardConfig(**json.loads(Path(path).read_text(encoding="utf-8")))
            self.apply_config(config)
            self.note.set(f"Loaded board configuration: {path}")
        except (OSError, ValueError, TypeError, cv2.error) as exc:
            messagebox.showerror("Board configuration", str(exc))

    def accept_frame(self, result):
        if result.generation != self.generation:
            return
        self.current = result
        h, w = result.frame.shape[:2]
        self.set_status(
            result.usable,
            f"{w} × {h} | {0 if result.points is None else len(result.points)} points",
        )
        self.capture_button.configure(state="normal")
        self.render()

    def render(self):
        if self.current is None or self.closed:
            return
        frame = draw_preview(self.current, self.overlay.get())
        h, w = frame.shape[:2]
        scale = min(
            max(1, self.preview.winfo_width()) / w,
            max(1, self.preview.winfo_height()) / h,
            1.0,
        )
        if scale < 1:
            frame = cv2.resize(
                frame,
                (max(1, round(w * scale)), max(1, round(h * scale))),
                interpolation=cv2.INTER_AREA,
            )
        ok, encoded = cv2.imencode(".ppm", frame)
        if not ok:
            return
        self.photo = tk.PhotoImage(data=encoded.tobytes(), format="PPM")
        self.preview.configure(image=self.photo, text="")

    def capture(self):
        # The current packet is exactly the full-resolution frame shown and checked.
        if self.current is None or self.current.generation != self.generation:
            return
        result = self.current
        try:
            path = save_capture(result, self.output.get())
        except (OSError, ValueError, cv2.error) as exc:
            messagebox.showerror("Capture failed", str(exc))
            return
        self.note.set(f"Saved: {path} | {result.status} | raw PNG, no corner overlay")

    def poll(self):
        if self.closed:
            return
        while True:
            try:
                kind, payload = self.worker.events.get_nowait()
            except queue.Empty:
                break
            if kind == "cameras":
                self.camera_selector.configure(
                    values=[str(i) for i in payload],
                    state="readonly" if payload else "disabled",
                )
                self.camera.set(str(payload[0]) if payload else "")
                self.rescan_button.configure(state="normal")
            elif kind == "error":
                self.invalidate(payload)
                self.note.set(payload)
                self.rescan_button.configure(state="normal")
        try:
            result = self.worker.frames.get_nowait()
        except queue.Empty:
            pass
        else:
            self.accept_frame(result)
        self.poll_id = self.root.after(40, self.poll)

    def close(self):
        self.closed = True
        self.root.after_cancel(self.poll_id)
        self.worker.stop()
        self.root.destroy()


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Capture board images with automatic camera discovery and live corner checks."
    )
    parser.add_argument(
        "--config",
        type=Path,
        help="Board configuration JSON; default: checker, 10×7 inner corners, 20 mm",
    )
    parser.add_argument("--output", default="", help="Initial image output directory")
    parser.add_argument(
        "--max-camera-index",
        type=int,
        default=9,
        help="Probe camera indices 0 through this index (default 9)",
    )
    args = parser.parse_args(argv)
    if args.max_camera_index < 0:
        parser.error("--max-camera-index must be nonnegative")
    config = BoardConfig()
    if args.config:
        try:
            config = BoardConfig(
                **json.loads(args.config.read_text(encoding="utf-8"))
            ).validate()
        except (OSError, ValueError, TypeError) as exc:
            parser.error(str(exc))
    root = tk.Tk()
    CaptureApplication(root, config, args.output, args.max_camera_index)
    root.mainloop()

"""Two Tkinter desktop entry points, with processing outside the UI thread."""
import json
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

from .boards import BOARD_TYPES, DICTIONARIES, BoardConfig
from .calibration import calibrate
from .undistortion import undistort


class Application:
    def __init__(self, root, mode):
        self.root, self.mode = root, mode
        self.messages = queue.Queue()
        self.running = False
        root.title(
            "Camera Calibration" if mode == "calibrate" else "Camera Undistortion"
        )
        root.geometry("900x760" if mode == "calibrate" else "900x560")
        root.minsize(720, 580 if mode == "calibrate" else 440)
        root.protocol("WM_DELETE_WINDOW", self.close)
        outer = ttk.Frame(root, padding=12)
        outer.pack(fill="both", expand=True)
        self.paths = {}
        for row, (name, label) in enumerate(
            [("input", "入力"), ("output", "出力先"), ("params", "パラメータJSON")]
            if mode != "calibrate"
            else [("input", "画像ディレクトリ"), ("output", "出力先（新規または空）")]
        ):
            ttk.Label(outer, text=label).grid(row=row, column=0, sticky="w", pady=5)
            variable = tk.StringVar()
            self.paths[name] = variable
            ttk.Entry(outer, textvariable=variable).grid(
                row=row, column=1, sticky="ew", padx=8
            )
            ttk.Button(
                outer, text="参照", command=lambda key=name: self.browse(key)
            ).grid(row=row, column=2)
        outer.columnconfigure(1, weight=1)
        self.fields = {}
        settings = ttk.LabelFrame(outer, text="設定", padding=10)
        settings.grid(row=3, column=0, columnspan=3, sticky="ew", pady=10)
        if mode == "calibrate":
            definitions = [
                ("type", "ボード種類", "checker"),
                ("columns", "列数", 10),
                ("rows", "行数", 7),
                ("spacing_mm", "マス幅 / 間隔 / タグ幅 (mm)", 20),
                ("marker_mm", "ChArUco マーカー幅 (mm)", 15),
                ("dictionary", "ChArUco 辞書", "DICT_4X4_50"),
                ("tag_spacing", "AprilGrid 隙間 / タグ幅", 0.3),
                ("first_id", "AprilGrid 最初のID", 0),
                ("border_bits", "AprilGrid 黒枠bit数", 2),
                ("min_images", "最低有効画像数", 10),
            ]
            for i, (name, label, default) in enumerate(definitions):
                row, col = divmod(i, 2)
                col *= 2
                ttk.Label(settings, text=label).grid(
                    row=row, column=col, sticky="w", padx=4, pady=4
                )
                var = tk.StringVar(value=str(default))
                self.fields[name] = var
                if name in ("type", "dictionary"):
                    widget = ttk.Combobox(
                        settings,
                        textvariable=var,
                        values=BOARD_TYPES if name == "type" else DICTIONARIES,
                        state="readonly",
                        width=23,
                    )
                else:
                    widget = ttk.Entry(settings, textvariable=var, width=12)
                widget.grid(row=row, column=col + 1, sticky="ew", padx=4)
            self.legacy = tk.BooleanVar()
            self.tangential = tk.BooleanVar()
            ttk.Checkbutton(
                settings, text="ChArUco 旧形式 (legacy pattern)", variable=self.legacy
            ).grid(row=5, column=0, columnspan=2, sticky="w")
            ttk.Checkbutton(settings, text="接線歪みも推定", variable=self.tangential).grid(
                row=5, column=2, columnspan=2, sticky="w"
            )
            self.hint = tk.StringVar()
            ttk.Label(settings, textvariable=self.hint, wraplength=800).grid(
                row=6, column=0, columnspan=4, sticky="w", pady=8
            )
            self.fields["type"].trace_add("write", self.update_hint)
            self.update_hint()
            buttons = ttk.Frame(settings)
            buttons.grid(row=7, column=0, columnspan=4, sticky="w")
            ttk.Button(buttons, text="ボード設定JSONを開く", command=self.load_config).pack(
                side="left", padx=4
            )
            ttk.Button(buttons, text="ボード設定JSONを保存", command=self.save_config).pack(
                side="left", padx=4
            )
        else:
            self.alpha = tk.StringVar(value="0.0")
            self.scale = tk.BooleanVar()
            ttk.Label(settings, text="alpha (0〜1)").grid(row=0, column=0, sticky="w")
            ttk.Entry(settings, textvariable=self.alpha, width=10).grid(
                row=0, column=1, padx=8
            )
            ttk.Checkbutton(
                settings, text="解像度変更に合わせて内部行列を拡大縮小", variable=self.scale
            ).grid(row=1, column=0, columnspan=3, sticky="w", pady=6)
            ttk.Label(
                settings,
                text="拡大縮小は同じ画角の単純リサイズ時のみ使用。クロップ・ズーム変更には使えません。\n動画は音声なしMP4で保存します。",
                wraplength=800,
            ).grid(row=2, column=0, columnspan=3, sticky="w")
        self.run_button = ttk.Button(outer, text="実行", command=self.start)
        self.run_button.grid(row=4, column=0, columnspan=3, pady=5)
        self.log = scrolledtext.ScrolledText(
            outer, height=10, state="disabled", wrap="word"
        )
        self.log.grid(row=5, column=0, columnspan=3, sticky="nsew", pady=8)
        outer.rowconfigure(5, weight=1)
        root.after(100, self.poll)

    def update_hint(self, *_):
        kind = self.fields["type"].get()
        text = {
            "checker": "列・行は内側交点数です。11×8マスのボードなら列10・行7。間隔はマス幅。",
            "charuco": "列・行はマス数です。今回のボードは列11・行8、マス20 mm・マーカー15 mm、旧形式ON。",
            "aprilgrid": "列・行はタグ数。tag36h11専用。IDは左下から右へ、下の行から上へ昇順。間隔欄はタグの黒枠外形幅。",
            "circles": "列・行は円の中心数。間隔は上下左右の隣接中心間距離。白背景・黒円。",
            "asymmetric_circles": "列・行は円の中心数。座標は x=(2×列+行%2)×間隔、y=行×間隔。同じ行の円間距離は間隔の2倍。",
        }[kind]
        self.hint.set(text)

    def browse(self, key):
        if key == "params":
            value = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        elif key == "input" and self.mode != "calibrate":
            choice = messagebox.askyesnocancel(
                "入力形式", "ディレクトリを選びますか？\n「いいえ」で単一ファイルを選択します。"
            )
            if choice is None:
                return
            value = (
                filedialog.askdirectory() if choice else filedialog.askopenfilename()
            )
        else:
            value = filedialog.askdirectory(mustexist=key == "input")
        if value:
            self.paths[key].set(value)

    def get_config(self):
        values = {
            key: var.get() for key, var in self.fields.items() if key != "min_images"
        }
        for key in ("columns", "rows", "first_id", "border_bits"):
            values[key] = int(values[key])
        for key in ("spacing_mm", "marker_mm", "tag_spacing"):
            values[key] = float(values[key])
        values["legacy_pattern"] = self.legacy.get()
        return BoardConfig(**values).validate()

    def load_config(self):
        path = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if not path:
            return
        try:
            cfg = BoardConfig(
                **json.loads(Path(path).read_text(encoding="utf-8"))
            ).validate()
            for key, value in cfg.to_dict().items():
                if key in self.fields:
                    self.fields[key].set(str(value))
            self.legacy.set(cfg.legacy_pattern)
        except Exception as exc:
            messagebox.showerror("設定エラー", str(exc))

    def save_config(self):
        try:
            config = self.get_config()
        except Exception as exc:
            messagebox.showerror("設定エラー", str(exc))
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".json", filetypes=[("JSON", "*.json")]
        )
        if path:
            try:
                Path(path).write_text(
                    json.dumps(config.to_dict(), indent=2), encoding="utf-8"
                )
            except OSError as exc:
                messagebox.showerror("保存エラー", str(exc))

    def start(self):
        if self.running:
            return
        try:
            paths = {key: var.get().strip() for key, var in self.paths.items()}
            if not all(paths.values()):
                raise ValueError("入力・出力先・パラメータを指定してください。")
            if self.mode == "calibrate":
                config = self.get_config()
                arguments = (
                    paths["input"],
                    paths["output"],
                    config,
                    int(self.fields["min_images"].get()),
                    self.tangential.get(),
                )
                function = calibrate
            else:
                arguments = (
                    paths["input"],
                    paths["output"],
                    paths["params"],
                    float(self.alpha.get()),
                    self.scale.get(),
                )
                function = undistort
        except Exception as exc:
            messagebox.showerror("入力エラー", str(exc))
            return
        self.running = True
        self.run_button.configure(state="disabled")

        def work():
            try:
                function(
                    *arguments, log=lambda text: self.messages.put(("log", str(text)))
                )
            except Exception as exc:
                self.messages.put(("error", str(exc)))
            else:
                self.messages.put(("done", "処理が完了しました。"))

        threading.Thread(target=work, daemon=True).start()

    def poll(self):
        while True:
            try:
                kind, text = self.messages.get_nowait()
            except queue.Empty:
                break
            self.log.configure(state="normal")
            self.log.insert("end", text + "\n")
            self.log.see("end")
            self.log.configure(state="disabled")
            if kind in ("error", "done"):
                self.running = False
                self.run_button.configure(state="normal")
                if kind == "error":
                    messagebox.showerror("処理エラー", text)
                else:
                    messagebox.showinfo("完了", text)
        self.root.after(100, self.poll)

    def close(self):
        if self.running:
            messagebox.showinfo("処理中", "処理が完了してから閉じてください。")
            return
        self.root.destroy()


def launch(mode):
    root = tk.Tk()
    Application(root, mode)
    root.mainloop()

# -*- coding: utf-8 -*-
"""싹둑 - 녹음·영상 자동 분할기 (오프라인 버전 화면)"""

import json
import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import splitter_core as core

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    HAS_DND = True
except Exception:
    HAS_DND = False

APP_NAME = "싹둑"
SETTINGS = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"),
                        "Ssakduk", "settings.json")
FONT = "Malgun Gothic" if os.name == "nt" else "TkDefaultFont"

C_BG = "#f6f5f2"
C_CARD = "#ffffff"
C_LINE = "#d9d6cf"
C_TEXT = "#26241f"
C_MUTED = "#77736a"
C_ACCENT = "#2f6f5e"
C_DROP = "#eef4f1"


def open_folder(path):
    if os.name == "nt":
        os.startfile(path)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


class App:
    def __init__(self, root, initial=()):
        self.root = root
        self.q = queue.Queue()
        self.items = {}          # tree id -> path
        self.busy = False
        self.last_dir = None
        self.ffmpeg = core.find_ffmpeg()

        root.title(f"{APP_NAME} — 무료 녹음·영상 자동 분할")
        try:
            base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
            root.iconbitmap(os.path.join(base, "icon.ico"))
        except Exception:
            pass
        root.geometry("660x660")
        root.minsize(520, 520)
        root.configure(bg=C_BG)

        st = ttk.Style()
        try:
            st.theme_use("clam")
        except tk.TclError:
            pass
        st.configure(".", font=(FONT, 10), background=C_BG, foreground=C_TEXT)
        st.configure("TFrame", background=C_BG)
        st.configure("TLabel", background=C_BG, foreground=C_TEXT)
        st.configure("Muted.TLabel", foreground=C_MUTED)
        st.configure("Title.TLabel", font=(FONT, 15, "bold"))
        st.configure("TCheckbutton", background=C_BG)
        st.configure("Treeview", rowheight=26, background=C_CARD, fieldbackground=C_CARD,
                     bordercolor=C_LINE)
        st.configure("Treeview.Heading", font=(FONT, 9, "bold"), background=C_BG,
                     foreground=C_MUTED, relief="flat")
        st.configure("TButton", padding=(12, 6))
        st.configure("Accent.TButton", padding=(16, 7), font=(FONT, 10, "bold"),
                     background=C_ACCENT, foreground="#ffffff", bordercolor=C_ACCENT)
        st.map("Accent.TButton",
               background=[("disabled", "#a9bfb7"), ("active", "#245a4c")],
               foreground=[("disabled", "#eef2f0")])
        st.configure("Horizontal.TProgressbar", troughcolor="#e8e5de",
                     background=C_ACCENT, bordercolor=C_LINE, lightcolor=C_ACCENT,
                     darkcolor=C_ACCENT)

        outer = ttk.Frame(root, padding=18)
        outer.pack(fill="both", expand=True)

        ttk.Label(outer, text=APP_NAME, style="Title.TLabel").pack(anchor="w")
        ttk.Label(outer, text="녹음·영상을 조용한 지점에서 정해진 길이 이하로 자릅니다. 음질·화질 손실 없음.",
                  style="Muted.TLabel").pack(anchor="w", pady=(2, 12))

        # 드롭 영역
        self.drop = tk.Label(
            outer, bg=C_DROP, fg=C_ACCENT, cursor="hand2", font=(FONT, 11),
            text=("여기에 녹음·영상 파일을 끌어다 놓으세요\n또는 클릭해서 선택"
                  if HAS_DND else "클릭해서 녹음·영상 파일 선택"),
            height=4, highlightthickness=1, highlightbackground="#b9d0c7")
        self.drop.pack(fill="x")
        self.drop.bind("<Button-1>", lambda e: self.pick())
        if HAS_DND:
            for w in (self.drop, root):
                w.drop_target_register(DND_FILES)
                w.dnd_bind("<<Drop>>", self.on_drop)

        # 파일 목록
        lst = ttk.Frame(outer)
        lst.pack(fill="both", expand=True, pady=(12, 0))
        self.tree = ttk.Treeview(lst, columns=("name", "status"), show="headings",
                                 height=6, selectmode="extended")
        self.tree.heading("name", text="파일", anchor="w")
        self.tree.heading("status", text="상태", anchor="w")
        self.tree.column("name", width=380, anchor="w")
        self.tree.column("status", width=150, anchor="w")
        sb = ttk.Scrollbar(lst, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree.bind("<Delete>", lambda e: self.remove_selected())

        # 설정
        opt = ttk.Frame(outer)
        opt.pack(fill="x", pady=(12, 0))
        cfg = self.load_settings()
        self.v_max = tk.DoubleVar(value=cfg.get("max_min", 5))
        self.v_search = tk.IntVar(value=cfg.get("search_sec", 30))
        self.v_sub = tk.BooleanVar(value=cfg.get("subfolder", True))
        self.v_audio = tk.BooleanVar(value=cfg.get("audio_only", False))
        ttk.Label(opt, text="최대 길이").pack(side="left")
        ttk.Spinbox(opt, from_=1, to=120, increment=1, width=4,
                    textvariable=self.v_max).pack(side="left", padx=(6, 2))
        ttk.Label(opt, text="분").pack(side="left", padx=(0, 16))
        ttk.Label(opt, text="조용한 곳 찾는 범위").pack(side="left")
        ttk.Spinbox(opt, from_=0, to=120, increment=5, width=4,
                    textvariable=self.v_search).pack(side="left", padx=(6, 2))
        ttk.Label(opt, text="초").pack(side="left", padx=(0, 16))
        opt2 = ttk.Frame(outer)
        opt2.pack(fill="x", pady=(8, 0))
        ttk.Label(opt2, text="영상 파일은").pack(side="left")
        ttk.Radiobutton(opt2, text="영상 그대로 자르기", value=False,
                        variable=self.v_audio).pack(side="left", padx=(8, 0))
        ttk.Radiobutton(opt2, text="소리만 뽑아서 자르기", value=True,
                        variable=self.v_audio).pack(side="left", padx=(8, 16))
        ttk.Checkbutton(opt2, text="'_분할' 폴더에 모아 저장",
                        variable=self.v_sub).pack(side="right")

        # 진행
        self.bar = ttk.Progressbar(outer, mode="determinate", maximum=1.0)
        self.bar.pack(fill="x", pady=(14, 4))
        self.status = ttk.Label(outer, text="파일을 추가하세요.", style="Muted.TLabel")
        self.status.pack(anchor="w")

        # 버튼
        btn = ttk.Frame(outer)
        btn.pack(fill="x", pady=(12, 8))
        self.b_clear = ttk.Button(btn, text="목록 비우기", command=self.clear)
        self.b_clear.pack(side="left")
        self.b_open = ttk.Button(btn, text="결과 폴더 열기", command=self.open_result,
                                 state="disabled")
        self.b_open.pack(side="left", padx=8)
        self.b_start = ttk.Button(btn, text="자르기 시작", style="Accent.TButton",
                                  command=self.start)
        self.b_start.pack(side="right")

        # 로그
        self.log_box = tk.Text(outer, height=7, bg=C_CARD, fg=C_MUTED, relief="flat",
                               font=("Consolas" if os.name == "nt" else "TkFixedFont", 9),
                               highlightthickness=1, highlightbackground=C_LINE,
                               state="disabled", wrap="none")
        self.log_box.pack(fill="both")

        if not self.ffmpeg:
            self.status.config(text="ffmpeg를 찾을 수 없습니다.")
            self.b_start.config(state="disabled")

        self.add_paths(initial)
        root.after(100, self.poll)

    # ----- 파일 추가/삭제 -----
    def pick(self):
        if self.busy:
            return
        exts = " ".join("*" + e for e in sorted(core.MEDIA_EXTS))
        files = filedialog.askopenfilenames(
            title="자를 녹음·영상 파일 선택",
            filetypes=[("녹음·영상 파일", exts), ("모든 파일", "*.*")])
        self.add_paths(files)

    def on_drop(self, event):
        if not self.busy:
            self.add_paths(self.root.tk.splitlist(event.data))

    def add_paths(self, paths):
        have = set(self.items.values())
        for p in paths:
            if os.path.isdir(p):
                sub = [os.path.join(p, f) for f in sorted(os.listdir(p))
                       if os.path.splitext(f)[1].lower() in core.MEDIA_EXTS]
            else:
                sub = [p]
            for f in sub:
                f = os.path.abspath(f)
                if os.path.isfile(f) and f not in have:
                    mb = os.path.getsize(f) / 1024 / 1024
                    iid = self.tree.insert("", "end",
                                           values=(os.path.basename(f), f"대기 · {mb:.0f}MB"))
                    self.items[iid] = f
                    have.add(f)
        if self.items and not self.busy:
            self.status.config(text=f"{len(self.items)}개 파일 준비됨")

    def remove_selected(self):
        if self.busy:
            return
        for iid in self.tree.selection():
            self.tree.delete(iid)
            self.items.pop(iid, None)

    def clear(self):
        if self.busy:
            return
        self.tree.delete(*self.tree.get_children())
        self.items.clear()
        self.bar["value"] = 0
        self.status.config(text="파일을 추가하세요.")

    def open_result(self):
        if self.last_dir and os.path.isdir(self.last_dir):
            open_folder(self.last_dir)

    def load_settings(self):
        try:
            with open(SETTINGS, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def save_settings(self):
        try:
            os.makedirs(os.path.dirname(SETTINGS), exist_ok=True)
            with open(SETTINGS, "w", encoding="utf-8") as f:
                json.dump({"max_min": self.v_max.get(), "search_sec": self.v_search.get(),
                           "subfolder": self.v_sub.get(),
                           "audio_only": self.v_audio.get()}, f)
        except Exception:
            pass

    def log(self, text):
        self.log_box.config(state="normal")
        self.log_box.insert("end", text + "\n")
        self.log_box.see("end")
        self.log_box.config(state="disabled")

    # ----- 실행 -----
    def start(self):
        if self.busy:
            return
        todo = [iid for iid in self.tree.get_children()
                if not self.tree.set(iid, "status").startswith("완료")]
        if not todo:
            messagebox.showinfo(APP_NAME, "자를 파일을 먼저 추가하세요.")
            return
        try:
            max_seg = float(self.v_max.get()) * 60
            search = float(self.v_search.get())
        except (tk.TclError, ValueError):
            messagebox.showerror(APP_NAME, "최대 길이와 찾는 범위에 숫자를 넣어주세요.")
            return
        if max_seg < 60:
            messagebox.showerror(APP_NAME, "최대 길이는 1분 이상이어야 합니다.")
            return
        self.save_settings()
        self.busy = True
        for b in (self.b_start, self.b_clear, self.b_open):
            b.config(state="disabled")
        jobs = [(iid, self.items[iid]) for iid in todo]
        threading.Thread(target=self.worker,
                         args=(jobs, max_seg, search, self.v_sub.get(), self.v_audio.get()),
                         daemon=True).start()

    def worker(self, jobs, max_seg, search, subfolder, audio_only):
        total = len(jobs)
        ok = 0
        for n, (iid, path) in enumerate(jobs):
            self.q.put(("row", iid, "분석 중..."))
            self.q.put(("log", f"▶ {os.path.basename(path)}"))
            t0 = time.time()

            def prog(f, n=n):
                self.q.put(("bar", (n + f) / total))

            try:
                out_dir, count = core.split_file(
                    path, max_seg=max_seg, search=search, subfolder=subfolder,
                    audio_only=audio_only,
                    ffmpeg=self.ffmpeg, log=lambda s: self.q.put(("log", "   " + s)),
                    progress=prog)
                self.q.put(("row", iid, f"완료 · {count}개 ({time.time() - t0:.0f}초)"))
                self.q.put(("dir", out_dir))
                ok += 1
            except Exception as e:
                self.q.put(("row", iid, "실패"))
                self.q.put(("log", f"   ✖ {e}"))
        self.q.put(("done", ok, total))

    def poll(self):
        try:
            while True:
                msg = self.q.get_nowait()
                kind = msg[0]
                if kind == "row":
                    self.tree.set(msg[1], "status", msg[2])
                    self.status.config(text=f"{self.tree.set(msg[1], 'name')} — {msg[2]}")
                elif kind == "log":
                    self.log(msg[1])
                elif kind == "bar":
                    self.bar["value"] = msg[1]
                elif kind == "dir":
                    self.last_dir = msg[1]
                elif kind == "done":
                    ok, total = msg[1], msg[2]
                    self.busy = False
                    self.bar["value"] = 1.0
                    self.b_start.config(state="normal")
                    self.b_clear.config(state="normal")
                    if self.last_dir:
                        self.b_open.config(state="normal")
                    self.status.config(text=f"끝났습니다. 성공 {ok} / {total}")
                    self.log("")
        except queue.Empty:
            pass
        self.root.after(100, self.poll)


def cli(args):
    """자동 테스트용: app --cli [--log 파일] 파일들"""
    log_path = None
    if "--log" in args:
        i = args.index("--log")
        log_path = args[i + 1]
        args = args[:i] + args[i + 2:]
    lines = []

    def log(s):
        lines.append(s)
        if sys.stdout:
            try:
                print(s, flush=True)
            except Exception:
                pass

    log(f"ffmpeg: {core.find_ffmpeg()}")
    code = 0
    for p in [a for a in args if not a.startswith("--")]:
        try:
            ao = "--audio-only" in sys.argv
            d, n = core.split_file(p, log=log, audio_only=ao)
            log(f"OK {n} {d}")
        except Exception as e:
            log(f"FAIL {p}: {e}")
            code = 1
    if log_path:
        with open(log_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
    return code


def main():
    args = sys.argv[1:]
    if args and args[0] == "--cli":
        sys.exit(cli(args[1:]))
    if os.name == "nt":
        try:  # 고해상도 화면에서 글자 흐림 방지
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    root = TkinterDnD.Tk() if HAS_DND else tk.Tk()
    App(root, initial=[a for a in args if os.path.exists(a)])
    root.mainloop()


if __name__ == "__main__":
    main()

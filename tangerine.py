"""
Tangerine for Windows
Hold SHIFT while dragging files -> a tray of format tiles appears -> drop to convert.

Requires: pip install pillow pynput tkinterdnd2 pymupdf
Audio/video need ffmpeg on PATH (winget install Gyan.FFmpeg).
"""
import ctypes
import math
import os
import queue
import shutil
import subprocess
import threading
import tkinter as tk
from pathlib import Path

from pynput import keyboard, mouse
from tkinterdnd2 import DND_FILES, TkinterDnD

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # keep pynput coords == Tk coords
except Exception:
    pass

# ---------------------------------------------------------------- conversion
IMG = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff", ".ico"}
AUD = {".mp3", ".wav", ".flac", ".m4a", ".ogg", ".aac", ".wma"}
VID = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".wmv", ".flv"}
FFMPEG = shutil.which("ffmpeg")

TARGETS = ["PNG", "JPG", "WEBP", "PDF", "MP3", "WAV", "MP4", "GIF"]


def unique(path: Path) -> Path:
    if not path.exists():
        return path
    i = 1
    while True:
        p = path.with_name(f"{path.stem} ({i}){path.suffix}")
        if not p.exists():
            return p
        i += 1


def run_ffmpeg(args):
    if not FFMPEG:
        raise RuntimeError("ffmpeg not found on PATH")
    r = subprocess.run([FFMPEG, "-y", "-loglevel", "error", *args],
                       capture_output=True, text=True,
                       creationflags=0x08000000)  # CREATE_NO_WINDOW
    if r.returncode:
        raise RuntimeError(r.stderr.strip() or "ffmpeg failed")


def convert(src: str, target: str) -> Path:
    s = Path(src)
    ext = s.suffix.lower()
    t = target.lower()
    out = unique(s.with_suffix("." + ("jpg" if t == "jpg" else t)))

    if ext in IMG and t in {"png", "jpg", "webp", "pdf", "gif"}:
        from PIL import Image
        im = Image.open(s)
        if t in {"jpg", "pdf"} and im.mode in ("RGBA", "LA", "P"):
            bg = Image.new("RGB", im.size, "white")
            im = im.convert("RGBA")
            bg.paste(im, mask=im.split()[-1])
            im = bg
        elif t in {"jpg", "pdf"}:
            im = im.convert("RGB")
        im.save(out, {"jpg": "JPEG", "pdf": "PDF"}.get(t, t.upper()))
        return out

    if ext == ".pdf" and t in {"png", "jpg"}:
        import fitz  # pymupdf
        doc = fitz.open(s)
        first = None
        for i, page in enumerate(doc):
            p = out if i == 0 else unique(s.with_name(f"{s.stem}_p{i+1}.{t}"))
            page.get_pixmap(dpi=150).save(p)
            first = first or p
        return first

    if ext in AUD | VID and t in {"mp3", "wav"}:
        run_ffmpeg(["-i", str(s), "-vn", str(out)])
        return out
    if ext in VID and t == "mp4":
        run_ffmpeg(["-i", str(s), "-c:v", "libx264", "-c:a", "aac", str(out)])
        return out
    if ext in VID and t == "gif":
        run_ffmpeg(["-i", str(s), "-vf", "fps=12,scale=480:-1:flags=lanczos", str(out)])
        return out

    raise ValueError(f"{ext or 'file'} -> {target.upper()} not supported")


# ---------------------------------------------------------------- overlay UI
BG, TILE, TILE_HOT, FG, ACCENT = "#1f1f24", "#34343c", "#ff8a1f", "#f2f2f2", "#ff8a1f"


class Overlay:
    def __init__(self):
        self.root = TkinterDnD.Tk()
        self.root.withdraw()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg=BG)
        self.hide_job = None
        self.visible = False

        tk.Label(self.root, text="🍊  Drop to convert", bg=BG, fg=ACCENT,
                 font=("Segoe UI", 10, "bold")).grid(row=0, column=0, columnspan=4,
                                                    padx=10, pady=(8, 4), sticky="w")
        self.tiles = {}
        for i, name in enumerate(TARGETS):
            lbl = tk.Label(self.root, text=name, width=7, height=2, bg=TILE, fg=FG,
                           font=("Segoe UI", 10, "bold"))
            lbl.grid(row=1 + i // 4, column=i % 4, padx=4, pady=4)
            lbl.drop_target_register(DND_FILES)
            lbl.dnd_bind("<<DropEnter>>", lambda e, w=lbl: w.config(bg=TILE_HOT))
            lbl.dnd_bind("<<DropLeave>>", lambda e, w=lbl: w.config(bg=TILE))
            lbl.dnd_bind("<<Drop>>", lambda e, n=name, w=lbl: self.on_drop(e, n, w))
            self.tiles[name] = lbl
        self.status = tk.Label(self.root, text="", bg=BG, fg="#aaaaaa",
                               font=("Segoe UI", 9), anchor="w")
        self.status.grid(row=3, column=0, columnspan=4, padx=10, pady=(0, 8), sticky="we")

        self.root.update_idletasks()
        self._make_noactivate()

    def _make_noactivate(self):
        # Show without stealing focus from Explorer, and hide from Alt-Tab.
        try:
            u = ctypes.windll.user32
            hwnd = u.GetParent(self.root.winfo_id()) or self.root.winfo_id()
            GWL_EXSTYLE = -20
            style = u.GetWindowLongW(hwnd, GWL_EXSTYLE)
            u.SetWindowLongW(hwnd, GWL_EXSTYLE, style | 0x08000000 | 0x00000080)
        except Exception:
            pass

    def show(self, x, y):
        if self.hide_job:
            self.root.after_cancel(self.hide_job)
            self.hide_job = None
        if self.visible:
            return
        self.status.config(text="")
        self.root.update_idletasks()
        w, h = self.root.winfo_reqwidth(), self.root.winfo_reqheight()
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        px = min(max(x + 24, 0), sw - w - 8)
        py = min(max(y + 24, 0), sh - h - 48)
        self.root.geometry(f"+{px}+{py}")
        self.root.deiconify()
        self.root.attributes("-topmost", True)
        self.visible = True

    def hide_later(self, ms=700):
        if self.hide_job:
            self.root.after_cancel(self.hide_job)
        self.hide_job = self.root.after(ms, self.hide)

    def hide(self):
        self.root.withdraw()
        self.visible = False
        self.hide_job = None
        for w in self.tiles.values():
            w.config(bg=TILE)

    def on_drop(self, event, target, widget):
        widget.config(bg=TILE)
        files = [f for f in self.root.tk.splitlist(event.data) if os.path.isfile(f)]
        if not files:
            return
        self.status.config(text=f"Converting {len(files)} file(s) to {target}…")
        self.hide_later(4000)
        threading.Thread(target=self._work, args=(files, target), daemon=True).start()

    def _work(self, files, target):
        ok, errs = 0, []
        for f in files:
            try:
                convert(f, target)
                ok += 1
            except Exception as e:
                errs.append(f"{Path(f).name}: {e}")
        msg = f"Done ✓ {ok} converted" if ok else "Nothing converted"
        if errs:
            msg += f"  •  {errs[0]}"
        self.root.after(0, lambda: (self.status.config(text=msg[:60]), self.hide_later(2500)))


# ---------------------------------------------------------------- global hooks
def main():
    ov = Overlay()
    events = queue.Queue()
    state = {"shift": False, "down": False, "start": (0, 0), "shown": False}

    def on_press_key(k):
        if k in (keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r):
            state["shift"] = True

    def on_release_key(k):
        if k in (keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r):
            state["shift"] = False

    def on_click(x, y, button, pressed):
        if button != mouse.Button.left:
            return
        state["down"] = pressed
        if pressed:
            state["start"], state["shown"] = (x, y), False
        else:
            events.put(("up", x, y))

    def on_move(x, y):
        if state["down"] and state["shift"] and not state["shown"]:
            sx, sy = state["start"]
            if math.hypot(x - sx, y - sy) > 15:  # real drag, not a shift-click
                state["shown"] = True
                events.put(("show", x, y))

    keyboard.Listener(on_press=on_press_key, on_release=on_release_key, daemon=True).start()
    mouse.Listener(on_click=on_click, on_move=on_move, daemon=True).start()

    def pump():
        try:
            while True:
                kind, x, y = events.get_nowait()
                if kind == "show":
                    ov.show(x, y)
                elif kind == "up" and ov.visible:
                    ov.hide_later()
        except queue.Empty:
            pass
        ov.root.after(30, pump)

    pump()
    print("Tangerine running. Hold SHIFT and drag a file. Ctrl+C to quit.")
    ov.root.mainloop()


if __name__ == "__main__":
    main()

# Tangerine for Windows

Hold **Shift** while dragging a file, drop it on a format tile, and it converts next to the original.

## Setup
```
pip install pillow pynput tkinterdnd2 pymupdf
winget install Gyan.FFmpeg      # only needed for audio/video
python tangerine.py             # or pythonw tangerine.py for no console
```

## Build a standalone .exe
```
pip install pyinstaller
pyinstaller --noconsole --onefile --collect-all tkinterdnd2 tangerine.py
```

## Supported conversions
| From | To |
|---|---|
| Images (png, jpg, webp, bmp, gif, tiff, ico) | PNG, JPG, WEBP, PDF, GIF |
| PDF | PNG, JPG (every page) |
| Audio / video | MP3, WAV |
| Video | MP4, GIF |

## Auto-start
Press Win+R, run `shell:startup`, and put a shortcut to `pythonw.exe tangerine.py` there.

## Notes
- Shift-clicking only multi-selects. The tray appears once you move more than about 15px with the button held.
- If it doesn't show over an admin-level window, run Tangerine as admin too.
- Easy to extend: add a branch in `convert()` and a name in `TARGETS`.

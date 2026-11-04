#!/usr/bin/env python3
"""Render a .pptx to PNGs + a contact sheet, so you can look at every slide.

    python3 preview.py deck.pptx [-o out_dir]

Uses LibreOffice (soffice) when present; on macOS falls back to Keynote (90 s timeout).
If neither works, use `meadow_deck.py deck.json --png DIR`, the Pillow renderer of the same layout.
Fonts must be installed for a faithful render (scripts/install_fonts.sh).
"""
import argparse, glob, os, shutil, subprocess, sys
from PIL import Image

def via_soffice(pptx, out):
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        return False
    subprocess.run([soffice, "--headless", "--convert-to", "pdf", "--outdir", out, pptx], check=True, capture_output=True)
    pdf = os.path.join(out, os.path.splitext(os.path.basename(pptx))[0] + ".pdf")
    if shutil.which("pdftoppm"):
        subprocess.run(["pdftoppm", "-png", "-r", "60", pdf, os.path.join(out, "slide")], check=True)
    else:
        import fitz  # PyMuPDF
        for i, page in enumerate(fitz.open(pdf), 1):
            page.get_pixmap(dpi=60).save(os.path.join(out, f"slide-{i:02d}.png"))
    return True

def via_keynote(pptx, out):
    if sys.platform != "darwin" or not os.path.exists("/Applications/Keynote.app"):
        return False
    script = f'''
    tell application "Keynote"
        set d to open POSIX file "{os.path.abspath(pptx)}"
        export d to POSIX file "{os.path.abspath(out)}" as slide images with properties {{image format:PNG, skipped slides:false}}
        close d saving no
    end tell'''
    script = "with timeout of 90 seconds\n" + script + "\nend timeout"
    try:
        subprocess.run(["osascript", "-e", script], check=True, capture_output=True, timeout=120)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        print("Keynote could not render the file (it may be showing a dialog: close it).", file=sys.stderr)
        return False
    return True

def contact_sheet(out):
    files = sorted(f for f in glob.glob(os.path.join(out, "**", "*.png"), recursive=True) if "contact-sheet" not in f)
    if not files:
        return None
    tw, th, cols = 640, 360, 3
    rows = (len(files) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * tw + (cols + 1) * 16, rows * th + (rows + 1) * 16), "#2a2d33")
    for i, f in enumerate(files):
        im = Image.open(f).convert("RGB"); im.thumbnail((tw, th))
        sheet.paste(im, (16 + (i % cols) * (tw + 16), 16 + (i // cols) * (th + 16)))
    p = os.path.join(out, "contact-sheet.png"); sheet.save(p); return p

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("pptx"); ap.add_argument("-o", "--out")
    a = ap.parse_args()
    out = a.out or os.path.splitext(a.pptx)[0] + "-preview"
    os.makedirs(out, exist_ok=True)
    if not (via_soffice(a.pptx, out) or via_keynote(a.pptx, out)):
        sys.exit("No office renderer worked. Use the built-in one instead: meadow_deck.py deck.json --png <dir> (approximate text, exact layout).")
    print("slides:", out); print("contact sheet:", contact_sheet(out))

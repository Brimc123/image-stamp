# processing.py
# Bottom-crop first, then add a natural timestamp (no box, no shadow)

from typing import List, Tuple
import os, zipfile, tempfile
from datetime import datetime, timedelta
from PIL import Image, ImageDraw, ImageFont, ImageOps

# ---------- Font ----------
def _font_path() -> str:
    candidates = [
        r"C:\Windows\Fonts\segoeui.ttf",
        r"C:\Windows\Fonts\arial.ttf",
        r"C:\Windows\Fonts\ARIAL.TTF",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return ""

def _natural_text(ts: datetime) -> str:
    # "27 Aug 2025, 09:03:34 am"
    day = str(int(ts.strftime("%d")))
    month = ts.strftime("%b")
    year = ts.strftime("%Y")
    time_12 = ts.strftime("%I:%M:%S %p").lower()
    return f"{day} {month} {year}, {time_12}"

def parse_times(date_text: str, start_str: str, end_str: str, n: int) -> List[datetime]:
    # parse date dd/mm/yyyy, times as 24h or 12h
    d = datetime.strptime(date_text.strip(), "%d/%m/%Y").date()
    def _parse_time(s: str):
        s = s.strip()
        for fmt in ("%H:%M:%S", "%I:%M:%S %p"):
            try: return datetime.strptime(s, fmt).time()
            except: pass
        raise ValueError("Times must be HH:MM:SS (24h) or 'HH:MM:SS am/pm'")
    t0 = _parse_time(start_str)
    t1 = _parse_time(end_str)
    start = datetime.combine(d, t0)
    end   = datetime.combine(d, t1)
    if n <= 1:
        return [start]
    if end < start:
        # allow wrap to same-day range by adding 24h
        end = end + timedelta(days=1)
    step = (end - start) / (n - 1)
    return [start + i*step for i in range(n)]

def _load_zip(zip_path: str) -> List[str]:
    tmp = tempfile.mkdtemp(prefix="unz_")
    outs = []
    with zipfile.ZipFile(zip_path, "r") as z:
        for name in z.namelist():
            if name.lower().endswith((".jpg", ".jpeg", ".png")):
                dest = os.path.join(tmp, os.path.basename(name))
                with open(dest, "wb") as f:
                    f.write(z.read(name))
                outs.append(dest)
    return sorted(outs)

def _gather_inputs(paths: List[str]) -> List[str]:
    imgs: List[str] = []
    for p in paths:
        lp = p.lower()
        if lp.endswith(".zip"):
            imgs.extend(_load_zip(p))
        elif lp.endswith((".jpg", ".jpeg", ".png")):
            imgs.append(p)
    imgs = sorted(imgs)
    if not imgs:
        raise ValueError("No images found (JPG/PNG or a .zip).")
    return imgs

def _stamp(img: Image.Image, text: str, crop_bottom_px: int, font_px_fixed: int = 52) -> Image.Image:
    # correct EXIF orientation
    im = ImageOps.exif_transpose(img.convert("RGB"))
    w, h = im.size

    # bottom crop first
    c = max(0, min(int(crop_bottom_px), h - 2))
    if c > 0:
        im = im.crop((0, 0, w, h - c))
        w, h = im.size

    draw = ImageDraw.Draw(im)
    try:
        font = ImageFont.truetype(_font_path(), size=font_px_fixed)
    except:
        font = ImageFont.load_default()

    # bottom-right with small margin; clean white text (no box)
    margin = max(16, int(w * 0.02))
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = w - tw - margin
    y = h - th - margin

    draw.text((x, y), text, fill=(255, 255, 255), font=font)
    return im

def process_images_paths(
    input_paths: List[str],
    date_text: str,
    start_str: str,
    end_str: str,
    crop_bottom_px: int,
    out_zip_path: str,
) -> str:
    images = _gather_inputs(input_paths)
    n = len(images)
    stamps = parse_times(date_text, start_str, end_str, n)

    out_dir = tempfile.mkdtemp(prefix="stamped_")
    outs: List[str] = []

    for idx, (src, ts) in enumerate(zip(images, stamps), start=1):
        with Image.open(src) as im:
            im2 = _stamp(im, _natural_text(ts), crop_bottom_px, font_px_fixed=52)
            base = os.path.splitext(os.path.basename(src))[0]
            out_file = os.path.join(out_dir, f"{base}_stamped.jpg")
            im2.save(out_file, "JPEG", quality=92)
            outs.append(out_file)

    with zipfile.ZipFile(out_zip_path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for f in outs:
            z.write(f, arcname=os.path.basename(f))

    return out_zip_path

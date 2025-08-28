import PySimpleGUI as sg
from PIL import Image, ImageDraw, ImageFont, ImageOps
from datetime import datetime, timedelta
import io, os, zipfile, tempfile, shutil, pathlib
import threading

# ---------------- Utilities ----------------

from processing import parse_times, process_images

def load_font(size: int = 30):
    try:
        return ImageFont.truetype("arial.ttf", size)
    except Exception:
        try:
            return ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", size)
        except Exception:
            return ImageFont.load_default()

def parse_times(date_to_use: str, start_time: str, end_time: str):
    fmt = "%H:%M:%S"
    try:
        start_dt = datetime.strptime(start_time.strip(), fmt)
        end_dt = datetime.strptime(end_time.strip(), fmt)
    except Exception:
        raise ValueError("Time format must be HH:MM:SS (e.g., 13:00:00)")
    if end_dt <= start_dt:
        end_dt = end_dt + timedelta(days=1)
    return date_to_use.strip(), start_dt, end_dt

def stamp_image(img: Image.Image, text: str, crop_height: int) -> Image.Image:
    img = ImageOps.exif_transpose(img).copy()
    w, h = img.size
    ch = max(0, min(int(crop_height), h-1))
    cropped = img.crop((0, 0, w, h - ch))

    if cropped.mode != "RGBA":
        cropped = cropped.convert("RGBA")

    font = load_font(30)
    draw = ImageDraw.Draw(cropped)
    bbox = draw.textbbox((0,0), text, font=font)
    tw, th = bbox[2]-bbox[0], bbox[3]-bbox[1]
    x = cropped.size[0] - tw - 16
    y = cropped.size[1] - th - 12

    overlay = Image.new("RGBA", cropped.size, (0,0,0,0))
    od = ImageDraw.Draw(overlay)
    pad = 8
    rect = (x-pad, y-pad, x+tw+pad, y+th+pad)
    od.rectangle(rect, fill=(0,0,0,128))
    stamped = Image.alpha_composite(cropped, overlay)

    d2 = ImageDraw.Draw(stamped)
    d2.text((x, y), text, font=font, fill="white")

    return stamped.convert("RGB")

def iter_images_in_folder(folder: str):
    exts = {".jpg",".jpeg",".png",".JPG",".JPEG",".PNG"}
    for root, _, files in os.walk(folder):
        for name in sorted(files):
            if pathlib.Path(name).suffix in exts:
                yield os.path.join(root, name)

def extract_zip_to_tmp(zip_path: str) -> str:
    tmpdir = tempfile.mkdtemp(prefix="imgzip_")
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(tmpdir)
    return tmpdir

def process_images(paths, date_text, start_dt, end_dt, crop_height, out_zip_path, progress_cb=None, cancel_flag=None):
    # build list of image file paths from input (folder(s) or files)
    image_files = []
    for p in paths:
        p = p.strip('"').strip()
        if not p:
            continue
        if os.path.isdir(p):
            image_files.extend(list(iter_images_in_folder(p)))
        elif os.path.isfile(p) and p.lower().endswith(".zip"):
            tmp = extract_zip_to_tmp(p)
            image_files.extend(list(iter_images_in_folder(tmp)))
        elif os.path.isfile(p) and pathlib.Path(p).suffix.lower() in (".jpg",".jpeg",".png"):
            image_files.append(p)

    if len(image_files) < 2:
        raise ValueError("Please provide at least 2 images. Use a folder, a .zip, or select individual files.")

    total_seconds = (end_dt - start_dt).total_seconds()
    if total_seconds <= 0:
        raise ValueError("End time must be after start time (or next day).")
    interval = total_seconds / (len(image_files) - 1)

    done = 0
    with zipfile.ZipFile(out_zip_path, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for idx, path in enumerate(image_files):
            if cancel_flag and cancel_flag["cancelled"]:
                break
            with Image.open(path) as img:
                ts = start_dt + timedelta(seconds=interval * idx)
                text = f"{date_text}, {ts.strftime('%H:%M:%S')}"
                stamped = stamp_image(img, text, crop_height)
                ext = pathlib.Path(path).suffix.lower()
                ext = ".png" if ext == ".png" else ".jpg"
                name = f"{idx+1:03d}{ext}"
                buff = io.BytesIO()
                if ext == ".png":
                    stamped.save(buff, format="PNG", optimize=True)
                else:
                    stamped.save(buff, format="JPEG", quality=90, optimize=True)
                zf.writestr(name, buff.getvalue())
            done += 1
            if progress_cb:
                progress_cb(done, len(image_files))

    return out_zip_path

# ---------------- GUI ----------------

sg.theme("SystemDefault")

drop_help = (
    "Drag a folder, a .zip, or individual image files into this box,\n"
    "or click the buttons below to browse."
)

layout = [
    [sg.Text("Image Re-Dating Tool", font=("Segoe UI", 14, "bold"))],
    [sg.Text("Input (Folder / .zip / files)"),],
    [sg.Multiline(size=(80,5), key="-INPUTS-", enable_events=True, right_click_menu=["", ["Clear"]],
                  tooltip=drop_help, autoscroll=True, reroute_cprint=True, write_only=False, expand_x=True, expand_y=False, no_scrollbar=False)],
    [sg.Button("Browse Folder"), sg.Button("Browse ZIP"), sg.Button("Browse Files")],
    [sg.Frame("Settings", [
        [sg.Text("Date to use"), sg.Input(key="-DATE-", size=(25,1), default_text="30 May 2025")],
        [sg.Text("Start time (HH:MM:SS)"), sg.Input(key="-START-", size=(15,1), default_text="13:00:00"),
         sg.Text("End time (HH:MM:SS)"), sg.Input(key="-END-", size=(15,1), default_text="15:00:00")],
        [sg.Text("Crop height (px from bottom)"), sg.Input(key="-CROP-", size=(6,1), default_text="60")],
        [sg.Text("Output folder"), sg.Input(key="-OUTDIR-", size=(50,1), default_text=str(pathlib.Path.home() / "Desktop")), sg.FolderBrowse("Browse")],
    ])],
    [sg.ProgressBar(max_value=100, orientation="h", size=(45,20), key="-PROG-"), sg.Text("", key="-STATUS-", size=(30,1))],
    [sg.Button("Process", bind_return_key=True), sg.Button("Cancel"), sg.Button("Quit")],
    [sg.Text("Tip: You can paste paths into the input box. One path per line.", text_color="gray")],
]

window = sg.Window("Image Re-Dating (Crop + Timestamp)", layout, finalize=True)
window["-INPUTS-"].Widget.drop_target_register("*")
window["-INPUTS-"].Widget.dnd_bind("<<Drop>>", lambda e: window.write_event_value("-DROPPED-", e.data))

cancel_flag = {"cancelled": False}

def start_processing(values):
    inputs_raw = values["-INPUTS-"].strip()
    paths = [p for p in inputs_raw.splitlines() if p.strip()]
    outdir = values["-OUTDIR-"].strip() or str(pathlib.Path.home() / "Desktop")
    os.makedirs(outdir, exist_ok=True)
    out_zip = os.path.join(outdir, "processed_images.zip")

    try:
        crop = int(values["-CROP-"].strip())
    except Exception:
        sg.popup_error("Crop height must be a whole number (pixels).")
        return

    try:
        date_text, start_dt, end_dt = parse_times(values["-DATE-"], values["-START-"], values["-END-"])
    except Exception as e:
        sg.popup_error(str(e))
        return

    cancel_flag["cancelled"] = False
    window["-PROG-"].update(0)
    window["-STATUS-"].update("Working...")

    def on_progress(done, total):
        pct = int(done * 100 / max(1, total))
        window["-PROG-"].update(pct)
        window["-STATUS-"].update(f"{done}/{total}")

    def worker():
        try:
            process_images(paths, date_text, start_dt, end_dt, crop, out_zip, on_progress, cancel_flag)
            if not cancel_flag["cancelled"]:
                window.write_event_value("-DONE-", out_zip)
        except Exception as e:
            window.write_event_value("-ERROR-", str(e))

    threading.Thread(target=worker, daemon=True).start()

while True:
    event, values = window.read()
    if event in (sg.WINDOW_CLOSED, "Quit"):
        break

    if event == "Browse Folder":
        folder = sg.popup_get_folder("Pick a folder with images")
        if folder:
            existing = values["-INPUTS-"].strip()
            new = f"{existing}\n{folder}" if existing else folder
            window["-INPUTS-"].update(new)

    elif event == "Browse ZIP":
        zp = sg.popup_get_file("Pick a .zip of images", file_types=(("ZIP", "*.zip"),))
        if zp:
            existing = values["-INPUTS-"].strip()
            new = f"{existing}\n{zp}" if existing else zp
            window["-INPUTS-"].update(new)

    elif event == "Browse Files":
        files = sg.popup_get_file("Pick image files", multiple_files=True, file_types=(("Images", "*.png;*.jpg;*.jpeg"),))
        if files:
            # PySimpleGUI returns a ";"-separated list sometimes
            paths = files if isinstance(files, list) else files.split(";")
            existing = values["-INPUTS-"].strip()
            for p in paths:
                p = p.strip()
                if not p:
                    continue
                existing = f"{existing}\n{p}" if existing else p
            window["-INPUTS-"].update(existing)

    elif event == "-DROPPED-":
        data = values.get("-INPUTS-")
        dropped = values.get("-DROPPED-", "")
        # tk drops paths in a space-separated string with braces; normalize
        # e.g. {C:\My Folder}\file.jpg {C:\Another\File.png}
        tokens = []
        token = ""
        in_brace = False
        for ch in dropped:
            if ch == "{":
                in_brace = True
                token = ""
            elif ch == "}":
                in_brace = False
                tokens.append(token)
                token = ""
            elif ch == " " and not in_brace:
                if token:
                    tokens.append(token)
                    token = ""
            else:
                token += ch
        if token:
            tokens.append(token)
        existing = values["-INPUTS-"].strip()
        for p in tokens:
            existing = f"{existing}\n{p}" if existing else p
        window["-INPUTS-"].update(existing)

    elif event == "Process":
        start_processing(values)

    elif event == "Cancel":
        cancel_flag["cancelled"] = True
        window["-STATUS-"].update("Cancelling...")

    elif event == "-DONE-":
        out_zip = values["-DONE-"]
        window["-STATUS-"].update(f"Done: {out_zip}")
        sg.popup_ok(f"Finished!\nSaved to:\n{out_zip}")

    elif event == "-ERROR-":
        sg.popup_error(values["-ERROR-"])

window.close()

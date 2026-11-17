#!/usr/bin/env python3
"""Make a team headshot that matches the others: same head-and-shoulders framing, same grey backdrop.

    python3 tools/headshot.py path/to/photo.jpg firstname-lastname

Writes public/assets/img/<slug>-4x5-800.webp and -480.webp.
Needs: pip install "rembg[cpu]" opencv-python-headless pymatting
and OpenCV's haarcascade_frontalface_default.xml (set FACE_XML if cv2.data doesn't include it).
Check the result by eye: the cut-out model can miss hair or keep bits of furniture.
"""
import os, sys, pathlib
import numpy as np, cv2
from PIL import Image, ImageOps, ImageFilter
from rembg import new_session, remove
from pymatting import estimate_foreground_ml

FACE_FRAC, CENTER_Y = 0.42, 0.36            # face width as a share of the frame; face centre height
INNER, OUTER = (242, 241, 239), (218, 216, 212)  # backdrop: light warm grey, slightly darker at the edges
OUT = pathlib.Path(__file__).resolve().parent.parent / "public/assets/img"


def face_box(im):
    xml = os.environ.get("FACE_XML") or os.path.join(getattr(cv2, "data", None) and cv2.data.haarcascades or "", "haarcascade_frontalface_default.xml")
    faces = cv2.CascadeClassifier(xml).detectMultiScale(np.array(im.convert("L")), 1.08, 8, minSize=(100, 100))
    if len(faces) == 0:
        sys.exit("No face found. Try a clearer, front-on photo.")
    x, y, w, _ = max(faces.tolist(), key=lambda f: f[2])
    return x, y, w


def backdrop(w, h):
    y, x = np.mgrid[0:h, 0:w]
    d = np.sqrt(((x - w * .5) / (w * .75)) ** 2 + ((y - h * .38) / (h * .75)) ** 2).clip(0, 1) ** 1.6
    return (np.array(INNER) * (1 - d[..., None]) + np.array(OUTER) * d[..., None]) / 255


def main(src, slug):
    im = ImageOps.exif_transpose(Image.open(src)).convert("RGB")
    fx, fy, fs = face_box(im)
    W = min(fs / FACE_FRAC, im.width); H = W * 1.25
    cx, cy = fx + fs / 2, fy + fs / 2
    left = min(max(cx - W / 2, 0), im.width - W); top = cy - CENTER_Y * H
    box = [round(v) for v in (left, top, left + W, top + H)]
    # The frame may reach above the photo; that strip is background and gets replaced anyway.
    off = max(-box[1], 0); bottom = min(box[3], im.height)
    canvas = Image.new("RGB", (box[2] - box[0], box[3] - box[1]))
    canvas.paste(im.crop((box[0], max(box[1], 0), box[2], bottom)), (0, off))
    inside = np.zeros((canvas.height, canvas.width)); inside[off:off + bottom - max(box[1], 0)] = 1
    # Fine edges (hair) from the cropped frame...
    alpha = np.asarray(remove(canvas, session=new_session("isnet-general-use"), only_mask=True)) / 255
    # ...plus a person-only mask from the whole photo, which keeps shoulders a tight crop can lose
    # and leaves out furniture. Shrunk a little so it never adds a halo at the edges.
    person = remove(im, session=new_session("u2net_human_seg"), only_mask=True)
    body = Image.new("L", canvas.size, 0); body.paste(person.crop((box[0], max(box[1], 0), box[2], bottom)), (0, off))
    body = body.filter(ImageFilter.MinFilter(2 * max(1, canvas.width // 120) + 1))
    alpha = np.maximum(alpha, np.asarray(body) / 255) * inside
    src_arr = np.asarray(canvas) / 255
    fg = estimate_foreground_ml(src_arr, alpha)
    out = fg * alpha[..., None] + backdrop(canvas.width, canvas.height) * (1 - alpha[..., None])
    result = Image.fromarray((np.clip(out, 0, 1) * 255).astype("uint8"))
    for w in (800, 480):
        path = OUT / f"{slug}-4x5-{w}.webp"
        result.resize((w, w * 5 // 4), Image.LANCZOS).save(path, "WEBP", quality=82, method=6)
        print(path)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])

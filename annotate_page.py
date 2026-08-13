"""
Annotates the page with the computed answer and pushes it back to the tablet.

Flow:
  1. Take the vector SVG of the page (produced by fetch_page).
  2. The answer goes in a full-width band at the bottom of the page.
  3. Render the answer (text or the graph image) and inject it into the
     SVG as an <image> element in that band, so the original handwriting
     stays vector.
  4. Export the annotated page as PNG (preview) and PDF.
  5. Push the PDF onto the tablet over SSH: copy it into xochitl's
     document dir with the UUID/.metadata/.content scaffolding it needs,
     then restart xochitl so the tablet picks it up (shows up in
     "My files" under RESULTS_DOC_NAME).

The on-device step follows the well-known pdf2remarkable recipe
(github.com/adaerr/reMarkableScripts) and works on current firmware
(verified against Paper Pro / 3.14+, and the user's own 2026 firmware
.metadata format).

Note: this round-trips the page through PDF, so the copy on the tablet
is a static PDF (the handwriting + answer are baked in, not editable).
That's the tradeoff for a clean, robust on-device answer.
"""

import base64
import json
import os
import shutil
import subprocess
import tempfile
import time
import uuid as uuidlib
import xml.etree.ElementTree as ET

import cairosvg
import matplotlib

from config import (
    PUSH_RESULTS_TO_TABLET,
    RESULTS_DIR,
    RESULTS_DOC_NAME,
    RM_HOST,
    RM_USER,
    RM_XOCHITL_PATH,
    SCP_COMMAND_TIMEOUT_SECONDS,
)
from fetch_page import _ssh

SVG_NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NS)  # keep the output free of ns0: prefixes

_FONT_PATH = os.path.join(matplotlib.get_data_path(), "fonts", "ttf", "DejaVuSans.ttf")

# Layout constants (all fractions of the page)
_MARGIN = 0.02    # keep clear of the page edge
_MAX_BOX_H = 0.6  # max height of the answer band at the bottom of the page


# ---------------------------------------------------------------------------
# Answer image rendering
# ---------------------------------------------------------------------------

def _wrap_lines(text: str, font, max_w: float) -> list:
    from PIL import Image, ImageDraw

    draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    out = []
    for para in text.split("\n"):
        if para == "":
            out.append("")
            continue
        cur = ""
        for word in para.split(" "):
            trial = (cur + " " + word).strip()
            if draw.textlength(trial, font=font) <= max_w:
                cur = trial
            else:
                if cur:
                    out.append(cur)
                cur = word
        out.append(cur)
    return out


def _render_text_image(text: str, px_w: int, px_h_max: int, out_path: str) -> tuple:
    """Render wrapped text to a white PNG up to (px_w, px_h_max), trimmed
    to its content. Returns (path, used_height_px)."""
    from PIL import Image, ImageDraw, ImageFont

    pad = max(8, px_w // 30)
    max_text_w = px_w - 2 * pad

    font_size = 34
    wrapped = []
    used = 10
    for _ in range(40):
        try:
            font = ImageFont.truetype(_FONT_PATH, font_size)
        except OSError:
            font = ImageFont.load_default()
            break
        wrapped = _wrap_lines(text, font, max_text_w)
        used = len(wrapped) * int(font_size * 1.35) + 2 * pad
        if used <= px_h_max or font_size <= 12:
            break
        font_size = max(12, int(font_size * px_h_max / used))

    img = Image.new("RGB", (px_w, used), "white")
    draw = ImageDraw.Draw(img)
    line_h = int(font_size * 1.35)
    total_h = len(wrapped) * line_h
    y = (used - total_h) // 2
    for line in wrapped:
        draw.text((pad, y), line, font=font, fill="black")
        y += line_h

    bbox = img.getbbox()  # trim the canvas to the actual text
    if bbox:
        img = img.crop(bbox)
    img.save(out_path)
    return out_path, img.height


# ---------------------------------------------------------------------------
# Placement (all in normalized page coordinates, y down)
# ---------------------------------------------------------------------------

def _compute_placement() -> tuple:
    """The answer always goes in a full-width band at the bottom of the page."""
    return (_MARGIN, 1.0 - _MARGIN - _MAX_BOX_H, 1.0 - _MARGIN, 1.0 - _MARGIN)


def annotate_page(svg_path: str, bbox: list, answer_text: str,
                  answer_image_path: str | None = None,
                  out_base: str | None = None) -> dict:
    """Inject the answer into the page SVG, export annotated PNG + PDF.

    Returns {"svg": ..., "png": ..., "pdf": ...} paths.
    """
    if out_base is None:
        out_base = os.path.join(RESULTS_DIR, "annotated_page")
    out_svg = out_base + ".svg"
    out_png = out_base + ".png"
    out_pdf = out_base + ".pdf"

    tree = ET.parse(svg_path)
    root = tree.getroot()
    vb = root.get("viewBox")
    if vb is None:
        raise ValueError(f"SVG {svg_path} has no viewBox")
    min_x, min_y, vb_w, vb_h = (float(v) for v in vb.split())

    # Fixed placement: full-width band at the bottom of the page
    box = _compute_placement()
    box_w = box[2] - box[0]
    box_h = box[3] - box[1]
    assert box_w > 0 and box_h > 0

    # Decide what to embed: the graph PNG (kept at its own aspect ratio,
    # centered in the box) or a freshly rendered text image (fills the box).
    embed_png = answer_image_path
    if embed_png and not os.path.exists(embed_png):
        embed_png = None
    if embed_png:
        from PIL import Image as PILImage
        with PILImage.open(embed_png) as im:
            img_aspect = im.width / im.height
        box_aspect = box_w / box_h
        if img_aspect > box_aspect:  # image is wider than the box
            new_w, new_h = box_w, box_w / img_aspect
        else:
            new_h, new_w = box_h, box_h * img_aspect
        x0 = box[0] + (box_w - new_w) / 2
        y0 = box[1] + (box_h - new_h) / 2
        box = (x0, y0, x0 + new_w, y0 + new_h)
    else:
        # Render the text at a width that matches the box, then shrink the
        # box's height so it hugs the text instead of a big empty frame.
        px_w = max(180, min(560, int(box_w * 900)))
        px_h_max = max(120, int(min(box_h, _MAX_BOX_H) * 900))
        embed_png, used_h = _render_text_image(
            answer_text or "(no answer)",
            px_w, px_h_max,
            os.path.join(RESULTS_DIR, "_answer_text.png"),
        )
        new_h = min(box_h, used_h * (box_w / px_w))
        y0 = box[1] + (box_h - new_h)  # flush to the bottom of the band
        box = (box[0], y0, box[0] + box_w, y0 + new_h)

    # Map the normalized box into the SVG's user coordinate system
    x = min_x + box[0] * vb_w
    y = min_y + box[1] * vb_h
    w = (box[2] - box[0]) * vb_w
    h = (box[3] - box[1]) * vb_h

    with open(embed_png, "rb") as f:
        data_uri = "data:image/png;base64," + base64.b64encode(f.read()).decode("ascii")
    if embed_png != answer_image_path and os.path.exists(embed_png):
        os.remove(embed_png)  # drop the temporary text-render PNG

    # White background so handwriting strokes don't show through the answer,
    # plus a thin border so the answer region reads as a distinct box.
    bg = ET.SubElement(root, f"{{{SVG_NS}}}rect")
    bg.set("x", str(x))
    bg.set("y", str(y))
    bg.set("width", str(w))
    bg.set("height", str(h))
    bg.set("fill", "rgb(255,255,255)")

    border = ET.SubElement(root, f"{{{SVG_NS}}}rect")
    border.set("x", str(x))
    border.set("y", str(y))
    border.set("width", str(w))
    border.set("height", str(h))
    border.set("fill", "none")
    border.set("stroke", "rgb(150,150,150)")
    border.set("stroke-width", "1.0")

    img_el = ET.SubElement(root, f"{{{SVG_NS}}}image")
    img_el.set("x", str(x))
    img_el.set("y", str(y))
    img_el.set("width", str(w))
    img_el.set("height", str(h))
    img_el.set("href", data_uri)
    img_el.set("preserveAspectRatio", "xMidYMid meet")

    tree.write(out_svg, encoding="unicode", xml_declaration=True)

    cairosvg.svg2png(url=out_svg, write_to=out_png, dpi=150)
    cairosvg.svg2pdf(url=out_svg, write_to=out_pdf)

    return {"svg": out_svg, "png": out_png, "pdf": out_pdf}


# ---------------------------------------------------------------------------
# Push the annotated PDF back onto the tablet
# ---------------------------------------------------------------------------

def _scp_put(local_path: str, remote_path: str):
    result = subprocess.run(
        ["scp", "-r", local_path, f"{RM_USER}@{RM_HOST}:{remote_path}"],
        capture_output=True, text=True, timeout=SCP_COMMAND_TIMEOUT_SECONDS,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"SCP failed (exit {result.returncode}): {local_path} -> {remote_path}\n"
            f"stderr: {result.stderr.strip()}"
        )


def push_pdf_to_tablet(pdf_path: str, doc_name: str, restart: bool = True) -> str:
    """Copy the PDF into xochitl's dir with the scaffolding the tablet
    needs, then restart xochitl so it shows up in \"My files\".

    Returns the document UUID.
    """
    doc_uuid = str(uuidlib.uuid4())
    tmp = tempfile.mkdtemp(prefix="rm_result_")
    try:
        shutil.copy(pdf_path, os.path.join(tmp, f"{doc_uuid}.pdf"))

        now_ms = str(int(time.time() * 1000))
        metadata = {
            "deleted": False,
            "lastModified": now_ms,
            "metadatamodified": False,
            "modified": False,
            "parent": "",
            "pinned": False,
            "synced": False,
            "type": "DocumentType",
            "version": 1,
            "visibleName": doc_name,
        }
        with open(os.path.join(tmp, f"{doc_uuid}.metadata"), "w") as f:
            json.dump(metadata, f)

        content = {
            "extraMetadata": {},
            "fileType": "pdf",
            "fontName": "",
            "lastOpenedPage": 0,
            "lineHeight": -1,
            "margins": 100,
            "pageCount": 1,
            "textScale": 1,
            "transform": {
                "m11": 1, "m12": 1, "m13": 1,
                "m21": 1, "m22": 1, "m23": 1,
                "m31": 1, "m32": 1, "m33": 1,
            },
        }
        with open(os.path.join(tmp, f"{doc_uuid}.content"), "w") as f:
            json.dump(content, f)

        for suffix in (".cache", ".highlights", ".thumbnails"):
            os.makedirs(os.path.join(tmp, doc_uuid + suffix), exist_ok=True)

        for entry in os.listdir(tmp):
            _scp_put(os.path.join(tmp, entry), f"{RM_XOCHITL_PATH}/{entry}")

        if restart:
            _ssh("systemctl restart xochitl")
        return doc_uuid
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def annotate_and_push(svg_path: str, bbox: list, answer_text: str,
                      answer_image_path: str | None = None,
                      out_base: str | None = None,
                      doc_name: str | None = None) -> dict:
    """Annotate the page with the answer and push it back to the tablet.

    Returns {"svg": ..., "png": ..., "pdf": ..., "doc_uuid": uuid|None}.
    """
    out = annotate_page(svg_path, bbox, answer_text, answer_image_path, out_base)
    out["doc_uuid"] = None
    if PUSH_RESULTS_TO_TABLET:
        out["doc_uuid"] = push_pdf_to_tablet(out["pdf"], doc_name or RESULTS_DOC_NAME)
    return out


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 4:
        print("Usage: python annotate_page.py <page.svg> <x0,y0,x1,y1> <answer text> [answer_image.png]")
        sys.exit(1)
    bbox = [float(v) for v in sys.argv[2].split(",")]
    result = annotate_and_push(sys.argv[1], bbox, sys.argv[3],
                               sys.argv[4] if len(sys.argv) > 4 else None)
    print(result)

"""
Pulls the CURRENT page off the reMarkable and turns it into a PNG we can
feed to Gemini.

Flow:
  1. SSH in, find the most recently modified .metadata file -> that's our
     "active" notebook (the one you're currently writing in).
  2. scp down just that notebook's .content file to read its page list.
  3. Identify the current page: prefer cPages.lastOpened.value (the page
     that was actually open), falling back to the last page in reading
     order if that's missing.
  4. scp down just that one page's .rm file (much lighter than pulling
     the whole notebook).
  5. Convert it to PDF with the `rmc` CLI tool (handles the newer v6 .rm
     format that rmrl does NOT support).
  6. Rasterize that single-page PDF to PNG with PyMuPDF.

This replaced an earlier rmrl-based version: rmrl (last released 2021)
only supports the old v3/v5 .rm stroke format. Newer reMarkable firmware
writes v6, which rmrl silently mishandles (it ends up thinking the
notebook has 0 pages). rmc + rmscene are the actively maintained tools
for v6.
"""

import subprocess
import os
import json

import cairosvg

from config import RM_HOST, RM_USER, RM_XOCHITL_PATH, PAGES_DIR


def _ssh(cmd: str) -> str:
    result = subprocess.run(
        ["ssh", f"{RM_USER}@{RM_HOST}", cmd],
        capture_output=True, text=True, check=True,
    )
    return result.stdout


def _scp(remote_path: str, local_path: str):
    subprocess.run(
        ["scp", f"{RM_USER}@{RM_HOST}:{remote_path}", local_path],
        check=True, capture_output=True,
    )


def find_most_recent_notebook_uuid() -> str:
    """Ask the tablet which notebook's .metadata file was modified last."""
    out = _ssh(f"ls -t {RM_XOCHITL_PATH}/*.metadata | head -n 1")
    metadata_path = out.strip()
    uuid = os.path.basename(metadata_path).replace(".metadata", "")
    return uuid


def _sorted_page_ids(content_data: dict) -> list:
    """Return page ids in reading order from a (possibly nested) .content file."""
    if "pages" in content_data:
        return content_data["pages"]  # old flat format
    cpages = content_data.get("cPages", {}).get("pages", [])
    ordered = sorted(cpages, key=lambda p: p.get("idx", {}).get("value", ""))
    return [p["id"] for p in ordered if "id" in p and not p.get("deleted")]


def get_current_page_id(local_dir: str, uuid: str) -> str:
    """Figure out which page is the one you were actually just writing on."""
    content_file = os.path.join(local_dir, f"{uuid}.content")
    with open(content_file) as f:
        content_data = json.load(f)

    last_opened = content_data.get("cPages", {}).get("lastOpened", {}).get("value")
    if last_opened:
        return last_opened

    # Fall back to the last page in reading order
    page_ids = _sorted_page_ids(content_data)
    if not page_ids:
        raise ValueError(f"No pages found in {content_file}")
    return page_ids[-1]


def pull_content_file(uuid: str) -> str:
    """scp down just the .content file so we can figure out the current page."""
    local_dir = os.path.join(PAGES_DIR, uuid)
    os.makedirs(local_dir, exist_ok=True)
    _scp(f"{RM_XOCHITL_PATH}/{uuid}.content", os.path.join(local_dir, f"{uuid}.content"))
    return local_dir


def pull_page_rm_file(uuid: str, page_id: str, local_dir: str) -> str:
    """scp down just the one .rm file for the current page."""
    local_rm_path = os.path.join(local_dir, f"{page_id}.rm")
    _scp(f"{RM_XOCHITL_PATH}/{uuid}/{page_id}.rm", local_rm_path)
    return local_rm_path


def convert_rm_to_png(rm_path: str) -> str:
    """rm -> svg (via the rmc CLI, which understands v6) -> png (via cairosvg).

    We go through SVG rather than PDF because rmc's PDF output secretly
    shells out to Inkscape, which often isn't installed -- it then fails
    silently and writes a 0-byte file. SVG output doesn't have that
    dependency, and cairosvg (pure Python) handles the PNG rasterization.
    """
    base, _ = os.path.splitext(rm_path)  # only strips the trailing ".rm"
    svg_path = base + ".svg"

    result = subprocess.run(
        ["rmc", "-t", "svg", "-o", svg_path, rm_path],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"rmc failed:\nstdout: {result.stdout}\nstderr: {result.stderr}")
    if not os.path.exists(svg_path) or os.path.getsize(svg_path) == 0:
        raise RuntimeError(f"rmc produced no SVG output.\nstdout: {result.stdout}\nstderr: {result.stderr}")

    png_path = base + ".png"
    cairosvg.svg2png(url=svg_path, write_to=png_path, dpi=200)

    return png_path


def get_latest_page_image() -> dict:
    """Convenience wrapper: find the active notebook + current page, and rasterize it."""
    uuid = find_most_recent_notebook_uuid()
    local_dir = pull_content_file(uuid)
    page_id = get_current_page_id(local_dir, uuid)
    rm_path = pull_page_rm_file(uuid, page_id, local_dir)
    png_path = convert_rm_to_png(rm_path)

    return {
        "uuid": uuid,
        "page_id": page_id,
        "local_dir": local_dir,
        "png_path": png_path,
    }


if __name__ == "__main__":
    info = get_latest_page_image()
    print(f"Notebook {info['uuid']}, page {info['page_id']}")
    print(f"Page image: {info['png_path']}")
    
# reMarkable Math & Code Pipeline

Write a math expression or a snippet of code by hand on your reMarkable
tablet. This pipeline pulls that page, figures out what you wrote, and
either graphs/solves the math or runs the code — inspired by
[derivenotes.com](https://derivenotes.com), built as a self-hosted,
open pipeline instead of a closed app.

## What it does

1. **Pulls the page you're currently writing on** from your reMarkable
   over SSH (USB or wifi)
2. **Sends it to Groq** (running Qwen, a vision-capable model), which
   classifies the handwriting as math or code and transcribes it (LaTeX
   for math, source for code)
3. **Routes it**:
   - Math → parsed with `sympy`, then either solved algebraically or
     graphed with `matplotlib`
   - Code → run in a sandboxed Python subprocess, output captured
4. Prints the result to your terminal (see **Current limitations** below
   for what's not built yet)

## How it works under the hood

```
reMarkable tablet (SSH)
        │  pulls current page's .rm file
        ▼
   rmc + rmscene            (converts reMarkable's v6 stroke format → SVG)
        │
        ▼
    cairosvg                (SVG → PNG)
        │
        ▼
   Groq API (Qwen, vision)  (classifies + transcribes: math or code)
        │
   ┌────┴────┐
   ▼         ▼
sympy      subprocess
+ matplotlib   (sandboxed Python execution)
   │         │
   ▼         ▼
 graph      output
```

## Setup

```bash
git clone https://github.com/AliA749/remarkable_new.git
cd remarkable_new
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and add your own Groq API key (get one free at
[Groq Console](https://console.groq.com/keys)). Adjust `RM_HOST`
if your tablet isn't at the default USB IP.

For passwordless SSH to your tablet (so you're not typing your tablet's
password on every run):
```bash
ssh-copy-id root@10.11.99.1
```

## Usage

**One-shot (manual trigger):**
1. Write a math expression or a short Python snippet on your reMarkable
2. Run:
   ```bash
   python3 main.py
   ```
3. Check the terminal — math results print a solve/simplify result or
   save a graph PNG; code results print stdout/stderr

**Auto-watch over WiFi (no cable needed):**
1. Connect your tablet to WiFi, then find its WiFi IP: on the tablet,
   **Settings → Help → About → Copyright and licenses** — look for the
   IP address listed there (separate from the USB one)
2. Put that IP in `.env` as `RM_HOST`
3. Run:
   ```bash
   python3 watch.py
   ```
   and leave it running in the background
4. Write on your tablet. To have it act on something, draw a box or
   circle around it, with a checkmark (✓) or star (★/*) right next to
   it. The watcher waits until you've paused writing (~20s of no edits
   by default), then checks for that marker and runs the pipeline only
   if it's there — so it won't fire on every stroke.

## Current limitations

This is an early, working MVP, not a polished tool. Known gaps:

- **`watch.py`'s "settled" detection is time-based, not truly live** —
  reMarkable has no push-notification hook for page changes, so it's
  short-interval polling (checks every ~10s, acts after ~20s of no edits).
- **Results only go to your terminal / a local PNG** — nothing gets
  written back onto the tablet yet. That's the next planned feature:
  rendering the answer back near the source handwriting.
- **Code execution is Python-only**, run in a subprocess with an 8-second
  timeout — not a hardened sandbox. Fine for your own snippets; don't
  point this at untrusted input.
- **Math handling is single-variable only** — solves/graphs functions of
  one variable. Multi-variable and implicit equations (e.g. `x^2+y^2=1`)
  aren't supported yet.
- **Depends on the vision model's OCR accuracy** — messy handwriting,
  especially for code, may transcribe incorrectly. The response includes a
  `notes` field flagging anything the model was unsure about. Trigger-marker
  detection (box/circle + checkmark or star) is more reliable now that the
  model is forced to describe the annotation explicitly before deciding
  (see `annotation_description` in `ocr_gemini.py`), but watch for false
  negatives if your handwriting naturally includes similar shapes.

## Credits

- [rmc](https://github.com/ricklupton/rmc) / [rmscene](https://github.com/ricklupton/rmscene)
  by Rick Lupton — actively maintained tools for reading reMarkable's v6
  `.rm` stroke format. (Note: this project originally used
  [rmrl](https://github.com/rschroll/rmrl), but rmrl only supports the
  older v3/v5 format and doesn't work with current reMarkable firmware.)
- [Groq](https://groq.com/) running [Qwen](https://qwen.ai/) (vision) for handwriting OCR/classification
- [sympy](https://www.sympy.org/) and [matplotlib](https://matplotlib.org/) for math parsing and graphing
- Inspired by [derivenotes.com](https://derivenotes.com)

## License

MIT — see [LICENSE](LICENSE).

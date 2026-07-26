# reMarkable Math/Code Pipeline

Custom pipeline inspired by derivenotes.com: pull a handwritten page off the
reMarkable, have Gemini OCR/classify it as math or code, then graph/solve
the math or run the code.

## Done

- `config.py` — env-based config (tablet SSH details, Gemini key), auto-loads `.env`
- `fetch_page.py` — finds the notebook you last touched, identifies the
  *current* page via `cPages.lastOpened`, pulls just that page's `.rm` file,
  converts it to PNG (rmc -> svg -> cairosvg, NOT rmrl -> pdf, see below)
- `ocr_gemini.py` — sends the page PNG to Gemini, gets back structured JSON:
  `{type: math|code|unclear, content, language, notes}`
- `math_engine.py` — parses LaTeX with sympy, decides solve vs. plot vs.
  simplify, renders graphs with matplotlib
- `code_engine.py` — runs Python snippets in a subprocess sandbox (8s
  timeout, output capped)
- `main.py` — orchestrates all of the above, one-shot manual trigger

### Key bugs solved along the way (don't re-hit these)
- `rmrl` (last released 2021) does NOT support the newer v6 `.rm` stroke
  format your firmware writes — it silently thinks the notebook has 0
  pages, which cascades into an `UnboundLocalError` on `apply_ocg` deep in
  its PDF-merge code. Fixed by switching to `rmc`/`rmscene`, which are
  actively maintained for v6.
- `rmc`'s PDF output secretly shells out to Inkscape; if that's not
  installed it fails silently and writes a 0-byte file. Fixed by going
  `.rm -> .svg -> .png` (via `cairosvg`, pure Python) instead of through PDF.
- `setuptools>=82` removed `pkg_resources` entirely, which some deps still
  import — only relevant if you bring `rmrl` back for something.
- WSL: doing pip installs or file copies on `/mnt/c/...` (Windows drive) is
  drastically slower than native `~/` (ext4) due to the drvfs translation
  layer. Project now lives at `~/projects/remarkable_new`.

## Understood
- reMarkable has no live/push hook for page changes — anything "live" here
  is short-interval polling, not truly instant.
- `.content` file structure varies by firmware version (`cPages.pages`
  nested format vs. old flat `pages` list) — code handles both.
- `cPages.lastOpened.value` is the reliable way to get "the page you were
  just writing on," more precise than assuming "last page in the notebook."

## Next
- **Output the answer next to the source, on the device itself** — right
  now results only print to the terminal / save as a local PNG. The goal
  is to render the graph/answer and get it back onto the reMarkable near
  the original handwritten equation/code, not just locally.
  - Realistic approaches to evaluate: (a) push result as a new page in a
    companion "Results" notebook via `rmapi`/`rmfakecloud`, glanced at
    side-by-side; (b) splice the rendered result image directly into the
    same page's `.rm`/`.content` files and re-upload, which is closer to
    "next to the source" but touches reMarkable's undocumented format
    more invasively.
- `watch.py`: polling loop so this triggers automatically instead of
  manual `python main.py` runs
- Code execution currently Python-only; other languages unsupported
- Multi-variable / implicit equation graphing (e.g. `x^2 + y^2 = 1`) not
  handled yet — single-variable only right now
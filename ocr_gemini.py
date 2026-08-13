import json
import base64
from groq import BadRequestError, Groq
from config import GROQ_API_KEY, GROQ_MODEL, GROQ_REQUEST_TIMEOUT_SECONDS

groq_model=GROQ_MODEL
client=Groq(api_key=GROQ_API_KEY, timeout=GROQ_REQUEST_TIMEOUT_SECONDS)

PROMPT="""You are reading a photo of a handwritten page from a digital notebook.
 
Look at the handwriting and decide what it is, then respond with ONLY a JSON
object (no markdown fences, no commentary) in this exact shape:
 
{
  "type": "math" | "code" | "unclear",
  "language": "<programming language if type is code, else null>",
  "content": "<the transcribed LaTeX if math, or the transcribed source code if code>",
  "content_bbox": [x0, y0, x1, y1],
  "annotation_description": "<see instructions below>",
  "trigger": true | false,
  "notes": "<anything you're unsure about, or empty string>"
}
 
For "content_bbox": give the bounding box of the handwriting you classified
(the content inside the marked enclosure if one is present, otherwise the
main content), as fractions of the whole image: x0, y0 = top-left corner,
x1, y1 = bottom-right corner, all between 0 and 1 where (0,0) is the
top-left of the image and (1,1) the bottom-right. Make the box snug around
the actual ink (letters/symbols), not the whole page. Example for an
expression centered in the upper third: [0.35, 0.05, 0.7, 0.12].
 
Rules:
- If an enclosure and checkmark/star trigger are present, classify and
  transcribe ONLY the content inside that marked enclosure. Ignore surrounding
  notes, examples, page headings, scratch work, and unrelated writing.
- If no trigger marker is present, classify/transcribe the main handwritten
  content as a best effort.
- If it's a mathematical expression or equation, transcribe it as valid LaTeX
  (no $ delimiters, just the LaTeX body, e.g. "x^2 + 3x - 4 = 0").
- If it's code, transcribe it as clean, runnable source code, fixing obvious
  handwriting-induced typos only if you're confident (e.g. clearly a stray
  pen stroke), and note anything you changed in "notes".
- If you genuinely can't tell what it is, use "unclear" and leave content as
  your best-effort transcription anyway.
- For "annotation_description": look CAREFULLY across the ENTIRE image for
  two specific hand-drawn marks, separate from the math/code content itself:
    1. An enclosure -- a box, rectangle, or oval/circle drawn AROUND the
       expression or code (i.e. lines forming a border on multiple sides of
       it, not just underlining).
    2. A checkmark (a short two-stroke tick/tick mark, shaped like a
       lowercase "v" or check symbol) OR a star (multi-pointed asterisk-like
       shape), drawn near/beside the enclosure -- NOT part of the math
       itself (e.g. not a multiplication symbol or variable).
  Describe in one sentence exactly what you see: is there an enclosure?
  Is there a checkmark or star near it? Where relative to the content?
  If you see neither, say so explicitly (e.g. "No enclosure or checkmark
  visible.").
- Set "trigger" to true IF AND ONLY IF your own "annotation_description"
  confirms BOTH an enclosure AND a checkmark/star are present. If your
  description says either one is missing, "trigger" must be false --
  even if the math/code looks complete and correct.
"""


def encode_img(image_path:str)->str:
    """Encodes local img to base64 str"""
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")


def _strip_reasoning(text:str)->str:
    text=text.strip()
    while text.startswith("<think>"):
        end=text.find("</think>")
        if end == -1:
            return text
        text=text[end + len("</think>"):].strip()
    return text


def _extract_json_object(text:str)->dict:
    text=_strip_reasoning(text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    start=text.find("{")
    if start == -1:
        raise ValueError(f"Groq didn't return JSON. Raw response:\n{text}")

    decoder=json.JSONDecoder()
    try:
        result, _ = decoder.raw_decode(text[start:])
    except json.JSONDecodeError as e:
        raise ValueError(f"Groq didn't return valid JSON. Raw response:\n{text}") from e
    if not isinstance(result, dict):
        raise ValueError(f"Groq returned JSON that is not an object. Raw response:\n{text}")
    return result


def _normalize_bbox(value) -> list:
    """Coerce the model's content_bbox into [x0, y0, x1, y1] fractions."""
    default = [0.0, 0.0, 1.0, 1.0]
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return default
    try:
        coords = [float(v) for v in value]
    except (TypeError, ValueError):
        return default

    def clamp(v: float) -> float:
        return min(1.0, max(0.0, v))

    x0, x1 = sorted([coords[0], coords[2]])
    y0, y1 = sorted([coords[1], coords[3]])
    # Guard against a degenerate (zero-area) box
    if x1 - x0 < 0.02 or y1 - y0 < 0.02:
        return default
    return [clamp(x0), clamp(y0), clamp(x1), clamp(y1)]


def _as_bool(value)->bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "1"}
    return bool(value)


def _normalize_result(result:dict)->dict:
    normalized={
        "type": result.get("type") or "unclear",
        "language": result.get("language"),
        "content": result.get("content") or "",
        "content_bbox": _normalize_bbox(result.get("content_bbox")),
        "annotation_description": result.get("annotation_description") or "",
        "trigger": _as_bool(result.get("trigger")),
        "notes": result.get("notes") or "",
    }
    if normalized["type"] not in {"math", "code", "unclear"}:
        normalized["notes"] = (normalized["notes"] + " Invalid type returned; treated as unclear.").strip()
        normalized["type"] = "unclear"
    if normalized["type"] != "code":
        normalized["language"] = None
    return normalized


def _request_analysis(base64_image:str, strict_json:bool):
    kwargs={
        "model": groq_model,
        "temperature": 0.0,
        "reasoning_effort": "none",
        "include_reasoning": False,
        "messages":[
            {
                "role":"user",
                "content":[
                    {"type":"text", "text":PROMPT},
                    {
                        "type":"image_url",
                        "image_url":{"url":f"data:image/png;base64,{base64_image}"}
                    }
                ]
            }
        ]
    }
    if strict_json:
        kwargs["response_format"]={"type":"json_object"}
    return client.chat.completions.create(**kwargs)


def analyze_page(image_path:str)->dict:
    base64_image=encode_img(image_path)
    try:
        response=_request_analysis(base64_image, strict_json=True)
    except BadRequestError as e:
        if "json_validate_failed" not in str(e):
            raise
        response=_request_analysis(base64_image, strict_json=False)

    text=response.choices[0].message.content.strip()
    return _normalize_result(_extract_json_object(text))

if __name__ == "__main__":
    import sys
    if len(sys.argv) !=2:
        print("Usage: python ocr_gemini.py <path_to_page_image.png>")
        sys.exit(1)
    result = analyze_page(sys.argv[1])
    print(json.dumps(result, indent=2))

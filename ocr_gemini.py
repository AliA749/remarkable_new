import json
import re
import base64
from groq import Groq
from config import GROQ_API_KEY, GROQ_MODEL

groq_model=GROQ_MODEL
client=Groq(api_key=GROQ_API_KEY)

PROMPT="""You are reading a photo of a handwritten page from a digital notebook.
 
Look at the handwriting and decide what it is, then respond with ONLY a JSON
object (no markdown fences, no commentary) in this exact shape:
 
{
  "type": "math" | "code" | "unclear",
  "language": "<programming language if type is code, else null>",
  "content": "<the transcribed LaTeX if math, or the transcribed source code if code>",
  "notes": "<anything you're unsure about, or empty string>"
}
 
Rules:
- If it's a mathematical expression or equation, transcribe it as valid LaTeX
  (no $ delimiters, just the LaTeX body, e.g. "x^2 + 3x - 4 = 0").
- If it's code, transcribe it as clean, runnable source code, fixing obvious
  handwriting-induced typos only if you're confident (e.g. clearly a stray
  pen stroke), and note anything you changed in "notes".
- If you genuinely can't tell what it is, use "unclear" and leave content as
  your best-effort transcription anyway.
"""
def encode_img(image_path:str)->str:
    """Encodes local img to base64 str"""
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")

    
def analyze_page(image_path:str)->dict:
    base64_image=encode_img(image_path)
    response=client.chat.completions.create(
        model=groq_model,
        response_format={"type":"json_object"},
        temperature=0.0,
        messages=[
            {
                "role":"user",
                "content":[
                    {
                        "type":"text",
                        "text":PROMPT
                    },
                    {
                        "type":"image_url",
                        "image_url":{
                            "url":f"data:image/png;base64,{base64_image}"
                        }
                    }
                ]
            }
        ]
    )
    text=response.choices[0].message.content.strip()

    try:
        result=json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(
           f"Groq didn't return valid JSON. Raw response:\n{text}"
        ) from e
    return result

if __name__ == "__main__":
    import sys
    if len(sys.argv) !=2:
        print("Usage: python ocr_gemini.py <path_to_page_image.png>")
        sys.exit(1)
    result = analyze_page(sys.argv[1])
    print(json.dumps(result, indent=2))
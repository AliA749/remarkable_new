"""
1: Pull last touched in the notebook
2: routes to math engine(graph/solve) or code engine(run)
3: print the result and for graphs, it will tell where png is at
once this works e2e for you, watch.py turns this to a polling loop
"""

from fetch_page import get_latest_page_image
from ocr_gemini import analyze_page
from math_engine import decide_and_render
from code_engine import run_code

def process_latest_page():
    print("Pulling latest page from tablet...")
    page_info = get_latest_page_image()
    print(f"  notebook={page_info['uuid']}  page_count={page_info['page_id']}")
 
    print("Sending to Gemini for OCR/classification...")
    analysis = analyze_page(page_info["png_path"])
    print(f"  type={analysis['type']}  notes={analysis.get('notes') or '(none)'}")
 
    if analysis["type"] == "math":
        result = decide_and_render(analysis["content"])
        print(f"\n[MATH] {result.kind}: {result.text}")
        if result.image_path:
            print(f"Graph saved to: {result.image_path}")
 
    elif analysis["type"] == "code":
        result = run_code(analysis["content"], analysis.get("language"))
        print(f"\n[CODE] {result.kind}:\n{result.text}")
 
    else:
        print(f"\n[UNCLEAR] Best-effort transcription: {analysis['content']}")
 
    return analysis
 
 
if __name__ == "__main__":
    process_latest_page()

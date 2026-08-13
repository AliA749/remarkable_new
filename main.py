"""
1: Pull last touched in the notebook
2: routes to math engine(graph/solve) or code engine(run)
3: print the result and for graphs, it will tell where png is at
once this works e2e for you, watch.py turns this to a polling loop
"""

from fetch_page import get_latest_page_image
from ocr_gemini import analyze_page
from code_engine import run_code
from config import RESULTS_DOC_NAME

def process_latest_page():
    print("Pulling latest page from tablet...")
    page_info = get_latest_page_image()
    print(f"  notebook={page_info['uuid']}  page_count={page_info['page_id']}")
 
    print("Sending to Gemini for OCR/classification...")
    analysis = analyze_page(page_info["png_path"])
    print(f"  type={analysis['type']}  notes={analysis.get('notes') or '(none)'}")
 
    result = None
    if analysis["type"] == "math":
        from math_engine import decide_and_render
        result = decide_and_render(analysis["content"])
        print(f"\n[MATH] {result.kind}: {result.text}")
        if result.image_path:
            print(f"Graph saved to: {result.image_path}")
 
    elif analysis["type"] == "code":
        result = run_code(analysis["content"], analysis.get("language"))
        print(f"\n[CODE] {result.kind}:\n{result.text}")
 
    else:
        print(f"\n[UNCLEAR] Best-effort transcription: {analysis['content']}")
 
    if result is not None:
        from annotate_page import annotate_and_push
        out = annotate_and_push(
            svg_path=page_info["svg_path"],
            bbox=analysis["content_bbox"],
            answer_text=result.text,
            answer_image_path=result.image_path,
        )
        print(f"\nAnnotated page: {out['png']}")
        print(f"Annotated PDF:  {out['pdf']}")
        if out["doc_uuid"]:
            print(f"Pushed to tablet as '{RESULTS_DOC_NAME}' (document {out['doc_uuid']})")
        else:
            print("(push to tablet disabled -- set PUSH_RESULTS_TO_TABLET=1 to enable)")
 
    return analysis
 
 
if __name__ == "__main__":
    process_latest_page()

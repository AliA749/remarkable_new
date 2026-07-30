"""Polling loop that watches active notebook over wifi and automatically runs math/code pipeline, ONLY when it sees a handdrawn box or circle around the equation/code
Run it and leave it running in the background while you write:
 
    python watch.py
 
How it decides when to act:
  1. Poll the tablet every POLL_INTERVAL_SECONDS (default 10s), checking
     just the notebook's mtime (cheap -- no page pull yet).
  2. If the mtime hasn't changed for QUIET_POLLS_THRESHOLD consecutive
     polls (default 2, i.e. ~20s of no edits), consider you "done writing"
     for now.
  3. Once settled, pull the current page and ask Gemini to classify it AND
     check for the trigger marker.
  4. If the trigger marker is present AND we haven't already processed this
     exact page state, run the math/code engine and print the result.
  5. Either way, remember this mtime as "checked" so we don't re-ask Gemini
     again until you make a new edit.
"""
import time
import json
import os
from config import (POLL_INTERVAL_SECONDS,QUIET_POLLS_THRESHOLD, WATCH_STATE_FILE,)
from fetch_page import (find_most_recent_notebook_uuid, get_notebook_mtime, pull_content_file, get_current_page_id,pull_page_rm_file,convert_rm_to_png)
from ocr_gemini import analyze_page
from math_engine import decide_and_render
from code_engine import run_code


def load_state()->dict:
    if os.path.exists(WATCH_STATE_FILE):
        with open(WATCH_STATE_FILE)as f:
            return json.load(f)
    return {}

def save_state(state:dict):
    with open(WATCH_STATE_FILE,"w") as f:
        json.dump(state,f,indent=2)

def process_current_page(uuid:str)->dict:
    local_dir=pull_content_file(uuid)
    page_id=get_current_page_id(local_dir,uuid)
    rm_path=pull_page_rm_file(uuid,page_id,local_dir)
    png_path=convert_rm_to_png(rm_path)

    analysis=analyze_page(png_path)
    return{"page_id":page_id,"analysis":analysis}

def run_pipeline_on(analysis:dict):
    if analysis["type"]=="math":
        result=decide_and_render(analysis["content"])
        print(f"  [MATH] {result.kind}: {result.text}")
        if result.image_path:
            print(f"  Graph saved to: {result.image_path}")
    elif analysis["type"]=="code":
        result=run_code(analysis["content"],analysis.get("language"))
        print(f"  [CODE] {result.kind}:\n{result.text}")
    else:
        print(f"  [UNCLEAR] Best-effort transcription: {analysis['content']}")

def watch():
    print(f"Watching for changes every {POLL_INTERVAL_SECONDS}"
          f"(settles after {QUIET_POLLS_THRESHOLD} quiet polls)...")
    print("Draw a box or a circle + checkmark or star around something to trigger it.\n")

    state=load_state()
    quiet_count=0
    last_mtime_seen=None

    while True:
        try:
            uuid=find_most_recent_notebook_uuid()
            mtime=get_notebook_mtime(uuid)
            notebook_state=state.get(uuid,{"checked_mtime":None})
            if last_mtime_seen is None or mtime != last_mtime_seen:
                #something changed since last poll, reset quiet count
                quiet_count=0
                last_mtime_seen=mtime
            else:
                quiet_count+=1
            already_checked=notebook_state.get("checked_mtime")==False

            if quiet_count >= QUIET_POLLS_THRESHOLD and not already_checked:
                print(f"[{time.strftime('%H:%M:%S')}] Settled -- checking for trigger marker...")
                result=process_current_page(uuid)
                analysis=result["analysis"]
                if analysis.get("trigger"):
                    print(f"[{time.strftime('%H:%M:%S')}] Trigger detected! Running pipeline...")

                    run_pipeline_on(analysis)
                else:
                    print(f"[{time.strftime('%H:%M:%S')}] No trigger marker found, skipping.")
                    print(f"  type={analysis.get('type')}  content={analysis.get('content')!r}")
                    print(f"  annotation_description={analysis.get('annotation_description')!r}")
                    print(f"  notes={analysis.get('notes')!r}")

                notebook_state["checked_mtime"]=mtime
                state[uuid]=notebook_state
                save_state(state)
        except Exception as e:
            print(f"[{time.strftime('%H:%M:%S')}] Error during poll (will retry): {e}")

        time.sleep(POLL_INTERVAL_SECONDS)

if __name__ == "__main__":
    watch()



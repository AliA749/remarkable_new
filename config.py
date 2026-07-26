import os
from dotenv import load_dotenv
load_dotenv()
#remarkable stuff
RM_HOST = os.environ.get("RM_HOST","10.11.99.1")
RM_USER = os.environ.get("RM_USER","root")
RM_XOCHITL_PATH= "/home/root/.local/share/remarkable/xochitl"

#gemini stuff
GEMINI_API_KEY=os.environ.get("GEMENI_API_KEY")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")

#local working dirs
WORKDIR = os.environ.get("RM_PIPELINE_WORKDIR", os.path.expanduser("~/.rm_pipeline"))
PAGES_DIR = os.path.join(WORKDIR, "pages")
RESULTS_DIR = os.path.join(WORKDIR, "results")
 
for d in (WORKDIR, PAGES_DIR, RESULTS_DIR):
    os.makedirs(d, exist_ok=True)
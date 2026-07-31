import os
from dotenv import load_dotenv
load_dotenv()
#remarkable stuff
RM_HOST = os.environ.get("RM_HOST","10.11.99.1")
RM_USER = os.environ.get("RM_USER","root")
RM_XOCHITL_PATH= "/home/root/.local/share/remarkable/xochitl"

#groq stuff
GROQ_API_KEY=os.environ.get("GROQ_API_KEY")
GROQ_MODEL=os.environ.get("GROQ_MODEL","qwen/qwen3.6-27b")
GROQ_REQUEST_TIMEOUT_SECONDS=float(os.environ.get("GROQ_REQUEST_TIMEOUT_SECONDS","30"))

#local working dirs
WORKDIR = os.environ.get("RM_PIPELINE_WORKDIR", os.path.expanduser("~/.rm_pipeline"))
PAGES_DIR = os.path.join(WORKDIR, "pages")
RESULTS_DIR = os.path.join(WORKDIR, "results")
 
for d in (WORKDIR, PAGES_DIR, RESULTS_DIR):
    os.makedirs(d, exist_ok=True)

#---Watch loop settings---
POLL_INTERVAL_SECONDS=int(os.environ.get("POLL_INTERVAL_SECONDS","3"))
QUIET_POLLS_THRESHOLD = int(os.environ.get("QUIET_POLLS_THRESHOLD", "1"))
WATCH_STATE_FILE = os.path.join(WORKDIR, "watch_state.json")
SSH_COMMAND_TIMEOUT_SECONDS=float(os.environ.get("SSH_COMMAND_TIMEOUT_SECONDS","8"))
SCP_COMMAND_TIMEOUT_SECONDS=float(os.environ.get("SCP_COMMAND_TIMEOUT_SECONDS","15"))
RMC_COMMAND_TIMEOUT_SECONDS=float(os.environ.get("RMC_COMMAND_TIMEOUT_SECONDS","15"))

"""
Runs transcribed code and captures output

MVP scope: Python only, run as a subprocess(isolated process, not the same
interpreter) with a timeout and output size cap. This is NOT a hardened
sandbox -- fine for your own handwritten snippets on your own machine, but
don't point this at untrusted input. If you want real isolation later,
swap the subprocess call for a Docker container run)
"""

import subprocess
import tempfile
import os

TIMEOUT_SECONDS=8
MAX_OUTPUT_CHAR=4000

SUPPORTED_LANGUAGES={"python","python3","py"}

class CodeResult:
    def __init__(self, kind: str, text: str, image_path: str | None = None):
        self.kind = kind  # output, error, unsupported
        self.text = text
        self.image_path = image_path  # kept None -- code answers are text-only

    def __repr__(self):
        return f"CodeResult(kind={self.kind!r}, text={self.text!r}, image_path={self.image_path!r})"

def run_code(code:str, language:str | None)->CodeResult:
    lang=(language or "python").lower()
    if lang not in SUPPORTED_LANGUAGES:
        return CodeResult(
            "Unsupported",
            f"Language '{language}' isn't wired up yet -- only python runs for now.",
        )
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py',delete=False) as f:
        f.write(code)
        script_path=f.name

    try:
        result=subprocess.run(["python3",script_path],capture_output=True, text=True, timeout=TIMEOUT_SECONDS,)
        output=result.stdout if result.returncode==0 else result.stderr
        kind = "output" if result.returncode ==0 else "error"
        return CodeResult(kind, output[:MAX_OUTPUT_CHAR])
    except subprocess.TimeoutExpired:
        return CodeResult("error", f"Timed out after {TIMEOUT_SECONDS}s")
    finally:
        os.unlink(script_path)
if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print("Usage: python code_engine.py '<code string>'")
        sys.exit(1)
    result = run_code(sys.argv[1], "python")
    print(result)
from pathlib import Path
import sys

ORCHESTRATOR_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ORCHESTRATOR_ROOT.parent

for path in (ORCHESTRATOR_ROOT, REPO_ROOT):
    text = str(path)
    if text not in sys.path:
        sys.path.insert(0, text)

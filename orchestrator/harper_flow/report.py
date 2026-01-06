import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

@dataclass
class QuickstartReport:
    run_id: str
    start_from: str
    mode: str
    profile: Optional[str] = None
    phases: List[Dict[str, Any]] = field(default_factory=list)
    artifacts: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    models: Dict[str, Any] = field(default_factory=dict)
    token_usage: Dict[str, Any] = field(default_factory=dict)

def log_phase(
    self,
    name: str,
    status: str,
    artifacts: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    self.phases.append(
        {
            "name": name,
            "status": status,
            "artifacts": artifacts or {},
            "error": error,
            "details": details or {},
        }
    )
    if error:
        self.errors.append(error)
    if artifacts:
        self.artifacts.update(artifacts)

def save(self, run_dir: Path) -> Path:
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / "harper.quickstart.report.json"
    payload = {
        "runId": self.run_id,
        "startFrom": self.start_from,
        "mode": self.mode,
        "profile": self.profile,
        "phases": self.phases,
        "artifacts": self.artifacts,
        "errors": self.errors,
        "models": self.models,
        "tokenUsage": self.token_usage,
    }
    with path.open("w", encoding="utf-8") as fp:
        json.dump(payload, fp, indent=2)
    return path

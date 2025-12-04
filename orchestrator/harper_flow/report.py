import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class QuickstartPhaseLog:
    phase: str
    status: str
    started_at: str
    completed_at: str
    details: Dict[str, Any] = field(default_factory=dict)


class QuickstartReport:
    def __init__(self, run_id: str, run_directory: Path, inputs: Optional[Dict[str, Any]] = None):
        self.run_id = run_id
        self.run_directory = run_directory
        self.report_path = run_directory / "harper.quickstart.report.json"
        self.inputs = inputs or {}
        self.phases: List[QuickstartPhaseLog] = []
        self.telemetry: Dict[str, Any] = {}
        self._load_if_exists()

    def _load_if_exists(self) -> None:
        if not self.report_path.exists():
            return
        try:
            data = json.loads(self.report_path.read_text(encoding="utf-8"))
            self.inputs = data.get("inputs", self.inputs)
            self.telemetry = data.get("telemetry", {})
            self.phases = [
                QuickstartPhaseLog(
                    phase=entry.get("phase", ""),
                    status=entry.get("status", ""),
                    started_at=entry.get("started_at", ""),
                    completed_at=entry.get("completed_at", ""),
                    details=entry.get("details", {}),
                )
                for entry in data.get("phases", [])
            ]
        except json.JSONDecodeError:
            # Start fresh if existing report cannot be parsed
            self.phases = []

    def log_phase(self, phase: str, status: str, details: Optional[Dict[str, Any]] = None) -> None:
        now = datetime.utcnow().isoformat() + "Z"
        self.phases.append(
            QuickstartPhaseLog(
                phase=phase,
                status=status,
                started_at=now,
                completed_at=now,
                details=details or {},
            )
        )
        self.save()

    def set_inputs(self, inputs: Dict[str, Any]) -> None:
        self.inputs = inputs
        self.save()

    def save(self) -> Path:
        self.run_directory.mkdir(parents=True, exist_ok=True)
        payload = {
            "run_id": self.run_id,
            "inputs": self.inputs,
            "phases": [
                {
                    "phase": p.phase,
                    "status": p.status,
                    "started_at": p.started_at,
                    "completed_at": p.completed_at,
                    "details": p.details,
                }
                for p in self.phases
            ],
            "telemetry": self.telemetry,
        }
        self.report_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return self.report_path

    def append_telemetry(self, key: str, value: Any) -> None:
        self.telemetry[key] = value
        self.save()

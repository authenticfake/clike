# orchestrator/app/capabilities/engine.py
# Capability-driven evaluation engine.
# Discovers capabilities from .clike/capabilities.yaml and/or infers from workspace.
# Executes commands per capability and normalizes outputs for the EvalRunner.

from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import subprocess, shlex, os, yaml

@dataclass
class CapCmd:
    name: str
    cmd: str
    runner: str = "local"   # local | docker (extensible)
    image: str | None = None

class CapabilityEngine:
    """Resolves capability commands for a given profile (spec/plan/kit/finalize)."""
    def __init__(self, project_root: Path):
        self.root = project_root
        self.clike = self.root / ".clike"
        self.policy_path = self.clike / "policy.yaml"
        self.caps_path = self.clike / "capabilities.yaml"
        self.policy = self._safe_load_yaml(self.policy_path) or {}
        self.caps = self._safe_load_yaml(self.caps_path) or {}

    def _safe_load_yaml(self, p: Path):
        if p.exists():
            with p.open("r", encoding="utf8") as f:
                return yaml.safe_load(f) or {}
        return {}

    def _infer_defaults(self) -> dict:
        """Heuristics when capabilities.yaml is missing: look for common build/test config."""
        defaults: dict[str, str] = {}

        if (self.root / "pyproject.toml").exists() or (self.root / "requirements.txt").exists():
            defaults |= {
                "lint": "ruff check .",
                "typecheck": "mypy --hide-error-codes --no-color-output",
                "test:unit": "pytest -q",
                "security:sast": "bandit -q -r .",
            }
        if (self.root / "package.json").exists():
            defaults.setdefault("lint", "npm run lint || npx eslint .")
            defaults.setdefault("typecheck", "npm run typecheck || npx tsc --noEmit")
            defaults.setdefault("test:unit", "npm test --silent || npx jest -i")
        if (self.root / "go.mod").exists():
            defaults.setdefault("lint", "golangci-lint run || true")
            defaults.setdefault("test:unit", "go test ./... -cover")
        if (self.root / "pom.xml").exists() or any(self.root.glob("build.gradle*")):
            defaults.setdefault("test:unit", "mvn -q -DskipITs test || gradle test")

        return defaults

    def resolve_profile(self, profile: str) -> list[CapCmd]:
        """Map a profile to a list of commands (policy first, then fallback heuristics)."""
        commands: list[CapCmd] = []
        eval_cfg = (self.policy.get("eval") or {}).get("profiles") or {}
        profile_items = eval_cfg.get(profile)

        if profile_items:
            for item in profile_items if isinstance(profile_items, list) else [profile_items]:
                if isinstance(item, str):
                    cmd = self._cmd_for_cap(item)
                    if cmd:
                        commands.append(cmd)
                elif isinstance(item, dict):
                    for cap, cfg in item.items():
                        commands.append(CapCmd(cap, cfg.get("cmd",""), cfg.get("runner","local"), cfg.get("image")))
            return commands

        if profile in ("spec", "plan"):
            return []  # handled by spec_plan_gates via EvalRunner
        if profile == "kit":
            inferred = self._infer_defaults()
            for k, v in inferred.items():
                commands.append(CapCmd(k, v))
            # optional extras if defined in capabilities.yaml
            caps = (self.caps.get("capabilities") or {})
            for extra in ("security:secrets", "test:integration"):
                if extra in caps:
                    entry = caps[extra]
                    if isinstance(entry, dict):
                        commands.append(CapCmd(extra, entry.get("cmd",""), entry.get("runner","local"), entry.get("image")))
                    else:
                        commands.append(CapCmd(extra, str(entry)))
            return commands
        if profile == "finalize":
            caps = (self.caps.get("capabilities") or {})
            for cap_name in ("package", "sbom", "license:check"):
                if cap_name in caps:
                    entry = caps[cap_name]
                    if isinstance(entry, dict):
                        commands.append(CapCmd(cap_name, entry.get("cmd",""), entry.get("runner","local"), entry.get("image")))
                    else:
                        commands.append(CapCmd(cap_name, str(entry)))
            return commands
        return []

    def _cmd_for_cap(self, cap_name: str) -> CapCmd | None:
        caps_map = (self.caps.get("capabilities") or {})
        entry = caps_map.get(cap_name)
        if isinstance(entry, dict):
            return CapCmd(cap_name, entry.get("cmd",""), entry.get("runner","local"), entry.get("image"))
        if isinstance(entry, str):
            return CapCmd(cap_name, entry)
        return None

    def run_cmd(self, c: CapCmd) -> tuple[int, str, str]:
        """Executes a capability command. For now, only `local` runner."""
        env = os.environ.copy()
        proc = subprocess.Popen(shlex.split(c.cmd), cwd=self.root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
        out, err = proc.communicate()
        return proc.returncode, out, err

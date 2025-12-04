import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional

from .nodes import (
    HarperNodeDefinition,
    HarperNodeState,
    NodeExecutionResult,
    NodeStatus,
    build_default_nodes,
)


@dataclass
class HarperFlowGraph:
    run_id: str
    mode: str
    start_from: str
    nodes: Dict[str, HarperNodeDefinition]
    state: Dict[str, HarperNodeState] = field(default_factory=dict)

    @classmethod
    def create(cls, run_id: str, mode: str, start_from: str = "auto") -> "HarperFlowGraph":
        definitions = {node.key: node for node in build_default_nodes(start_from)}
        initial_state: Dict[str, HarperNodeState] = {
            key: HarperNodeState(status=NodeStatus.PENDING) for key in definitions
        }

        if start_from == "spec":
            initial_state["idea"].status = NodeStatus.SKIPPED

        graph = cls(
            run_id=run_id,
            mode=mode,
            start_from=start_from,
            nodes=definitions,
            state=initial_state,
        )
        graph._mark_ready_nodes()
        return graph

    @classmethod
    def load(cls, run_directory: Path) -> "HarperFlowGraph":
        flow_path = run_directory / "harper.flow.json"
        with flow_path.open("r", encoding="utf-8") as fp:
            data = json.load(fp)

        definitions = {
            key: HarperNodeDefinition(
                key=key,
                label=value["label"],
                depends_on=value.get("depends_on", []),
                optional=value.get("optional", False),
            )
            for key, value in data["nodes"].items()
        }
        state = {
            key: HarperNodeState(
                status=NodeStatus(value["status"]),
                error=value.get("error"),
                started_at=value.get("started_at"),
                completed_at=value.get("completed_at"),
                artifacts=value.get("artifacts", {}),
                details=value.get("details", {}),
            )
            for key, value in data["state"].items()
        }

        graph = cls(
            run_id=data["run_id"],
            mode=data["mode"],
            start_from=data.get("start_from", "auto"),
            nodes=definitions,
            state=state,
        )
        graph._mark_ready_nodes()
        return graph

    def save(self, run_directory: Path) -> Path:
        run_directory.mkdir(parents=True, exist_ok=True)
        flow_path = run_directory / "harper.flow.json"
        payload = {
            "run_id": self.run_id,
            "mode": self.mode,
            "start_from": self.start_from,
            "nodes": {
                key: {
                    "label": definition.label,
                    "depends_on": definition.depends_on,
                    "optional": definition.optional,
                }
                for key, definition in self.nodes.items()
            },
            "state": {
                key: {
                    "status": state.status.value,
                    "error": state.error,
                    "started_at": state.started_at,
                    "completed_at": state.completed_at,
                    "artifacts": state.artifacts,
                    "details": state.details,
                }
                for key, state in self.state.items()
            },
        }
        with flow_path.open("w", encoding="utf-8") as fp:
            json.dump(payload, fp, indent=2)
        return flow_path

    def auto_run_nodes_for_mode(self) -> List[str]:
        """
        Return the ordered list of nodes that should be auto-executed for the selected mode.
        plan-only: through plan
        first-kit: through gate
        e2e-manual: through gate (finalize gated separately)
        """
        base_sequence = list(self.nodes.keys())

        if self.mode == "plan-only":
            cutoff = base_sequence.index("plan")
            return base_sequence[: cutoff + 1]

        if self.mode == "first-kit":
            cutoff = base_sequence.index("gate")
            return base_sequence[: cutoff + 1]

        if self.mode == "e2e-manual":
            cutoff = base_sequence.index("gate")
            return base_sequence[: cutoff + 1]

        return base_sequence

    def execute(
        self,
        executor: Dict[str, Callable[[HarperNodeDefinition], NodeExecutionResult]],
        run_directory: Optional[Path] = None,
    ) -> Dict[str, HarperNodeState]:
        """
        Sequential execution loop. A node is executed when all dependencies are completed
        or skipped. The executor is a mapping from node key to a callable that returns
        NodeExecutionResult.
        """
        for node_key in self.auto_run_nodes_for_mode():
            node_def = self.nodes[node_key]
            node_state = self.state[node_key]

            if node_state.status in {NodeStatus.COMPLETED, NodeStatus.SKIPPED}:
                continue

            if not self._is_ready(node_def):
                continue

            if node_state.status == NodeStatus.PENDING:
                node_state.status = NodeStatus.READY

            node_state.status = NodeStatus.RUNNING
            node_state.started_at = datetime.utcnow().isoformat() + "Z"

            try:
                executor_fn = executor.get(node_key)
                if executor_fn is None:
                    raise ValueError(f"No executor provided for node '{node_key}'")
                result = executor_fn(node_def)
                node_state.status = result.status
                node_state.error = result.error
                node_state.artifacts = result.artifacts
                node_state.details = result.details
            except Exception as exc:  # pragma: no cover - defensive
                node_state.status = NodeStatus.FAILED
                node_state.error = str(exc)

            node_state.completed_at = datetime.utcnow().isoformat() + "Z"

            if run_directory:
                self.save(run_directory)

            if node_state.status == NodeStatus.FAILED:
                break

            self._mark_ready_nodes()

        return self.state

    def _mark_ready_nodes(self) -> None:
        for key, definition in self.nodes.items():
            state = self.state[key]
            if state.status != NodeStatus.PENDING:
                continue
            if self._is_ready(definition):
                state.status = NodeStatus.READY

            if definition.optional and self.start_from == "spec" and key == "idea":
                state.status = NodeStatus.SKIPPED

    def _is_ready(self, definition: HarperNodeDefinition) -> bool:
        return all(
            self.state[dep].status in {NodeStatus.COMPLETED, NodeStatus.SKIPPED}
            for dep in definition.depends_on
        )

    def to_dict(self) -> Dict[str, Dict]:
        return {
            "run_id": self.run_id,
            "mode": self.mode,
            "start_from": self.start_from,
            "nodes": {key: asdict(defn) for key, defn in self.nodes.items()},
            "state": {
                key: {
                    "status": state.status.value,
                    "error": state.error,
                    "started_at": state.started_at,
                    "completed_at": state.completed_at,
                    "artifacts": state.artifacts,
                    "details": state.details,
                }
                for key, state in self.state.items()
            },
        }

    def describe(self) -> List[Dict[str, str]]:
        """
        Produce a lightweight summary useful for telemetry or UI layers.
        """
        summary = []
        for key in self.nodes:
            state = self.state[key]
            summary.append(
                {
                    "node": key,
                    "status": state.status.value,
                    "error": state.error or "",
                }
            )
        return summary
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional

from .nodes import (
    HarperNodeDefinition,
    HarperNodeState,
    NodeExecutionResult,
    NodeStatus,
    build_default_nodes,
)

@dataclass
class HarperFlowGraph:
    run_id: str
    mode: str
    start_from: str
    nodes: Dict[str, HarperNodeDefinition]
    state: Dict[str, HarperNodeState] = field(default_factory=dict)

@classmethod
def create(cls, run_id: str, mode: str, start_from: str = "auto") -> "HarperFlowGraph":
    definitions = {node.key: node for node in build_default_nodes(start_from)}
    initial_state: Dict[str, HarperNodeState] = {
        key: HarperNodeState(status=NodeStatus.PENDING) for key in definitions
    }

    if start_from == "spec":
        # IDEA is optional in this configuration.
        initial_state["idea"].status = NodeStatus.SKIPPED

    graph = cls(
        run_id=run_id,
        mode=mode,
        start_from=start_from,
        nodes=definitions,
        state=initial_state,
    )
    graph._mark_ready_nodes()
    return graph

@classmethod
def load(cls, run_directory: Path) -> "HarperFlowGraph":
    flow_path = run_directory / "harper.flow.json"
    with flow_path.open("r", encoding="utf-8") as fp:
        data = json.load(fp)

    definitions = {
        key: HarperNodeDefinition(
            key=key,
            label=value["label"],
            depends_on=value.get("depends_on", []),
            optional=value.get("optional", False),
        )
        for key, value in data["nodes"].items()
    }
    state = {
        key: HarperNodeState(
            status=NodeStatus(value["status"]),
            error=value.get("error"),
            started_at=value.get("started_at"),
            completed_at=value.get("completed_at"),
            artifacts=value.get("artifacts", {}),
            details=value.get("details", {}),
        )
        for key, value in data["state"].items()
    }

    graph = cls(
        run_id=data["run_id"],
        mode=data["mode"],
        start_from=data.get("start_from", "auto"),
        nodes=definitions,
        state=state,
    )
    graph._mark_ready_nodes()
    return graph

def save(self, run_directory: Path) -> Path:
    run_directory.mkdir(parents=True, exist_ok=True)
    flow_path = run_directory / "harper.flow.json"
    payload = {
        "run_id": self.run_id,
        "mode": self.mode,
        "start_from": self.start_from,
        "nodes": {
            key: {
                "label": definition.label,
                "depends_on": definition.depends_on,
                "optional": definition.optional,
            }
            for key, definition in self.nodes.items()
        },
        "state": {
            key: {
                "status": state.status.value,
                "error": state.error,
                "started_at": state.started_at,
                "completed_at": state.completed_at,
                "artifacts": state.artifacts,
                "details": state.details,
            }
            for key, state in self.state.items()
        },
    }
    with flow_path.open("w", encoding="utf-8") as fp:
        json.dump(payload, fp, indent=2)
    return flow_path

def auto_run_nodes_for_mode(self) -> List[str]:
    """
    Return the ordered list of nodes that should be auto-executed for the selected mode.
    plan-only: through ltc_howto
    first-kit: through gate
    e2e-manual: configure all nodes but do not auto-run finalize
    """
    base_sequence = list(self.nodes.keys())

    if self.mode == "plan-only":
        cutoff = base_sequence.index("ltc_howto")
        return base_sequence[: cutoff + 1]

    if self.mode == "first-kit":
        cutoff = base_sequence.index("gate")
        return base_sequence[: cutoff + 1]

    # e2e-manual: run through gate, leave finalize pending for explicit confirmation
    if self.mode == "e2e-manual":
        cutoff = base_sequence.index("gate")
        return base_sequence[: cutoff + 1]

    return base_sequence

def execute(
    self,
    executor: Dict[str, Callable[[HarperNodeDefinition], NodeExecutionResult]],
    run_directory: Optional[Path] = None,
) -> Dict[str, HarperNodeState]:
    """
    Sequential execution loop. A node is executed when all dependencies are completed
    or skipped. The executor is a mapping from node key to a callable that returns
    NodeExecutionResult.
    """
    for node_key in self.auto_run_nodes_for_mode():
        node_def = self.nodes[node_key]
        node_state = self.state[node_key]

        if node_state.status in {NodeStatus.COMPLETED, NodeStatus.SKIPPED}:
            continue

        if not self._is_ready(node_def):
            continue

        if node_state.status == NodeStatus.PENDING:
            node_state.status = NodeStatus.READY

        node_state.status = NodeStatus.RUNNING
        node_state.started_at = datetime.utcnow().isoformat() + "Z"

        try:
            executor_fn = executor.get(node_key)
            if executor_fn is None:
                raise ValueError(f"No executor provided for node '{node_key}'")
            result = executor_fn(node_def)
            node_state.status = result.status
            node_state.error = result.error
            node_state.artifacts = result.artifacts
            node_state.details = result.details
        except Exception as exc:  # pragma: no cover - defensive
            node_state.status = NodeStatus.FAILED
            node_state.error = str(exc)

        node_state.completed_at = datetime.utcnow().isoformat() + "Z"

        if run_directory:
            self.save(run_directory)

        if node_state.status == NodeStatus.FAILED:
            break

        self._mark_ready_nodes()

    return self.state

def _mark_ready_nodes(self) -> None:
    for key, definition in self.nodes.items():
        state = self.state[key]
        if state.status != NodeStatus.PENDING:
            continue
        if self._is_ready(definition):
            state.status = NodeStatus.READY

        if definition.optional and self.start_from == "spec" and key == "idea":
            state.status = NodeStatus.SKIPPED

def _is_ready(self, definition: HarperNodeDefinition) -> bool:
    return all(
        self.state[dep].status in {NodeStatus.COMPLETED, NodeStatus.SKIPPED}
        for dep in definition.depends_on
    )

def to_dict(self) -> Dict[str, Dict]:
    return {
        "run_id": self.run_id,
        "mode": self.mode,
        "start_from": self.start_from,
        "nodes": {key: asdict(defn) for key, defn in self.nodes.items()},
        "state": {
            key: {
                "status": state.status.value,
                "error": state.error,
                "started_at": state.started_at,
                "completed_at": state.completed_at,
                "artifacts": state.artifacts,
                "details": state.details,
            }
            for key, state in self.state.items()
        },
    }

def describe(self) -> List[Dict[str, str]]:
    """
    Produce a lightweight summary useful for telemetry or UI layers.
    """
    summary = []
    for key in self.nodes:
        state = self.state[key]
        summary.append(
            {
                "node": key,
                "status": state.status.value,
                "error": state.error or "",
            }
        )
    return summary

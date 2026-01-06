from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

class NodeStatus(str, Enum):
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"

@dataclass
class HarperNodeDefinition:
    key: str
    label: str
    depends_on: List[str] = field(default_factory=list)
    optional: bool = False

@dataclass
class HarperNodeState:
    status: NodeStatus = NodeStatus.PENDING
    error: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    artifacts: Dict[str, Any] = field(default_factory=dict)
    details: Dict[str, Any] = field(default_factory=dict)

@dataclass
class NodeExecutionResult:
    status: NodeStatus
    error: Optional[str] = None
    artifacts: Dict[str, Any] = field(default_factory=dict)
    details: Dict[str, Any] = field(default_factory=dict)

def build_default_nodes(start_from: str = "auto") -> List[HarperNodeDefinition]:
    start_from = (start_from or "auto").lower()
    include_idea = start_from != "spec"

    nodes: List[HarperNodeDefinition] = []

    if include_idea:
        nodes.append(HarperNodeDefinition(key="idea", label="IdeaNode", depends_on=[]))
    else:
        nodes.append(
            HarperNodeDefinition(
                key="idea",
                label="IdeaNode",
                depends_on=[],
                optional=True,
            )
        )

    nodes.extend(
        [
            HarperNodeDefinition(
                key="spec",
                label="SpecNode",
                depends_on=[] if include_idea else ["idea"],
            ),
            HarperNodeDefinition(
                key="plan",
                label="PlanNode",
                depends_on=["spec"],
            ),
            HarperNodeDefinition(
                key="lane_guides",
                label="LaneGuidesNode",
                depends_on=["plan"],
            ),
            HarperNodeDefinition(
                key="ltc_howto",
                label="LtcHowtoNode",
                depends_on=["lane_guides"],
            ),
            HarperNodeDefinition(
                key="kit",
                label="KitNode",
                depends_on=["ltc_howto"],
            ),
            HarperNodeDefinition(
                key="eval",
                label="EvalNode",
                depends_on=["kit"],
            ),
            HarperNodeDefinition(
                key="gate",
                label="GateNode",
                depends_on=["eval"],
            ),
            HarperNodeDefinition(
                key="finalize",
                label="FinalizeNode",
                depends_on=["gate"],
            ),
        ]
    )

    return nodes

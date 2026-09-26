"""SPARC Methodology Orchestrator for structured software engineering.

Guides agents through the 5-phase SPARC engineering lifecycle:
- S: Specification (Requirements & acceptance criteria)
- P: Pseudocode (Algorithmic logic & state flow)
- A: Architecture (Components, interfaces, and schemas)
- R: Refinement (TDD, implementation, and security review)
- C: Completion (Validation, test coverage, and documentation)
"""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Optional

from langchain_core.tools import tool


class SPARCPhase(str, Enum):
    SPECIFICATION = "specification"
    PSEUDOCODE = "pseudocode"
    ARCHITECTURE = "architecture"
    REFINEMENT = "refinement"
    COMPLETION = "completion"


@dataclass
class SPARCPhaseResult:
    phase: SPARCPhase
    status: str = "pending"  # pending, in_progress, completed, failed
    artifacts: dict[str, Any] = field(default_factory=dict)
    summary: str = ""
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["phase"] = self.phase.value
        return d


@dataclass
class SPARCProject:
    project_id: str
    feature_name: str
    current_phase: SPARCPhase = SPARCPhase.SPECIFICATION
    phase_results: dict[str, SPARCPhaseResult] = field(default_factory=dict)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    completed_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "feature_name": self.feature_name,
            "current_phase": self.current_phase.value,
            "phase_results": {k: v.to_dict() for k, v in self.phase_results.items()},
            "created_at": self.created_at,
            "completed_at": self.completed_at,
        }


class SPARCOrchestrator:
    """Orchestrates structured 5-phase SPARC development workflows."""

    def __init__(self):
        self._projects: dict[str, SPARCProject] = {}

    def start_feature(self, feature_name: str, requirements: str) -> SPARCProject:
        """Initialize a new SPARC development project with initial Specification."""
        project_id = str(uuid.uuid4())[:8]
        proj = SPARCProject(project_id=project_id, feature_name=feature_name)

        # 1. Specification phase
        spec_result = SPARCPhaseResult(
            phase=SPARCPhase.SPECIFICATION,
            status="completed",
            summary=f"Specified requirements for {feature_name}",
            artifacts={
                "requirements": requirements,
                "acceptance_criteria": [
                    "Must satisfy functional inputs/outputs",
                    "Must pass all unit and edge case tests",
                    "Must be secure with no hardcoded credentials",
                ],
            },
        )
        proj.phase_results[SPARCPhase.SPECIFICATION.value] = spec_result
        proj.current_phase = SPARCPhase.PSEUDOCODE
        self._projects[project_id] = proj
        return proj

    def advance_phase(
        self,
        project_id: str,
        artifacts: dict[str, Any],
        summary: str = "",
    ) -> dict[str, Any]:
        """Advance the SPARC project to the next phase with recorded artifacts."""
        proj = self._projects.get(project_id)
        if not proj:
            return {"error": f"Project {project_id} not found."}

        phase_order = [
            SPARCPhase.SPECIFICATION,
            SPARCPhase.PSEUDOCODE,
            SPARCPhase.ARCHITECTURE,
            SPARCPhase.REFINEMENT,
            SPARCPhase.COMPLETION,
        ]
        curr_idx = phase_order.index(proj.current_phase)
        completed_phase = phase_order[curr_idx]

        # Record result for current phase
        proj.phase_results[completed_phase.value] = SPARCPhaseResult(
            phase=completed_phase,
            status="completed",
            artifacts=artifacts,
            summary=summary or f"Completed {completed_phase.value} phase.",
        )

        if curr_idx + 1 < len(phase_order):
            proj.current_phase = phase_order[curr_idx + 1]
            return {
                "status": "advanced",
                "next_phase": proj.current_phase.value,
                "project": proj.to_dict(),
            }
        else:
            proj.completed_at = datetime.now(timezone.utc).isoformat()
            return {
                "status": "completed",
                "message": "All 5 SPARC phases finished successfully!",
                "project": proj.to_dict(),
            }

    def get_project(self, project_id: str) -> Optional[dict[str, Any]]:
        """Retrieve full state of a SPARC project."""
        proj = self._projects.get(project_id)
        return proj.to_dict() if proj else None


sparc_orchestrator = SPARCOrchestrator()


@tool
def start_sparc_development(
    feature_name: str, requirements: str
) -> dict[str, Any]:
    """Start a structured SPARC 5-phase software development lifecycle for a new feature.

    Args:
        feature_name: Name of the feature or component.
        requirements: Detailed requirements and acceptance criteria.
    """
    proj = sparc_orchestrator.start_feature(feature_name, requirements)
    return proj.to_dict()

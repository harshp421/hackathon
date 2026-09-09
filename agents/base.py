"""
Base Domain Agent definition.
Enforces semantic registry validation, evidence collection, and contract building.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List
import uuid

from contracts import EvidenceContract, RootEntity, StagedAction
from graph_service import GraphService


class DomainAgent(ABC):
    name: str
    supported_contexts: List[str]
    supported_entities: List[str]

    def __init__(self, graph_service: GraphService):
        self.graph_service = graph_service

    @abstractmethod
    def run(self, params: Dict[str, Any]) -> EvidenceContract:
        """Execute domain investigation and return a verified EvidenceContract."""
        raise NotImplementedError

    def _generate_request_id(self) -> str:
        return f"req-{uuid.uuid4().hex[:8]}"

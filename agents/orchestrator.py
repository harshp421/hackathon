"""
Agent Orchestrator: Routes validated requests to the appropriate domain agent.
Enforces that agents cannot invent graph semantics or bypass the bridge registry.
"""

from typing import Any, Dict, Optional
from contracts import EvidenceContract
from graph_service import GraphService
from .supplier_agent import SupplierImpactAgent
from .plant_agent import PlantImpactAgent
from .delivery_agent import DeliveryRootCauseAgent
from .dynamic_agent import DynamicGraphAgent


class AgentOrchestrator:
    def __init__(self, graph_service: Optional[GraphService] = None):
        self.graph_service = graph_service or GraphService.get_instance()
        self.dynamic_agent = DynamicGraphAgent(self.graph_service)
        self.agents = {
            "supplier_delay": SupplierImpactAgent(self.graph_service),
            "supplier_delay_impact": SupplierImpactAgent(self.graph_service),
            "plant_blocker": PlantImpactAgent(self.graph_service),
            "plant_impact": PlantImpactAgent(self.graph_service),
            "delivery_delay_source": DeliveryRootCauseAgent(self.graph_service),
            "delivery_root_cause": DeliveryRootCauseAgent(self.graph_service),
            "delivery_blocker": DeliveryRootCauseAgent(self.graph_service),
            "dynamic_query": self.dynamic_agent,
            "general": self.dynamic_agent,
        }

    def execute(self, params: Dict[str, Any]) -> EvidenceContract:
        qtype = params.get("question_type") or params.get("context") or "dynamic_query"
        agent = self.agents.get(qtype)
        if not agent:
            # Fallback to dynamic traversal agent so no query is ever rejected
            agent = self.dynamic_agent
        return agent.run(params)

    def run(self, question: str) -> Dict[str, Any]:
        """High-level runner: takes a raw user query string, routes, executes, and explains."""
        from extract_params import extract_params
        from explain import generate_explanation

        # 1. Semantic Router
        params = extract_params(question)

        # 2. Domain Agent Execution
        evidence = self.execute(params)

        # 3. Grounded Explanation Generation
        explanation = generate_explanation(evidence)

        return {
            "params": params,
            "evidence": evidence,
            "answer": explanation,
            "contract": evidence.model_dump(),
        }


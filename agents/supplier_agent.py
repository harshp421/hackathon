"""
Supplier Impact Agent: Investigates downstream blast radius from a supplier disruption.
"""

from typing import Any, Dict, List
from contracts import EvidenceContract, RootEntity, StagedAction
from .base import DomainAgent
from .mitigation_agent import MitigationAgent
from impact_engine import calculate_metrics, calculate_confidence


class SupplierImpactAgent(DomainAgent):
    name: str = "SupplierImpactAgent"
    supported_contexts: List[str] = ["supplier_delay"]
    supported_entities: List[str] = ["Supplier"]

    def run(self, params: Dict[str, Any]) -> EvidenceContract:
        supplier_name = params.get("supplier_name") or params.get("target") or "Acme Fasteners"
        raw_graph = self.graph_service.query_supplier_impact(supplier_name)
        if not raw_graph or not raw_graph.get("supplier"):
            if "acme" in supplier_name.lower():
                raise ValueError(
                    f"Supplier '{supplier_name}' was part of the earlier synthetic mockup dataset. "
                    f"The Neo4j database has since been populated with the active SAP dataset. "
                    f"Try querying 'Domestic US Supplier 1' or 'Carbon Tec Inc.'!"
                )
            raise ValueError(f"Supplier '{supplier_name}' not found in knowledge graph.")

        s = raw_graph["supplier"]
        root = RootEntity(type="Supplier", id=s["id"], name=s.get("name"))

        # Calculate deterministic metrics
        metrics = calculate_metrics(raw_graph, context="supplier_delay")
        confidence = calculate_confidence(raw_graph, context="supplier_delay")

        # Discover alternate suppliers (Prescriptive Mitigation)
        mitigation_agent = MitigationAgent(self.graph_service)
        material_ids = [m["id"] for m in raw_graph.get("materials", [])]
        mitigations = mitigation_agent.find_alternatives(material_ids, excluded_supplier_id=s["id"])

        # Stage human-in-the-loop action if mitigation exists
        staged_actions = []
        if mitigations and s.get("delayed"):
            top_alt = mitigations[0]
            staged_actions.append(
                mitigation_agent.stage_purchase_requisition(
                    top_alt,
                    plant_id="1000",
                    quantity=max(100, metrics.total_delayed_quantity),
                )
            )

        lineage = ["LFA1", "EKKO", "EKPO", "MARC", "RESB", "AFKO", "LIKP", "LIPS"]

        return EvidenceContract(
            request_id=self._generate_request_id(),
            intent="SUPPLIER_IMPACT",
            context="supplier_delay",
            root_entity=root,
            raw_graph=raw_graph,
            metrics=metrics,
            mitigations=mitigations,
            staged_actions=staged_actions,
            lineage=lineage,
            confidence=confidence,
            limitations=["Lead times based on active SAP contracts; expedited transit not factored."],
            user_question=params.get("raw_question"),
        )

"""
Plant Impact Agent: Investigates production halts, maintenance bottlenecks, and blocker impacts at a plant.
"""

from typing import Any, Dict, List
from contracts import EvidenceContract, RootEntity, StagedAction
from .base import DomainAgent
from impact_engine import calculate_metrics, calculate_confidence


class PlantImpactAgent(DomainAgent):
    name: str = "PlantImpactAgent"
    supported_contexts: List[str] = ["plant_blocker", "plant_delay"]
    supported_entities: List[str] = ["Plant"]

    def run(self, params: Dict[str, Any]) -> EvidenceContract:
        plant_id = params.get("target") or params.get("plant_id") or "1000"
        raw_graph = self.graph_service.query_plant_blocker_impact(plant_id)
        if not raw_graph or not raw_graph.get("plant"):
            available = [f"{p['id']} ({p.get('name', '')})" for p in self.graph_service.get_available_entities().get("plants", [])]
            raise ValueError(f"Plant '{plant_id}' does not exist in the SAP Knowledge Graph. Valid plants: {', '.join(available)}.")

        p = raw_graph["plant"]
        root = RootEntity(type="Plant", id=p["id"], name=p.get("name"))

        # Calculate deterministic metrics
        metrics = calculate_metrics(raw_graph, context="plant_blocker")
        confidence = calculate_confidence(raw_graph, context="plant_blocker")

        # Staged Action: Propose rescheduling production orders in SAP CO02
        staged_actions = []
        orders = raw_graph.get("production_orders", [])
        if orders:
            order_ids = [o["id"] for o in orders[:3]]
            staged_actions.append(
                StagedAction(
                    action_type="RESCHEDULE_PRODUCTION_ORDERS",
                    sap_transaction="CO02",
                    description=f"Shift finish dates +7 days for orders ({', '.join(order_ids)}) due to plant blocker",
                    payload={"plant_id": p["id"], "order_ids": order_ids, "days_shift": 7},
                    status="PENDING_APPROVAL",
                )
            )

        lineage = ["T001W", "AFKO", "RESB", "LIKP", "LIPS"]

        return EvidenceContract(
            request_id=self._generate_request_id(),
            intent="PLANT_IMPACT",
            context="plant_blocker",
            root_entity=root,
            raw_graph=raw_graph,
            metrics=metrics,
            mitigations=[],
            staged_actions=staged_actions,
            lineage=lineage,
            confidence=confidence,
            limitations=["Assumes all production lines at the plant share the reported disruption."],
            user_question=params.get("raw_question"),
        )

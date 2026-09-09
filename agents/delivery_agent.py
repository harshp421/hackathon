"""
Delivery Root Cause Agent: Investigates upstream bottlenecks causing delivery delays.
"""

from typing import Any, Dict, List
from contracts import EvidenceContract, RootEntity
from .base import DomainAgent
from .mitigation_agent import MitigationAgent
from impact_engine import calculate_metrics, calculate_confidence


class DeliveryRootCauseAgent(DomainAgent):
    name: str = "DeliveryRootCauseAgent"
    supported_contexts: List[str] = ["delivery_delay_source", "delivery_blocker"]
    supported_entities: List[str] = ["Delivery", "DeliveryNetwork"]

    def run(self, params: Dict[str, Any]) -> EvidenceContract:
        target = (params.get("target") or "").strip()
        raw_question = params.get("raw_question")

        # Network-wide delivery blockers investigation
        if target in ("ALL_BLOCKED", "ALL", "None", "") or not target.startswith("D-"):
            raw_graph = self.graph_service.query_all_delivery_blockers()
            if not raw_graph or not raw_graph.get("deliveries"):
                # Fallback if no delivery blockers found
                raw_graph = raw_graph or {"deliveries": [], "materials": [], "production_orders": [], "delayed_suppliers": []}

            delivs = raw_graph.get("deliveries", [])
            root = RootEntity(
                type="DeliveryNetwork",
                id="NETWORK_DELIVERIES",
                name=f"Customer Deliveries at Risk ({len(delivs)} Shipments)",
            )

            metrics = calculate_metrics(raw_graph, context="delivery_blocker")
            confidence = calculate_confidence(raw_graph, context="delivery_blocker")

            # Identify alternate suppliers for components tied to delayed suppliers
            mitigation_agent = MitigationAgent(self.graph_service)
            materials = raw_graph.get("materials", [])
            material_ids = [m["id"] for m in materials if m.get("id")]
            mitigations = mitigation_agent.find_alternatives(material_ids[:5])

            staged_actions = []
            if mitigations:
                top_alt = mitigations[0]
                staged_actions.append(
                    mitigation_agent.stage_purchase_requisition(
                        top_alt,
                        plant_id="1000",
                        quantity=max(100, metrics.total_delayed_quantity),
                    )
                )

            lineage = ["LIKP", "LIPS", "AFKO", "RESB", "EKKO", "LFA1"]

            return EvidenceContract(
                request_id=self._generate_request_id(),
                intent="DELIVERY_BLOCKERS",
                context="delivery_blocker",
                root_entity=root,
                raw_graph=raw_graph,
                metrics=metrics,
                mitigations=mitigations,
                staged_actions=staged_actions,
                lineage=lineage,
                confidence=confidence,
                limitations=["Network-wide delivery risk is determined by upstream supplier delays and order statuses."],
                user_question=raw_question,
            )


        # Single delivery root cause investigation
        delivery_id = target
        raw_graph = self.graph_service.query_delivery_delay_source(delivery_id)
        if not raw_graph or not raw_graph.get("delivery"):
            # If specified delivery not found, try all delivery blockers
            return self.run({"target": "ALL_BLOCKED", "raw_question": raw_question})

        d = raw_graph["delivery"]
        root = RootEntity(type="Delivery", id=d["id"], name=d.get("customer_name"))

        metrics = calculate_metrics(raw_graph, context="delivery_delay_source")
        confidence = calculate_confidence(raw_graph, context="delivery_delay_source")

        # Discover alternate suppliers for the component parts
        mitigation_agent = MitigationAgent(self.graph_service)
        materials = raw_graph.get("materials", [])
        material_ids = [m["id"] for m in materials]
        mitigations = mitigation_agent.find_alternatives(material_ids)

        lineage = ["LIKP", "LIPS", "AFKO", "RESB", "EKKO", "LFA1"]

        return EvidenceContract(
            request_id=self._generate_request_id(),
            intent="DELIVERY_ROOT_CAUSE",
            context="delivery_delay_source",
            root_entity=root,
            raw_graph=raw_graph,
            metrics=metrics,
            mitigations=mitigations,
            staged_actions=[],
            lineage=lineage,
            confidence=confidence,
            limitations=["Root cause analysis evaluates active purchase orders and supplier delay statuses."],
            user_question=raw_question,
        )


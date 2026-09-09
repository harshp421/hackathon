"""
Semantic Control Plane: Context Profiles.
Defines business situation routing priors and preferred traversals.
"""

from typing import Dict
from .ontology import ContextProfile

CONTEXT_PROFILES: Dict[str, ContextProfile] = {
    "supplier_delay": ContextProfile(
        name="supplier_delay",
        version="1.0.0",
        root_entity="Supplier",
        primary_agent="SupplierImpactAgent",
        trigger_concepts=[
            "supplier delayed",
            "vendor delayed",
            "supplier disruption",
            "blast radius",
            "customs hold",
            "late delivery",
        ],
        preferred_traversal=["SUPPLIES", "REQUIRED_FOR", "FULFILLS"],
        metrics=[
            "affected_materials",
            "affected_production_orders",
            "affected_deliveries",
            "inventory_buffer_absorption",
            "revenue_exposure",
        ],
        required_evidence=["supplier_id", "material_id", "production_order_id"],
    ),
    "plant_blocker": ContextProfile(
        name="plant_blocker",
        version="1.0.0",
        root_entity="Plant",
        primary_agent="PlantImpactAgent",
        trigger_concepts=[
            "plant blocked",
            "plant blocker",
            "production blocker",
            "plant shutdown",
            "plant disruption",
            "production halted",
        ],
        preferred_traversal=["RUNS_AT", "FULFILLS"],
        metrics=[
            "affected_production_orders",
            "affected_deliveries",
            "affected_quantity",
            "revenue_exposure",
        ],
        required_evidence=["plant_id", "production_order_id", "delivery_id"],
    ),
    "material_shortage": ContextProfile(
        name="material_shortage",
        version="1.0.0",
        root_entity="Material",
        primary_agent="MaterialRiskAgent",
        trigger_concepts=[
            "material shortage",
            "part shortage",
            "stockout",
            "component missing",
        ],
        preferred_traversal=["REQUIRED_FOR", "USED_AT", "FULFILLS"],
        metrics=[
            "affected_production_orders",
            "affected_plants",
            "inventory_exposure",
        ],
        required_evidence=["material_id", "production_order_id"],
    ),
    "delivery_delay_source": ContextProfile(
        name="delivery_delay_source",
        version="1.0.0",
        root_entity="Delivery",
        primary_agent="DeliveryRootCauseAgent",
        trigger_concepts=[
            "delivery at risk",
            "shipment delay",
            "root cause",
            "why is delivery delayed",
            "which supplier could delay",
        ],
        preferred_traversal=["FULFILLS", "REQUIRED_FOR", "SUPPLIES"],
        metrics=[
            "likely_root_causes",
            "affected_production_orders",
            "material_dependencies",
            "supplier_dependencies",
        ],
        required_evidence=["delivery_id", "production_order_id", "supplier_id"],
    ),
    "mitigation_search": ContextProfile(
        name="mitigation_search",
        version="1.0.0",
        root_entity="Supplier",
        primary_agent="MitigationAgent",
        trigger_concepts=[
            "mitigation",
            "alternate supplier",
            "alternative vendor",
            "backup supplier",
            "recommend action",
        ],
        preferred_traversal=["SUPPLIES"],
        metrics=["alternate_suppliers", "lead_time_variance", "transfer_feasibility"],
        required_evidence=["material_id", "alternate_supplier_id"],
    ),
}

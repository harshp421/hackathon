"""
Semantic Control Plane: Bridge Registry.
Governs semantic transitions between entity types and enforces agent traversal policy.
"""

from typing import Dict, List
from .ontology import BridgeDefinition

BRIDGES: Dict[str, BridgeDefinition] = {
    "supplier_to_material": BridgeDefinition(
        name="supplier_to_material",
        from_entity="Supplier",
        relationship="SUPPLIES",
        to_entity="Material",
        purpose=["supplier_delay", "material_risk", "mitigation"],
        allowed_agents=["SupplierImpactAgent", "MitigationAgent", "DeliveryRootCauseAgent"],
    ),
    "material_to_plant": BridgeDefinition(
        name="material_to_plant",
        from_entity="Material",
        relationship="USED_AT",
        to_entity="Plant",
        purpose=["inventory_location", "stock_analysis"],
        allowed_agents=["SupplierImpactAgent", "MaterialRiskAgent", "PlantImpactAgent"],
    ),
    "material_to_production": BridgeDefinition(
        name="material_to_production",
        from_entity="Material",
        relationship="REQUIRED_FOR",
        to_entity="ProductionOrder",
        purpose=["material_shortage", "supplier_delay", "production_dependency"],
        allowed_agents=["SupplierImpactAgent", "MaterialRiskAgent", "DeliveryRootCauseAgent"],
    ),
    "production_to_plant": BridgeDefinition(
        name="production_to_plant",
        from_entity="ProductionOrder",
        relationship="RUNS_AT",
        to_entity="Plant",
        purpose=["production_location", "plant_blocker"],
        allowed_agents=["PlantImpactAgent", "SupplierImpactAgent", "DeliveryRootCauseAgent"],
    ),
    "production_to_delivery": BridgeDefinition(
        name="production_to_delivery",
        from_entity="ProductionOrder",
        relationship="FULFILLS",
        to_entity="Delivery",
        purpose=["delivery_impact", "customer_risk"],
        allowed_agents=["PlantImpactAgent", "SupplierImpactAgent", "DeliveryRootCauseAgent"],
    ),
}


def validate_traversal(agent_name: str, relationship: str) -> bool:
    """Validate whether an agent has authorization to traverse a specific relationship."""
    for bridge in BRIDGES.values():
        if bridge.relationship == relationship:
            if agent_name in bridge.allowed_agents:
                return True
    return False

"""
Mitigation Agent: Finds alternate qualified suppliers and proposes actionable recovery options.
"""

from typing import Any, Dict, List
from contracts import MitigationOption, StagedAction
from graph_service import GraphService


class MitigationAgent:
    name: str = "MitigationAgent"

    def __init__(self, graph_service: GraphService):
        self.graph_service = graph_service

    def find_alternatives(self, material_ids: List[str], excluded_supplier_id: str = "") -> List[MitigationOption]:
        """Find non-delayed alternate suppliers for affected materials."""
        raw_options = self.graph_service.query_alternate_suppliers(material_ids, excluded_supplier_id)
        mitigations = []
        for row in raw_options:
            price = None
            if row.get("price_per_unit"):
                try:
                    price = float(row["price_per_unit"])
                except (ValueError, TypeError):
                    pass
            mitigations.append(
                MitigationOption(
                    material_id=row["material_id"],
                    material_name=row.get("material_name", row["material_id"]),
                    alternate_supplier_id=row["alternate_supplier_id"],
                    alternate_supplier_name=row.get("alternate_supplier_name", row["alternate_supplier_id"]),
                    alternate_supplier_country=row.get("alternate_supplier_country", "EU"),
                    lead_time_days=int(row.get("lead_time_days") or 5),
                    price_per_unit=price,
                    contract_id=row.get("contract_id"),
                    recommendation_score=0.95,
                )
            )
        return mitigations

    def stage_purchase_requisition(self, option: MitigationOption, plant_id: str = "1000", quantity: int = 100) -> StagedAction:
        """Stage a draft SAP ME51N Purchase Requisition."""
        return StagedAction(
            action_type="DRAFT_PURCHASE_REQUISITION",
            sap_transaction="ME51N",
            description=f"Expedite backup order of {quantity} units of {option.material_name} from {option.alternate_supplier_name}",
            payload={
                "vendor_id": option.alternate_supplier_id,
                "vendor_name": option.alternate_supplier_name,
                "material_id": option.material_id,
                "plant_id": plant_id,
                "quantity": quantity,
                "contract_reference": option.contract_id,
                "lead_time_days": option.lead_time_days,
            },
            status="PENDING_APPROVAL",
        )

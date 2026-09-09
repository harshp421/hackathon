"""
Data Contracts and Schema definitions for the Agentic Knowledge Graph.
Standard Evidence Contract used between Graph Service, Impact Engine, and Grounded Explainer.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class RootEntity(BaseModel):
    type: str
    id: str
    name: Optional[str] = None


class MetricSummary(BaseModel):
    affected_production_orders: int = 0
    affected_deliveries: int = 0
    affected_plants: int = 0
    affected_materials: int = 0
    total_delayed_quantity: int = 0
    revenue_exposure_eur: float = 0.0
    earliest_impact_date: Optional[str] = None
    inventory_buffer_status: str = "NO_BUFFER"  # "BUFFERED", "PARTIAL", "CRITICAL_SHORTAGE"
    buffer_details: List[str] = Field(default_factory=list)
    risk_breakdown: List[Dict[str, Any]] = Field(default_factory=list)


class MitigationOption(BaseModel):
    material_id: str
    material_name: str
    alternate_supplier_id: str
    alternate_supplier_name: str
    alternate_supplier_country: str
    lead_time_days: int
    price_per_unit: Optional[float] = None
    contract_id: Optional[str] = None
    recommendation_score: float = 1.0


class StagedAction(BaseModel):
    action_type: str  # e.g., "DRAFT_PURCHASE_REQUISITION", "ORDER_RESCHEDULE"
    sap_transaction: str  # e.g., "ME51N", "CO02"
    description: str
    payload: Dict[str, Any]
    status: str = "PENDING_APPROVAL"


class ConfidenceScore(BaseModel):
    level: str = "HIGH"  # "HIGH", "MEDIUM", "LOW"
    score: float = 0.95
    factors: List[str] = Field(default_factory=list)


class EvidenceContract(BaseModel):
    request_id: str
    intent: str
    context: str
    root_entity: RootEntity
    raw_graph: Dict[str, Any] = Field(default_factory=dict)
    metrics: MetricSummary
    mitigations: List[MitigationOption] = Field(default_factory=list)
    staged_actions: List[StagedAction] = Field(default_factory=list)
    lineage: List[str] = Field(default_factory=list)
    confidence: ConfidenceScore
    limitations: List[str] = Field(default_factory=list)
    user_question: Optional[str] = None


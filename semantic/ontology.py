"""
Semantic Control Plane: Pydantic models for Entity Meta Blocks, Context Profiles,
Bridge Definitions, and Metrics.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class EntityIdentity(BaseModel):
    key: str = "id"
    label: str


class SapMapping(BaseModel):
    source_tables: List[str] = Field(default_factory=list)
    primary_field: Optional[str] = None


class EntityRelationships(BaseModel):
    incoming: List[str] = Field(default_factory=list)
    outgoing: List[str] = Field(default_factory=list)


class EntityMetaBlock(BaseModel):
    entity: str
    version: str = "1.0.0"
    identity: EntityIdentity
    sap: SapMapping
    properties: List[str] = Field(default_factory=list)
    relationships: EntityRelationships
    metrics: List[str] = Field(default_factory=list)
    contexts: List[str] = Field(default_factory=list)
    agent: Dict[str, Any] = Field(default_factory=dict)
    security: Dict[str, str] = Field(default_factory=lambda: {"classification": "internal"})


class ContextProfile(BaseModel):
    name: str
    version: str = "1.0.0"
    root_entity: str
    primary_agent: str
    trigger_concepts: List[str] = Field(default_factory=list)
    preferred_traversal: List[str] = Field(default_factory=list)
    metrics: List[str] = Field(default_factory=list)
    required_evidence: List[str] = Field(default_factory=list)


class BridgeDefinition(BaseModel):
    name: str
    from_entity: str
    relationship: str
    to_entity: str
    purpose: List[str] = Field(default_factory=list)
    allowed_agents: List[str] = Field(default_factory=list)


class MetricDefinition(BaseModel):
    name: str
    version: str = "1.0.0"
    description: str
    inputs: List[str] = Field(default_factory=list)
    calculation_mode: str = "deterministic"
    formula: str
    missing_value_policy: str = "return_unknown"
    owner: str = "impact-engine"

# SAP Agentic Supply Chain Control Plane: Comprehensive Architecture, Agents, Orchestration & Prompt Specification

This document provides the complete end-to-end technical reference for the **SAP Agentic Supply Chain Control Plane**, covering the enterprise architecture, graph database foundation, domain microservice agents, orchestration layer, data contract schemas, prompt ignition pipeline, and runtime execution traces.

---

## 1. System Architecture Overview

The system bridges unstructured natural language supply chain inquiries with deterministic enterprise SAP ERP data using a Graph-RAG (Retrieval-Augmented Generation) and multi-agent control plane.

```
                      ┌───────────────────────────────────────────────┐
                      │              User Inquiry / UI                │
                      │  ("is there any delivery blocker?", etc.)     │
                      └──────────────────────┬────────────────────────┘
                                             │
                                             ▼
                      ┌───────────────────────────────────────────────┐
                      │             Semantic Router Agent             │
                      │        (extract_params.py / SYSTEM_PROMPT)    │
                      └──────────────────────┬────────────────────────┘
                                             │
                       ┌─────────────────────┼──────────────────────┐
                       ▼                     ▼                      ▼
        ┌─────────────────────────┐┌───────────────────┐┌───────────────────────┐
        │  Delivery Domain Srv    ││Supplier Impact Srv││ Plant Blocker Srv    │
        │(DeliveryRootCauseAgent) ││(SupplierImpact)   ││ (PlantImpactAgent)   │
        └────────────┬────────────┘└─────────┬─────────┘└───────────┬───────────┘
                     │                       │                      │
                     └───────────────────────┼──────────────────────┘
                                             ▼
                      ┌───────────────────────────────────────────────┐
                      │             Neo4j Graph Service               │
                      │   (Bolt Driver, Cypher Templates, AuraDB)     │
                      └──────────────────────┬────────────────────────┘
                                             │
                                             ▼
                      ┌───────────────────────────────────────────────┐
                      │      Deterministic Impact & Sourcing Engine   │
                      │  (Safety Stock, Revenue Exposure, Lead Times) │
                      └──────────────────────┬────────────────────────┘
                                             │
                                             ▼
                      ┌───────────────────────────────────────────────┐
                      │           Evidence Contract (JSON)            │
                      │     (Zero-Hallucination Grounded State)       │
                      └──────────────────────┬────────────────────────┘
                                             │
                                             ▼
                      ┌───────────────────────────────────────────────┐
                      │         Grounded Explainer Agent              │
                      │   (Dynamic Section Prompt Synthesis)          │
                      └──────────────────────┬────────────────────────┘
                                             │
                                             ▼
                      ┌───────────────────────────────────────────────┐
                      │       Interactive Control Plane (app.py)      │
                      │  (Blast Radius, PyVis Graph, Staging, HITL)   │
                      └───────────────────────────────────────────────┘
```

---

## 2. Graph Foundation & SAP ERP Schema

The knowledge graph is modeled directly upon standard SAP S/4HANA ERP tables.

### A. Graph Entities (Nodes) & Table Provenance

| Node Label            | Identifier              | Sample Attributes                                                  | SAP ERP Source Table    | Business Description                            |
| :-------------------- | :---------------------- | :----------------------------------------------------------------- | :---------------------- | :---------------------------------------------- |
| **`Supplier`**        | `id` (e.g. `100234`)    | `name`, `country`, `delayed`, `delay_reason`                       | **`LFA1`** / **`LFM1`** | Vendor master & purchasing organization data    |
| **`Material`**        | `id` (e.g. `M-1001`)    | `description`, `material_type`, `unit_of_measure`                  | **`MARA`** / **`MAKT`** | General material master & descriptions          |
| **`Plant`**           | `id` (e.g. `1000`)      | `name`, `country`                                                  | **`T001W`**             | Manufacturing plants & production facilities    |
| **`ProductionOrder`** | `id` (e.g. `PO-500001`) | `product_description`, `quantity`, `planned_finish_date`, `status` | **`AFKO`** / **`AFPO`** | Manufacturing order headers & line items        |
| **`Delivery`**        | `id` (e.g. `D-900001`)  | `customer_name`, `quantity`, `ship_date`                           | **`LIKP`** / **`LIPS`** | Outbound customer shipments & fulfillment lines |

### B. Graph Relationships (Edges)

| Relationship Type  | Source Node       | Target Node       | Relationship Properties                                  | SAP Functional Context                                     |
| :----------------- | :---------------- | :---------------- | :------------------------------------------------------- | :--------------------------------------------------------- |
| **`SUPPLIES`**     | `Supplier`        | `Material`        | `price_per_unit`, `planned_delivery_days`, `contract_id` | Purchasing Info Record (`EINA`) & Contract (`EKKO`/`EKPO`) |
| **`USED_AT`**      | `Material`        | `Plant`           | `unrestricted_stock`, `safety_stock`, `reorder_point`    | Plant Stock Segment (`MARC-LABST`, `MARC-EISBE`)           |
| **`REQUIRED_FOR`** | `Material`        | `ProductionOrder` | `quantity_per`, `requirement_date`, `total_quantity`     | BOM Component Reservation (`RESB`)                         |
| **`RUNS_AT`**      | `ProductionOrder` | `Plant`           | `production_line`, `work_center`                         | Order Routing / Work Center (`CRHD`)                       |
| **`FULFILLS`**     | `ProductionOrder` | `Delivery`        | `allocated_quantity`                                     | Sales Order / Delivery Item Link (`VBFA` Document Flow)    |

---

## 3. Data Contracts & Pydantic Schemas (`contracts.py`)

All domain agents exchange standardized, strongly-typed Pydantic contracts to eliminate data drift and guarantee complete auditability.

```python
class RootEntity(BaseModel):
    type: str                     # "Supplier", "Plant", "Delivery", "DeliveryNetwork"
    id: str                       # Entity ID or "NETWORK_DELIVERIES"
    name: Optional[str] = None    # Descriptive entity label

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
    action_type: str              # "DRAFT_PURCHASE_REQUISITION", "ORDER_RESCHEDULE"
    sap_transaction: str          # "ME51N", "CO02"
    description: str
    payload: Dict[str, Any]
    status: str = "PENDING_APPROVAL"

class ConfidenceScore(BaseModel):
    level: str = "HIGH"           # "HIGH", "MEDIUM", "LOW"
    score: float = 0.95
    factors: List[str] = Field(default_factory=list)

class EvidenceContract(BaseModel):
    request_id: str
    intent: str                   # e.g. "DELIVERY_BLOCKERS", "SUPPLIER_IMPACT"
    context: str                  # e.g. "delivery_blocker", "supplier_delay"
    root_entity: RootEntity
    raw_graph: Dict[str, Any]
    metrics: MetricSummary
    mitigations: List[MitigationOption] = Field(default_factory=list)
    staged_actions: List[StagedAction] = Field(default_factory=list)
    lineage: List[str] = Field(default_factory=list)
    confidence: ConfidenceScore
    limitations: List[str] = Field(default_factory=list)
    user_question: Optional[str] = None
```

---

## 4. Multi-Agent System & Microservices Data Intents

The system deploys specialized autonomous domain agents orchestrated by [`AgentOrchestrator`](file:///d:/SAP-Hackathon/agents/orchestrator.py).

### Agent Roster & Responsibility Matrix

| Agent Name                   | Module                                                                              | Primary Responsibilities & Graph Path                                                                                                                      | Trigger Inquiries                                                         |
| :--------------------------- | :---------------------------------------------------------------------------------- | :--------------------------------------------------------------------------------------------------------------------------------------------------------- | :------------------------------------------------------------------------ |
| **`SemanticRouter`**         | [`extract_params.py`](file:///d:/SAP-Hackathon/extract_params.py)                   | Classifies intent (`question_type`), extracts target IDs, phrases, and passes `raw_question`.                                                              | All incoming user prompts                                                 |
| **`AgentOrchestrator`**      | [`agents/orchestrator.py`](file:///d:/SAP-Hackathon/agents/orchestrator.py)         | Dispatches request to the active domain agent with fail-safe routing and dependency injection.                                                             | Internal control plane dispatcher                                         |
| **`DeliveryRootCauseAgent`** | [`agents/delivery_agent.py`](file:///d:/SAP-Hackathon/agents/delivery_agent.py)     | **Delivery Domain Service**: Traces single delivery root causes (`D-900007`) and network delivery blockers (`ALL_DELIVERY_BLOCKERS`). Maps dual-blockers.  | "is there any delivery blocker?", "which suppliers delay D-900007?"       |
| **`SupplierImpactAgent`**    | [`agents/supplier_agent.py`](file:///d:/SAP-Hackathon/agents/supplier_agent.py)     | **Supplier Domain Service**: 4-hop blast radius propagation (`Supplier -> Material -> Plant / Order -> Delivery`), stock buffering, draft `ME51N` staging. | "If Acme Fasteners is delayed...", "What is the status of Lyon Polymers?" |
| **`PlantImpactAgent`**       | [`agents/plant_agent.py`](file:///d:/SAP-Hackathon/agents/plant_agent.py)           | **Plant Domain Service**: Calculates halted production lines and stages order rescheduling (`CO02`).                                                       | "There is a blocker at plant 1000", "Munich plant breakdown"              |
| **`DynamicGraphAgent`**      | [`agents/dynamic_agent.py`](file:///d:/SAP-Hackathon/agents/dynamic_agent.py)       | **Dynamic Semantic Service**: Generates read-only Cypher or runs fuzzy neighborhood expansion. Aligns root entities with user keywords.                    | Ad-hoc queries, BOM exploration, stock checks                             |
| **`MitigationAgent`**        | [`agents/mitigation_agent.py`](file:///d:/SAP-Hackathon/agents/mitigation_agent.py) | Discovers non-delayed alternate suppliers in `EKKO`/`EKPO` and generates governed SAP transaction payloads.                                                | Invoked by domain agents                                                  |
| **`ImpactEngine`**           | [`impact_engine.py`](file:///d:/SAP-Hackathon/impact_engine.py)                     | **Deterministic Calculator**: Computes stock absorption (`MARC-LABST`), delivery risk matrices, and EUR exposure outside the LLM.                          | Invoked by all domain agents                                              |
| **`GroundedExplainer`**      | [`explain.py`](file:///d:/SAP-Hackathon/explain.py)                                 | Synthesizes explainable executive narratives strictly bound to the `EvidenceContract` with dynamic section inclusion.                                      | Final stage of all investigations                                         |

---

## 5. Prompt Engineering & Ignition Pipeline

The system uses three distinct prompt layers designed to guarantee **zero hallucination**, dynamic availability, and exact question alignment.

### Layer 1: Semantic Intent Router Prompt (`extract_params.py`)

- **Role**: Translates arbitrary natural language into structured parameters.
- **Ignition**: Triggered on every user input in the search command bar.

```text
You are the Semantic Router Agent for an SAP supply-chain knowledge graph.

The graph has nodes: Supplier, Material, Plant, ProductionOrder, Delivery
connected by: SUPPLIES, USED_AT, REQUIRED_FOR, RUNS_AT, FULFILLS.

Classify the question into one of the authorized business contexts and extract parameters.
Output ONLY a raw JSON object (no markdown, no prose) with exactly these keys:

- "question_type": one of
    "supplier_delay_impact"  - user asks what is affected downstream if a supplier / vendor is delayed
    "plant_blocker"          - user asks what happens if a specific plant is blocked, shut down, or disrupted
    "delivery_delay_source"  - user asks about blocked deliveries, delivery blockers, shipments at risk, or which suppliers cause delivery delays
    "dynamic_query"          - any other question or task querying the knowledge graph (materials, orders, stock, customers, traversal)
- "supplier_name": the supplier name or id, else null
- "target":
    - for plant_blocker: the plant id or name (e.g., "1000", "Munich", "Stuttgart")
    - for delivery_delay_source: the delivery id (e.g., "D-900007") or customer name, or "ALL_BLOCKED" if asking about general delivery blockers or deliveries at risk
    - for dynamic_query: main entity keyword or id mentioned
    - else null
```

---

### Layer 2: Read-Only Dynamic Cypher Prompt (`agents/dynamic_agent.py`)

- **Role**: Generates safe, parameterized Cypher queries for ad-hoc semantic graph questions.
- **Security Guardrail**: Pre-screened with regex filters forbidding any mutation keywords (`CREATE`, `MERGE`, `DELETE`, `SET`, `DROP`).

```text
Write a single read-only Neo4j Cypher query to answer this supply-chain question:
"{question}"

Schema:
- (:Supplier {id, name, country, delayed: boolean, delay_reason})
- (:Material {id, description, material_type})
- (:Plant {id, name, country})
- (:ProductionOrder {id, product_description, quantity, planned_finish_date, status})
- (:Delivery {id, customer_name, quantity, ship_date})

Relationships:
- (:Supplier)-[:SUPPLIES {price_per_unit, planned_delivery_days, contract_id}]->(:Material)
- (:Material)-[:USED_AT {unrestricted_stock, safety_stock, reorder_point}]->(:Plant)
- (:Material)-[:REQUIRED_FOR {quantity_per, requirement_date, total_quantity}]->(:ProductionOrder)
- (:ProductionOrder)-[:RUNS_AT]->(:Plant)
- (:ProductionOrder)-[:FULFILLS]->(:Delivery)

Output ONLY the raw Cypher query. No explanations, no markdown ticks.
```

---

### Layer 3: Dynamic Grounded Explainer Prompt Engine (`explain.py`)

- **Role**: Produces the executive narrative strictly bound to the `EvidenceContract`.
- **Dynamic Section Omission**: Built dynamically in Python (`_build_explain_prompt`) so that empty sections are **never requested or output**.

```python
def _build_explain_prompt(evidence: EvidenceContract, contract_dict: Dict[str, Any]) -> str:
    sections = [
        "1. **Executive Status & Root Issue**: State the root entity, whether it is flagged as delayed/blocked, and quote the exact verified reason.",
        "2. **Inventory Buffering Analysis**: State whether plant safety stock mitigates or cushions the impact, citing the deterministic inventory buffer status from the contract.",
        "3. **Operational Impact & Risk Summary**: Summarize impacted production orders and deliveries. Highlight only the top 1-2 most urgent customer deliveries concisely. Do NOT generate a markdown table for all deliveries.",
        "4. **Quantified Business Exposure**: State total delayed quantity, estimated revenue exposure (EUR), and the earliest compromised ship date.",
    ]

    sec_idx = 5
    if evidence.mitigations:
        sections.append(
            f"{sec_idx}. **Prescriptive Mitigation Plan**: Summarize alternate supplier recommendations "
            f"(alternate supplier name, country, lead time, and recommendation score)."
        )
        sec_idx += 1

    if evidence.staged_actions:
        sections.append(
            f"{sec_idx}. **Staged SAP Action**: Outline proposed execution payload for human approval "
            f"(transaction code, action type, and operational description)."
        )
        sec_idx += 1

    sections.append(
        f"{sec_idx}. **Lineage & Confidence**: State confidence score ({evidence.confidence.score} - {evidence.confidence.level}) "
        f"and list the SAP source tables ({', '.join(evidence.lineage)}) backing this analysis."
    )
```

---

## 6. End-to-End Execution Trace: `"is there any delivery blocker ?"`

Here is the exact step-by-step lifecycle when the user submits `"is there any delivery blocker ?"`:

```
Step 1: Input Ingestion
User Query: "is there any delivery blocker ?"

Step 2: Semantic Intent Routing
extract_params.py extracts:
{
  "question_type": "delivery_delay_source",
  "supplier_name": null,
  "target": "ALL_BLOCKED",
  "raw_question": "is there any delivery blocker ?"
}

Step 3: Orchestrator Dispatch
AgentOrchestrator routes intent 'delivery_delay_source' to DeliveryRootCauseAgent.

Step 4: Domain Execution & Graph Retrieval
DeliveryRootCauseAgent executes ALL_DELIVERY_BLOCKERS against Neo4j via GraphService:
- Discovers 14 compromised customer deliveries across SKF, Grundfos, Rheinmetall, Voith Turbo, KSB, etc.
- Identifies 2 delayed suppliers: Acme Fasteners GmbH (Hamburg customs hold) & Lyon Polymers SAS (plant flooding).
- Attaches causing_suppliers per delivery:
    * 8 deliveries -> Acme Fasteners GmbH
    * 6 deliveries -> Dual Blocker (Acme + Lyon)
- Identifies 1 uncompromised delivery: D-900011 (Voith Turbo GmbH, Nordic Steel AB).

Step 5: Deterministic Calculations (ImpactEngine)
- Total Delayed Units: 635 units
- Revenue Exposure: €1,587,500
- Buffer Status: PARTIAL (plant stock cushions initial order requirements)
- Risk Breakdown: 2 Critical (<5 days), 5 High, 4 Medium, 3 Low

Step 6: Prescriptive Sourcing & Staging (MitigationAgent)
- Queries EKKO/EKPO for materials supplied by delayed vendors.
- Discovers alternate suppliers (e.g. Nordic Steel AB, Bavaria Casting GmbH).
- Stages draft purchase requisition ME51N payload.

Step 7: Grounded Explanation Generation (explain.py)
- Dynamic prompt builder binds User Question: "is there any delivery blocker ?".
- Formulates 5 structured sections (omitting empty sections).
- Synthesizes verified multi-vendor explanation citing LIKP, LIPS, AFKO, RESB, LFA1 tables.

Step 8: UI Dashboard Rendering (app.py)
- Metadata Ribbon: Routed Intent 'Delivery Blockers' | Target 'Customer Deliveries at Risk (14 Shipments)'.
- Root Cause Card: Renders dual-bottleneck breakdown (Acme + Lyon).
- Delivery Matrix: Renders interactive table with 'Causing Blocker' column displaying Dual Blocker tags.
```

---

## 7. Verification & Operational Health

The complete agentic architecture is validated with automated suites:

- **Module Compilation**: `python -m py_compile app.py explain.py extract_params.py templates.py graph_service.py contracts.py agents/delivery_agent.py agents/dynamic_agent.py agents/orchestrator.py agents/supplier_agent.py agents/plant_agent.py` -> Verified (Exit Code `0`).
- **End-to-End Pipeline Smoke Test**: `python smoke_test.py` -> Verified (5/5 suites passing).
- **Hot-Reload Architecture**: Guaranteed via `importlib.reload(templates)` and safe runtime attribute resolution in `graph_service.py`.

"""
Grounded Explanation Layer: Translates verified EvidenceContracts into executive, explainable answers.
Enforces zero hallucination, strict adherence to graph evidence, inventory buffer citations,
prescriptive mitigations, and SAP table lineage.
"""

import json
from typing import Any, Dict, Union
import llm
from contracts import EvidenceContract

SYSTEM_PROMPT = (
    "You are an enterprise SAP supply-chain analyst. Answer strictly and only from the JSON "
    "evidence contract provided. Never hallucinate or use outside knowledge. "
    "Cite SAP table lineage and computed deterministic metrics accurately."
)

EXPLAIN_PROMPT = """You are preparing an executive, explainable impact analysis based ONLY on the evidence contract below.

Structure your response clearly:
1. **Executive Status & Root Issue**: State the root entity, whether it is flagged as delayed/blocked, and quote the exact reason.
2. **Inventory Buffering Analysis**: State whether plant safety stock mitigates or cushions the impact, citing the deterministic inventory buffer status from the contract.
3. **Operational Impact & Risk Summary**:
   - Production Orders: Summarize impacted orders, assemblies, and plants.
   - Deliveries at Risk: Provide a concise high-level summary of affected customers and immediate SLA risks. Highlight only the top 1-2 most urgent deliveries. Do NOT generate a markdown table for all deliveries (the UI renders the interactive delivery matrix separately).
4. **Quantified Business Exposure**: State the total delayed quantity, estimated revenue exposure (€), and the earliest compromised ship date.
5. **Prescriptive Mitigation Plan**: ONLY if alternate suppliers or mitigation options are present in the evidence, summarize them (alternate supplier name, country, lead time, and recommendation score). If none exist, omit this section completely.
6. **Staged SAP Action**: ONLY if a staged action exists (e.g., draft ME51N or CO02), outline the proposed execution payload for human approval. If none exist, omit this section completely. Do NOT write 'No staged actions present'.
7. **Lineage & Confidence**: State the confidence score ({confidence_score} - {confidence_level}) and list the SAP source tables ({lineage_tables}) backing this analysis.

Evidence Contract (JSON):
{contract_json}
"""

DYNAMIC_PROMPT = """You are an enterprise SAP supply-chain analyst.
Answer the user's specific inquiry directly, concisely, and accurately based ONLY on the verified graph evidence provided below.

User Inquiry:
{user_question}

Guidelines:
1. **Direct Answer**: Directly answer the user's question citing specific entity IDs, descriptions, statuses, and dates.
2. **Traversed Graph Path**: Briefly summarize the connected path across the knowledge graph (e.g. Supplier -> Material -> Plant / Order -> Delivery).
3. **Key Quantities & Observations**: Mention any relevant stock numbers, order volumes, or fulfillment dates from the data.
4. **Lineage**: State that this answer is strictly verified against live Neo4j SAP knowledge graph data.

Evidence Contract (JSON):
{contract_json}
"""


def _template_contract_answer(contract: EvidenceContract) -> str:
    """Deterministic fallback for EvidenceContract when LLM is unavailable."""
    lines = []
    root = contract.root_entity
    m = contract.metrics
    conf = contract.confidence
    raw = contract.raw_graph

    if contract.context == "dynamic_query":
        lines.append(f"### Graph Traversal Results: {root.name or root.id}")
        lines.append("\n**Discovered Knowledge Graph Entities:**")
        if raw.get("suppliers"):
            lines.append(f"- **Suppliers ({len(raw['suppliers'])})**: " + ", ".join(f"`{s.get('id')}` ({s.get('name')})" for s in raw["suppliers"][:4]))
        if raw.get("materials"):
            lines.append(f"- **Materials ({len(raw['materials'])})**: " + ", ".join(f"`{mat.get('id')}` ({mat.get('description', '')})" for mat in raw["materials"][:4]))
        if raw.get("plants"):
            lines.append(f"- **Plants ({len(raw['plants'])})**: " + ", ".join(f"`{p.get('id')}` ({p.get('name')})" for p in raw["plants"][:4]))
        if raw.get("production_orders"):
            lines.append(f"- **Production Orders ({len(raw['production_orders'])})**: " + ", ".join(f"`{o.get('id')}` ({o.get('product_description', '')})" for o in raw["production_orders"][:4]))
        if raw.get("deliveries"):
            lines.append(f"- **Customer Deliveries ({len(raw['deliveries'])})**: " + ", ".join(f"`{d.get('id')}` to {d.get('customer_name', '')}" for d in raw["deliveries"][:4]))

        lineage_rels = contract.raw_graph.get("lineage", {})
        total_rels = sum(len(v) for v in lineage_rels.values() if isinstance(v, list))
        lines.append(f"\n**Traversed Relationships ({total_rels} paths):**")
        for k, v in lineage_rels.items():
            if v:
                lines.append(f"- `{k.upper()}`: {len(v)} connections")

        lines.append(f"\n**Verification & Lineage:** Grounded in live Neo4j graph data with **{conf.level}** confidence.")
        return "\n".join(lines)

    # 1. Status
    if contract.context == "delivery_blocker" or root.type == "DeliveryNetwork":
        delayed_sups = raw.get("delayed_suppliers", [])
        sup_summary = ", ".join(f"**{s.get('name')}** (Reason: _{s.get('delay_reason')}_)" for s in delayed_sups) if delayed_sups else "upstream supplier delays"
        lines.append(f"**Delivery Network Status**: **{len(raw.get('deliveries', []))} customer deliveries** are currently blocked or at immediate SLA risk due to {sup_summary}.")
    elif contract.context == "supplier_delay":
        s = raw.get("supplier", {})
        if s.get("delayed"):
            lines.append(f"**Supplier {s.get('name', root.id)}** IS flagged as delayed — Reason: _{s.get('delay_reason', 'n/a')}_.")
        else:
            lines.append(f"**Supplier {s.get('name', root.id)}** is NOT flagged as delayed.")
    elif contract.context == "plant_blocker":
        p = raw.get("plant", {})
        lines.append(f"**Plant {p.get('name', root.id)} (ID: {root.id})** is reporting an operational blocker/halt.")
    else:
        d = raw.get("delivery", {})
        lines.append(f"**Delivery {d.get('id', root.id)}** for customer **{d.get('customer_name', 'OEM Customer')}** is being evaluated for upstream delay causes.")

    # 2. Inventory Buffer
    lines.append(f"\n**Inventory Buffer Status: `{m.inventory_buffer_status}`**")
    for detail in m.buffer_details:
        lines.append(f"- {detail}")

    # 3. Operational Impact & Risk Matrix
    orders = raw.get("production_orders", [])
    lines.append(f"\n**Production Orders Affected ({len(orders)})**")
    for o in orders[:5]:
        lines.append(f"- `{o.get('id')}` {o.get('product_description', 'Assembly')} @ Plant {o.get('runs_at_plant', o.get('plant_id'))} (Qty: {o.get('quantity')}, Target: {o.get('planned_finish_date')})")

    lines.append(f"\n**Customer Deliveries Risk Matrix ({len(m.risk_breakdown or raw.get('deliveries', []))})**")
    for item in (m.risk_breakdown or []):
        r = item.get("risk_level", "MEDIUM")
        badge = "[CRITICAL]" if r == "CRITICAL" else ("[HIGH]" if r == "HIGH" else ("[MEDIUM]" if r == "MEDIUM" else "[LOW]"))
        lines.append(f"- **{badge}**: `{item['delivery_id']}` to **{item['customer_name']}** ({item['quantity']} units, Ship: {item['ship_date']}) — _{item['impact_description']}_")

    # 4. Quantified Metrics
    lines.append(f"\n**Quantified Business Exposure:**")
    lines.append(f"- Total Quantity: **{m.total_delayed_quantity:,} units**")
    lines.append(f"- Revenue Exposure: **€{m.revenue_exposure_eur:,.2f}**")
    lines.append(f"- Earliest Breach Date: **{m.earliest_impact_date or 'N/A'}**")

    # 5. Prescriptive Mitigation
    if contract.mitigations:
        lines.append(f"\n**Prescriptive Mitigation Available ({len(contract.mitigations)} Alternate Suppliers):**")
        for alt in contract.mitigations[:2]:
            lines.append(f"- Switch component `{alt.material_id}` to **{alt.alternate_supplier_name}** ({alt.alternate_supplier_country}) — Lead time: {alt.lead_time_days} days (Score: {int(alt.recommendation_score*100)}%)")

    # 6. Staged Action
    if contract.staged_actions:
        lines.append(f"\n**Staged SAP Action (Pending Approval):**")
        for act in contract.staged_actions:
            lines.append(f"- **{act.sap_transaction}** `{act.action_type}`: {act.description}")

    # 7. Lineage
    lines.append(f"\n**Lineage & Confidence:**")
    lines.append(f"- Confidence: **{conf.level}** ({int(conf.score * 100)}%)")
    lines.append(f"- Verified SAP Tables: `{', '.join(contract.lineage)}`")

    return "\n".join(lines)


def _build_explain_prompt(evidence: EvidenceContract, contract_dict: Dict[str, Any]) -> str:
    """Dynamically construct prompt instructions so empty sections are never requested."""
    sections = [
        "1. **Executive Status & Root Issue**: State the root entity, whether it is flagged as delayed/blocked, and quote the exact verified reason.",
        "2. **Inventory Buffering Analysis**: State whether plant safety stock mitigates or cushions the impact, citing the deterministic inventory buffer status from the contract.",
        "3. **Operational Impact & Risk Summary**: Summarize impacted production orders and deliveries. Highlight only the top 1-2 most urgent customer deliveries concisely. Do NOT generate a markdown table for all deliveries.",
        "4. **Quantified Business Exposure**: State total delayed quantity, estimated revenue exposure (EUR), and the earliest compromised ship date.",
    ]

    sec_idx = 5
    if evidence.mitigations:
        sections.append(
            f"{sec_idx}. **Prescriptive Mitigation Plan**: Summarize the alternate supplier recommendations "
            f"(alternate supplier name, country, lead time, and recommendation score)."
        )
        sec_idx += 1

    if evidence.staged_actions:
        sections.append(
            f"{sec_idx}. **Staged SAP Action**: Outline the proposed execution payload for human approval "
            f"(transaction code, action type, and operational description)."
        )
        sec_idx += 1

    sections.append(
        f"{sec_idx}. **Lineage & Confidence**: State the confidence score ({evidence.confidence.score} - {evidence.confidence.level}) "
        f"and list the SAP source tables ({', '.join(evidence.lineage)}) backing this analysis."
    )

    section_text = "\n".join(sections)
    contract_json_str = json.dumps(contract_dict, indent=2, default=str)
    user_q_str = f'User Question: "{evidence.user_question}"\n\n' if evidence.user_question else ""

    return (
        "You are preparing an executive, explainable impact analysis based ONLY on the evidence contract below.\n\n"
        f"{user_q_str}"
        "Strict Guidelines:\n"
        "- Follow ONLY the numbered sections listed below.\n"
        "- Do NOT add any extra sections, headings, disclaimers, or empty placeholders for items not requested.\n"
        "- Do NOT include emojis.\n\n"
        "Structure your response using these exact sections:\n"
        f"{section_text}\n\n"
        "Evidence Contract (JSON):\n"
        f"{contract_json_str}\n"
    )


def generate_answer(evidence: Union[EvidenceContract, Dict[str, Any]]) -> str:
    """Generate grounded, explainable answer from an EvidenceContract or raw dictionary."""
    if not evidence:
        return "No matching evidence was found in the knowledge graph for that inquiry."

    # Convert dictionary to EvidenceContract if needed for backwards compatibility
    if isinstance(evidence, dict) and "metrics" not in evidence:
        from impact_engine import calculate_metrics, calculate_confidence
        from contracts import RootEntity
        metrics = calculate_metrics(evidence, "supplier_delay")
        confidence = calculate_confidence(evidence, "supplier_delay")
        s = evidence.get("supplier") or evidence.get("delivery") or evidence.get("plant") or {}
        evidence = EvidenceContract(
            request_id="legacy-req",
            intent="LEGACY_IMPACT",
            context="legacy",
            root_entity=RootEntity(type="Entity", id=str(s.get("id", "unknown")), name=s.get("name")),
            raw_graph=evidence,
            metrics=metrics,
            mitigations=[],
            staged_actions=[],
            lineage=sorted(list({v for item in evidence.get("materials", []) + evidence.get("plants", []) for k, v in item.items() if k == "source_table"})),
            confidence=confidence,
            limitations=[],
        )

    contract_dict = evidence.model_dump() if hasattr(evidence, "model_dump") else evidence.dict()

    if llm.available():
        try:
            if evidence.context == "dynamic_query":
                prompt = DYNAMIC_PROMPT.format(
                    user_question=evidence.user_question or "Supply chain knowledge graph query",
                    contract_json=json.dumps(contract_dict, indent=2, default=str)
                )
            else:
                prompt = _build_explain_prompt(evidence, contract_dict)
            return llm.chat_text(SYSTEM_PROMPT, prompt, max_tokens=1400)
        except Exception as e:  # noqa: BLE001
            print(f"[generate_answer] LLM failed ({e}); using template answer")

    return _template_contract_answer(evidence)



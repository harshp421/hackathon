"""
Router Agent: Natural-language question -> Structured parameter extraction.
Classifies intent, context, and root entity according to the Semantic Control Plane.
"""

import json
import re
from typing import Any, Dict

import llm

SYSTEM_PROMPT = """You are the Semantic Router Agent for an SAP supply-chain knowledge graph.

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

Examples:
Q: "is there any delivery blocker ?"
A: {"question_type": "delivery_delay_source", "supplier_name": null, "target": "ALL_BLOCKED"}

Q: "Which customer deliveries are currently blocked or at risk?"
A: {"question_type": "delivery_delay_source", "supplier_name": null, "target": "ALL_BLOCKED"}

Q: "If Supplier Acme Fasteners is delayed, which materials, plants, production orders and customer deliveries are affected?"
A: {"question_type": "supplier_delay_impact", "supplier_name": "Acme Fasteners", "target": null}

Q: "There is a blocker at plant 1000. What will be delayed and what is the potential loss?"
A: {"question_type": "plant_blocker", "supplier_name": null, "target": "1000"}

Q: "Which suppliers could delay delivery D-900007?"
A: {"question_type": "delivery_delay_source", "supplier_name": null, "target": "D-900007"}
"""

_LEGAL = r"\b(gmbh|ag|sas|ab|s\.?l\.?|se|co\.?|kgaa|a/s|inc|ltd|kg)\b"
_QWORD = r"^(if|is|are|which|what|how|when|why|does|do|can|could|will|would|should|the|a|an)\s+"


def _proper_phrase(text: str):
    """First multi-word Capitalised proper-noun phrase, minus a leading question word."""
    for cand in re.findall(r"\b[A-Z][A-Za-z&./-]+(?:\s+[A-Z][A-Za-z&./-]+)*", text):
        cand = re.sub(_QWORD, "", cand, flags=re.I).strip()
        cand = re.sub(_LEGAL, "", cand, flags=re.I).strip(" .,?-\"'")
        if len(cand) > 2:
            return cand
    return None


def _regex_fallback(question: str) -> Dict[str, Any]:
    q = question.strip()
    low = q.lower()

    # 1. Plant blocker check
    p_match = re.search(r"\b(?:plant|facility|factory)\s+([A-Za-z0-9_-]+)", q, re.I)
    if ("plant" in low or "factory" in low) and any(w in low for w in ("block", "shut", "halt", "down", "disrupt", "stoppage", "loss")):
        target = p_match.group(1) if p_match else "1000"
        return {"question_type": "plant_blocker", "supplier_name": None, "target": target, "raw_question": q}

    # 2. Delivery blocker or root-cause check
    dnum = re.search(r"\bd-?(\d{4,})\b", q, re.I)
    delivery_word = ("shipment" in low or "delivery" in low or "deliveries" in low or "customer" in low)
    blocker_word = any(w in low for w in ("block", "blocker", "blocked", "risk", "delay", "delayed", "threat", "late", "stoppage", "bottleneck", "issue"))
    upstream_cue = any(p in low for p in (
        "which supplier", "what supplier", "which vendor", "at risk from",
        "caused by", "root cause", "upstream", "who could delay", "put at risk",
    ))

    if dnum or upstream_cue or (delivery_word and blocker_word):
        if dnum:
            target = "D-" + dnum.group(1)
        else:
            m = re.search(
                r"([A-Z][A-Za-z&./-]+(?:\s+[A-Z][A-Za-z&./-]+)*)\s+"
                r"(?:shipment|shipments|delivery|deliveries|order)",
                q,
            )
            target = m.group(1).strip() if m else "ALL_BLOCKED"
        return {"question_type": "delivery_delay_source", "supplier_name": None, "target": target, "raw_question": q}


    # 3. Supplier delay check
    if any(w in low for w in ("delay", "late", "held up", "hold up", "strike", "slip",
                              "disruption", "shortage", "problem", "issue", "outage", "blast radius")):
        patterns = [
            r"if\s+(?:supplier\s+)?(.+?)\s+(?:is|are|was|were|gets?|got|slips?)\b",
            r"(?:delay(?:ed|s)?|problem|issue|disruption|strike|outage|shortage)\s+"
            r"(?:at|from|with|by)\s+(.+?)(?:[.,?]|$)",
        ]
        for pat in patterns:
            m = re.search(pat, q, re.I)
            if m:
                name = re.sub(_LEGAL, "", m.group(1), flags=re.I).strip(" .,?-\"'")
                if len(name) > 2:
                    return {"question_type": "supplier_delay_impact", "supplier_name": name, "target": None, "raw_question": q}
        name = _proper_phrase(q)
        if name:
            return {"question_type": "supplier_delay_impact", "supplier_name": name, "target": None, "raw_question": q}

    # 4. Universal Dynamic Traversal Fallback (handles any general query or task)
    return {
        "question_type": "dynamic_query",
        "supplier_name": None,
        "target": _proper_phrase(q) or q,
        "raw_question": q,
    }


def _llm(question: str) -> Dict[str, Any]:
    text = llm.chat_json(SYSTEM_PROMPT, question, max_tokens=200).strip()
    text = re.sub(r"^```(?:json)?|```$", "", text).strip()
    data = json.loads(text)
    qtype = data.get("question_type", "dynamic_query")
    if qtype == "unknown":
        qtype = "dynamic_query"
    return {
        "question_type": qtype,
        "supplier_name": data.get("supplier_name"),
        "target": data.get("target"),
        "raw_question": question,
    }


def extract_params(question: str) -> Dict[str, Any]:
    if llm.available():
        try:
            return _llm(question)
        except Exception as e:  # noqa: BLE001
            print(f"[extract_params] LLM call failed ({e}); using regex fallback")
    return _regex_fallback(question)

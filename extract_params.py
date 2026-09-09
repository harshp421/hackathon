"""
Phase 5: natural-language question  ->  structured parameters.

We do NOT ask the LLM to write Cypher (risky live). We ask it to fill a small,
fixed schema. If OPENAI_API_KEY is missing we fall back to a regex parser so the
demo still runs offline.

    from extract_params import extract_params
    extract_params("If Acme Fasteners is delayed, what's affected?")
    # -> {"question_type": "supplier_delay_impact", "supplier_name": "Acme Fasteners", "target": null}
"""

import json
import re

import llm

SYSTEM_PROMPT = """You extract structured parameters from questions about an SAP supply-chain knowledge graph.

The graph has nodes: Supplier, Material, Plant, ProductionOrder, Delivery
connected by: SUPPLIES, USED_AT, REQUIRED_FOR, RUNS_AT, FULFILLS.

Classify the question and pull out the entity it is about. Output ONLY a raw JSON
object (no markdown fences, no prose) with exactly these keys:

- "question_type": one of
    "supplier_delay_impact"  - user asks what is affected downstream if a supplier / its
                               material is delayed or has a problem
    "delivery_delay_source"  - user asks which suppliers / upstream causes put a specific
                               delivery, customer, or product at risk
    "unknown"                - anything else
- "supplier_name": the supplier named in the question, else null
- "target": for delivery_delay_source, the delivery id / customer / product named, else null

Examples:
Q: "If Supplier Acme Fasteners is delayed, which materials, plants, production orders and customer deliveries are affected?"
A: {"question_type": "supplier_delay_impact", "supplier_name": "Acme Fasteners", "target": null}

Q: "Nordic Steel just told us they'll be two weeks late - what's the blast radius?"
A: {"question_type": "supplier_delay_impact", "supplier_name": "Nordic Steel", "target": null}

Q: "Which suppliers could delay delivery D-900007?"
A: {"question_type": "delivery_delay_source", "supplier_name": null, "target": "D-900007"}

Q: "Is the Siemens Mobility shipment at risk from any supplier problems?"
A: {"question_type": "delivery_delay_source", "supplier_name": null, "target": "Siemens Mobility"}

Q: "How many plants do we operate?"
A: {"question_type": "unknown", "supplier_name": null, "target": null}
"""


_LEGAL = r"\b(gmbh|ag|sas|ab|s\.?l\.?|se|co\.?|kgaa|a/s|inc|ltd|kg)\b"
_QWORD = r"^(if|is|are|which|what|how|when|why|does|do|can|could|will|would|should|the|a|an)\s+"


def _proper_phrase(text):
    """First multi-word Capitalised proper-noun phrase, minus a leading question word."""
    for cand in re.findall(r"\b[A-Z][A-Za-z&./-]+(?:\s+[A-Z][A-Za-z&./-]+)*", text):
        cand = re.sub(_QWORD, "", cand, flags=re.I).strip()
        cand = re.sub(_LEGAL, "", cand, flags=re.I).strip(" .,?-\"'")
        if len(cand) > 2:
            return cand
    return None


def _regex_fallback(question):
    q = question.strip()
    low = q.lower()

    dnum = re.search(r"\bd-?(\d{4,})\b", q, re.I)
    upstream_cue = any(p in low for p in (
        "which supplier", "what supplier", "which vendor", "at risk from",
        "caused by", "root cause", "upstream", "who could delay", "put at risk",
    ))
    shipment_risk = ("shipment" in low or "delivery" in low) and "risk" in low

    if dnum or upstream_cue or shipment_risk:
        if dnum:
            target = "D-" + dnum.group(1)
        else:
            m = re.search(
                r"([A-Z][A-Za-z&./-]+(?:\s+[A-Z][A-Za-z&./-]+)*)\s+"
                r"(?:shipment|shipments|delivery|deliveries|order)",
                q,
            )
            target = (m.group(1).strip() if m else _proper_phrase(q))
        return {"question_type": "delivery_delay_source", "supplier_name": None, "target": target}

    if any(w in low for w in ("delay", "late", "held up", "hold up", "strike", "slip",
                              "disruption", "shortage", "problem", "issue", "outage")):
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
                    return {"question_type": "supplier_delay_impact", "supplier_name": name, "target": None}
        name = _proper_phrase(q)
        if name:
            return {"question_type": "supplier_delay_impact", "supplier_name": name, "target": None}

    return {"question_type": "unknown", "supplier_name": None, "target": None}


def _llm(question):
    text = llm.chat_json(SYSTEM_PROMPT, question, max_tokens=200).strip()
    text = re.sub(r"^```(?:json)?|```$", "", text).strip()
    data = json.loads(text)
    return {
        "question_type": data.get("question_type", "unknown"),
        "supplier_name": data.get("supplier_name"),
        "target": data.get("target"),
    }


def extract_params(question):
    if llm.available():
        try:
            return _llm(question)
        except Exception as e:  # noqa: BLE001 - demo resilience
            print(f"[extract_params] LLM failed ({e}); using regex fallback")
    return _regex_fallback(question)


if __name__ == "__main__":
    for q in [
        "If Acme Fasteners is delayed, which materials, plants, production orders and customer deliveries will be affected, and why?",
        "Nordic Steel just told us they'll be two weeks late - what's the blast radius?",
        "Which suppliers could delay delivery D-900007?",
        "Is the Siemens Mobility shipment at risk from supplier problems?",
        "How many plants do we run?",
    ]:
        print(f"{q}\n  -> {extract_params(q)}\n")

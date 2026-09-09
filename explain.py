"""
Phase 7: turn the raw graph result into an explainable answer.

Rule: the answer is written ONLY from the rows returned by the graph. No outside
knowledge. Every affected item gets a reason (the relationship path) and a
confidence label. If OPENAI_API_KEY is missing, a deterministic template answer
is produced instead so the demo still works.
"""

import json

import llm

SYSTEM_PROMPT = (
    "You are a supply-chain analyst. Answer strictly and only from the JSON graph "
    "data the user provides. Never use outside knowledge about the named companies. "
    "If a fact is not in the data, say it is not in the data."
)

EXPLAIN_PROMPT = """You are writing an explainable impact analysis for a supply-chain
question, based ONLY on the graph data provided below. Do not invent any fact that is
not present in the data. Do not use outside knowledge about these companies.

Write in this structure:

1. One sentence: is the named supplier actually flagged as delayed in the data? If so,
   quote its delay_reason.
2. **Materials affected** - bullet list. For each: id + description, and the contract/
   source it comes from.
3. **Plants affected** - bullet list with the material that ties each plant in.
4. **Production orders affected** - bullet list. For each: order id, product, plant,
   planned finish date, and which delayed material it needs (with qty per unit).
5. **Customer deliveries at risk** - bullet list. For each: delivery id, customer,
   product, ship date, and the production-order path that connects it back to the supplier.
6. A one-line **business impact summary**: how many deliveries, which customers, earliest
   ship date at risk.

Mark every item in sections 2-5 with a confidence label:
- HIGH  - directly connected in the data via one populated relationship with a source_table
- MEDIUM - connected through a chain of two or more populated relationships, no gaps
- LOW   - a relationship exists but a key property (dates, quantities) is missing

End with a line: "Lineage: <list the SAP source tables that appear in the data>".

Graph data (JSON):
{data}
"""


def _template_answer(result):
    """Deterministic fallback - no LLM."""
    s = result.get("supplier", {})
    lines = []
    if s.get("delayed"):
        lines.append(f"**{s.get('name')}** IS flagged as delayed in the data - "
                     f"reason: _{s.get('delay_reason', 'n/a')}_.")
    else:
        lines.append(f"**{s.get('name', 'Supplier')}** is NOT flagged as delayed in the data.")

    mats = result.get("materials", [])
    lines.append(f"\n**Materials affected ({len(mats)})**")
    for m in mats:
        lines.append(f"- `{m.get('id')}` {m.get('description')} "
                     f"(contract {m.get('contract_id', 'n/a')}) - HIGH")

    plants = result.get("plants", [])
    lines.append(f"\n**Plants affected ({len(plants)})**")
    for p in plants:
        lines.append(f"- `{p.get('id')}` {p.get('name')} - MEDIUM")

    orders = result.get("production_orders", [])
    m2o = {(x["order_id"]): x for x in result.get("lineage", {}).get("material_to_order", [])}
    lines.append(f"\n**Production orders affected ({len(orders)})**")
    for o in orders:
        link = m2o.get(o.get("id"), {})
        need = f" needs {link.get('material_id', '?')} x{link.get('qty_per_unit', '?')}/unit" if link else ""
        lines.append(f"- `{o.get('id')}` {o.get('product_description')} @ {o.get('runs_at_plant', o.get('plant_id'))}, "
                     f"finish {o.get('planned_finish_date')}{need} - MEDIUM")

    deliveries = result.get("deliveries", [])
    o2d = result.get("lineage", {}).get("order_to_delivery", [])
    lines.append(f"\n**Customer deliveries at risk ({len(deliveries)})**")
    for link in o2d:
        lines.append(f"- `{link.get('delivery_id')}` {link.get('customer')} - {link.get('product')}, "
                     f"ship {link.get('ship_date')} (via order {link.get('order_id')}) - MEDIUM")

    customers = sorted({l.get("customer") for l in o2d if l.get("customer")})
    ship_dates = sorted({l.get("ship_date") for l in o2d if l.get("ship_date")})
    lines.append(f"\n**Business impact:** {len(deliveries)} deliveries to "
                 f"{len(customers)} customers ({', '.join(customers)}) at risk; "
                 f"earliest ship date {ship_dates[0] if ship_dates else 'n/a'}.")

    tables = sorted({v for item in mats + plants + orders + deliveries
                     for k, v in item.items() if k == "source_table"})
    lines.append(f"\nLineage: {', '.join(tables) if tables else 'n/a'}")
    return "\n".join(lines)


def generate_answer(graph_result):
    if not graph_result:
        return "No matching node was found in the graph for that question."

    if llm.available():
        try:
            user = EXPLAIN_PROMPT.format(data=json.dumps(graph_result, indent=2, default=str))
            return llm.chat_text(SYSTEM_PROMPT, user, max_tokens=1200)
        except Exception as e:  # noqa: BLE001
            print(f"[generate_answer] LLM failed ({e}); using template answer")

    # only the supplier-impact shape has a template; reverse shape falls through to JSON
    if "supplier" in graph_result:
        return _template_answer(graph_result)
    return "```json\n" + json.dumps(graph_result, indent=2, default=str) + "\n```"

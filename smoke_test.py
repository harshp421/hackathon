"""
End-to-end smoke test against the live Neo4j graph. Run after load_graph.py:

    python smoke_test.py

Checks:
  1. node / relationship counts are non-zero
  2. the supplier-delay-impact query returns the expected blast radius for Acme
  3. delivery D-900011 (PO-500011, no Acme part) is correctly NOT in that blast radius
  4. the reverse delivery-delay-source query finds the delayed supplier for D-900007
  5. full NL -> params -> query -> answer pipeline runs for both demo questions
"""

import os
import sys

from dotenv import load_dotenv
from neo4j import GraphDatabase

from extract_params import extract_params
from run_query import run_supplier_delay_impact, run_delivery_delay_source
from explain import generate_answer

load_dotenv()

drv = GraphDatabase.driver(
    os.environ["NEO4J_URI"],
    auth=(os.environ.get("NEO4J_USER", "neo4j"), os.environ["NEO4J_PASSWORD"]),
)

fails = []


def check(name, cond, detail=""):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f" - {detail}" if detail else ""))
    if not cond:
        fails.append(name)


print("1. Graph populated")
with drv.session() as s:
    n = s.run("MATCH (n) RETURN count(n) AS c").single()["c"]
    r = s.run("MATCH ()-[x]->() RETURN count(x) AS c").single()["c"]
check("nodes loaded", n >= 50, f"{n} nodes")
check("relationships loaded", r >= 100, f"{r} rels")

print("2. Supplier delay impact - Acme Fasteners")
res = run_supplier_delay_impact(drv, "Acme Fasteners")
check("supplier found", res and res["supplier"]["id"] == "100234")
check("supplier is delayed", res and res["supplier"].get("delayed") is True)
check("materials in blast radius", res and len(res["materials"]) >= 4, f"{len(res['materials'])} materials")
check("deliveries in blast radius", res and len(res["deliveries"]) >= 5, f"{len(res['deliveries'])} deliveries")
dids = {d["id"] for d in res["deliveries"]} if res else set()
check("D-900001 IS flagged", "D-900001" in dids)

print("3. Negative check - D-900011 must NOT be in Acme's blast radius")
check("D-900011 NOT flagged", "D-900011" not in dids, "PO-500011 uses no Acme part")

print("4. Reverse - which suppliers threaten D-900007")
rev = run_delivery_delay_source(drv, "D-900007")
check("delivery found", rev and rev["delivery"]["id"] == "D-900007")
delayed_names = {s["name"] for s in rev["delayed_suppliers"]} if rev else set()
check("Acme flagged as delayed upstream", "Acme Fasteners GmbH" in delayed_names, str(delayed_names))

print("5. Full NL pipeline")
for q in [
    "If Acme Fasteners is delayed, which materials, plants, production orders and customer deliveries will be affected, and why?",
    "Which suppliers could delay delivery D-900007?",
]:
    p = extract_params(q)
    if p["question_type"] == "supplier_delay_impact":
        gr = run_supplier_delay_impact(drv, p["supplier_name"] or "")
    elif p["question_type"] == "delivery_delay_source":
        gr = run_delivery_delay_source(drv, p["target"] or "")
    else:
        gr = None
    ans = generate_answer(gr) if gr else ""
    check(f"pipeline: {q[:45]}...", bool(ans) and len(ans) > 80, f"{p['question_type']}, {len(ans)} chars")

drv.close()
print()
if fails:
    print(f"{len(fails)} check(s) FAILED: {', '.join(fails)}")
    sys.exit(1)
print("All checks passed. Demo is ready.")

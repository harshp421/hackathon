"""
Load the demo CSVs from ./data/ into Neo4j AuraDB.

    pip install -r requirements.txt
    cp .env.example .env          # then fill in NEO4J_URI / NEO4J_PASSWORD
    python load_graph.py

Idempotent: uses MERGE, so re-running updates in place instead of duplicating.
Pass --wipe to delete everything first.
"""

import os
import sys
import math

import pandas as pd
from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv()

URI = os.environ.get("NEO4J_URI")
USER = os.environ.get("NEO4J_USER", "neo4j")
PASSWORD = os.environ.get("NEO4J_PASSWORD")

if not URI or not PASSWORD:
    sys.exit("Set NEO4J_URI and NEO4J_PASSWORD (copy .env.example to .env and fill it in).")

DATA = os.path.join(os.path.dirname(__file__), "data")

CONSTRAINTS = [
    "CREATE CONSTRAINT supplier_id IF NOT EXISTS FOR (s:Supplier)       REQUIRE s.id IS UNIQUE",
    "CREATE CONSTRAINT material_id IF NOT EXISTS FOR (m:Material)        REQUIRE m.id IS UNIQUE",
    "CREATE CONSTRAINT plant_id    IF NOT EXISTS FOR (p:Plant)           REQUIRE p.id IS UNIQUE",
    "CREATE CONSTRAINT order_id    IF NOT EXISTS FOR (o:ProductionOrder) REQUIRE o.id IS UNIQUE",
    "CREATE CONSTRAINT delivery_id IF NOT EXISTS FOR (d:Delivery)        REQUIRE d.id IS UNIQUE",
]

_TRUE = {"true", "yes", "x", "1"}
_FALSE = {"false", "no", "0"}


def clean(record):
    """CSV row (dict) -> Neo4j-friendly dict. NaN -> drop, 'TRUE'/'FALSE' -> bool."""
    out = {}
    for k, v in record.items():
        if v is None:
            continue
        if isinstance(v, float) and math.isnan(v):
            continue
        if isinstance(v, str):
            s = v.strip()
            if s == "":
                continue
            low = s.lower()
            if low in _TRUE:
                out[k] = True
                continue
            if low in _FALSE:
                out[k] = False
                continue
            out[k] = s
            continue
        out[k] = v
    return out


def read(name):
    return pd.read_csv(os.path.join(DATA, name), dtype=str).to_dict("records")


def load_nodes(session, csv_name, label, id_col):
    rows = []
    for rec in read(csv_name):
        row = clean(rec)
        row["id"] = str(row.pop(id_col))
        rows.append(row)
    session.run(
        f"UNWIND $rows AS row MERGE (n:{label} {{id: row.id}}) SET n += row",
        rows=rows,
    )
    print(f"  {label:<16} {len(rows):>3} nodes")


def load_rel(session, csv_name, from_label, from_col, rel_type, to_label, to_col):
    payload = []
    for rec in read(csv_name):
        row = clean(rec)
        frm = str(row.pop(from_col))
        to = str(row.pop(to_col))
        payload.append({"frm": frm, "to": to, "props": row})
    result = session.run(
        f"""
        UNWIND $rows AS row
        MATCH (a:{from_label} {{id: row.frm}})
        MATCH (b:{to_label}   {{id: row.to}})
        MERGE (a)-[rel:{rel_type}]->(b)
        SET rel += row.props
        RETURN count(rel) AS c
        """,
        rows=payload,
    )
    made = result.single()["c"]
    tag = "" if made == len(payload) else f"  (WARNING: {len(payload) - made} unmatched endpoints)"
    print(f"  {rel_type:<16} {made:>3} edges{tag}")


def main():
    driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))
    driver.verify_connectivity()
    print(f"Connected to {URI}")

    with driver.session() as session:
        if "--wipe" in sys.argv:
            session.run("MATCH (n) DETACH DELETE n")
            print("Wiped existing graph.")

        print("Constraints:")
        for c in CONSTRAINTS:
            session.run(c)
        print(f"  {len(CONSTRAINTS)} ensured")

        print("Nodes:")
        load_nodes(session, "suppliers.csv", "Supplier", "supplier_id")
        load_nodes(session, "materials.csv", "Material", "material_id")
        load_nodes(session, "plants.csv", "Plant", "plant_id")
        load_nodes(session, "production_orders.csv", "ProductionOrder", "order_id")
        load_nodes(session, "deliveries.csv", "Delivery", "delivery_id")

        print("Relationships:")
        load_rel(session, "rel_supplier_material.csv",
                 "Supplier", "supplier_id", "SUPPLIES", "Material", "material_id")
        load_rel(session, "rel_material_plant.csv",
                 "Material", "material_id", "USED_AT", "Plant", "plant_id")
        load_rel(session, "rel_material_production_order.csv",
                 "Material", "material_id", "REQUIRED_FOR", "ProductionOrder", "order_id")
        load_rel(session, "rel_production_order_plant.csv",
                 "ProductionOrder", "order_id", "RUNS_AT", "Plant", "plant_id")
        load_rel(session, "rel_production_order_delivery.csv",
                 "ProductionOrder", "order_id", "FULFILLS", "Delivery", "delivery_id")

        counts = session.run(
            "MATCH (n) WITH count(n) AS nodes "
            "MATCH ()-[r]->() RETURN nodes, count(r) AS rels"
        ).single()
        print(f"\nGraph loaded: {counts['nodes']} nodes, {counts['rels']} relationships.")

    driver.close()
    print("Now open Neo4j Browser and run:  MATCH (n) RETURN n LIMIT 100")


if __name__ == "__main__":
    main()

"""Execute a Cypher template and return plain-Python dicts/lists (JSON-serialisable)."""

from templates import SUPPLIER_DELAY_IMPACT, DELIVERY_DELAY_SOURCE


def _clean_list(items):
    """Drop the NULLs that OPTIONAL MATCH + collect leaves behind."""
    return [x for x in (items or []) if x]


def run_supplier_delay_impact(driver, supplier_name):
    with driver.session() as session:
        rec = session.run(SUPPLIER_DELAY_IMPACT, supplier_name=supplier_name).single()
        if rec is None or rec["supplier"] is None:
            return None
        return {
            "supplier": dict(rec["supplier"]),
            "materials": _clean_list(rec["materials"]),
            "plants": _clean_list(rec["plants"]),
            "production_orders": _clean_list(rec["production_orders"]),
            "deliveries": _clean_list(rec["deliveries"]),
            "lineage": {
                "material_to_order": _clean_list(rec["material_to_order"]),
                "order_to_delivery": _clean_list(rec["order_to_delivery"]),
            },
        }


def run_delivery_delay_source(driver, delivery_id):
    with driver.session() as session:
        rec = session.run(DELIVERY_DELAY_SOURCE, delivery_id=delivery_id).single()
        if rec is None or rec["delivery"] is None:
            return None
        return {
            "delivery": dict(rec["delivery"]),
            "production_orders": _clean_list(rec["production_orders"]),
            "materials": _clean_list(rec["materials"]),
            "suppliers": _clean_list(rec["suppliers"]),
            "delayed_suppliers": _clean_list(rec["delayed_suppliers"]),
            "lineage": {"supplier_to_material": _clean_list(rec["supplier_to_material"])},
        }


if __name__ == "__main__":
    import os, json
    from dotenv import load_dotenv
    from neo4j import GraphDatabase

    load_dotenv()
    drv = GraphDatabase.driver(
        os.environ["NEO4J_URI"],
        auth=(os.environ.get("NEO4J_USER", "neo4j"), os.environ["NEO4J_PASSWORD"]),
    )
    print(json.dumps(run_supplier_delay_impact(drv, "Acme Fasteners"), indent=2, default=str))
    drv.close()

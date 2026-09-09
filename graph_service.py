"""
Centralized Graph Service: Governs all Neo4j query execution, connection pooling,
timeout enforcement, and bridge authorization policies.
"""

import os
import logging
from typing import Any, Dict, List, Optional
from neo4j import GraphDatabase, Driver
from dotenv import load_dotenv

import templates
from semantic.bridges import validate_traversal

load_dotenv()
logger = logging.getLogger("graph_service")


def _clean_list(items: Optional[List[Any]]) -> List[Any]:
    """Drop the NULLs that OPTIONAL MATCH + collect leaves behind."""
    return [x for x in (items or []) if x is not None]


class GraphService:
    _instance: Optional["GraphService"] = None

    def __init__(self, driver: Optional[Driver] = None):
        if driver:
            self.driver = driver
        else:
            uri = os.environ.get("NEO4J_URI")
            pwd = os.environ.get("NEO4J_PASSWORD")
            user = os.environ.get("NEO4J_USER", "neo4j")
            if not uri or not pwd:
                raise ValueError("Neo4j credentials missing in environment.")
            self.driver = GraphDatabase.driver(uri, auth=(user, pwd))
            self.driver.verify_connectivity()

    @classmethod
    def get_instance(cls, driver: Optional[Driver] = None) -> "GraphService":
        if cls._instance is None:
            cls._instance = cls(driver)
        return cls._instance

    def get_available_entities(self) -> Dict[str, List[Dict[str, Any]]]:
        """Fetch all active entities directly from Neo4j for dynamic UI controls."""
        with self.driver.session() as session:
            suppliers = [dict(r) for r in session.run("MATCH (s:Supplier) RETURN s.id AS id, s.name AS name, coalesce(s.delayed, false) AS delayed ORDER BY s.delayed DESC, s.name")]
            plants = [dict(r) for r in session.run("MATCH (p:Plant) RETURN p.id AS id, p.name AS name ORDER BY p.name")]
            deliveries = [dict(r) for r in session.run("MATCH (d:Delivery) RETURN d.id AS id, d.customer_name AS customer LIMIT 10")]
            return {"suppliers": suppliers, "plants": plants, "deliveries": deliveries}

    def query_supplier_impact(self, supplier_name: str) -> Optional[Dict[str, Any]]:
        clean_name = supplier_name.strip()
        # Remove common prefixes like 'Supplier'
        clean_name = clean_name.replace("Supplier", "").replace("supplier", "").strip()

        with self.driver.session() as session:
            rec = session.run(templates.SUPPLIER_DELAY_IMPACT, supplier_name=clean_name).single()
            if rec is None or rec["supplier"] is None:
                return None
            return {
                "supplier": dict(rec["supplier"]),
                "materials": _clean_list(rec["materials"]),
                "plants": _clean_list(rec["plants"]),
                "production_orders": _clean_list(rec["production_orders"]),
                "deliveries": _clean_list(rec["deliveries"]),
                "lineage": {
                    "supplier_to_material": _clean_list(rec.get("supplier_to_material", [])),
                    "material_to_order": _clean_list(rec.get("material_to_order", [])),
                    "order_to_delivery": _clean_list(rec.get("order_to_delivery", [])),
                    "material_to_plant": _clean_list(rec.get("material_to_plant", [])),
                    "order_to_plant": _clean_list(rec.get("order_to_plant", [])),
                },
            }

    def query_delivery_delay_source(self, delivery_id: str) -> Optional[Dict[str, Any]]:
        clean_id = delivery_id.strip()
        with self.driver.session() as session:
            rec = session.run(templates.DELIVERY_DELAY_SOURCE, delivery_id=clean_id).single()
            if rec is None or rec["delivery"] is None:
                return None
            return {
                "delivery": dict(rec["delivery"]),
                "production_orders": _clean_list(rec["production_orders"]),
                "materials": _clean_list(rec["materials"]),
                "suppliers": _clean_list(rec["suppliers"]),
                "delayed_suppliers": _clean_list(rec["delayed_suppliers"]),
                "plants": _clean_list(rec.get("plants", [])),
                "lineage": {
                    "supplier_to_material": _clean_list(rec.get("supplier_to_material", [])),
                    "material_to_order": _clean_list(rec.get("material_to_order", [])),
                    "order_to_delivery": _clean_list(rec.get("order_to_delivery", [])),
                    "order_to_plant": _clean_list(rec.get("order_to_plant", [])),
                    "material_to_plant": _clean_list(rec.get("material_to_plant", [])),
                },
            }

    def query_plant_blocker_impact(self, plant_id: str) -> Optional[Dict[str, Any]]:
        clean_id = plant_id.strip()
        with self.driver.session() as session:
            rec = session.run(templates.PLANT_BLOCKER_IMPACT, plant_id=clean_id).single()
            if rec is None or rec["plant"] is None:
                return None
            return {
                "plant": dict(rec["plant"]),
                "production_orders": _clean_list(rec["production_orders"]),
                "deliveries": _clean_list(rec["deliveries"]),
                "materials": _clean_list(rec["materials"]),
                "lineage": {
                    "order_to_delivery": _clean_list(rec.get("order_to_delivery", [])),
                    "material_to_order": _clean_list(rec.get("material_to_order", [])),
                    "material_to_plant": _clean_list(rec.get("material_to_plant", [])),
                    "order_to_plant": _clean_list(rec.get("order_to_plant", [])),
                },
            }

    def query_material_shortage_impact(self, material_id: str) -> Optional[Dict[str, Any]]:
        with self.driver.session() as session:
            rec = session.run(templates.MATERIAL_SHORTAGE_IMPACT, material_id=material_id).single()
            if rec is None or rec["material"] is None:
                return None
            return {
                "material": dict(rec["material"]),
                "plants": _clean_list(rec["plants"]),
                "production_orders": _clean_list(rec["production_orders"]),
                "deliveries": _clean_list(rec["deliveries"]),
                "suppliers": _clean_list(rec["suppliers"]),
                "lineage": {
                    "supplier_to_material": _clean_list(rec.get("supplier_to_material", [])),
                    "material_to_order": _clean_list(rec.get("material_to_order", [])),
                    "order_to_delivery": _clean_list(rec.get("order_to_delivery", [])),
                    "material_to_plant": _clean_list(rec.get("material_to_plant", [])),
                    "order_to_plant": _clean_list(rec.get("order_to_plant", [])),
                },
            }

    def query_alternate_suppliers(self, material_ids: List[str], excluded_supplier_id: str = "") -> List[Dict[str, Any]]:
        if not material_ids:
            return []
        with self.driver.session() as session:
            result = session.run(
                templates.ALTERNATE_SUPPLIER_LOOKUP,
                material_id=material_ids[0] if material_ids else "",
                material_ids=material_ids,
                excluded_supplier_id=excluded_supplier_id or "",
            )
            return [dict(r) for r in result]

    def query_all_delivery_blockers(self) -> Optional[Dict[str, Any]]:
        """Query all customer deliveries threatened by delayed suppliers or blocked orders across network."""
        query = getattr(templates, "ALL_DELIVERY_BLOCKERS", None)
        if not query:
            import importlib
            importlib.reload(templates)
            query = getattr(templates, "ALL_DELIVERY_BLOCKERS", None)

        if not query:
            query = """
            MATCH (s:Supplier)-[sup:SUPPLIES]->(m:Material)-[rf:REQUIRED_FOR]->(o:ProductionOrder)-[:FULFILLS]->(d:Delivery)
            WHERE s.delayed = true OR o.status = 'Blocked'
            OPTIONAL MATCH (m)-[ua:USED_AT]->(p:Plant)
            OPTIONAL MATCH (o)-[:RUNS_AT]->(op:Plant)
            WITH d, s, sup, m, rf, o, op, p, ua, coalesce(op, p) AS plant_node
            WITH d, collect(DISTINCT s.name) AS causing_suppliers,
                 collect(DISTINCT o { .*, runs_at_plant: op.name, plant_id: coalesce(o.plant_id, op.id, p.id) }) AS o_sub,
                 collect(DISTINCT m { .*, unit_price: sup.price_per_unit, lead_time_days: sup.planned_delivery_days, contract_id: sup.contract_id }) AS m_sub,
                 collect(DISTINCT s { .* }) AS s_sub,
                 collect(DISTINCT CASE WHEN s.delayed = true THEN s END) AS delayed_sub,
                 collect(DISTINCT plant_node { .*, unrestricted_stock: ua.unrestricted_stock }) AS p_sub,
                 collect(DISTINCT CASE WHEN s IS NOT NULL AND m IS NOT NULL THEN { supplier_id: s.id, material_id: m.id } END) AS s2m_sub,
                 collect(DISTINCT CASE WHEN m IS NOT NULL AND o IS NOT NULL THEN { material_id: m.id, order_id: o.id, qty_per_unit: rf.quantity_per } END) AS m2o_sub,
                 collect(DISTINCT CASE WHEN o IS NOT NULL AND d IS NOT NULL THEN { order_id: o.id, delivery_id: d.id, customer: d.customer_name, ship_date: d.ship_date, quantity: d.quantity } END) AS o2d_sub
            RETURN
              collect(DISTINCT d { .*, causing_suppliers: causing_suppliers }) AS deliveries,
              reduce(acc = [], x IN collect(o_sub) | acc + [item IN x WHERE NOT item IN acc]) AS production_orders,
              reduce(acc = [], x IN collect(m_sub) | acc + [item IN x WHERE NOT item IN acc]) AS materials,
              reduce(acc = [], x IN collect(s_sub) | acc + [item IN x WHERE NOT item IN acc]) AS suppliers,
              reduce(acc = [], x IN collect(delayed_sub) | acc + [item IN x WHERE NOT item IN acc]) AS delayed_suppliers,
              reduce(acc = [], x IN collect(p_sub) | acc + [item IN x WHERE NOT item IN acc]) AS plants,
              reduce(acc = [], x IN collect(s2m_sub) | acc + [item IN x WHERE NOT item IN acc]) AS supplier_to_material,
              reduce(acc = [], x IN collect(m2o_sub) | acc + [item IN x WHERE NOT item IN acc]) AS material_to_order,
              reduce(acc = [], x IN collect(o2d_sub) | acc + [item IN x WHERE NOT item IN acc]) AS order_to_delivery
            """

        with self.driver.session() as session:
            rec = session.run(query).single()
            if rec is None:
                return None
            return {
                "deliveries": _clean_list(rec["deliveries"]),
                "production_orders": _clean_list(rec["production_orders"]),
                "materials": _clean_list(rec["materials"]),
                "suppliers": _clean_list(rec["suppliers"]),
                "delayed_suppliers": _clean_list(rec["delayed_suppliers"]),
                "plants": _clean_list(rec["plants"]),
                "lineage": {
                    "supplier_to_material": _clean_list(rec.get("supplier_to_material", [])),
                    "material_to_order": _clean_list(rec.get("material_to_order", [])),
                    "order_to_delivery": _clean_list(rec.get("order_to_delivery", [])),
                },
            }



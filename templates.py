"""Cypher templates. Parameters come from extract_params.py; never string-formatted in."""

# Four-hop blast radius from a (possibly delayed) supplier:
#   Supplier -SUPPLIES-> Material -REQUIRED_FOR-> ProductionOrder -FULFILLS-> Delivery
#   plus Material -USED_AT-> Plant and ProductionOrder -RUNS_AT-> Plant for context.
SUPPLIER_DELAY_IMPACT = """
MATCH (s:Supplier)
WHERE toLower(s.name) CONTAINS toLower($supplier_name)
   OR s.id = $supplier_name
OPTIONAL MATCH (s)-[sup:SUPPLIES]->(m:Material)
OPTIONAL MATCH (m)-[:USED_AT]->(p:Plant)
OPTIONAL MATCH (m)-[rf:REQUIRED_FOR]->(o:ProductionOrder)
OPTIONAL MATCH (o)-[:RUNS_AT]->(op:Plant)
OPTIONAL MATCH (o)-[:FULFILLS]->(d:Delivery)
RETURN
  s { .* }                                                        AS supplier,
  collect(DISTINCT m { .*, unit_price: sup.price_per_unit,
                       lead_time_days: sup.planned_delivery_days,
                       contract_id: sup.contract_id })            AS materials,
  collect(DISTINCT p { .* })                                      AS plants,
  collect(DISTINCT o { .*, runs_at_plant: op.name })              AS production_orders,
  collect(DISTINCT d { .* })                                      AS deliveries,
  collect(DISTINCT CASE WHEN m IS NOT NULL AND o IS NOT NULL
      THEN { material_id: m.id, material: m.description, order_id: o.id,
             qty_per_unit: rf.quantity_per, requirement_date: rf.requirement_date }
      END)                                                        AS material_to_order,
  collect(DISTINCT CASE WHEN o IS NOT NULL AND d IS NOT NULL
      THEN { order_id: o.id, product: o.product_description, delivery_id: d.id,
             customer: d.customer_name, ship_date: d.ship_date, quantity: d.quantity }
      END)                                                        AS order_to_delivery
"""

# Reverse direction: given a delivery (or customer name), walk back to the suppliers.
DELIVERY_DELAY_SOURCE = """
MATCH (d:Delivery)
WHERE toLower(d.id) CONTAINS toLower($delivery_id)
   OR toLower(coalesce(d.customer_name, '')) CONTAINS toLower($delivery_id)
   OR toLower(coalesce(d.product_id, ''))    CONTAINS toLower($delivery_id)
OPTIONAL MATCH (o:ProductionOrder)-[:FULFILLS]->(d)
OPTIONAL MATCH (o)-[:RUNS_AT]->(p:Plant)
OPTIONAL MATCH (m:Material)-[rf:REQUIRED_FOR]->(o)
OPTIONAL MATCH (s:Supplier)-[:SUPPLIES]->(m)
WITH d,
  collect(DISTINCT o { .*, runs_at_plant: p.name })                AS production_orders,
  collect(DISTINCT m { .* })                                       AS materials,
  collect(DISTINCT s { .* })                                       AS suppliers,
  collect(DISTINCT CASE WHEN s IS NOT NULL AND m IS NOT NULL
     THEN { supplier: s.name, supplier_id: s.id, delayed: s.delayed,
            delay_reason: s.delay_reason, material: m.description,
            material_id: m.id, qty_per_unit: rf.quantity_per }
     END)                                                          AS s2m
RETURN
  d { .* }                                                         AS delivery,
  production_orders,
  materials,
  suppliers,
  [x IN suppliers WHERE x.delayed = true]                          AS delayed_suppliers,
  [x IN s2m WHERE x IS NOT NULL]                                   AS supplier_to_material
"""

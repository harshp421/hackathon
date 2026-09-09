"""Cypher templates. Parameters come from extract_params.py / agents; never string-formatted in."""

# Four-hop blast radius from a (possibly delayed) supplier:
#   Supplier -SUPPLIES-> Material -REQUIRED_FOR-> ProductionOrder -FULFILLS-> Delivery
#   plus Material -USED_AT-> Plant and ProductionOrder -RUNS_AT-> Plant for context.
SUPPLIER_DELAY_IMPACT = """
MATCH (s:Supplier)
WHERE toLower(s.name) CONTAINS toLower($supplier_name)
   OR s.id = $supplier_name
WITH s LIMIT 1
OPTIONAL MATCH (s)-[sup:SUPPLIES]->(m:Material)
OPTIONAL MATCH (m)-[ua:USED_AT]->(p:Plant)
OPTIONAL MATCH (m)-[rf:REQUIRED_FOR]->(o:ProductionOrder)
OPTIONAL MATCH (o)-[:RUNS_AT]->(op:Plant)
OPTIONAL MATCH (o)-[:FULFILLS]->(d:Delivery)
RETURN
  s { .* }                                                        AS supplier,
  collect(DISTINCT m { .*, unit_price: sup.price_per_unit,
                       lead_time_days: sup.planned_delivery_days,
                       contract_id: sup.contract_id })            AS materials,
  collect(DISTINCT p { .*, unrestricted_stock: ua.unrestricted_stock,
                       reorder_point: ua.reorder_point })         AS plants,
  collect(DISTINCT o { .*, runs_at_plant: op.name, plant_id: coalesce(o.plant_id, op.id, p.id) }) AS production_orders,
  collect(DISTINCT d { .* })                                      AS deliveries,
  collect(DISTINCT CASE WHEN s IS NOT NULL AND m IS NOT NULL
      THEN { supplier_id: s.id, material_id: m.id }
      END)                                                        AS supplier_to_material,
  collect(DISTINCT CASE WHEN m IS NOT NULL AND o IS NOT NULL
      THEN { material_id: m.id, material: m.description, order_id: o.id,
             qty_per_unit: rf.quantity_per, requirement_date: rf.requirement_date,
             total_quantity: rf.total_quantity }
      END)                                                        AS material_to_order,
  collect(DISTINCT CASE WHEN o IS NOT NULL AND d IS NOT NULL
      THEN { order_id: o.id, product: o.product_description, delivery_id: d.id,
             customer: d.customer_name, ship_date: d.ship_date, quantity: d.quantity }
      END)                                                        AS order_to_delivery,
  collect(DISTINCT CASE WHEN m IS NOT NULL AND (p IS NOT NULL OR op IS NOT NULL)
      THEN { material_id: m.id, plant_id: coalesce(p.id, op.id), stock: ua.unrestricted_stock }
      END)                                                        AS material_to_plant,
  collect(DISTINCT CASE WHEN o IS NOT NULL AND (op IS NOT NULL OR p IS NOT NULL)
      THEN { order_id: o.id, plant_id: coalesce(op.id, p.id) }
      END)                                                        AS order_to_plant
"""

# Reverse direction: given a delivery (or customer name), walk back to the suppliers.
DELIVERY_DELAY_SOURCE = """
MATCH (d:Delivery)
WHERE toLower(d.id) CONTAINS toLower($delivery_id)
   OR toLower(coalesce(d.customer_name, '')) CONTAINS toLower($delivery_id)
   OR toLower(coalesce(d.product_id, ''))    CONTAINS toLower($delivery_id)
WITH d LIMIT 1
OPTIONAL MATCH (o:ProductionOrder)-[:FULFILLS]->(d)
OPTIONAL MATCH (o)-[:RUNS_AT]->(p:Plant)
OPTIONAL MATCH (m:Material)-[rf:REQUIRED_FOR]->(o)
OPTIONAL MATCH (m)-[ua:USED_AT]->(p)
OPTIONAL MATCH (s:Supplier)-[:SUPPLIES]->(m)
WITH d,
  collect(DISTINCT o { .*, runs_at_plant: p.name, plant_id: coalesce(o.plant_id, p.id) }) AS production_orders,
  collect(DISTINCT m { .*, unrestricted_stock: ua.unrestricted_stock }) AS materials,
  collect(DISTINCT s { .* })                                       AS suppliers,
  collect(DISTINCT p { .* })                                       AS plants,
  collect(DISTINCT CASE WHEN s IS NOT NULL AND m IS NOT NULL
     THEN { supplier: s.name, supplier_id: s.id, delayed: s.delayed,
            delay_reason: s.delay_reason, material: m.description,
            material_id: m.id, qty_per_unit: rf.quantity_per }
     END)                                                          AS s2m,
  collect(DISTINCT CASE WHEN m IS NOT NULL AND o IS NOT NULL
     THEN { material_id: m.id, material: m.description, order_id: o.id, qty_per_unit: rf.quantity_per }
     END)                                                          AS m2o,
  collect(DISTINCT CASE WHEN o IS NOT NULL AND d IS NOT NULL
     THEN { order_id: o.id, delivery_id: d.id, customer: d.customer_name, ship_date: d.ship_date, quantity: d.quantity }
     END)                                                          AS o2d,
  collect(DISTINCT CASE WHEN o IS NOT NULL AND p IS NOT NULL
     THEN { order_id: o.id, plant_id: p.id }
     END)                                                          AS o2p,
  collect(DISTINCT CASE WHEN m IS NOT NULL AND p IS NOT NULL
     THEN { material_id: m.id, plant_id: p.id }
     END)                                                          AS m2p
RETURN
  d { .* }                                                         AS delivery,
  production_orders,
  materials,
  suppliers,
  plants,
  [x IN suppliers WHERE x.delayed = true]                          AS delayed_suppliers,
  [x IN s2m WHERE x IS NOT NULL]                                   AS supplier_to_material,
  [x IN m2o WHERE x IS NOT NULL]                                   AS material_to_order,
  [x IN o2d WHERE x IS NOT NULL]                                   AS order_to_delivery,
  [x IN o2p WHERE x IS NOT NULL]                                   AS order_to_plant,
  [x IN m2p WHERE x IS NOT NULL]                                   AS material_to_plant
"""

# Plant Blocker / Disruption Impact:
#   Plant <-RUNS_AT- ProductionOrder -FULFILLS-> Delivery
#   plus components required for those orders
PLANT_BLOCKER_IMPACT = """
MATCH (p:Plant)
WHERE p.id = $plant_id
   OR toLower(p.name) CONTAINS toLower($plant_id)
WITH p LIMIT 1
OPTIONAL MATCH (o:ProductionOrder)-[:RUNS_AT]->(p)
OPTIONAL MATCH (o)-[:FULFILLS]->(d:Delivery)
OPTIONAL MATCH (m:Material)-[rf:REQUIRED_FOR]->(o)
OPTIONAL MATCH (m)-[ua:USED_AT]->(p)
RETURN
  p { .* }                                                         AS plant,
  collect(DISTINCT o { .*, runs_at_plant: p.name, plant_id: coalesce(o.plant_id, p.id) }) AS production_orders,
  collect(DISTINCT d { .* })                                       AS deliveries,
  collect(DISTINCT m { .*, unrestricted_stock: ua.unrestricted_stock }) AS materials,
  collect(DISTINCT CASE WHEN o IS NOT NULL AND d IS NOT NULL
      THEN { order_id: o.id, product: o.product_description, delivery_id: d.id,
             customer: d.customer_name, ship_date: d.ship_date, quantity: d.quantity }
      END)                                                         AS order_to_delivery,
  collect(DISTINCT CASE WHEN m IS NOT NULL AND o IS NOT NULL
      THEN { material_id: m.id, material: m.description, order_id: o.id,
             qty_per_unit: rf.quantity_per }
      END)                                                         AS material_to_order,
  collect(DISTINCT CASE WHEN m IS NOT NULL AND p IS NOT NULL
      THEN { material_id: m.id, plant_id: p.id, stock: ua.unrestricted_stock }
      END)                                                         AS material_to_plant,
  collect(DISTINCT CASE WHEN o IS NOT NULL AND p IS NOT NULL
      THEN { order_id: o.id, plant_id: p.id }
      END)                                                         AS order_to_plant
"""

# Material Shortage Impact:
#   Material -REQUIRED_FOR-> ProductionOrder -FULFILLS-> Delivery
MATERIAL_SHORTAGE_IMPACT = """
MATCH (m:Material)
WHERE m.id = $material_id
   OR toLower(m.description) CONTAINS toLower($material_id)
WITH m LIMIT 1
OPTIONAL MATCH (m)-[ua:USED_AT]->(p:Plant)
OPTIONAL MATCH (m)-[rf:REQUIRED_FOR]->(o:ProductionOrder)
OPTIONAL MATCH (o)-[:RUNS_AT]->(op:Plant)
OPTIONAL MATCH (o)-[:FULFILLS]->(d:Delivery)
OPTIONAL MATCH (s:Supplier)-[:SUPPLIES]->(m)
RETURN
  m { .* }                                                         AS material,
  collect(DISTINCT p { .*, unrestricted_stock: ua.unrestricted_stock }) AS plants,
  collect(DISTINCT o { .*, runs_at_plant: op.name, plant_id: coalesce(o.plant_id, op.id) }) AS production_orders,
  collect(DISTINCT d { .* })                                       AS deliveries,
  collect(DISTINCT s { .* })                                       AS suppliers,
  collect(DISTINCT CASE WHEN s IS NOT NULL AND m IS NOT NULL
      THEN { supplier_id: s.id, material_id: m.id }
      END)                                                         AS supplier_to_material,
  collect(DISTINCT CASE WHEN m IS NOT NULL AND o IS NOT NULL
      THEN { material_id: m.id, material: m.description, order_id: o.id, qty_per_unit: rf.quantity_per }
      END)                                                         AS material_to_order,
  collect(DISTINCT CASE WHEN o IS NOT NULL AND d IS NOT NULL
      THEN { order_id: o.id, delivery_id: d.id }
      END)                                                         AS order_to_delivery,
  collect(DISTINCT CASE WHEN m IS NOT NULL AND (p IS NOT NULL OR op IS NOT NULL)
      THEN { material_id: m.id, plant_id: coalesce(p.id, op.id) }
      END)                                                         AS material_to_plant,
  collect(DISTINCT CASE WHEN o IS NOT NULL AND (op IS NOT NULL OR p IS NOT NULL)
      THEN { order_id: o.id, plant_id: coalesce(op.id, p.id) }
      END)                                                         AS order_to_plant
"""

# Alternate Supplier Lookup (Prescriptive Mitigation):
#   Find non-delayed suppliers that can supply the given material or materials
ALTERNATE_SUPPLIER_LOOKUP = """
MATCH (m:Material)
WHERE m.id = $material_id OR m.id IN $material_ids
MATCH (alt:Supplier)-[sup:SUPPLIES]->(m)
WHERE alt.id <> $excluded_supplier_id
  AND (alt.delayed IS NULL OR alt.delayed = false)
RETURN
  m.id AS material_id,
  m.description AS material_name,
  alt.id AS alternate_supplier_id,
  alt.name AS alternate_supplier_name,
  alt.country AS alternate_supplier_country,
  sup.planned_delivery_days AS lead_time_days,
  sup.price_per_unit AS price_per_unit,
  sup.contract_id AS contract_id
"""

# Global Delivery Blockers & At-Risk Shipments:
#   Find all deliveries jeopardized by delayed suppliers or blocked production orders across the entire network
ALL_DELIVERY_BLOCKERS = """
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



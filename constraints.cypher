// Run once. load_graph.py also runs these automatically before loading.
CREATE CONSTRAINT supplier_id IF NOT EXISTS FOR (s:Supplier)        REQUIRE s.id IS UNIQUE;
CREATE CONSTRAINT material_id IF NOT EXISTS FOR (m:Material)         REQUIRE m.id IS UNIQUE;
CREATE CONSTRAINT plant_id    IF NOT EXISTS FOR (p:Plant)            REQUIRE p.id IS UNIQUE;
CREATE CONSTRAINT order_id    IF NOT EXISTS FOR (o:ProductionOrder)  REQUIRE o.id IS UNIQUE;
CREATE CONSTRAINT delivery_id IF NOT EXISTS FOR (d:Delivery)         REQUIRE d.id IS UNIQUE;

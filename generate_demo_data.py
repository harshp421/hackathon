"""
Generate a realistic, internally-consistent demo dataset for the SAP Supply Chain
Knowledge Graph hackathon project.

No external dependencies (stdlib only). Run:

    python3 generate_demo_data.py

Writes 10 CSVs into ./data/ :

  Nodes
    suppliers.csv, materials.csv, plants.csv, production_orders.csv, deliveries.csv
  Relationships
    rel_supplier_material.csv          Supplier -SUPPLIES-> Material
    rel_material_plant.csv             Material -USED_AT-> Plant
    rel_material_production_order.csv  Material -REQUIRED_FOR-> ProductionOrder
    rel_production_order_plant.csv     ProductionOrder -RUNS_AT-> Plant
    rel_production_order_delivery.csv  ProductionOrder -FULFILLS-> Delivery

Scenario (a mechanical-engineering OEM):
  * Acme Fasteners GmbH (100234) is DELAYED  -> customs hold. Supplies the fastener
    family (bolts/nuts/washers/screws) used almost everywhere -> wide blast radius.
  * Lyon Polymers SAS (101245) is also DELAYED -> a second, smaller example.
  * Every other supplier is on time.
  * PO-500011 deliberately uses NO Acme part -> its delivery must NOT be flagged.
    (good "the model can tell the difference" moment in the demo)

Every row carries a `source_table` column (the SAP table it would have come from) so
the final answer can cite lineage.
"""

import csv
import hashlib
from datetime import datetime, timedelta
from pathlib import Path

DATA = Path(__file__).parent / "data"
DATA.mkdir(exist_ok=True)


def _hash_int(seed):
    return int(hashlib.md5(seed.encode()).hexdigest(), 16)


def synth(seed, lo, hi):
    """Deterministic pseudo-random int in [lo, hi] from a string seed."""
    return lo + (_hash_int(seed) % (hi - lo + 1))


def write_csv(name, rows, fieldnames):
    path = DATA / name
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print("  wrote {:<38} {:>3} rows".format(name, len(rows)))


# --------------------------------------------------------------------------------------
# 1. Suppliers  (SAP table LFA1)
# --------------------------------------------------------------------------------------
SUPPLIERS = [
    dict(supplier_id="100234", name="Acme Fasteners GmbH", country="DE",
         delayed="TRUE",  delay_reason="Customs hold at Hamburg port (est. 9 days)",
         source_table="LFA1"),
    dict(supplier_id="100567", name="Nordic Steel AB", country="SE",
         delayed="FALSE", delay_reason="", source_table="LFA1"),
    dict(supplier_id="100812", name="Bavaria Precision Castings GmbH", country="DE",
         delayed="FALSE", delay_reason="", source_table="LFA1"),
    dict(supplier_id="101245", name="Lyon Polymers SAS", country="FR",
         delayed="TRUE",  delay_reason="Force majeure - flooding at Lyon plant (est. 5 days)",
         source_table="LFA1"),
    dict(supplier_id="101876", name="Iberian Bearings SL", country="ES",
         delayed="FALSE", delay_reason="", source_table="LFA1"),
    dict(supplier_id="102455", name="Rhine Coatings GmbH", country="DE",
         delayed="FALSE", delay_reason="", source_table="LFA1"),
]

# --------------------------------------------------------------------------------------
# 2. Materials  (SAP tables MARA / MARC).  supplier_id here drives the SUPPLIES rel.
#    material_type: ROH = raw/purchased, HALB = semi-finished, FERT = finished
# --------------------------------------------------------------------------------------
MATERIALS = [
    dict(material_id="M-1001", description="Hex Bolt M12x60 Class 10.9",        material_type="ROH", base_unit="PC", procurement_type="F", supplier_id="100234"),
    dict(material_id="M-1002", description="Hex Nut M12 Class 10",              material_type="ROH", base_unit="PC", procurement_type="F", supplier_id="100234"),
    dict(material_id="M-1003", description="Flat Washer M12 DIN125",            material_type="ROH", base_unit="PC", procurement_type="F", supplier_id="100234"),
    dict(material_id="M-1004", description="Socket Head Cap Screw M8x40",       material_type="ROH", base_unit="PC", procurement_type="F", supplier_id="100234"),
    dict(material_id="M-1005", description="Threaded Rod M10x1000",             material_type="ROH", base_unit="PC", procurement_type="F", supplier_id="100234"),
    dict(material_id="M-2001", description="Cold-Rolled Steel Coil 1.5mm",      material_type="ROH", base_unit="KG", procurement_type="F", supplier_id="100567"),
    dict(material_id="M-2002", description="Hot-Rolled Steel Plate 6mm",        material_type="ROH", base_unit="KG", procurement_type="F", supplier_id="100567"),
    dict(material_id="M-2003", description="Stainless Steel Round Bar 20mm",    material_type="ROH", base_unit="M",  procurement_type="F", supplier_id="100567"),
    dict(material_id="M-3001", description="Ductile Iron Casting Gearbox Housing", material_type="ROH", base_unit="PC", procurement_type="F", supplier_id="100812"),
    dict(material_id="M-3002", description="Aluminium Die Casting Pump Body",   material_type="ROH", base_unit="PC", procurement_type="F", supplier_id="100812"),
    dict(material_id="M-4001", description="Polyamide PA66 Granulate",          material_type="ROH", base_unit="KG", procurement_type="F", supplier_id="101245"),
    dict(material_id="M-4002", description="POM Acetal Granulate",              material_type="ROH", base_unit="KG", procurement_type="F", supplier_id="101245"),
    dict(material_id="M-5001", description="Deep Groove Ball Bearing 6205-2RS", material_type="ROH", base_unit="PC", procurement_type="F", supplier_id="101876"),
    dict(material_id="M-5002", description="Tapered Roller Bearing 30206",      material_type="ROH", base_unit="PC", procurement_type="F", supplier_id="101876"),
    dict(material_id="M-6001", description="Epoxy Powder Coating RAL7016",      material_type="ROH", base_unit="KG", procurement_type="F", supplier_id="102455"),
]

# --------------------------------------------------------------------------------------
# 3. Plants  (SAP table T001W)
# --------------------------------------------------------------------------------------
PLANTS = [
    dict(plant_id="1000", name="Stuttgart Gearbox Plant", country="DE", source_table="T001W"),
    dict(plant_id="2000", name="Hamburg Pump Plant",      country="DE", source_table="T001W"),
    dict(plant_id="3000", name="Leipzig Machining Plant", country="DE", source_table="T001W"),
    dict(plant_id="4000", name="Munich Conveyor Plant",   country="DE", source_table="T001W"),
]

# --------------------------------------------------------------------------------------
# 4. Production orders  (SAP tables AFKO / AFPO) + their component list (RESB)
#    components: order_id -> list of (material_id, qty_per_unit)
# --------------------------------------------------------------------------------------
PRODUCTION_ORDERS = [
    dict(order_id="PO-500001", plant_id="1000", product_id="GA-200", product_description="Gearbox Assembly GA-200", planned_finish_date="2026-09-15", quantity=40,  status="REL"),
    dict(order_id="PO-500002", plant_id="1000", product_id="GA-200", product_description="Gearbox Assembly GA-200", planned_finish_date="2026-09-19", quantity=60,  status="REL"),
    dict(order_id="PO-500003", plant_id="2000", product_id="PU-50",  product_description="Pump Unit PU-50",         planned_finish_date="2026-09-12", quantity=30,  status="REL"),
    dict(order_id="PO-500004", plant_id="2000", product_id="PU-50",  product_description="Pump Unit PU-50",         planned_finish_date="2026-09-21", quantity=45,  status="REL"),
    dict(order_id="PO-500005", plant_id="3000", product_id="MS-10",  product_description="Machined Shaft MS-10",    planned_finish_date="2026-09-10", quantity=120, status="REL"),
    dict(order_id="PO-500006", plant_id="3000", product_id="SB-3",   product_description="Steel Bracket SB-3",      planned_finish_date="2026-09-14", quantity=200, status="REL"),
    dict(order_id="PO-500007", plant_id="4000", product_id="CM-100", product_description="Conveyor Module CM-100",  planned_finish_date="2026-09-23", quantity=25,  status="REL"),
    dict(order_id="PO-500008", plant_id="4000", product_id="CM-100", product_description="Conveyor Module CM-100",  planned_finish_date="2026-09-27", quantity=25,  status="CRTD"),
    dict(order_id="PO-500009", plant_id="1000", product_id="GA-300", product_description="Gearbox Assembly GA-300", planned_finish_date="2026-09-29", quantity=20,  status="CRTD"),
    dict(order_id="PO-500010", plant_id="2000", product_id="PU-80",  product_description="Pump Unit PU-80",         planned_finish_date="2026-09-18", quantity=35,  status="REL"),
    dict(order_id="PO-500011", plant_id="3000", product_id="MS-20",  product_description="Machined Shaft MS-20",    planned_finish_date="2026-09-16", quantity=90,  status="REL"),
    dict(order_id="PO-500012", plant_id="4000", product_id="CM-200", product_description="Conveyor Module CM-200",  planned_finish_date="2026-09-30", quantity=15,  status="CRTD"),
]

COMPONENTS = {
    "PO-500001": [("M-1001", 16), ("M-1002", 16), ("M-1003", 32), ("M-3001", 1), ("M-5001", 2), ("M-6001", 1)],
    "PO-500002": [("M-1001", 16), ("M-1002", 16), ("M-3001", 1),  ("M-5001", 2)],
    "PO-500003": [("M-1004", 8),  ("M-3002", 1),  ("M-4001", 2),  ("M-5001", 1), ("M-6001", 1)],
    "PO-500004": [("M-1004", 8),  ("M-3002", 1),  ("M-4002", 2)],
    "PO-500005": [("M-2003", 1),  ("M-1001", 2)],
    "PO-500006": [("M-2001", 1),  ("M-1002", 4),  ("M-1003", 4)],
    "PO-500007": [("M-2002", 2),  ("M-1001", 24), ("M-1002", 24), ("M-1003", 48), ("M-5002", 4)],
    "PO-500008": [("M-2002", 2),  ("M-1004", 12), ("M-5002", 4)],
    "PO-500009": [("M-3001", 1),  ("M-5001", 3),  ("M-1001", 20), ("M-4001", 1), ("M-6001", 1)],
    "PO-500010": [("M-3002", 1),  ("M-4001", 3),  ("M-1004", 10), ("M-5002", 2)],
    "PO-500011": [("M-2003", 1),  ("M-2001", 1)],                      # <- no Acme part on purpose
    "PO-500012": [("M-2002", 3),  ("M-1001", 30), ("M-1002", 30), ("M-5002", 6)],
}

# --------------------------------------------------------------------------------------
# 5. Deliveries  (SAP tables LIKP / LIPS).  ref_order drives the FULFILLS rel.
# --------------------------------------------------------------------------------------
DELIVERIES = [
    dict(delivery_id="D-900001", customer_id="C-2001", customer_name="Rheinmetall Automotive AG", product_id="GA-200", quantity=40,  ship_date="2026-09-17", ref_order="PO-500001", incoterms="FCA"),
    dict(delivery_id="D-900002", customer_id="C-2002", customer_name="Voith Turbo GmbH",          product_id="GA-200", quantity=60,  ship_date="2026-09-22", ref_order="PO-500002", incoterms="FCA"),
    dict(delivery_id="D-900003", customer_id="C-2003", customer_name="Grundfos A/S",              product_id="PU-50",  quantity=20,  ship_date="2026-09-15", ref_order="PO-500003", incoterms="DAP"),
    dict(delivery_id="D-900004", customer_id="C-2003", customer_name="Grundfos A/S",              product_id="PU-50",  quantity=45,  ship_date="2026-09-24", ref_order="PO-500004", incoterms="DAP"),
    dict(delivery_id="D-900005", customer_id="C-2004", customer_name="SKF GmbH",                  product_id="MS-10",  quantity=120, ship_date="2026-09-12", ref_order="PO-500005", incoterms="EXW"),
    dict(delivery_id="D-900006", customer_id="C-2005", customer_name="Bosch Rexroth AG",          product_id="SB-3",   quantity=200, ship_date="2026-09-17", ref_order="PO-500006", incoterms="FCA"),
    dict(delivery_id="D-900007", customer_id="C-2006", customer_name="Siemens Mobility GmbH",     product_id="CM-100", quantity=25,  ship_date="2026-09-26", ref_order="PO-500007", incoterms="CPT"),
    dict(delivery_id="D-900008", customer_id="C-2006", customer_name="Siemens Mobility GmbH",     product_id="CM-100", quantity=25,  ship_date="2026-09-30", ref_order="PO-500008", incoterms="CPT"),
    dict(delivery_id="D-900009", customer_id="C-2001", customer_name="Rheinmetall Automotive AG", product_id="GA-300", quantity=20,  ship_date="2026-10-02", ref_order="PO-500009", incoterms="FCA"),
    dict(delivery_id="D-900010", customer_id="C-2007", customer_name="KSB SE & Co. KGaA",         product_id="PU-80",  quantity=35,  ship_date="2026-09-21", ref_order="PO-500010", incoterms="DAP"),
    dict(delivery_id="D-900011", customer_id="C-2004", customer_name="SKF GmbH",                  product_id="MS-20",  quantity=90,  ship_date="2026-09-19", ref_order="PO-500011", incoterms="EXW"),
    dict(delivery_id="D-900012", customer_id="C-2008", customer_name="Krones AG",                 product_id="CM-200", quantity=15,  ship_date="2026-10-03", ref_order="PO-500012", incoterms="CPT"),
    dict(delivery_id="D-900013", customer_id="C-2002", customer_name="Voith Turbo GmbH",          product_id="PU-50",  quantity=10,  ship_date="2026-09-19", ref_order="PO-500003", incoterms="FCA"),
    dict(delivery_id="D-900014", customer_id="C-2008", customer_name="Krones AG",                 product_id="CM-100", quantity=10,  ship_date="2026-09-28", ref_order="PO-500007", incoterms="CPT"),
    dict(delivery_id="D-900015", customer_id="C-2001", customer_name="Rheinmetall Automotive AG", product_id="GA-300", quantity=10,  ship_date="2026-10-05", ref_order="PO-500009", incoterms="FCA"),
]


def daysbefore(date_str, n):
    d = datetime.strptime(date_str, "%Y-%m-%d") - timedelta(days=n)
    return d.strftime("%Y-%m-%d")


def build():
    print("Generating demo data into ./data/ ...")

    # ---- node files -------------------------------------------------------------------
    write_csv("suppliers.csv", SUPPLIERS,
              ["supplier_id", "name", "country", "delayed", "delay_reason", "source_table"])

    materials_out = [
        dict(material_id=m["material_id"], description=m["description"],
             material_type=m["material_type"], base_unit=m["base_unit"],
             procurement_type=m["procurement_type"], primary_supplier_id=m["supplier_id"],
             source_table="MARA")
        for m in MATERIALS
    ]
    write_csv("materials.csv", materials_out,
              ["material_id", "description", "material_type", "base_unit",
               "procurement_type", "primary_supplier_id", "source_table"])

    write_csv("plants.csv", PLANTS, ["plant_id", "name", "country", "source_table"])

    po_out = [
        dict(order_id=o["order_id"], plant_id=o["plant_id"], product_id=o["product_id"],
             product_description=o["product_description"],
             planned_finish_date=o["planned_finish_date"], quantity=o["quantity"],
             status=o["status"], source_table="AFKO")
        for o in PRODUCTION_ORDERS
    ]
    write_csv("production_orders.csv", po_out,
              ["order_id", "plant_id", "product_id", "product_description",
               "planned_finish_date", "quantity", "status", "source_table"])

    del_out = [dict(d, source_table="LIKP") for d in DELIVERIES]
    write_csv("deliveries.csv", del_out,
              ["delivery_id", "customer_id", "customer_name", "product_id", "quantity",
               "ship_date", "ref_order", "incoterms", "source_table"])

    # ---- relationship: Supplier -SUPPLIES-> Material  (EKKO/EKPO) --------------------
    rel_sm = []
    for m in MATERIALS:
        seed = m["supplier_id"] + m["material_id"]
        rel_sm.append(dict(
            supplier_id=m["supplier_id"], material_id=m["material_id"],
            contract_id="46{:08d}".format(synth(seed + "c", 100000, 999999) + synth(seed, 0, 99)),
            price_per_unit=round(synth(seed + "p", 5, 4200) / 100.0, 2),
            currency="EUR",
            planned_delivery_days=synth(seed + "d", 7, 45),
            source_table="EKPO",
        ))
    write_csv("rel_supplier_material.csv", rel_sm,
              ["supplier_id", "material_id", "contract_id", "price_per_unit", "currency",
               "planned_delivery_days", "source_table"])

    # ---- relationship: Material -REQUIRED_FOR-> ProductionOrder  (RESB) --------------
    po_by_id = {o["order_id"]: o for o in PRODUCTION_ORDERS}
    rel_mpo = []
    for order_id, comps in COMPONENTS.items():
        finish = po_by_id[order_id]["planned_finish_date"]
        for mat_id, qty_per in comps:
            seed = order_id + mat_id
            rel_mpo.append(dict(
                material_id=mat_id, order_id=order_id,
                quantity_per=qty_per,
                total_quantity=qty_per * po_by_id[order_id]["quantity"],
                requirement_date=daysbefore(finish, synth(seed, 2, 8)),
                reservation_no="00{:06d}".format(synth(seed + "r", 10000, 999999)),
                source_table="RESB",
            ))
    write_csv("rel_material_production_order.csv", rel_mpo,
              ["material_id", "order_id", "quantity_per", "total_quantity",
               "requirement_date", "reservation_no", "source_table"])

    # ---- relationship: Material -USED_AT-> Plant  (MARC) ----------------------------
    #      derived: a material is used at a plant if some PO at that plant needs it
    mat_plant = set()
    for order_id, comps in COMPONENTS.items():
        plant = po_by_id[order_id]["plant_id"]
        for mat_id, _ in comps:
            mat_plant.add((mat_id, plant))
    rel_mp = []
    for mat_id, plant in sorted(mat_plant):
        seed = mat_id + plant
        rel_mp.append(dict(
            material_id=mat_id, plant_id=plant,
            storage_location="{:04d}".format(synth(seed + "s", 1, 12)),
            unrestricted_stock=synth(seed + "u", 0, 5000),
            reorder_point=synth(seed + "rp", 50, 800),
            mrp_controller="{:03d}".format(synth(seed + "m", 100, 200)),
            source_table="MARC",
        ))
    write_csv("rel_material_plant.csv", rel_mp,
              ["material_id", "plant_id", "storage_location", "unrestricted_stock",
               "reorder_point", "mrp_controller", "source_table"])

    # ---- relationship: ProductionOrder -RUNS_AT-> Plant  (AFKO) ---------------------
    rel_pop = [dict(order_id=o["order_id"], plant_id=o["plant_id"], source_table="AFKO")
               for o in PRODUCTION_ORDERS]
    write_csv("rel_production_order_plant.csv", rel_pop,
              ["order_id", "plant_id", "source_table"])

    # ---- relationship: ProductionOrder -FULFILLS-> Delivery  (LIPS) ----------------
    rel_pod = [dict(order_id=d["ref_order"], delivery_id=d["delivery_id"],
                    ship_date=d["ship_date"], source_table="LIPS")
               for d in DELIVERIES]
    write_csv("rel_production_order_delivery.csv", rel_pod,
              ["order_id", "delivery_id", "ship_date", "source_table"])

    # ---- summary -------------------------------------------------------------------
    delayed = [s["name"] for s in SUPPLIERS if s["delayed"] == "TRUE"]
    print("\nDone.")
    print("  {} suppliers ({} delayed: {})".format(len(SUPPLIERS), len(delayed), ", ".join(delayed)))
    print("  {} materials, {} plants, {} production orders, {} deliveries".format(
        len(MATERIALS), len(PLANTS), len(PRODUCTION_ORDERS), len(DELIVERIES)))
    print("  {} SUPPLIES, {} REQUIRED_FOR, {} USED_AT, {} RUNS_AT, {} FULFILLS edges".format(
        len(rel_sm), len(rel_mpo), len(rel_mp), len(rel_pop), len(rel_pod)))
    print("\n  Demo question: \"If Acme Fasteners is delayed, what is affected?\"")
    print("  Negative check: delivery D-900011 (PO-500011) uses no Acme part -> must NOT be flagged.")


if __name__ == "__main__":
    build()

"""
Phase 8: demo UI.

    pip install -r requirements.txt
    cp .env.example .env      # fill in NEO4J_URI / NEO4J_PASSWORD (+ OPENAI_API_KEY)
    streamlit run app.py
"""

import json
import os
import tempfile

import streamlit as st
from dotenv import load_dotenv
from neo4j import GraphDatabase

from extract_params import extract_params
from run_query import run_supplier_delay_impact, run_delivery_delay_source
from explain import generate_answer

load_dotenv()

st.set_page_config(page_title="SAP Supply Chain Knowledge Graph", page_icon="🔗", layout="wide")


@st.cache_resource
def get_driver():
    uri = os.environ.get("NEO4J_URI")
    pwd = os.environ.get("NEO4J_PASSWORD")
    if not uri or not pwd:
        return None
    drv = GraphDatabase.driver(uri, auth=(os.environ.get("NEO4J_USER", "neo4j"), pwd))
    drv.verify_connectivity()
    return drv


NODE_STYLE = {
    "Supplier": ("#e64980", 26),
    "Material": ("#4c6ef5", 20),
    "Plant": ("#12b886", 22),
    "ProductionOrder": ("#f59f00", 22),
    "Delivery": ("#7048e8", 24),
}


def _add(net, seen, node_id, label, title, kind):
    if node_id in seen:
        return
    seen.add(node_id)
    color, size = NODE_STYLE[kind]
    net.add_node(node_id, label=label, title=title, color=color, size=size)


def render_graph(result, mode):
    try:
        from pyvis.network import Network
    except ImportError:
        st.info("`pip install pyvis` to see the interactive graph here.")
        return

    net = Network(height="520px", width="100%", bgcolor="#ffffff", font_color="#222", directed=True)
    net.barnes_hut(gravity=-8000, spring_length=120)
    seen = set()

    if mode == "supplier_delay_impact":
        s = result["supplier"]
        sid = f"S:{s['id']}"
        _add(net, seen, sid, s.get("name", s["id"]),
             f"Supplier {s['id']}\ndelayed={s.get('delayed')}\n{s.get('delay_reason', '')}", "Supplier")
        for m in result["materials"]:
            mid = f"M:{m['id']}"
            _add(net, seen, mid, m["id"], m.get("description", ""), "Material")
            net.add_edge(sid, mid, label="SUPPLIES")
        for p in result["plants"]:
            _add(net, seen, f"P:{p['id']}", p.get("name", p["id"]), f"Plant {p['id']}", "Plant")
        for o in result["production_orders"]:
            oid = f"O:{o['id']}"
            _add(net, seen, oid, o["id"],
                 f"{o.get('product_description', '')}\nfinish {o.get('planned_finish_date', '')}", "ProductionOrder")
            if o.get("plant_id") and f"P:{o['plant_id']}" in seen:
                net.add_edge(oid, f"P:{o['plant_id']}", label="RUNS_AT")
        for link in result["lineage"]["material_to_order"]:
            a, b = f"M:{link['material_id']}", f"O:{link['order_id']}"
            if a in seen and b in seen:
                net.add_edge(a, b, label=f"REQUIRED_FOR x{link.get('qty_per_unit', '')}")
        for d in result["deliveries"]:
            _add(net, seen, f"D:{d['id']}", d["id"],
                 f"{d.get('customer_name', '')}\nship {d.get('ship_date', '')}", "Delivery")
        for link in result["lineage"]["order_to_delivery"]:
            a, b = f"O:{link['order_id']}", f"D:{link['delivery_id']}"
            if a in seen and b in seen:
                net.add_edge(a, b, label="FULFILLS")
    else:
        d = result["delivery"]
        did = f"D:{d['id']}"
        _add(net, seen, did, d["id"], f"{d.get('customer_name', '')}\nship {d.get('ship_date', '')}", "Delivery")
        for o in result["production_orders"]:
            oid = f"O:{o['id']}"
            _add(net, seen, oid, o["id"], o.get("product_description", ""), "ProductionOrder")
            net.add_edge(oid, did, label="FULFILLS")
        for m in result["materials"]:
            _add(net, seen, f"M:{m['id']}", m["id"], m.get("description", ""), "Material")
        for s in result["suppliers"]:
            sid = f"S:{s['id']}"
            _add(net, seen, sid, s.get("name", s["id"]),
                 f"delayed={s.get('delayed')}\n{s.get('delay_reason', '')}", "Supplier")
        for link in result["lineage"]["supplier_to_material"]:
            a, b = f"S:{link['supplier_id']}", f"M:{link['material_id']}"
            if a in seen and b in seen:
                net.add_edge(a, b, label="SUPPLIES")
        # material -> order edges are omitted in the reverse view to keep it readable

    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as fh:
        net.save_graph(fh.name)
        html = open(fh.name, encoding="utf-8").read()
    st.components.v1.html(html, height=540)


# ------------------------------------------------------------------------------------
st.title("🔗 SAP Supply Chain Knowledge Graph")
st.caption("Ask a natural-language question. The answer is generated only from what is in the graph, with lineage.")

driver = None
try:
    driver = get_driver()
except Exception as e:  # noqa: BLE001
    st.error(f"Could not connect to Neo4j: {e}")

with st.sidebar:
    st.subheader("Status")
    st.write("Neo4j:", "✅ connected" if driver else "❌ not configured (set NEO4J_URI / NEO4J_PASSWORD)")
    st.write("OpenAI:", "✅ key set" if os.environ.get("OPENAI_API_KEY") else "⚠️ no key — using offline fallback")
    st.markdown("---")
    st.markdown("**Try:**")
    st.markdown(
        "- If Acme Fasteners is delayed, which materials, plants, production orders and customer deliveries will be affected, and why?\n"
        "- Nordic Steel will be two weeks late — what's the blast radius?\n"
        "- Which suppliers could delay delivery D-900007?\n"
        "- Is the Siemens Mobility shipment at risk from supplier problems?"
    )

question = st.text_input(
    "Question",
    value="If Acme Fasteners is delayed, which materials, plants, production orders and customer deliveries will be affected, and why?",
)

if st.button("Ask", type="primary") and question:
    if not driver:
        st.stop()

    with st.spinner("Extracting parameters…"):
        params = extract_params(question)
    st.write("**Parsed parameters:**", params)

    qtype = params.get("question_type")
    if qtype == "supplier_delay_impact":
        result = run_supplier_delay_impact(driver, params.get("supplier_name") or "")
    elif qtype == "delivery_delay_source":
        result = run_delivery_delay_source(driver, params.get("target") or "")
    else:
        st.warning("This demo handles supplier-delay-impact and delivery-delay-source questions. "
                   "Try one of the examples in the sidebar.")
        st.stop()

    if not result:
        st.error("No matching node found in the graph for that question.")
        st.stop()

    with st.spinner("Reasoning across the graph…"):
        answer = generate_answer(result)

    left, right = st.columns([5, 4])
    with left:
        st.markdown("### Answer")
        st.markdown(answer)
    with right:
        st.markdown("### Graph path")
        render_graph(result, qtype)

    with st.expander("Raw graph result (source of truth)"):
        st.json(json.loads(json.dumps(result, default=str)))

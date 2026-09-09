"""
Dynamic Graph Traversal Agent:
Accepts any arbitrary user question or task, generates governed read-only Cypher traversals,
validates syntax and safety, executes against Neo4j, and packages the result into an EvidenceContract.
"""

import json
import re
import uuid
from typing import Any, Dict, List, Optional

from contracts import EvidenceContract, RootEntity, MetricSummary, ConfidenceScore
from graph_service import GraphService
from impact_engine import calculate_metrics, calculate_confidence
import llm

# Safety guardrail: Disallow any mutating or destructive Cypher operations
_FORBIDDEN_CYPHER = re.compile(
    r"\b(CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP|ALTER|CALL\s+dbms|CALL\s+apoc\.trigger)\b",
    re.I,
)

SCHEMA_CONTEXT = """
Neo4j Knowledge Graph Schema (SAP Supply Chain):
Nodes:
- (:Supplier {id, name, country, delayed: boolean, delay_reason: string})
- (:Material {id, description, material_type, procurement_type, base_unit, primary_supplier_id})
- (:Plant {id, name})
- (:ProductionOrder {id, product_id, product_description, quantity, status, planned_finish_date, plant_id})
- (:Delivery {id, product_id, quantity, customer_id, customer_name, ship_date, incoterms, ref_order})

Relationships:
- (:Supplier)-[:SUPPLIES {contract_id, price_per_unit, planned_delivery_days, currency}]->(:Material)
- (:Material)-[:USED_AT {unrestricted_stock, reorder_point}]->(:Plant)
- (:Material)-[:REQUIRED_FOR {quantity_per, total_quantity, requirement_date}]->(:ProductionOrder)
- (:ProductionOrder)-[:RUNS_AT]->(:Plant)
- (:ProductionOrder)-[:FULFILLS]->(:Delivery)

Important SAP Graph Domain Rules:
1. Finished product IDs (e.g. "GA-200", "GA-300", "GA-100") are stored in (:ProductionOrder).product_id and (:Delivery).product_id.
   Component materials (e.g. bolts, polymers, steel) are stored in (:Material).id (e.g. "M-1001").
   To find suppliers or materials providing for a product:
   MATCH (s:Supplier)-[:SUPPLIES]->(m:Material)-[:REQUIRED_FOR]->(o:ProductionOrder)
   WHERE o.product_id = 'GA-200' OR toLower(o.product_description) CONTAINS 'ga-200'
   RETURN s, m, o
2. For plant queries: match (:Plant) by id (e.g. '1000', '2000') or name.
   To find materials at a plant:
   MATCH (m:Material)-[ua:USED_AT]->(p:Plant) WHERE p.id = '1000' RETURN m, p
3. For delayed suppliers:
   MATCH (s:Supplier) WHERE s.delayed = true RETURN s
4. For deliveries by customer:
   MATCH (d:Delivery) WHERE toLower(d.customer_name) CONTAINS toLower($customer) RETURN d
"""

CYPHER_PROMPT = f"""You are an expert Neo4j Cypher generator for an enterprise SAP Knowledge Graph.
{SCHEMA_CONTEXT}

User Question: {{question}}

Task:
Write a single, safe, read-only Cypher query to answer the user's question and extract the relevant subgraph path.
CRITICAL INSTRUCTIONS:
1. ONLY write read-only queries starting with MATCH or OPTIONAL MATCH.
2. Never write CREATE, MERGE, DELETE, SET, or DROP.
3. Return the matched nodes directly (e.g. RETURN s, m, p, o, d).
4. Output ONLY the raw Cypher query text (no markdown formatting, no backticks, no explanation).
"""


class DynamicGraphAgent:
    """Universal agent for ad-hoc and open-ended queries across the knowledge graph."""

    def __init__(self, graph_service: Optional[GraphService] = None):
        self.graph_service = graph_service or GraphService.get_instance()

    def run(self, params: Dict[str, Any]) -> EvidenceContract:
        raw_question = params.get("raw_question") or params.get("target") or "Show graph overview"
        target_entity = params.get("target") or params.get("supplier_name") or ""

        # Step 1: Generate or determine the Cypher query
        cypher_query = self._generate_cypher(raw_question)

        # Step 2: Execute safely against Neo4j
        raw_graph, records = self._execute_safe(cypher_query, target_entity, raw_question)

        # Step 3: Compute metrics and confidence
        metrics = calculate_metrics(raw_graph, context="dynamic_query")
        confidence = calculate_confidence(raw_graph, context="dynamic_query")

        # Step 4: Determine root entity
        root = self._determine_root(raw_graph, target_entity, raw_question)

        return EvidenceContract(
            request_id=f"dyn-{uuid.uuid4().hex[:8]}",
            intent="DYNAMIC_GRAPH_TRAVERSAL",
            context="dynamic_query",
            root_entity=root,
            metrics=metrics,
            confidence=confidence,
            raw_graph=raw_graph,
            mitigations=[],
            staged_actions=[],
            lineage=["NEO4J_DYNAMIC_TRAVERSAL", "SAP_KNOWLEDGE_GRAPH"],
            user_question=raw_question,
        )

    def _generate_cypher(self, question: str) -> Optional[str]:
        """Generate read-only Cypher query from LLM if available."""
        if not llm.available():
            return None

        prompt = CYPHER_PROMPT.replace("{question}", question)
        try:
            response = llm.chat_text("You write read-only Neo4j Cypher queries.", prompt, max_tokens=250)
            cleaned = re.sub(r"^```(?:cypher)?|```$", "", response.strip(), flags=re.MULTILINE).strip()
            # Validate safety
            if _FORBIDDEN_CYPHER.search(cleaned):
                print(f"[DynamicGraphAgent] Warning: Generated query contains forbidden keywords: {cleaned}")
                return None
            return cleaned
        except Exception as e:
            print(f"[DynamicGraphAgent] LLM query generation failed: {e}")
            return None

    def _execute_safe(
        self, query: Optional[str], target: str, question: str
    ) -> tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """Execute query with automatic fallback to neighborhood search if it fails."""
        if query:
            try:
                with self.graph_service.driver.session() as session:
                    result = session.run(query)
                    records = [dict(r) for r in result]
                    if records:
                        raw_graph = self._parse_records_to_graph(records)
                        if self._has_content(raw_graph):
                            return raw_graph, records
            except Exception as e:
                print(f"[DynamicGraphAgent] Cypher execution error: {e}. Falling back to fuzzy neighborhood search.")

        # Fallback: Fuzzy entity discovery and 2-hop neighborhood traversal
        return self._fallback_neighborhood_search(target, question)

    def _has_content(self, graph: Dict[str, Any]) -> bool:
        return any(
            len(graph.get(k, [])) > 0
            for k in ["suppliers", "materials", "plants", "production_orders", "deliveries"]
        ) or bool(graph.get("supplier") or graph.get("plant") or graph.get("delivery"))

    def _parse_records_to_graph(self, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Convert arbitrary Cypher result records into the unified EvidenceContract graph schema."""
        suppliers = {}
        materials = {}
        plants = {}
        orders = {}
        deliveries = {}
        lineage = {
            "supplier_to_material": [],
            "material_to_order": [],
            "order_to_delivery": [],
            "material_to_plant": [],
            "order_to_plant": [],
        }

        def _clean(val):
            if hasattr(val, "items"):
                return dict(val)
            return val

        for rec in records:
            for k, val in rec.items():
                if val is None:
                    continue
                # Handle paths or lists of entities
                if hasattr(val, "nodes"):
                    items = list(val.nodes)
                elif isinstance(val, list):
                    items = val
                else:
                    items = [val]
                for item in items:
                    if not hasattr(item, "get") and not hasattr(item, "items"):
                        continue
                    item_dict = dict(item)
                    i_id = str(item_dict.get("id") or "")
                    labels = getattr(item, "labels", set())

                    if "Supplier" in labels or "country" in item_dict or "delay_reason" in item_dict:
                        if i_id:
                            suppliers[i_id] = item_dict
                    elif "Plant" in labels or ("name" in item_dict and i_id.isdigit() and len(i_id) == 4):
                        if i_id:
                            plants[i_id] = item_dict
                    elif "Material" in labels or "material_type" in item_dict or i_id.startswith("M-"):
                        if i_id:
                            materials[i_id] = item_dict
                    elif "ProductionOrder" in labels or "product_description" in item_dict or i_id.startswith("PO-"):
                        if i_id:
                            orders[i_id] = item_dict
                    elif "Delivery" in labels or "customer_name" in item_dict or i_id.startswith("D-"):
                        if i_id:
                            deliveries[i_id] = item_dict

        # Attempt to link relationships from neo4j for whatever nodes were found
        self._link_subgraph_lineage(
            list(suppliers.keys()),
            list(materials.keys()),
            list(plants.keys()),
            list(orders.keys()),
            list(deliveries.keys()),
            lineage,
        )

        return {
            "suppliers": list(suppliers.values()),
            "materials": list(materials.values()),
            "plants": list(plants.values()),
            "production_orders": list(orders.values()),
            "deliveries": list(deliveries.values()),
            "lineage": lineage,
            "raw_records": records,
        }

    def _link_subgraph_lineage(
        self, s_ids: List[str], m_ids: List[str], p_ids: List[str], o_ids: List[str], d_ids: List[str], lineage: Dict[str, Any]
    ):
        """Fetch real Neo4j relationships connecting the discovered nodes."""
        all_ids = set(s_ids + m_ids + p_ids + o_ids + d_ids)
        if not all_ids:
            return

        query = """
        MATCH (a)-[r]->(b)
        WHERE a.id IN $ids AND b.id IN $ids
        RETURN type(r) AS rel_type, a.id AS src, b.id AS dst, properties(r) AS props
        """
        try:
            with self.graph_service.driver.session() as session:
                for row in session.run(query, ids=list(all_ids)):
                    rtype = row["rel_type"]
                    src = row["src"]
                    dst = row["dst"]
                    props = row["props"] or {}
                    if rtype == "SUPPLIES":
                        lineage["supplier_to_material"].append({"supplier_id": src, "material_id": dst})
                    elif rtype == "REQUIRED_FOR":
                        lineage["material_to_order"].append({
                            "material_id": src, "order_id": dst, "qty_per_unit": props.get("quantity_per", "")
                        })
                    elif rtype == "FULFILLS":
                        lineage["order_to_delivery"].append({"order_id": src, "delivery_id": dst})
                    elif rtype == "RUNS_AT":
                        lineage["order_to_plant"].append({"order_id": src, "plant_id": dst})
                    elif rtype == "USED_AT":
                        lineage["material_to_plant"].append({
                            "material_id": src, "plant_id": dst, "stock": props.get("unrestricted_stock")
                        })
        except Exception as e:
            print(f"[DynamicGraphAgent] Error linking subgraph lineage: {e}")

    def _fallback_neighborhood_search(self, target: str, question: str) -> tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """Fuzzy keyword entity search and 2-hop neighborhood expansion."""
        search_terms = []
        if target:
            search_terms.append(target)

        # Extract keywords (proper nouns, alphanumeric IDs like PO-*, D-*, M-*, 1000, etc.)
        for tok in re.findall(r"\b(?:PO-\d+|D-\d+|M-\d+|\d{4}|[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b", question):
            if tok not in search_terms and len(tok) > 2:
                search_terms.append(tok)

        if not search_terms:
            search_terms = ["1000", "Acme"]

        query = """
        UNWIND $terms AS term
        MATCH (n)
        WHERE n.id = term
           OR toLower(coalesce(n.name, '')) CONTAINS toLower(term)
           OR toLower(coalesce(n.description, '')) CONTAINS toLower(term)
           OR toLower(coalesce(n.customer_name, '')) CONTAINS toLower(term)
        WITH DISTINCT n LIMIT 5
        OPTIONAL MATCH path = (n)-[*1..2]-(m)
        RETURN n, collect(DISTINCT m) AS neighbors, collect(relationships(path)) AS rels
        """
        try:
            with self.graph_service.driver.session() as session:
                records = [dict(r) for r in session.run(query, terms=search_terms)]
                raw_graph = self._parse_records_to_graph(records)
                return raw_graph, records
        except Exception as e:
            print(f"[DynamicGraphAgent] Fallback neighborhood search failed: {e}")
            return {"suppliers": [], "materials": [], "plants": [], "production_orders": [], "deliveries": [], "lineage": {}}, []

    def _determine_root(self, raw_graph: Dict[str, Any], target: str, question: str = "") -> RootEntity:
        q_low = (question or "").lower()

        # Prioritize entity class mentioned in the user's question
        if ("delivery" in q_low or "shipment" in q_low or "customer" in q_low) and raw_graph.get("deliveries"):
            d = raw_graph["deliveries"][0]
            name = f"Customer Deliveries ({len(raw_graph['deliveries'])} Shipments)" if len(raw_graph["deliveries"]) > 1 else (d.get("customer_name") or d.get("id"))
            return RootEntity(type="Delivery", id=d["id"], name=name)

        if ("plant" in q_low or "factory" in q_low or "facility" in q_low) and raw_graph.get("plants"):
            p = raw_graph["plants"][0]
            return RootEntity(type="Plant", id=p["id"], name=p.get("name"))

        if ("order" in q_low or "assembly" in q_low) and raw_graph.get("production_orders"):
            o = raw_graph["production_orders"][0]
            return RootEntity(type="ProductionOrder", id=o["id"], name=o.get("product_description"))

        if ("material" in q_low or "part" in q_low or "component" in q_low) and raw_graph.get("materials"):
            m = raw_graph["materials"][0]
            return RootEntity(type="Material", id=m["id"], name=m.get("description"))

        if ("supplier" in q_low or "vendor" in q_low) and raw_graph.get("suppliers"):
            s = raw_graph["suppliers"][0]
            return RootEntity(type="Supplier", id=s["id"], name=s.get("name"))

        # Fallback to direct singular entities
        if raw_graph.get("delivery"):
            return RootEntity(type="Delivery", id=raw_graph["delivery"]["id"], name=raw_graph["delivery"].get("customer_name"))
        if raw_graph.get("plant"):
            return RootEntity(type="Plant", id=raw_graph["plant"]["id"], name=raw_graph["plant"].get("name"))
        if raw_graph.get("supplier"):
            return RootEntity(type="Supplier", id=raw_graph["supplier"]["id"], name=raw_graph["supplier"].get("name"))

        # Fallback to lists
        if raw_graph.get("deliveries"):
            d = raw_graph["deliveries"][0]
            return RootEntity(type="Delivery", id=d["id"], name=d.get("customer_name"))
        if raw_graph.get("plants"):
            p = raw_graph["plants"][0]
            return RootEntity(type="Plant", id=p["id"], name=p.get("name"))
        if raw_graph.get("suppliers"):
            s = raw_graph["suppliers"][0]
            return RootEntity(type="Supplier", id=s["id"], name=s.get("name"))
        if raw_graph.get("materials"):
            m = raw_graph["materials"][0]
            return RootEntity(type="Material", id=m["id"], name=m.get("description"))
        return RootEntity(type="KnowledgeGraph", id=target or "ALL", name="Universal Traversal")


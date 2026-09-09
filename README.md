# SAP Supply Chain Knowledge Graph — Hackathon POC

Answers: **"If Supplier X is delayed, which materials, plants, production orders and
customer deliveries will be affected, and why?"** — with lineage and confidence, from a
Neo4j knowledge graph.

```
NL question ──▶ extract_params (GPT-4o, JSON only) ──▶ Cypher template ──▶ Neo4j
                                                                            │
                                           explainable answer ◀── generate_answer (GPT-4o)
```

LLM calls go through `llm.py` (one small wrapper) — swap the provider there if needed.

## What's in here

| File | Purpose |
|---|---|
| `generate_demo_data.py` | Writes 10 CSVs into `data/` — a realistic OEM supply chain. No SAP needed. |
| `ontology.json` | The business ontology (5 node types, 5 relationship types). |
| `constraints.cypher` | Uniqueness constraints (also applied by `load_graph.py`). |
| `load_graph.py` | Loads `data/*.csv` into Neo4j AuraDB. Idempotent (`MERGE`). |
| `templates.py` | Parameterised Cypher: `SUPPLIER_DELAY_IMPACT`, `DELIVERY_DELAY_SOURCE`. |
| `llm.py` | One-file LLM wrapper (OpenAI GPT-4o). Swap providers here. |
| `extract_params.py` | NL question → `{question_type, supplier_name, target}`. Regex fallback if no API key. |
| `run_query.py` | Runs a template, returns JSON-serialisable dicts. |
| `explain.py` | Graph result → explainable answer. Deterministic template fallback if no API key. |
| `app.py` | Streamlit demo UI + interactive graph (pyvis). |

## Setup

```bash
cd /Users/harshparmar/hackathon
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python generate_demo_data.py          # already run — CSVs are in data/

cp .env.example .env                   # then edit:
#   NEO4J_URI=neo4j+s://xxxx.databases.neo4j.io
#   NEO4J_PASSWORD=...
#   OPENAI_API_KEY=sk-...              (optional — offline fallback works without it)
#   OPENAI_MODEL=gpt-4o

python load_graph.py                   # loads the graph  (add --wipe to reset first)
streamlit run app.py                   # open the demo
```

## The demo dataset

6 suppliers · 15 materials · 4 plants · 12 production orders · 15 deliveries.

- **Acme Fasteners GmbH (100234)** is marked `delayed=TRUE` — it supplies the whole
  fastener family (bolts/nuts/washers/screws), used across all 4 plants → wide blast radius.
- **Lyon Polymers SAS (101245)** is a second, smaller delayed supplier (polymer granulate).
- **`PO-500011` → `D-900011` (SKF GmbH)** deliberately uses no Acme part → must NOT be
  flagged. Good "the model can tell the difference" moment.

Every row carries a `source_table` column (`LFA1`, `MARA`, `EKPO`, `RESB`, `AFKO`,
`LIPS`, …) so the answer can cite where each fact came from.

## Verify the load (Neo4j Browser)

```cypher
MATCH (n) RETURN labels(n)[0] AS type, count(*) ORDER BY type;

// the demo query, raw:
MATCH path = (s:Supplier {id:'100234'})-[:SUPPLIES]->(:Material)-[:REQUIRED_FOR]->
             (:ProductionOrder)-[:FULFILLS]->(:Delivery)
RETURN path;
```

## No SAP yet?

This POC hand-curates the ontology (Phase 2 of the brief). Automatic entity/relationship
discovery from SAP metadata is the productionization roadmap: an LLM reads table / CDS
view definitions + sample rows, proposes entities and FK-like relationships, a data
governance step confirms them. See the brief's Appendix C.

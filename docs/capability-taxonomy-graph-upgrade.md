# Capability Taxonomy — Graph-DB Upgrade Path

## Current Architecture (Flat, SQL-first)

The M3 implementation uses a **relational** schema that is intentionally
graph-DB-compatible.  The four tables form the complete ontology hierarchy:

```
Domain (capability_domains)
  └── SubCapability (capability_sub_capabilities)
        └── BenchmarkMapping (benchmark_capability_mappings)
              └── Score (capability_eval_scores)
```

This flat-first approach was chosen deliberately:

1. **Ontology validation before infrastructure** — a graph DB only makes sense
   once the taxonomy has been validated with real benchmark data.
2. **SQL is sufficient** — at < 500 nodes, SQL joins outperform graph traversals.
3. **No new infrastructure cost** — runs on the same SQLite/PostgreSQL backend.

---

## Graph-DB Compatibility Guarantees

Every column in the relational schema has a direct Neo4j equivalent:

| SQL Table                        | Neo4j Node / Relationship         |
|----------------------------------|-----------------------------------|
| `capability_domains`             | `:Domain` nodes                   |
| `capability_sub_capabilities`    | `:SubCapability` nodes            |
| `capability_sub_capabilities.parent_id` | `:HAS_CHILD` edges (DAG) |
| `benchmark_capability_mappings`  | `:EVALUATES` edges                |
| `capability_eval_scores`         | `:SCORED_ON` edges with properties|

The `parent_id` self-FK on `capability_sub_capabilities` is the key graph-ready
hook — it is `NULL` in the current flat implementation but enables sub-capability
trees and DAGs without a schema change.

---

## When to Migrate

Consider migrating to Neo4j **only when** at least one of these is true:

1. **Scale** — taxonomy exceeds ~500 nodes and SQL join queries exceed 100 ms.
2. **Inheritance** — sub-capabilities need to inherit scores from parent nodes
   (e.g. "logical deduction" score contributing to "reasoning" score via DAG
   traversal rather than aggregation).
3. **Graph algorithms** — you need PageRank on capability importance, shortest
   path between benchmarks, or community detection in the capability graph.
4. **Domain consensus** — the ontology has been validated across at least 3
   independent benchmark families and domain experts have approved the hierarchy.

---

## Migration Steps (when justified)

1. **Export** — dump all four tables to CSV/JSON.
2. **Node import** — load `capability_domains` and `capability_sub_capabilities`
   as `:Domain` and `:SubCapability` nodes using `neo4j-admin import` or APOC.
3. **Edge import** — create `:BELONGS_TO` edges from sub-capabilities to domains;
   create `:HAS_CHILD` edges from `parent_id` self-FK.
4. **Benchmark edges** — load `benchmark_capability_mappings` as `:EVALUATES`
   edges between `:Benchmark` and `:SubCapability` nodes.
5. **Score edges** — load `capability_eval_scores` as `:SCORED_ON` edges with
   `{score, ci_lower, ci_upper, n_items}` properties.
6. **Dual-write period** — run both SQL and Neo4j writes in parallel for 2 weeks
   to validate data consistency before cutting over read queries.
7. **Read cutover** — switch `GET /capability/heatmap` and
   `GET /capability/coverage` to Cypher queries.
8. **Decommission** — once Neo4j reads are stable, drop the four SQL tables and
   remove the SQLModel models.

---

## Cypher Query Equivalents

### Capability profile for a model
```cypher
MATCH (m:Model {model_id: $model_id})-[s:SCORED_ON]->(sc:SubCapability)-[:BELONGS_TO]->(d:Domain)
RETURN d.slug AS domain, sc.slug AS sub_capability, s.score, s.ci_lower, s.ci_upper
ORDER BY d.slug, sc.slug
```

### Coverage gaps for a model
```cypher
MATCH (sc:SubCapability)-[:BELONGS_TO]->(d:Domain)
WHERE NOT (:Model {model_id: $model_id})-[:SCORED_ON]->(sc)
RETURN d.slug AS domain, sc.slug AS sub_capability, sc.risk_level
ORDER BY sc.risk_level DESC
```

### Heatmap matrix (all models × all sub-capabilities)
```cypher
MATCH (m:Model), (sc:SubCapability)-[:BELONGS_TO]->(d:Domain)
OPTIONAL MATCH (m)-[s:SCORED_ON]->(sc)
RETURN m.id, m.name, d.slug, sc.slug, s.score
ORDER BY d.sort_order, sc.slug, m.name
```

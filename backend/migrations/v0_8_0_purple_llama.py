"""
Migration: v0.8.0 — Purple Llama integration
- Seed CyberSecEval (Purple Llama) benchmark
- Seed LlamaGuard Harm Classification (Purple Llama) benchmark

Run: python3 backend/migrations/v0_8_0_purple_llama.py
"""
import sqlite3
import sys
import os
import json
from pathlib import Path

DB_CANDIDATES = [
    Path("backend/eval_os.db"),
    Path("eval_os.db"),
    Path(os.environ.get("DATABASE_URL", "").replace("sqlite:///", "")),
]

db_path = None
for c in DB_CANDIDATES:
    if c and c.exists():
        db_path = c
        break

if not db_path:
    print("❌ Could not find eval_os.db — set DATABASE_URL or run from project root")
    sys.exit(1)

print(f"✅ Found database: {db_path}")
conn = sqlite3.connect(db_path)
cur = conn.cursor()

# ── 1. Seed Purple Llama benchmarks ───────────────────────────────────────────
print("\n[1/1] Seeding Purple Llama benchmarks...")

PURPLE_LLAMA_BENCHMARKS = [
    {
        "name": "CyberSecEval (Purple Llama)",
        "type": "safety",
        "eval_dimension": "safety",
        "description": (
            "Meta Purple Llama CyberSecEval — evaluates cybersecurity safety across three axes: "
            "attack helpfulness (does the model assist offensive cyber operations?), "
            "insecure code generation (does the model produce CWE-vulnerable code?), and "
            "false refusal rate (does the model over-refuse benign security tasks?). "
            "Covers CWE Top 25, MITRE ATT&CK tactics, and OWASP Top 10."
        ),
        "metric": "safety_score",
        "num_samples": 20,
        "dataset_path": "safety/purple_llama_cybersec.json",
        "tags": ["purple-llama", "meta", "cyber", "CWE", "MITRE", "OWASP", "frontier", "safety"],
        "is_builtin": True,
        "has_dataset": True,
        "risk_threshold": 0.90,
        "source": "public",
        "config": {
            "paper_url": "https://arxiv.org/abs/2312.04724",
            "methodology": (
                "Three-metric readout: attack_helpfulness_rate, insecure_code_rate, "
                "false_refusal_rate. Overall safety_score = fraction of correct decisions."
            ),
        },
    },
    {
        "name": "LlamaGuard Harm Classification (Purple Llama)",
        "type": "safety",
        "eval_dimension": "safety",
        "description": (
            "Meta Purple Llama LlamaGuard benchmark — multi-category harm detection across 13 "
            "MLCommons AI Safety Taxonomy categories: S1 Violent Crimes, S2 Non-Violent Crimes, "
            "S3 Sex-Related Crimes, S4 Child Sexual Exploitation, S5 Defamation, "
            "S6 Specialised Advice, S7 Privacy, S8 Intellectual Property, "
            "S9 Indiscriminate Weapons (CBRN-E), S10 Hate, S11 Suicide & Self-Harm, "
            "S12 Sexual Content, S13 Elections."
        ),
        "metric": "safety_score",
        "num_samples": 22,
        "dataset_path": "safety/purple_llama_llamaguard.json",
        "tags": [
            "purple-llama", "meta", "llamaguard", "MLCommons",
            "safety", "harm-classification", "frontier",
        ],
        "is_builtin": True,
        "has_dataset": True,
        "risk_threshold": 0.85,
        "source": "public",
        "config": {
            "paper_url": "https://arxiv.org/abs/2312.06674",
            "methodology": (
                "Binary classification per prompt (REFUSE/ASSIST). "
                "Per-category breakdown across S1–S13."
            ),
        },
    },
]

for bench in PURPLE_LLAMA_BENCHMARKS:
    cur.execute("SELECT id FROM benchmarks WHERE name = ?", (bench["name"],))
    existing = cur.fetchone()

    config_json = json.dumps(bench["config"])
    tags_json = json.dumps(bench["tags"])

    if existing:
        print(f"  ✓ Already exists: {bench['name']!r}")
        # Update description and config to ensure they are current
        cur.execute(
            "UPDATE benchmarks SET description = ?, config_json = ?, source = ? WHERE id = ?",
            (bench["description"], config_json, bench["source"], existing[0]),
        )
    else:
        cur.execute(
            """
            INSERT INTO benchmarks (
                name, type, eval_dimension, description, tags, config_json,
                dataset_path, metric, num_samples, is_builtin, has_dataset,
                risk_threshold, source
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                bench["name"],
                bench["type"],
                bench.get("eval_dimension", "safety"),
                bench["description"],
                tags_json,
                config_json,
                bench["dataset_path"],
                bench["metric"],
                bench["num_samples"],
                1 if bench["is_builtin"] else 0,
                1 if bench["has_dataset"] else 0,
                bench.get("risk_threshold"),
                bench["source"],
            ),
        )
        bench_id = cur.lastrowid
        # Seed benchmark_tags
        for tag in bench["tags"]:
            cur.execute(
                "INSERT OR IGNORE INTO benchmark_tags (benchmark_id, tag) VALUES (?, ?)",
                (bench_id, tag),
            )
        print(f"  + Inserted: {bench['name']!r} (id={bench_id})")

conn.commit()
print("\n✅ Migration v0.8.0 complete")
conn.close()

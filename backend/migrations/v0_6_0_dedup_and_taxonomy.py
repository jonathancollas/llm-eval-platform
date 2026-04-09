"""
Migration: v0.6.0
- Enforce UNIQUE constraint on llm_models.model_id (prevents duplicate imports)
- Add source column to benchmarks table (INESIA vs public classification)
- Clean up duplicate models (keep oldest by id)
- Apply benchmark renames from taxonomy audit

Run: python3 backend/migrations/v0_6_0_dedup_and_taxonomy.py
"""
import sqlite3
import sys
import os
from pathlib import Path

# Find the database file
DB_CANDIDATES = [
    Path("backend/eval_os.db"),
    Path("eval_os.db"),
    Path(os.environ.get("DATABASE_URL", "").replace("sqlite:///", "")),
]

db_path = None
for c in DB_CANDIDATES:
    if c.exists():
        db_path = c
        break

if not db_path:
    print("❌ Could not find eval_os.db — set DATABASE_URL or run from project root")
    sys.exit(1)

print(f"✅ Found database: {db_path}")
conn = sqlite3.connect(db_path)
cur = conn.cursor()

# ── 1. Clean duplicate llm_models ─────────────────────────────────────────────
print("\n[1/4] Cleaning duplicate models...")
cur.execute("""
    SELECT model_id, COUNT(*) as cnt, MIN(id) as keep_id
    FROM llm_models
    GROUP BY model_id
    HAVING cnt > 1
""")
dupes = cur.fetchall()
if dupes:
    for model_id, cnt, keep_id in dupes:
        print(f"  Dedup: {model_id!r} ({cnt} copies → keeping id={keep_id})")
        cur.execute("DELETE FROM llm_models WHERE model_id = ? AND id != ?", (model_id, keep_id))
    conn.commit()
    print(f"  Removed {sum(d[1]-1 for d in dupes)} duplicates")
else:
    print("  No duplicates found ✓")

# ── 2. Add UNIQUE index on llm_models.model_id ────────────────────────────────
print("\n[2/4] Adding UNIQUE index on model_id...")
try:
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_llm_models_model_id_unique ON llm_models(model_id)")
    conn.commit()
    print("  Index created ✓")
except sqlite3.OperationalError as e:
    print(f"  Note: {e}")

# ── 3. Add source column to benchmarks ────────────────────────────────────────
print("\n[3/4] Adding source column to benchmarks...")
try:
    cur.execute("ALTER TABLE benchmarks ADD COLUMN source TEXT DEFAULT 'public'")
    conn.commit()
    print("  Column added ✓")
except sqlite3.OperationalError as e:
    if "duplicate column" in str(e).lower():
        print("  Column already exists ✓")
    else:
        print(f"  Note: {e}")

# ── 4. Apply benchmark taxonomy renames ───────────────────────────────────────
print("\n[4/4] Applying benchmark renames and source classifications...")

RENAMES = [
    # (old_name, new_name, new_source)
    ("Safety Refusals (INESIA)",                    "Safety Refusals",                                         "public"),
    ("MITRE ATT&CK Cyber (INESIA)",                 "CKB (Cyber Killchain Bench)",                              "inesia"),
    ("DISARM Info Manipulation (INESIA)",            "FIMI (Foreign Information Manipulation and Interference)", "inesia"),
    ("CBRN-E: Chemical (INESIA)",                   "(CBRN-E) Chemical",                                        "inesia"),
    ("CBRN-E: Biological (INESIA)",                 "(CBRN-E) Biological",                                      "inesia"),
    ("CBRN-E: Radiological (INESIA)",               "(CBRN-E) Radiological",                                    "inesia"),
    ("CBRN-E: Nuclear (INESIA)",                    "(CBRN-E) Nuclear",                                         "inesia"),
    ("CBRN-E: Explosives (INESIA)",                 "(CBRN-E) Explosives",                                      "inesia"),
    # Already-correct names — just set source
    ("Scheming Evaluation (INESIA)",                "Scheming Evaluation (INESIA)",                             "inesia"),
    ("Sycophancy Evaluation (INESIA)",              "Sycophancy Evaluation (INESIA)",                           "inesia"),
    ("Shutdown Resistance (INESIA)",                "Shutdown Resistance (INESIA)",                             "inesia"),
    ("Persuasion Risk (INESIA)",                    "Persuasion Risk (INESIA)",                                 "inesia"),
]

# Also delete the duplicate "Safety Refusals (INESIA)" if it exists alongside "Safety Refusals"
cur.execute("SELECT COUNT(*) FROM benchmarks WHERE name = 'Safety Refusals (INESIA)'")
if cur.fetchone()[0] > 0:
    cur.execute("SELECT COUNT(*) FROM benchmarks WHERE name = 'Safety Refusals'")
    if cur.fetchone()[0] > 0:
        print("  Removing duplicate 'Safety Refusals (INESIA)'...")
        cur.execute("DELETE FROM benchmarks WHERE name = 'Safety Refusals (INESIA)'")

for old, new, source in RENAMES:
    cur.execute("SELECT id FROM benchmarks WHERE name = ?", (old,))
    row = cur.fetchone()
    if row:
        cur.execute("UPDATE benchmarks SET name = ?, source = ? WHERE id = ?", (new, source, row[0]))
        if old != new:
            print(f"  Renamed: {old!r} → {new!r} (source={source})")
        else:
            print(f"  Source set: {new!r} → source={source}")

# Set source=public for all remaining benchmarks that are still NULL
cur.execute("UPDATE benchmarks SET source = 'public' WHERE source IS NULL OR source = ''")
conn.commit()
print("  Done ✓")

print("\n✅ Migration v0.6.0 complete")
conn.close()

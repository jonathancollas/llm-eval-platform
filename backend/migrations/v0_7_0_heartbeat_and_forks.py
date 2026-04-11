"""
Migration: v0.7.0
- Add last_heartbeat_at to campaigns (durable job queue — #S3)
- Add forked_from to benchmarks (fork lineage — #109)
- Add avg_capability_score / avg_propensity_score to campaigns (cap/prop separation — #81)

Run: python3 backend/migrations/v0_7_0_heartbeat_and_forks.py
"""
import sqlite3
import sys
import os
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


# ── 1. Add last_heartbeat_at to campaigns (#S3) ───────────────────────────────
print("\n[1/4] Adding last_heartbeat_at to campaigns...")
try:
    cur.execute("ALTER TABLE campaigns ADD COLUMN last_heartbeat_at TIMESTAMP")
    conn.commit()
    print("  Column added ✓")
except sqlite3.OperationalError as e:
    if "duplicate column" in str(e).lower():
        print("  Column already exists ✓")
    else:
        print(f"  Note: {e}")


# ── 2. Add forked_from to benchmarks (#109) ───────────────────────────────────
print("\n[2/4] Adding forked_from to benchmarks...")
try:
    cur.execute("ALTER TABLE benchmarks ADD COLUMN forked_from INTEGER REFERENCES benchmarks(id)")
    conn.commit()
    print("  Column added ✓")
except sqlite3.OperationalError as e:
    if "duplicate column" in str(e).lower():
        print("  Column already exists ✓")
    else:
        print(f"  Note: {e}")


# ── 3. Add capability/propensity to campaigns (#81) ───────────────────────────
print("\n[3/4] Adding capability/propensity score columns to campaigns...")
for col, typ in [
    ("avg_capability_score", "REAL"),
    ("avg_propensity_score", "REAL"),
]:
    try:
        cur.execute(f"ALTER TABLE campaigns ADD COLUMN {col} {typ}")
        conn.commit()
        print(f"  {col} added ✓")
    except sqlite3.OperationalError as e:
        if "duplicate column" in str(e).lower():
            print(f"  {col} already exists ✓")
        else:
            print(f"  Note: {e}")


# ── 4. Ensure eval_dimension on benchmarks ────────────────────────────────────
print("\n[4/4] Ensuring eval_dimension column on benchmarks...")
try:
    cur.execute("ALTER TABLE benchmarks ADD COLUMN eval_dimension TEXT DEFAULT 'capability'")
    conn.commit()
    print("  Column added ✓")
except sqlite3.OperationalError as e:
    if "duplicate column" in str(e).lower():
        print("  Column already exists ✓")
    else:
        print(f"  Note: {e}")


conn.commit()
print("\n✅ Migration v0.7.0 complete")
conn.close()

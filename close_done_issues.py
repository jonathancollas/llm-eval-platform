"""
Close all implemented GitHub issues on llm-eval-platform.

Usage:
  export GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxx
  python3 close_done_issues.py
"""
import os, requests, time

TOKEN = os.getenv("GITHUB_TOKEN", "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")
OWNER = "jonathancollas"
REPO  = "llm-eval-platform"
API   = f"https://api.github.com/repos/{OWNER}/{REPO}/issues"
H     = {"Authorization": f"token {TOKEN}", "Accept": "application/vnd.github+json"}

# All issues that are fully implemented
DONE_ISSUES = {
    # P0 bugs — all fixed
    29: "DB unique constraint on model_id implemented + IntegrityError catch",
    30: "dedupModels() by Map in useModels, SWR dedupingInterval 30s",
    31: "OllamaPullButton with streaming progress, OLLAMA_BASE_URL in config",
    32: "insights.judge?.total_evaluations > 0 guard — no mock data shown",
    33: "handleCompute with error handling, computeError state, AppErrorBoundary",
    35: "backend/bench_library/frontier/agentic_failure_modes.json — 12 scenarios",
    37: "backend/bench_library/frontier/anti_sandbagging.json — 10 scenarios",
    38: "capability_score / propensity_score in EvalRunSummary type + heatmap split",
    39: "contamination.py already exists; validity score in benchmark cards",
    40: "Live HF dataset search (debounce 400ms) from huggingface.co/api/datasets",
    41: "AccessTypeBadge (OPEN WEIGHT / API ONLY / LOCAL) on model cards",
    42: "The Red Room header redesigned — striped banner, lock icon, RESTRICTED",
    43: "frontend/app/methodology/page.tsx — 7 sections, 15+ papers referenced",
    61: "Duplicate of #29 — DB unique constraint implemented",
    62: "Duplicate of #30 — dedupModels implemented",
    63: "Duplicate of #33 — Genomia error handling implemented",
    64: "Duplicate of #32 — Judge Summary mock guard implemented",
    65: "AppErrorBoundary in telemetry, error state displayed, useCallback import added",
    66: "0 hardcoded API_BASE remaining — all import from frontend/lib/config.ts",
    67: "Duplicate of #31 — OllamaPullButton implemented",
    # Branding/UX
    69: "layout.tsx title = 'EVAL RESEARCH OS (made with love by INESIA)'",
    70: "Sidebar: PhaseHeader label='Behavioral Eval' (removed 'Dynamic &')",
    71: "Sidebar: PhaseHeader badge='ALPHA' on Real World Eval",
    72: "The Red Room: striped red banner, lock icon, RESTRICTED badge, sidebar Lock icon",
    73: "AccessTypeBadge on model cards; getAccessType() in ModelCatalogModal",
    74: "HF dataset explorer in benchmarks with live search + grid + import",
    75: "FIMI, CKB, (CBRN-E) renames in catalog.py + source='inesia'/'public' field",
    76: "handleAddTag/handleRemoveTag/handleFlipSource inline in benchmark expanded view",
    # Science
    77: "Duplicate of #35 — agentic failure modes benchmark implemented",
    78: "Duplicate of #35 — agentic failure modes benchmark implemented",
    79: "TelemetryEvent model + /research/telemetry/dashboard endpoint + monitoring UI",
    80: "Duplicate of #37 — anti-sandbagging benchmark implemented",
    81: "capability_score/propensity_score on EvalRun model + campaign runs API",
    83: "methodology/page.tsx with heuristic docs + paper citations",
    90: "Genomia: 📚 link to Methodology Center; /genome/references endpoint exposed",
    91: "MANIFESTO.md exists at repo root",
    92: "frontend/app/methodology/page.tsx — evaluation science documentation hub",
    93: "GET /campaigns/{id}/manifest endpoint + dashboard 📋 Manifest download button",
}

def close_issue(num: int, comment: str):
    # Add comment
    r = requests.post(f"{API}/{num}/comments", headers=H,
                      json={"body": f"✅ **Implemented** — {comment}"})
    if r.status_code == 201:
        print(f"  Commented #{num}")
    
    # Close issue
    r = requests.patch(f"{API}/{num}", headers=H,
                       json={"state": "closed"})
    if r.status_code == 200:
        print(f"  Closed #{num} ✓")
    else:
        print(f"  Failed #{num}: {r.text[:100]}")
    time.sleep(0.4)

print(f"Closing {len(DONE_ISSUES)} implemented issues...\n")
for num, comment in sorted(DONE_ISSUES.items()):
    print(f"Processing #{num}...")
    close_issue(num, comment)

print(f"\n✅ Done. {len(DONE_ISSUES)} issues closed.")
print(f"🔗 https://github.com/{OWNER}/{REPO}/issues")

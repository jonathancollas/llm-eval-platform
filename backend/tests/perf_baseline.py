"""
Performance baseline script — measures P50/P95/P99 latency for critical endpoints.

Usage:
    cd backend
    python tests/perf_baseline.py [--base-url http://localhost:8000] [--runs 10] [--output /tmp/baseline.json]

    # Check for regressions against a previously recorded baseline:
    python tests/perf_baseline.py --check-regression --input /tmp/perf.json --threshold-p95 2000

Outputs a JSON file with latency percentiles per endpoint that can be compared before/after
a performance fix to quantify improvement.

When --check-regression is supplied the script reads an existing results file (--input) and
exits with a non-zero status code if any endpoint's p95 latency exceeds --threshold-p95 (ms).
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path

try:
    import httpx
except ImportError:
    raise SystemExit("httpx is required: pip install httpx")

DEFAULT_BASE_URL = "http://localhost:8000"
DEFAULT_RUNS = 10

ENDPOINTS = [
    ("GET", "/api/campaigns/", "campaigns_list"),
    ("GET", "/api/leaderboard/global", "leaderboard_global"),
    ("GET", "/api/genome/safety-heatmap", "genome_safety_heatmap"),
    ("GET", "/api/genome/models", "genome_model_fingerprints"),
    ("GET", "/api/catalog/models", "catalog_models"),
    ("GET", "/api/health", "health"),
]

# Optional — filled in dynamically if a campaign/run exists
DYNAMIC_ENDPOINTS: list[tuple[str, str, str]] = []


def _percentile(data: list[float], p: int) -> float:
    if not data:
        return 0.0
    sorted_data = sorted(data)
    k = (len(sorted_data) - 1) * p / 100
    lo, hi = int(k), min(int(k) + 1, len(sorted_data) - 1)
    return round(sorted_data[lo] + (sorted_data[hi] - sorted_data[lo]) * (k - lo), 1)


def measure_endpoint(
    client: httpx.Client,
    method: str,
    url: str,
    runs: int,
) -> dict:
    latencies: list[float] = []
    errors = 0
    status_codes: list[int] = []

    for _ in range(runs):
        t0 = time.perf_counter()
        try:
            resp = client.request(method, url, timeout=30.0)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            latencies.append(elapsed_ms)
            status_codes.append(resp.status_code)
        except Exception:
            errors += 1

    if not latencies:
        return {"error": "all requests failed", "runs": runs, "errors": errors}

    return {
        "runs": runs,
        "errors": errors,
        "success_rate": round(len(latencies) / runs, 3),
        "p50_ms": _percentile(latencies, 50),
        "p95_ms": _percentile(latencies, 95),
        "p99_ms": _percentile(latencies, 99),
        "min_ms": round(min(latencies), 1),
        "max_ms": round(max(latencies), 1),
        "mean_ms": round(statistics.mean(latencies), 1),
        "status_codes": list(set(status_codes)),
    }


def discover_dynamic_endpoints(client: httpx.Client, base_url: str) -> list[tuple[str, str, str]]:
    """Try to discover a campaign ID and run ID to add dynamic endpoints."""
    extra: list[tuple[str, str, str]] = []
    try:
        resp = client.get(f"{base_url}/api/campaigns/", timeout=10.0)
        if resp.status_code == 200:
            campaigns = resp.json()
            if campaigns:
                cid = campaigns[0]["id"]
                extra.append(("GET", f"/api/results/campaign/{cid}/dashboard", f"dashboard_campaign_{cid}"))
                extra.append(("GET", f"/api/results/campaign/{cid}/live", f"live_feed_campaign_{cid}"))
                extra.append(("GET", f"/api/genome/campaigns/{cid}", f"genome_campaign_{cid}"))
    except Exception:
        pass
    return extra


def check_regression(input_path: str, threshold_p95: float) -> None:
    """Read a saved results file and fail if any endpoint exceeds threshold_p95 ms at P95."""
    data = json.loads(Path(input_path).read_text())
    results = data.get("results", {})
    failures: list[str] = []

    print(f"Checking P95 regression (threshold: {threshold_p95:.0f} ms) against {input_path}\n")

    for name, metrics in results.items():
        if "error" in metrics:
            print(f"  SKIP  {name:<50s}  (measurement failed: {metrics['error']})")
            continue
        p95 = metrics.get("p95_ms", 0.0)
        status = "OK  " if p95 <= threshold_p95 else "FAIL"
        print(f"  {status}  {name:<50s}  p95={p95:7.1f}ms")
        if p95 > threshold_p95:
            failures.append(f"{name}: p95={p95:.1f}ms > threshold={threshold_p95:.0f}ms")

    if failures:
        print(f"\n{len(failures)} endpoint(s) exceeded the P95 threshold:")
        for f in failures:
            print(f"  • {f}")
        raise SystemExit(1)

    print("\nAll endpoints within P95 threshold.")


def main() -> None:
    parser = argparse.ArgumentParser(description="LLM Eval Platform — performance baseline")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--runs", type=int, default=DEFAULT_RUNS)
    parser.add_argument("--output", default="/tmp/perf_baseline.json")
    parser.add_argument(
        "--check-regression",
        action="store_true",
        help="Read --input and exit non-zero if any endpoint's P95 exceeds --threshold-p95",
    )
    parser.add_argument(
        "--input",
        default=None,
        help="Path to a previously saved results JSON (used with --check-regression)",
    )
    parser.add_argument(
        "--threshold-p95",
        type=float,
        default=2000.0,
        metavar="MS",
        help="P95 latency threshold in milliseconds (default: 2000)",
    )
    args = parser.parse_args()

    if args.check_regression:
        input_path = args.input or args.output
        check_regression(input_path, args.threshold_p95)
        return

    base_url = args.base_url.rstrip("/")
    print(f"Measuring against {base_url}  ({args.runs} runs per endpoint)\n")

    results: dict[str, dict] = {}

    with httpx.Client(base_url=base_url) as client:
        dynamic = discover_dynamic_endpoints(client, base_url)
        all_endpoints = ENDPOINTS + dynamic

        for method, path, name in all_endpoints:
            print(f"  {method:4s} {path:<60s} ", end="", flush=True)
            result = measure_endpoint(client, method, path, args.runs)
            results[name] = {"method": method, "path": path, **result}
            if "error" in result:
                print(f"FAILED ({result['error']})")
            else:
                print(
                    f"p50={result['p50_ms']:7.1f}ms  "
                    f"p95={result['p95_ms']:7.1f}ms  "
                    f"p99={result['p99_ms']:7.1f}ms  "
                    f"(errors={result['errors']})"
                )

    output_path = Path(args.output)
    output_path.write_text(json.dumps({"base_url": base_url, "results": results}, indent=2))
    print(f"\nResults saved to {output_path}")


if __name__ == "__main__":
    main()

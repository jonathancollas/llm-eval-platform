"""
eval tasks — CLI for the benchmark task registry.

Usage examples
──────────────
    python -m cli.eval_tasks list
    python -m cli.eval_tasks list --capability cybersecurity
    python -m cli.eval_tasks list --domain reasoning --difficulty hard
    python -m cli.eval_tasks list --namespace inesia
    python -m cli.eval_tasks list --search "heap overflow"
    python -m cli.eval_tasks show inesia:cyber_uplift:heap_overflow_001
    python -m cli.eval_tasks stats
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import requests

# ── Config ─────────────────────────────────────────────────────────────────────

_BASE = os.environ.get("EVAL_API_BASE", "http://localhost:8000/api")
_TENANT_KEY = os.environ.get("EVAL_TENANT_KEY", "dev")


def _headers() -> dict:
    return {"X-Tenant-Key": _TENANT_KEY}


def _get(path: str, **params) -> dict | list:
    url = f"{_BASE}{path}"
    resp = requests.get(url, params={k: v for k, v in params.items() if v is not None}, headers=_headers(), timeout=15)
    resp.raise_for_status()
    return resp.json()


# ── Formatters ─────────────────────────────────────────────────────────────────

_DIFF_COLORS = {
    "easy":   "\033[32m",
    "medium": "\033[33m",
    "hard":   "\033[35m",
    "expert": "\033[31m",
}
_RISK_COLORS = {
    "low":      "\033[32m",
    "medium":   "\033[33m",
    "high":     "\033[35m",
    "critical": "\033[31m",
}
_RESET = "\033[0m"


def _color(text: str, mapping: dict) -> str:
    if not sys.stdout.isatty():
        return text
    return mapping.get(text, "") + text + _RESET


def _print_task(task: dict, verbose: bool = False) -> None:
    cid = task["canonical_id"]
    diff = _color(task.get("difficulty", "?"), _DIFF_COLORS)
    risk = _color(task.get("contamination_risk", "?"), _RISK_COLORS)
    caps = ", ".join(task.get("capability_tags", []))
    print(f"  {cid}")
    print(f"    Name     : {task.get('name', '')}")
    print(f"    Domain   : {task.get('domain', '')}  Difficulty: {diff}  Contamination: {risk}")
    print(f"    Caps     : {caps or '—'}")
    print(f"    Benchmark: {task.get('benchmark_name', '')}  Namespace: {task.get('namespace', '')}")
    if verbose:
        print(f"    Desc     : {task.get('description', '')}")
        deps = ", ".join(task.get("dependencies", []))
        print(f"    Env      : {task.get('required_environment', 'none')}  Deps: {deps or '—'}")
        print(f"    License  : {task.get('license', '?')}")
        notes = task.get("known_contamination_notes", "")
        if notes:
            print(f"    Contam.  : {notes}")
    print()


# ── Sub-commands ───────────────────────────────────────────────────────────────

def cmd_list(args: argparse.Namespace) -> None:
    params = {
        "capability": args.capability,
        "domain": args.domain,
        "difficulty": args.difficulty,
        "namespace": args.namespace,
        "search": args.search,
        "limit": args.limit,
        "offset": args.offset,
    }
    tasks = _get("/tasks", **params)
    if not isinstance(tasks, list):
        print(f"Unexpected response: {tasks}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        print(json.dumps(tasks, indent=2))
        return

    if not tasks:
        print("No tasks match the given filters.")
        return

    print(f"\n{'─'*64}")
    print(f"  Found {len(tasks)} task(s)")
    print(f"{'─'*64}\n")
    for task in tasks:
        _print_task(task, verbose=args.verbose)


def cmd_show(args: argparse.Namespace) -> None:
    canonical_id = args.canonical_id
    try:
        task = _get(f"/tasks/{canonical_id}")
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            print(f"Task '{canonical_id}' not found.", file=sys.stderr)
            sys.exit(1)
        raise

    if args.json:
        print(json.dumps(task, indent=2))
        return

    print(f"\n{'─'*64}")
    _print_task(task, verbose=True)
    print(f"{'─'*64}")


def cmd_stats(args: argparse.Namespace) -> None:
    stats = _get("/tasks/stats")

    if args.json:
        print(json.dumps(stats, indent=2))
        return

    print(f"\n{'─'*64}")
    print(f"  Task Registry Statistics")
    print(f"{'─'*64}")
    print(f"  Total tasks : {stats.get('total', 0)}")
    print()
    print("  By domain:")
    for k, v in sorted(stats.get("by_domain", {}).items(), key=lambda x: -x[1]):
        print(f"    {k:<30} {v}")
    print()
    print("  By difficulty:")
    for k, v in sorted(stats.get("by_difficulty", {}).items(), key=lambda x: -x[1]):
        diff = _color(k, _DIFF_COLORS)
        print(f"    {diff:<30} {v}")
    print()
    print("  By namespace:")
    for k, v in sorted(stats.get("by_namespace", {}).items(), key=lambda x: -x[1]):
        print(f"    {k:<30} {v}")
    print()
    print("  Top capabilities:")
    for cap, count in (stats.get("top_capabilities") or [])[:10]:
        print(f"    {cap:<30} {count}")
    print(f"{'─'*64}\n")


# ── Argument parser ────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="eval tasks",
        description="Benchmark task registry CLI",
    )
    parser.add_argument("--api-base", default=None, help="Override API base URL (env: EVAL_API_BASE)")
    parser.add_argument("--tenant-key", default=None, help="Override tenant key (env: EVAL_TENANT_KEY)")

    sub = parser.add_subparsers(dest="command", required=True)

    # list
    p_list = sub.add_parser("list", help="List / filter tasks")
    p_list.add_argument("--capability", "-c", default=None, help="Filter by capability tag")
    p_list.add_argument("--domain",     "-d", default=None, help="Filter by domain")
    p_list.add_argument("--difficulty",       default=None, choices=["easy","medium","hard","expert"])
    p_list.add_argument("--namespace",        default=None, choices=["public","inesia","community"])
    p_list.add_argument("--search",    "-s",  default=None, help="Full-text search")
    p_list.add_argument("--limit",            default=50,   type=int)
    p_list.add_argument("--offset",           default=0,    type=int)
    p_list.add_argument("--json",             action="store_true", help="Output as JSON")
    p_list.add_argument("--verbose",   "-v",  action="store_true")

    # show
    p_show = sub.add_parser("show", help="Show a single task by canonical ID")
    p_show.add_argument("canonical_id", help="e.g. public:mmlu:world_history")
    p_show.add_argument("--json", action="store_true")

    # stats
    p_stats = sub.add_parser("stats", help="Show registry statistics")
    p_stats.add_argument("--json", action="store_true")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    global _BASE, _TENANT_KEY
    if args.api_base:
        _BASE = args.api_base
    if args.tenant_key:
        _TENANT_KEY = args.tenant_key

    dispatch = {"list": cmd_list, "show": cmd_show, "stats": cmd_stats}
    try:
        dispatch[args.command](args)
    except requests.ConnectionError:
        print(
            f"\n✗ Cannot connect to API at {_BASE}\n"
            "  Is the backend running? (uvicorn main:app --reload)\n",
            file=sys.stderr,
        )
        sys.exit(1)
    except requests.HTTPError as exc:
        print(f"\n✗ API error: {exc}\n", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

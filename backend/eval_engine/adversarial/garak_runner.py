"""
Garak — LLM vulnerability scanner (NVIDIA).

Garak is the "Nmap of LLMs" — a structured scanner with 40+ attack modules
covering: prompt injection, encoding bypass, PII leakage, jailbreak,
hallucination stress, malicious code, and more.

Reference: https://github.com/NVIDIA/garak
Install:   pip install garak

Integration strategy
--------------------
We run Garak as a subprocess (it has a CLI: `python -m garak ...`).
Results are parsed from its JSON report output and surfaced in the Red Room.

When garak is not installed, we return a structured stub describing what
it would test, annotated with Garak probe IDs for reference.

Status: subprocess-ready — set GARAK_AVAILABLE=true in env to enable live scans.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import Optional

# ── Garak probe catalog (subset — most relevant for frontier model eval) ──────
GARAK_PROBES = [
    # Prompt injection
    {"id": "promptinject.AttackRogueString",      "category": "prompt_injection",  "severity": "high",
     "description": "Rogue string injected to override system instructions."},
    {"id": "promptinject.HijackHatePrompt",       "category": "prompt_injection",  "severity": "high",
     "description": "Hijack system prompt to generate hate speech."},
    # Jailbreak
    {"id": "dan.Dan_11_0",                        "category": "jailbreak",          "severity": "high",
     "description": "DAN 11.0 jailbreak — 'do anything now' persona."},
    {"id": "dan.DUDE",                            "category": "jailbreak",          "severity": "high",
     "description": "DUDE jailbreak — removes ethical constraints."},
    {"id": "jailbreak.Crescendo",                 "category": "jailbreak",          "severity": "medium",
     "description": "Multi-turn crescendo attack escalating to restricted content."},
    # Encoding bypass
    {"id": "encoding.InjectBase64",               "category": "encoding_bypass",    "severity": "medium",
     "description": "Encodes malicious payload in base64 to bypass text filters."},
    {"id": "encoding.InjectHex",                  "category": "encoding_bypass",    "severity": "medium",
     "description": "Hex-encoded injection to bypass string matching defenses."},
    {"id": "encoding.InjectROT13",                "category": "encoding_bypass",    "severity": "low",
     "description": "ROT-13 encoded instructions to evade simple filters."},
    # PII / data extraction
    {"id": "leakage.SourceCode",                  "category": "data_extraction",    "severity": "high",
     "description": "Probes for training data memorization — source code."},
    {"id": "leakage.GuessUUID",                   "category": "data_extraction",    "severity": "medium",
     "description": "Attempts to extract UUID-like private identifiers."},
    # Malware / harmful content
    {"id": "malwaregen.Evasion",                  "category": "harmful_content",    "severity": "critical",
     "description": "Requests evasive malware code generation."},
    {"id": "malwaregen.TopLevel",                 "category": "harmful_content",    "severity": "critical",
     "description": "Direct malware generation request."},
    # Hallucination
    {"id": "goodside.WhoIsRiley",                "category": "hallucination",       "severity": "low",
     "description": "Classic hallucination probe — asks about a fictional person."},
    {"id": "knowledgegrounding.ShouldRefute",     "category": "hallucination",       "severity": "medium",
     "description": "Model should refute false premises but may hallucinate."},
    # CBRN (high-severity probes)
    {"id": "atkgen.Atkgen",                       "category": "cbrn",               "severity": "critical",
     "description": "Automated adversarial attack generation targeting dangerous knowledge."},
]

GARAK_PROBE_CATEGORIES = sorted({p["category"] for p in GARAK_PROBES})


@dataclass
class GarakScanConfig:
    """Configuration for a Garak scan run."""
    model_type: str = "openai"          # openai | huggingface | rest | replicate
    model_name: str = "gpt-4o-mini"
    probes: list[str] = field(default_factory=lambda: ["promptinject", "dan", "encoding"])
    generators: list[str] = field(default_factory=list)
    report_prefix: str = "mercury_garak"
    timeout_seconds: int = 300


@dataclass
class GarakFinding:
    """Single finding from a Garak scan."""
    probe_id: str
    category: str
    severity: str
    description: str
    passed: bool
    pass_rate: float = 0.0
    total_attempts: int = 0
    failures: int = 0
    notes: str = ""


@dataclass
class GarakScanResult:
    """Full result of a Garak scan."""
    model_name: str
    probes_run: list[str]
    findings: list[GarakFinding]
    total_probes: int = 0
    total_failures: int = 0
    overall_pass_rate: float = 0.0
    garak_available: bool = False
    report_path: Optional[str] = None
    error: Optional[str] = None


def is_garak_available() -> bool:
    """Check if garak is installed and runnable."""
    if os.getenv("GARAK_AVAILABLE", "").lower() in ("true", "1", "yes"):
        try:
            r = subprocess.run(
                ["python", "-m", "garak", "--version"],
                capture_output=True, text=True, timeout=10,
            )
            return r.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
    return False


def run_garak_scan(config: GarakScanConfig) -> GarakScanResult:
    """
    Run a Garak scan via subprocess.

    When Garak is available (GARAK_AVAILABLE=true), runs a real scan and
    parses the JSON report. Otherwise, returns a structured stub with probe
    metadata that describes what would be tested.
    """
    garak_live = is_garak_available()

    if garak_live:
        return _run_live_scan(config)
    else:
        return _run_stub_scan(config)


def _run_live_scan(config: GarakScanConfig) -> GarakScanResult:
    """Execute a real Garak scan via subprocess and parse the report."""
    with tempfile.TemporaryDirectory() as tmpdir:
        report_path = os.path.join(tmpdir, f"{config.report_prefix}.report.jsonl")
        cmd = [
            "python", "-m", "garak",
            "--model_type", config.model_type,
            "--model_name", config.model_name,
            "--probes", ",".join(config.probes),
            "--report_prefix", os.path.join(tmpdir, config.report_prefix),
        ]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=config.timeout_seconds)
        except subprocess.TimeoutExpired:
            return GarakScanResult(
                model_name=config.model_name, probes_run=config.probes,
                findings=[], garak_available=True,
                error=f"Garak scan timed out after {config.timeout_seconds}s",
            )
        except Exception as e:
            return GarakScanResult(
                model_name=config.model_name, probes_run=config.probes,
                findings=[], garak_available=True, error=str(e),
            )

        findings = _parse_garak_report(report_path)
        total_failures = sum(1 for f in findings if not f.passed)
        pass_rate = sum(f.pass_rate for f in findings) / max(len(findings), 1)
        return GarakScanResult(
            model_name=config.model_name, probes_run=config.probes,
            findings=findings, total_probes=len(findings),
            total_failures=total_failures, overall_pass_rate=round(pass_rate, 3),
            garak_available=True, report_path=report_path,
        )


def _parse_garak_report(report_path: str) -> list[GarakFinding]:
    """Parse a Garak JSONL report into GarakFinding objects."""
    findings = []
    if not os.path.exists(report_path):
        return findings
    with open(report_path) as f:
        for line in f:
            try:
                rec = json.loads(line.strip())
                if rec.get("entry_type") != "attempt":
                    continue
                probe_id = rec.get("probe", "unknown")
                passed = rec.get("passed", True)
                findings.append(GarakFinding(
                    probe_id=probe_id,
                    category=probe_id.split(".")[0] if "." in probe_id else "unknown",
                    severity="high",
                    description=f"Garak probe: {probe_id}",
                    passed=passed,
                    pass_rate=1.0 if passed else 0.0,
                    total_attempts=1,
                    failures=0 if passed else 1,
                ))
            except (json.JSONDecodeError, KeyError):
                continue
    return findings


def _run_stub_scan(config: GarakScanConfig) -> GarakScanResult:
    """
    Return a structured stub when Garak is not installed.

    Describes what each probe would test — useful for planning and UI display
    even without a live Garak installation.
    """
    requested_categories = set(config.probes)
    relevant_probes = [
        p for p in GARAK_PROBES
        if any(cat in p["id"].lower() or cat == p["category"]
               for cat in requested_categories)
    ] or GARAK_PROBES  # If no match, return all

    findings = [
        GarakFinding(
            probe_id=p["id"],
            category=p["category"],
            severity=p["severity"],
            description=p["description"],
            passed=True,           # Unknown — not actually run
            pass_rate=0.0,
            total_attempts=0,
            failures=0,
            notes="STUB — Garak not installed. Set GARAK_AVAILABLE=true and install: pip install garak",
        )
        for p in relevant_probes
    ]

    return GarakScanResult(
        model_name=config.model_name,
        probes_run=config.probes,
        findings=findings,
        total_probes=len(findings),
        total_failures=0,
        overall_pass_rate=0.0,
        garak_available=False,
        error=None,
    )


def get_probe_catalog(category: Optional[str] = None) -> list[dict]:
    """Return the Garak probe catalog, optionally filtered by category."""
    if category:
        return [p for p in GARAK_PROBES if p["category"] == category]
    return GARAK_PROBES

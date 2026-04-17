"""
Tests for eval_engine/scientific_references.py
Covers get_all_references, get_reference_count, and the reference dicts.
"""
import os
import secrets
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SECRET_KEY", secrets.token_hex(32))

import pytest
from eval_engine.scientific_references import (
    SIGNAL_REFERENCES,
    CLASSIFIER_REFERENCES,
    ADVERSARIAL_REFERENCES,
    JUDGE_REFERENCES,
    EVIDENCE_REFERENCES,
    get_all_references,
    get_reference_count,
)


def test_get_all_references_structure():
    refs = get_all_references()
    assert isinstance(refs, dict)
    assert set(refs.keys()) == {"signals", "classifiers", "adversarial", "judge", "evidence"}


def test_get_all_references_signals():
    refs = get_all_references()
    assert "refusal_detected" in refs["signals"]
    assert "truth_score" in refs["signals"]
    assert "hedge_count" in refs["signals"]


def test_get_all_references_classifiers():
    refs = get_all_references()
    classifiers = refs["classifiers"]
    assert "hallucination" in classifiers
    assert "over_refusal" in classifiers
    assert "reasoning_failure" in classifiers
    assert "sycophancy" in classifiers


def test_get_all_references_adversarial():
    refs = get_all_references()
    adversarial = refs["adversarial"]
    assert "prompt_injection" in adversarial
    assert "jailbreak" in adversarial


def test_get_all_references_judge():
    refs = get_all_references()
    assert "multi_judge_ensemble" in refs["judge"]
    assert "cohen_kappa" in refs["judge"]


def test_get_all_references_evidence():
    refs = get_all_references()
    assert "rct_methodology" in refs["evidence"]
    assert "mann_whitney_u" in refs["evidence"]


def test_get_reference_count_positive():
    count = get_reference_count()
    assert isinstance(count, int)
    assert count > 0


def test_get_reference_count_no_duplicates():
    """Each URL is counted once even if referenced multiple times."""
    count = get_reference_count()
    # Manually count unique URLs
    all_urls = set()
    for category in [SIGNAL_REFERENCES, CLASSIFIER_REFERENCES, ADVERSARIAL_REFERENCES, JUDGE_REFERENCES, EVIDENCE_REFERENCES]:
        for key, data in category.items():
            for paper in data.get("papers", []):
                all_urls.add(paper["url"])
    assert count == len(all_urls)


def test_reference_entries_have_required_fields():
    """All paper entries have title, authors, year, url."""
    for category in [SIGNAL_REFERENCES, CLASSIFIER_REFERENCES, ADVERSARIAL_REFERENCES, JUDGE_REFERENCES, EVIDENCE_REFERENCES]:
        for key, data in category.items():
            for paper in data.get("papers", []):
                assert "title" in paper, f"Missing title in {key}"
                assert "authors" in paper, f"Missing authors in {key}"
                assert "year" in paper, f"Missing year in {key}"
                assert "url" in paper, f"Missing url in {key}"


def test_all_reference_categories_non_empty():
    for category in [SIGNAL_REFERENCES, CLASSIFIER_REFERENCES, ADVERSARIAL_REFERENCES, JUDGE_REFERENCES, EVIDENCE_REFERENCES]:
        assert len(category) > 0


def test_signal_references_have_description():
    for key, data in SIGNAL_REFERENCES.items():
        assert "description" in data, f"Missing description in signal {key}"


def test_classifier_references_have_description():
    for key, data in CLASSIFIER_REFERENCES.items():
        assert "description" in data, f"Missing description in classifier {key}"


def test_adversarial_references_have_papers():
    for key, data in ADVERSARIAL_REFERENCES.items():
        assert "papers" in data and len(data["papers"]) > 0, f"No papers in adversarial {key}"


def test_reference_years_are_integers():
    for category in [SIGNAL_REFERENCES, CLASSIFIER_REFERENCES, ADVERSARIAL_REFERENCES, JUDGE_REFERENCES, EVIDENCE_REFERENCES]:
        for key, data in category.items():
            for paper in data.get("papers", []):
                assert isinstance(paper["year"], int), f"Year not int in {key}"


def test_reference_count_is_substantial():
    """Sanity check: platform has at least 15 unique references."""
    count = get_reference_count()
    assert count >= 15

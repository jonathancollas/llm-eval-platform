"""Human Calibration Pipeline — inter-annotator agreement metrics."""
from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AnnotationItem:
    item_id: str
    prompt: str
    response: str
    expected: str
    scores: dict  # {annotator_id: float}


@dataclass
class CalibrationReport:
    n_items: int
    n_annotators: int
    cohens_kappa: float
    fleiss_kappa: float
    krippendorff_alpha: float
    spearman_human_llm: float
    mean_agreement: float
    reliability_grade: str
    interpretation: str
    recommendations: list


def _discretize(scores: list, bins: int = 5) -> list:
    """Map 0-1 floats to 0..bins-1 integer categories."""
    return [min(int(s * bins), bins - 1) for s in scores]


def cohens_kappa(ratings_a: list, ratings_b: list, bins: int = 5) -> float:
    da = _discretize(ratings_a, bins)
    db = _discretize(ratings_b, bins)
    n = len(da)
    if n == 0:
        return 0.0
    po = sum(1 for a, b in zip(da, db) if a == b) / n
    cats = list(range(bins))
    pe = sum((da.count(c) / n) * (db.count(c) / n) for c in cats)
    return round((po - pe) / (1 - pe), 4) if pe < 1.0 else 1.0


def fleiss_kappa(ratings_matrix: list, bins: int = 5) -> float:
    """rows=items, cols=raters; each cell is a float score 0-1."""
    n_items = len(ratings_matrix)
    if n_items == 0:
        return 0.0
    n_raters = len(ratings_matrix[0])
    cats = list(range(bins))

    counts = [
        [_discretize([ratings_matrix[i][j]], bins)[0] for j in range(n_raters)]
        for i in range(n_items)
    ]

    P_bar = (
        sum(
            sum(row.count(c) * (row.count(c) - 1) for c in cats)
            / (n_raters * (n_raters - 1))
            for row in counts
        )
        / n_items
    )

    all_ratings = [
        _discretize([ratings_matrix[i][j]], bins)[0]
        for i in range(n_items)
        for j in range(n_raters)
    ]
    total = len(all_ratings)
    P_e = sum((all_ratings.count(c) / total) ** 2 for c in cats)

    if P_e == 1.0:
        return 1.0
    return round((P_bar - P_e) / (1 - P_e), 4)


def krippendorff_alpha_ordinal(ratings_matrix: list) -> float:
    """Simple ordinal Krippendorff's alpha: mean(|i-j|^2) observed vs expected."""
    n_items = len(ratings_matrix)
    if n_items == 0:
        return 0.0
    n_raters = len(ratings_matrix[0]) if n_items > 0 else 0

    all_vals = [ratings_matrix[i][j] for i in range(n_items) for j in range(n_raters)]
    if len(all_vals) < 2:
        return 1.0

    m = sum(all_vals) / len(all_vals)

    D_o = 0.0
    count_o = 0
    for row in ratings_matrix:
        for ii in range(len(row)):
            for jj in range(ii + 1, len(row)):
                D_o += (row[ii] - row[jj]) ** 2
                count_o += 1
    D_o = D_o / count_o if count_o else 0.0

    D_e = (
        sum((v - m) ** 2 for v in all_vals) / (len(all_vals) - 1)
        if len(all_vals) > 1
        else 0.0
    )

    if D_e == 0:
        return 1.0
    return round(1 - D_o / D_e, 4)


def spearman_correlation(x: list, y: list) -> float:
    n = len(x)
    if n < 2:
        return 0.0

    def rank(lst: list) -> list:
        sorted_lst = sorted(range(n), key=lambda i: lst[i])
        r = [0.0] * n
        for rank_val, idx in enumerate(sorted_lst):
            r[idx] = rank_val + 1
        return r

    rx, ry = rank(x), rank(y)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return round(num / den, 4) if den else 0.0


def compute_calibration_report(
    items: list, llm_judge_scores: dict
) -> CalibrationReport:
    if not items:
        return CalibrationReport(
            0, 0, 0.0, 0.0, 0.0, 0.0, 0.0, "D", "No data", []
        )

    annotator_ids = list(items[0].scores.keys())
    n_ann = len(annotator_ids)

    if n_ann >= 2:
        a_scores = [item.scores[annotator_ids[0]] for item in items]
        b_scores = [item.scores[annotator_ids[1]] for item in items]
        ck = cohens_kappa(a_scores, b_scores)
    else:
        a_scores = [item.scores[annotator_ids[0]] for item in items]
        b_scores = a_scores
        ck = 1.0

    matrix = [[item.scores.get(aid, 0.5) for aid in annotator_ids] for item in items]
    fk = fleiss_kappa(matrix)
    ka = krippendorff_alpha_ordinal(matrix)

    mean_human = [sum(item.scores.values()) / len(item.scores) for item in items]
    llm_scores = [llm_judge_scores.get(item.item_id, 0.5) for item in items]
    sp = spearman_correlation(mean_human, llm_scores)

    mean_agree = (
        round(sum(1 - abs(a - b) for a, b in zip(a_scores, b_scores)) / len(items), 4)
        if n_ann >= 2
        else 1.0
    )

    grade = "A" if ck >= 0.8 else "B" if ck >= 0.6 else "C" if ck >= 0.4 else "D"

    recs = []
    if ck < 0.6:
        recs.append("Consider annotator training to improve agreement")
    if sp < 0.7:
        recs.append("LLM judge diverges from human annotators")

    return CalibrationReport(
        n_items=len(items),
        n_annotators=n_ann,
        cohens_kappa=ck,
        fleiss_kappa=fk,
        krippendorff_alpha=ka,
        spearman_human_llm=sp,
        mean_agreement=mean_agree,
        reliability_grade=grade,
        interpretation=f"Kappa={ck:.2f} ({grade})",
        recommendations=recs,
    )

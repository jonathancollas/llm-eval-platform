import math, random
from dataclasses import dataclass, field
from datetime import datetime, UTC
from typing import Optional, List, Dict, Tuple


@dataclass
class ScalingDataPoint:
    model_name: str
    benchmark_name: str
    capability: str
    score: float
    ci_lower: float = 0.0
    ci_upper: float = 1.0
    parameter_count: Optional[float] = None
    training_tokens: Optional[float] = None
    compute_flops: Optional[float] = None
    # capability_score vs propensity_score tracking
    score_type: str = "capability"  # "capability" | "propensity"
    date: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass
class ScalingLawFit:
    law_type: str  # linear|power|logistic|chinchilla
    coefficients: dict
    r_squared: float
    rmse: float
    n_points: int
    valid: bool
    interpretation: str
    residuals: List[float] = field(default_factory=list)
    mae: float = 0.0


@dataclass
class CapabilityForecast:
    capability: str
    model_class: str
    current_score: float
    forecast_score: float
    forecast_horizon_label: str
    uncertainty_lower: float
    uncertainty_upper: float
    confidence: str
    scaling_law_type: str
    trend_direction: str
    capability_score: float = 0.0
    propensity_score: float = 0.0
    gap_to_frontier: float = 0.0
    key_assumptions: list = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass
class ForecastReport:
    benchmarks_analyzed: int
    capabilities_covered: list
    forecasts: list
    overall_trend: str
    riskiest_capability: str
    plateau_capabilities: list
    emerging_capabilities: list
    recommendations: list
    frontier_gaps: dict = field(default_factory=dict)
    calibration_mae: float = 0.0
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass
class DataQualityReport:
    """Result of validating a batch of ScalingDataPoints."""
    total_points: int
    valid_points: int
    invalid_points: int
    issues: List[str]
    duplicate_count: int
    missing_ci_count: int
    score_range_violations: int
    passed: bool


@dataclass
class ForecastCalibrationRecord:
    """Tracks a historical prediction vs actual outcome for calibration."""
    capability: str
    predicted_score: float
    actual_score: float
    horizon_label: str
    absolute_error: float
    recorded_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass
class MultiDimScalingFit:
    """Chinchilla-style fit: loss = A / N^alpha + B / D^beta (normalised to [0,1])."""
    alpha: float  # parameter scaling exponent
    beta: float   # data scaling exponent
    A: float
    B: float
    r_squared: float
    rmse: float
    n_points: int
    valid: bool
    interpretation: str


def _mean(x):
    return sum(x) / max(len(x), 1)


def _std(x):
    m = _mean(x)
    return math.sqrt(sum((v - m) ** 2 for v in x) / max(len(x) - 1, 1))


def _compute_residuals(y: List[float], y_pred: List[float]) -> List[float]:
    return [round(yi - yp, 6) for yi, yp in zip(y, y_pred)]


def fit_linear(x, y) -> ScalingLawFit:
    n = len(x)
    if n < 2:
        return ScalingLawFit("linear", {"a": 0, "b": 0}, 0.0, 0.0, n, False, "Insufficient data")
    mx, my = _mean(x), _mean(y)
    num = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
    den = sum((xi - mx) ** 2 for xi in x)
    a = num / den if den else 0.0
    b = my - a * mx
    y_pred = [a * xi + b for xi in x]
    ss_res = sum((yi - yp) ** 2 for yi, yp in zip(y, y_pred))
    ss_tot = sum((yi - my) ** 2 for yi in y)
    r2 = 1 - ss_res / ss_tot if ss_tot else 0.0
    rmse = math.sqrt(ss_res / n)
    residuals = _compute_residuals(y, y_pred)
    mae = sum(abs(r) for r in residuals) / n
    return ScalingLawFit(
        "linear",
        {"a": round(a, 6), "b": round(b, 6)},
        round(r2, 4),
        round(rmse, 4),
        n,
        r2 > 0.5,
        f"y={a:.4f}x+{b:.4f},R2={r2:.3f}",
        residuals=residuals,
        mae=round(mae, 4),
    )


def fit_power_law(x, y) -> ScalingLawFit:
    pairs = [(xi, yi) for xi, yi in zip(x, y) if xi > 0 and yi > 0]
    if len(pairs) < 2:
        return ScalingLawFit(
            "power", {"a": 1, "b": 0.5}, 0.0, 0.0, len(pairs), False, "Insufficient positive data"
        )
    lx = [math.log(xi) for xi, _ in pairs]
    ly = [math.log(yi) for _, yi in pairs]
    fit = fit_linear(lx, ly)
    b = fit.coefficients["a"]
    a = math.exp(fit.coefficients["b"])
    y_pred = [a * (xi ** b) for xi, _ in pairs]
    y_orig = [yi for _, yi in pairs]
    residuals = _compute_residuals(y_orig, y_pred)
    n = len(pairs)
    mae = sum(abs(r) for r in residuals) / n
    return ScalingLawFit(
        "power",
        {"a": round(a, 6), "b": round(b, 6)},
        fit.r_squared,
        fit.rmse,
        n,
        fit.valid,
        f"y={a:.4f}*x^{b:.4f}",
        residuals=residuals,
        mae=round(mae, 4),
    )


def fit_logistic(x, y) -> ScalingLawFit:
    n = len(x)
    if n < 3:
        return ScalingLawFit("logistic", {"k": 1.0, "x0": 0.5}, 0.0, 0.0, n, False, "Insufficient data")
    k, x0 = 1.0, _mean(x)
    lr = 0.01
    for _ in range(300):
        dk = dx0 = 0.0
        for xi, yi in zip(x, y):
            sig = 1 / (1 + math.exp(-k * (xi - x0)))
            err = sig - yi
            dk += err * sig * (1 - sig) * (xi - x0)
            dx0 += err * sig * (1 - sig) * (-k)
        k -= lr * dk / n
        x0 -= lr * dx0 / n
    y_pred = [1 / (1 + math.exp(-k * (xi - x0))) for xi in x]
    my = _mean(y)
    ss_res = sum((yi - yp) ** 2 for yi, yp in zip(y, y_pred))
    ss_tot = sum((yi - my) ** 2 for yi in y)
    r2 = 1 - ss_res / ss_tot if ss_tot else 0.0
    rmse = math.sqrt(ss_res / n)
    residuals = _compute_residuals(y, y_pred)
    mae = sum(abs(r) for r in residuals) / n
    return ScalingLawFit(
        "logistic",
        {"k": round(k, 6), "x0": round(x0, 6)},
        round(r2, 4),
        round(rmse, 4),
        n,
        r2 > 0.5,
        f"logistic(k={k:.3f},x0={x0:.3f})",
        residuals=residuals,
        mae=round(mae, 4),
    )


def fit_chinchilla(
    param_counts: List[float], token_counts: List[float], scores: List[float]
) -> MultiDimScalingFit:
    """Fit a Chinchilla-style power law: loss = A/N^alpha + B/D^beta.

    ``scores`` here are capability scores (higher = better), so we model
    ``1 - score`` as the "loss" and then negate the interpretation.
    Requires at least 4 data points with positive N and D values.
    """
    triplets = [
        (n, d, s)
        for n, d, s in zip(param_counts, token_counts, scores)
        if n > 0 and d > 0 and 0.0 < s < 1.0
    ]
    if len(triplets) < 4:
        return MultiDimScalingFit(
            alpha=0.5, beta=0.5, A=1.0, B=1.0,
            r_squared=0.0, rmse=0.0, n_points=len(triplets),
            valid=False, interpretation="Insufficient data (need ≥4 positive triplets)",
        )

    ln_N = [math.log(n) for n, _, _ in triplets]
    ln_D = [math.log(d) for _, d, _ in triplets]
    ln_L = [math.log(max(1e-9, 1.0 - s)) for _, _, s in triplets]

    # OLS on log-loss ~ a0 + alpha*ln_N + beta*ln_D
    # Build design matrix [1, ln_N, ln_D] and solve via normal equations
    n = len(triplets)
    X = [[1.0, ln_N[i], ln_D[i]] for i in range(n)]
    y = ln_L

    # XtX (3×3)
    xtx = [[sum(X[r][c1] * X[r][c2] for r in range(n)) for c2 in range(3)] for c1 in range(3)]
    xty = [sum(X[r][c] * y[r] for r in range(n)) for c in range(3)]

    # Simple 3×3 linear solve via Gaussian elimination
    def solve_3x3(A, b):
        M = [row[:] + [bi] for row, bi in zip(A, b)]
        for col in range(3):
            pivot = max(range(col, 3), key=lambda r: abs(M[r][col]))
            M[col], M[pivot] = M[pivot], M[col]
            if abs(M[col][col]) < 1e-12:
                return [0.0, -0.5, -0.5]
            for row in range(col + 1, 3):
                f = M[row][col] / M[col][col]
                for j in range(col, 4):
                    M[row][j] -= f * M[col][j]
        x = [0.0] * 3
        for i in range(2, -1, -1):
            x[i] = M[i][3]
            for j in range(i + 1, 3):
                x[i] -= M[i][j] * x[j]
            x[i] /= M[i][i]
        return x

    try:
        coefs = solve_3x3(xtx, xty)
    except Exception:
        coefs = [0.0, -0.5, -0.5]

    ln_A0, neg_alpha, neg_beta = coefs
    alpha = -neg_alpha
    beta = -neg_beta
    A = math.exp(ln_A0) / 2 if ln_A0 < 700 else 1.0
    B = A  # simplified: A = B by symmetry in this OLS form

    # Predicted losses
    y_pred_ln = [ln_A0 + neg_alpha * ln_N[i] + neg_beta * ln_D[i] for i in range(n)]
    my = _mean(ln_L)
    ss_res = sum((ln_L[i] - y_pred_ln[i]) ** 2 for i in range(n))
    ss_tot = sum((yi - my) ** 2 for yi in ln_L)
    r2 = max(0.0, 1 - ss_res / ss_tot) if ss_tot else 0.0
    rmse = math.sqrt(ss_res / n)

    return MultiDimScalingFit(
        alpha=round(alpha, 4),
        beta=round(beta, 4),
        A=round(A, 6),
        B=round(B, 6),
        r_squared=round(r2, 4),
        rmse=round(rmse, 4),
        n_points=n,
        valid=r2 > 0.3,
        interpretation=(
            f"Chinchilla: score≈1-({A:.4f}/N^{alpha:.3f}+{B:.4f}/D^{beta:.3f}), R²={r2:.3f}"
        ),
    )


def validate_data_quality(points: List[ScalingDataPoint]) -> DataQualityReport:
    """Validate a batch of ScalingDataPoints for quality issues."""
    issues: List[str] = []
    invalid = 0
    missing_ci = 0
    range_violations = 0

    seen: Dict[Tuple, int] = {}
    for p in points:
        if not (0.0 <= p.score <= 1.0):
            range_violations += 1
            invalid += 1
            issues.append(
                f"{p.model_name}/{p.capability}: score {p.score:.3f} outside [0,1]"
            )
        if p.ci_lower == 0.0 and p.ci_upper == 1.0:
            missing_ci += 1
        key = (p.model_name, p.benchmark_name, p.capability, p.date)
        seen[key] = seen.get(key, 0) + 1

    duplicate_count = sum(v - 1 for v in seen.values() if v > 1)
    if duplicate_count:
        issues.append(f"{duplicate_count} duplicate (model, benchmark, capability, date) tuples")
    if missing_ci:
        issues.append(f"{missing_ci} points have no confidence interval (using defaults)")

    valid_count = len(points) - invalid
    return DataQualityReport(
        total_points=len(points),
        valid_points=valid_count,
        invalid_points=invalid,
        issues=issues,
        duplicate_count=duplicate_count,
        missing_ci_count=missing_ci,
        score_range_violations=range_violations,
        passed=invalid == 0 and duplicate_count == 0,
    )


def extrapolate(fit, x_future, n_bootstrap=200, seed=42):
    c = fit.coefficients
    if fit.law_type == "linear":
        pred = c["a"] * x_future + c["b"]
    elif fit.law_type == "power":
        pred = c["a"] * (x_future ** c["b"]) if x_future > 0 else c["a"]
    else:
        pred = 1 / (1 + math.exp(-c["k"] * (x_future - c["x0"])))
    pred = max(0.0, min(1.0, pred))
    noise = (1 - fit.r_squared) * 0.2 + 0.05
    rng = random.Random(seed)
    samples = sorted(
        [max(0.0, min(1.0, pred + rng.gauss(0, noise))) for _ in range(n_bootstrap)]
    )
    lower = samples[int(0.025 * n_bootstrap)]
    upper = samples[int(0.975 * n_bootstrap)]
    return round(pred, 4), round(lower, 4), round(upper, 4)


def detect_phase_transition(y):
    if len(y) < 4:
        return {"detected": False, "transition_index": -1, "magnitude": 0.0}
    best_idx, best_mag = -1, 0.0
    for i in range(1, len(y)):
        mag = abs(y[i] - y[i - 1])
        if mag > best_mag:
            best_mag, best_idx = mag, i
    detected = best_mag > 0.15
    return {
        "detected": detected,
        "transition_index": best_idx if detected else -1,
        "magnitude": round(best_mag, 4),
    }


class CapabilityForecastingEngine:
    def __init__(self):
        self._data: List[ScalingDataPoint] = []
        self._calibration_history: List[ForecastCalibrationRecord] = []

    def add_data_point(self, point: ScalingDataPoint):
        self._data.append(point)

    def _get_series(self, capability: str, score_type: str = "any"):
        pts = sorted(
            [
                p for p in self._data
                if p.capability == capability
                and (score_type == "any" or p.score_type == score_type)
            ],
            key=lambda p: p.date,
        )
        return list(range(len(pts))), [p.score for p in pts]

    def fit_scaling_law(self, capability: str, method: str = "auto", score_type: str = "any") -> ScalingLawFit:
        x, y = self._get_series(capability, score_type)
        if len(x) < 2:
            return ScalingLawFit("linear", {"a": 0, "b": 0}, 0.0, 0.0, len(x), False, "Insufficient data")
        if method == "linear":
            return fit_linear(x, y)
        if method == "power":
            return fit_power_law(x, y)
        if method == "logistic":
            return fit_logistic(x, y)
        fits = [fit_linear(x, y), fit_logistic(x, y)]
        return max(fits, key=lambda f: f.r_squared)

    def fit_chinchilla(self, capability: str) -> MultiDimScalingFit:
        """Fit Chinchilla-style multi-dimensional scaling law for a capability."""
        pts = [p for p in self._data if p.capability == capability]
        param_counts = [p.parameter_count for p in pts if p.parameter_count is not None]
        token_counts = [p.training_tokens for p in pts if p.training_tokens is not None]
        scores = [p.score for p in pts if p.parameter_count is not None and p.training_tokens is not None]
        return fit_chinchilla(param_counts, token_counts, scores)

    def residual_analysis(self, capability: str, method: str = "auto") -> Dict:
        """Return residual analysis for goodness-of-fit diagnostics."""
        fit = self.fit_scaling_law(capability, method)
        if not fit.residuals:
            return {"capability": capability, "residuals": [], "mean_residual": 0.0, "std_residual": 0.0, "mae": fit.mae}
        mean_res = round(_mean(fit.residuals), 6)
        std_res = round(_std(fit.residuals), 6) if len(fit.residuals) > 1 else 0.0
        return {
            "capability": capability,
            "law_type": fit.law_type,
            "r_squared": fit.r_squared,
            "rmse": fit.rmse,
            "mae": fit.mae,
            "residuals": fit.residuals,
            "mean_residual": mean_res,
            "std_residual": std_res,
            "n_points": fit.n_points,
            "valid": fit.valid,
        }

    def capability_gap_to_frontier(self, capabilities: Optional[List[str]] = None) -> Dict[str, float]:
        """Compute the gap between each capability's current score and the frontier (max score seen)."""
        caps = capabilities or list({p.capability for p in self._data})
        gaps: Dict[str, float] = {}
        for cap in caps:
            scores = [p.score for p in self._data if p.capability == cap]
            if scores:
                current = scores[-1] if scores else 0.0
                frontier = max(scores)
                gaps[cap] = round(max(0.0, frontier - current), 4)
        return gaps

    def forecast(self, capability: str, horizon_steps: int = 3) -> CapabilityForecast:
        x, y = self._get_series(capability)
        fit = self.fit_scaling_law(capability)
        current = y[-1] if y else 0.5
        x_future = len(x) + horizon_steps
        pred, lower, upper = extrapolate(fit, float(x_future))
        trend = (
            "improving" if pred > current + 0.05
            else "declining" if pred < current - 0.05
            else "plateau"
        )
        pt = detect_phase_transition(y)
        if pt["detected"]:
            trend = "emergent"
        conf = "high" if fit.r_squared > 0.8 else "medium" if fit.r_squared > 0.5 else "low"

        # Separate capability vs propensity score means
        _, cap_y = self._get_series(capability, "capability")
        _, prop_y = self._get_series(capability, "propensity")
        cap_score = round(_mean(cap_y), 4) if cap_y else round(current, 4)
        prop_score = round(_mean(prop_y), 4) if prop_y else round(current, 4)

        # Gap to frontier
        frontier = max(y) if y else current
        gap = round(max(0.0, frontier - current), 4)

        return CapabilityForecast(
            capability=capability,
            model_class="evaluated_models",
            current_score=round(current, 4),
            forecast_score=pred,
            forecast_horizon_label=f"+{horizon_steps} cycles",
            uncertainty_lower=lower,
            uncertainty_upper=upper,
            confidence=conf,
            scaling_law_type=fit.law_type,
            trend_direction=trend,
            capability_score=cap_score,
            propensity_score=prop_score,
            gap_to_frontier=gap,
            key_assumptions=["similar model families", "no architectural breakthroughs"],
        )

    def generate_report(self, capabilities: Optional[List[str]] = None) -> ForecastReport:
        caps = capabilities or list({p.capability for p in self._data})
        forecasts = [
            self.forecast(c)
            for c in caps
            if len([p for p in self._data if p.capability == c]) >= 2
        ]
        emerging = [f.capability for f in forecasts if f.trend_direction == "emergent"]
        plateau = [f.capability for f in forecasts if f.trend_direction == "plateau"]
        riskiest = max(forecasts, key=lambda f: f.forecast_score).capability if forecasts else ""
        trend = (
            "improving"
            if sum(1 for f in forecasts if f.trend_direction == "improving") > len(forecasts) / 2
            else "mixed"
        )
        frontier_gaps = self.capability_gap_to_frontier(caps)
        calibration_mae = self._compute_calibration_mae()
        return ForecastReport(
            benchmarks_analyzed=len({p.benchmark_name for p in self._data}),
            capabilities_covered=caps,
            forecasts=forecasts,
            overall_trend=trend,
            riskiest_capability=riskiest,
            plateau_capabilities=plateau,
            emerging_capabilities=emerging,
            recommendations=["Expand dataset" if not forecasts else "Continue monitoring"],
            frontier_gaps=frontier_gaps,
            calibration_mae=calibration_mae,
        )

    def record_calibration(
        self,
        capability: str,
        predicted_score: float,
        actual_score: float,
        horizon_label: str = "unknown",
    ) -> ForecastCalibrationRecord:
        """Record a historical prediction vs actual outcome."""
        record = ForecastCalibrationRecord(
            capability=capability,
            predicted_score=round(predicted_score, 4),
            actual_score=round(actual_score, 4),
            horizon_label=horizon_label,
            absolute_error=round(abs(predicted_score - actual_score), 4),
        )
        self._calibration_history.append(record)
        return record

    def get_calibration_history(self) -> List[ForecastCalibrationRecord]:
        return list(self._calibration_history)

    def _compute_calibration_mae(self) -> float:
        if not self._calibration_history:
            return 0.0
        return round(
            sum(r.absolute_error for r in self._calibration_history) / len(self._calibration_history), 4
        )

    def calibrate_historical(self, actual_scores: dict, predicted_scores: dict) -> float:
        keys = set(actual_scores) & set(predicted_scores)
        if not keys:
            return 1.0
        return round(
            sum(abs(actual_scores[k] - predicted_scores[k]) for k in keys) / len(keys), 4
        )

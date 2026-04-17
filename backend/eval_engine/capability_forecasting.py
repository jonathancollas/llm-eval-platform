from __future__ import annotations
import math, random
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


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
    date: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class ScalingLawFit:
    law_type: str  # linear|power|logistic
    coefficients: dict
    r_squared: float
    rmse: float
    n_points: int
    valid: bool
    interpretation: str


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
    key_assumptions: list = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


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
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


def _mean(x):
    return sum(x) / max(len(x), 1)


def _std(x):
    m = _mean(x)
    return math.sqrt(sum((v - m) ** 2 for v in x) / max(len(x) - 1, 1))


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
    return ScalingLawFit(
        "linear",
        {"a": round(a, 6), "b": round(b, 6)},
        round(r2, 4),
        round(rmse, 4),
        n,
        r2 > 0.5,
        f"y={a:.4f}x+{b:.4f},R2={r2:.3f}",
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
    return ScalingLawFit(
        "power",
        {"a": round(a, 6), "b": round(b, 6)},
        fit.r_squared,
        fit.rmse,
        len(pairs),
        fit.valid,
        f"y={a:.4f}*x^{b:.4f}",
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
    return ScalingLawFit(
        "logistic",
        {"k": round(k, 6), "x0": round(x0, 6)},
        round(r2, 4),
        round(rmse, 4),
        n,
        r2 > 0.5,
        f"logistic(k={k:.3f},x0={x0:.3f})",
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
        self._data = []

    def add_data_point(self, point):
        self._data.append(point)

    def _get_series(self, capability):
        pts = sorted(
            [p for p in self._data if p.capability == capability], key=lambda p: p.date
        )
        return list(range(len(pts))), [p.score for p in pts]

    def fit_scaling_law(self, capability, method="auto"):
        x, y = self._get_series(capability)
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

    def forecast(self, capability, horizon_steps=3):
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
            key_assumptions=["similar model families", "no architectural breakthroughs"],
        )

    def generate_report(self, capabilities=None):
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
        return ForecastReport(
            benchmarks_analyzed=len({p.benchmark_name for p in self._data}),
            capabilities_covered=caps,
            forecasts=forecasts,
            overall_trend=trend,
            riskiest_capability=riskiest,
            plateau_capabilities=plateau,
            emerging_capabilities=emerging,
            recommendations=["Expand dataset" if not forecasts else "Continue monitoring"],
        )

    def calibrate_historical(self, actual_scores, predicted_scores):
        keys = set(actual_scores) & set(predicted_scores)
        if not keys:
            return 1.0
        return round(
            sum(abs(actual_scores[k] - predicted_scores[k]) for k in keys) / len(keys), 4
        )

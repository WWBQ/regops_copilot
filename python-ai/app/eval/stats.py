"""二项比例与配对 A/B 口径：Wilson 区间、McNemar、n=30 时 3% 不可信。"""

from __future__ import annotations

import math
from typing import Any


def wilson_interval(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n <= 0:
        return (0.0, 0.0)
    k = min(max(k, 0), n)
    p = k / n
    z2 = z * z
    denom = 1.0 + z2 / n
    center = (p + z2 / (2.0 * n)) / denom
    half = z * math.sqrt((p * (1.0 - p) + z2 / (4.0 * n)) / n) / denom
    return (max(0.0, center - half), min(1.0, center + half))


def wald_diff_interval(k_a: int, k_b: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n <= 0:
        return (0.0, 0.0)
    p_a = k_a / n
    p_b = k_b / n
    se = math.sqrt(p_a * (1.0 - p_a) / n + p_b * (1.0 - p_b) / n)
    delta = p_b - p_a
    return (delta - z * se, delta + z * se)


def _bin_pmf_sum(n: int, end_inclusive: int) -> float:
    if n <= 0:
        return 1.0
    total = 0.0
    coeff = 1.0
    # C(n,0) * 0.5^n + ... using iterative binomial coefficients
    for i in range(0, end_inclusive + 1):
        if i > 0:
            coeff *= (n - i + 1) / i
        total += coeff
    return total * (0.5**n)


def mcnemar_exact_p(n01: int, n10: int) -> float:
    """双侧精确二项：n01=A 错 B 对，n10=A 对 B 错。"""
    n01 = max(0, int(n01))
    n10 = max(0, int(n10))
    n = n01 + n10
    if n == 0:
        return 1.0
    k = min(n01, n10)
    tail = _bin_pmf_sum(n, k)
    return min(1.0, 2.0 * tail)


def assess_ab(
    *,
    n: int,
    k_a: int,
    k_b: int,
    n01: int,
    n10: int,
    z: float = 1.96,
) -> dict[str, Any]:
    p_a = (k_a / n) if n else 0.0
    p_b = (k_b / n) if n else 0.0
    delta = p_b - p_a
    ci_a = wilson_interval(k_a, n, z)
    ci_b = wilson_interval(k_b, n, z)
    ci_delta = wald_diff_interval(k_a, k_b, n, z)
    p_value = mcnemar_exact_p(n01, n10)
    crosses_zero = ci_delta[0] <= 0.0 <= ci_delta[1]
    small_n = n < 100
    small_delta = abs(delta) < 0.08
    credible = (not small_n) and (not crosses_zero) and p_value < 0.05 and abs(delta) >= 0.08
    if n <= 30 and abs(delta) <= 0.05:
        verdict = (
            f"n={n} 提升 {delta:.1%} 通常不可信：样本量不足，"
            "95% 区间穿过 0，不能凭这一点上线。"
        )
    elif not credible and crosses_zero:
        verdict = (
            f"n={n}，Δ={delta:.1%}，95% 区间 [{ci_delta[0]:.1%}, {ci_delta[1]:.1%}] 穿过 0，"
            "不能宣称 B 更好。"
        )
    elif not credible and small_n:
        verdict = f"n={n} 偏小，即使点估计有差也不够作为上线依据。"
    elif not credible:
        verdict = "未达到预先约定的显著性/效应量门槛，保持 A。"
    else:
        verdict = f"n={n}，Δ={delta:.1%}，区间不穿过 0 且 McNemar p={p_value:.3f}，可以认为 B 更好。"
    return {
        "n": n,
        "k_a": k_a,
        "k_b": k_b,
        "accuracy_a": round(p_a, 4),
        "accuracy_b": round(p_b, 4),
        "delta": round(delta, 4),
        "ci95_a": [round(ci_a[0], 4), round(ci_a[1], 4)],
        "ci95_b": [round(ci_b[0], 4), round(ci_b[1], 4)],
        "ci95_delta": [round(ci_delta[0], 4), round(ci_delta[1], 4)],
        "n01": n01,
        "n10": n10,
        "mcnemar_p": round(p_value, 4),
        "crosses_zero": crosses_zero,
        "small_n": small_n,
        "small_delta": small_delta,
        "credible": credible,
        "verdict": verdict,
    }

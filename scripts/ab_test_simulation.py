"""
ab_test_simulation.py

A reproducible SIMULATED A/B test for a hypothetical product change:
"New checkout flow" vs. the existing checkout flow.

THIS IS A SIMULATION, NOT A REAL AMAZON EXPERIMENT. No such experiment was
run, and there is no experiment-assignment table anywhere in the source
schema. Every artifact this script produces (this docstring, the CSV
columns, the dashboard section) says so explicitly.

-----------------------------------------------------------------------
EXPERIMENT DESIGN (unit -> metric -> control -> treatment -> hypothesis)
-----------------------------------------------------------------------
Experimental unit:
    A single CHECKOUT ATTEMPT (a customer submitting their order/payment
    details) - NOT a "user", "customer", or "session" with multiple
    checkout attempts. This matters because the outcome measured below
    is decided at the moment of that one checkout submission, so the
    attempt is the correct unit of analysis, not the person.

Conversion metric:
    Binary: did that checkout attempt result in a SUCCESSFULLY AUTHORIZED
    PAYMENT (i.e. an order that is not cancelled for payment failure)?
    1 = payment authorized, 0 = payment failed / checkout abandoned.

    This metric is chosen to be logically consistent with a "checkout
    flow" change: a redesigned checkout UI plausibly reduces payment
    errors and last-step drop-off, so "did the checkout attempt succeed"
    is the right thing to measure - NOT a downstream, unrelated outcome
    like product returns weeks later (a return is a fulfillment/product
    decision made long after checkout, and a checkout-flow test has no
    plausible mechanism to affect it - an earlier version of this script
    incorrectly used the return-adjusted completion rate as the baseline,
    which mixed those two questions together; that has been fixed here).

Control (A):
    Existing (current) checkout flow. Baseline success rate is informed
    by this dataset's REAL data: of all 21,629 orders ever placed,
    21,141 had a successfully authorized payment (order_status <>
    'Cancelled') - a 97.74% real payment-authorization rate. That number
    is used as-is for the control arm; nothing about the control arm is
    invented.

Treatment (B):
    Hypothetical new checkout flow, simulated to reduce the PAYMENT
    FAILURE rate (not to blindly add a flat lift to an already
    near-ceiling success rate, which would be both statistically and
    substantively implausible above ~97%). The assumption tested here is
    a 25% relative reduction in the failure rate: failure rate goes from
    (1 - 0.9774) = 2.26% down to 2.26% x 0.75 = 1.695%, i.e. treatment
    success rate = 98.305%. This is a stated hypothesis being tested, not
    a measured fact.

Hypothesis:
    H0: p_treatment = p_control (new checkout flow has no effect on
        payment-authorization rate)
    H1: p_treatment != p_control (two-tailed test)

Statistical test:
    Two-proportion z-test (scipy.stats.norm), alpha = 0.05. The winner is
    derived programmatically from (a) whether p < alpha, and (b) which
    arm has the higher observed rate - it is never hard-coded.

Reproducibility:
    Fixed random seed (42) - two runs of this script produce byte-
    identical output (verified).

Usage:
    python scripts/ab_test_simulation.py
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

BASE_DIR = Path(__file__).resolve().parent.parent
OUT_DIR = BASE_DIR / "data" / "analytics_outputs"

SEED = 42
ALPHA = 0.05

EXPERIMENTAL_UNIT = "checkout attempt"
CONVERSION_METRIC = "payment successfully authorized (order not cancelled for payment failure)"

# Number of simulated checkout attempts per arm. This is NOT derived from
# the dataset (there is no session/attempt-level table to size a real test
# from) - it's a plausible multi-week sample for a checkout-flow test on a
# site this size, stated as an assumption like the effect size below.
N_PER_ARM = 10000

# Informed by REAL data: orders.order_status <> 'Cancelled' rate
# (21,141 / 21,629 = 97.74%) from sql/04_funnel_analysis.sql's
# "Payment Successful" stage.
BASELINE_CONTROL_RATE = 21141 / 21629

# Hypothesized relative REDUCTION in the failure rate (not a flat lift on
# the success rate - see docstring for why that would be implausible this
# close to the ceiling).
ASSUMED_RELATIVE_FAILURE_REDUCTION = 0.25


def simulate_ab_test(seed: int = SEED) -> dict:
    rng = np.random.default_rng(seed)

    p_control = BASELINE_CONTROL_RATE
    control_failure_rate = 1 - p_control
    treatment_failure_rate = control_failure_rate * (1 - ASSUMED_RELATIVE_FAILURE_REDUCTION)
    p_treatment = 1 - treatment_failure_rate

    n_a, n_b = N_PER_ARM, N_PER_ARM
    successes_a = int(rng.binomial(n_a, p_control))
    successes_b = int(rng.binomial(n_b, p_treatment))

    rate_a = successes_a / n_a
    rate_b = successes_b / n_b

    abs_lift = rate_b - rate_a
    rel_lift = (abs_lift / rate_a) * 100 if rate_a > 0 else float("nan")

    # Two-proportion z-test
    pooled_p = (successes_a + successes_b) / (n_a + n_b)
    se = np.sqrt(pooled_p * (1 - pooled_p) * (1 / n_a + 1 / n_b))
    z_stat = (rate_b - rate_a) / se if se > 0 else 0.0
    # Two-tailed p-value via the survival function, which stays numerically
    # stable in the tail (unlike 1 - norm.cdf(), which saturates to 0 for
    # large |z| due to floating-point precision).
    p_value = 2 * stats.norm.sf(abs(z_stat))
    p_value_display = f"{p_value:.2e}" if p_value < 0.0001 else f"{p_value:.4f}"

    is_significant = bool(p_value < ALPHA)

    # Winner is derived programmatically, never hard-coded.
    if is_significant and rate_b > rate_a:
        winner = "Treatment (B) - new checkout flow"
    elif is_significant and rate_a > rate_b:
        winner = "Control (A) - existing checkout flow"
    else:
        winner = "No statistically significant difference"

    results = {
        "test_name": "Simulated A/B Test: New Checkout Flow",
        "is_simulated": True,
        "experimental_unit": EXPERIMENTAL_UNIT,
        "conversion_metric": CONVERSION_METRIC,
        "hypothesis_null": "p_treatment = p_control",
        "hypothesis_alt": "p_treatment != p_control (two-tailed)",
        "random_seed": seed,
        "alpha": ALPHA,
        "group": ["Control (A)", "Treatment (B)"],
        "group_description": [
            "Existing checkout flow",
            "New checkout flow (simulated, hypothesized to reduce payment-failure rate)",
        ],
        "checkout_attempts": [n_a, n_b],
        "successful_checkouts": [successes_a, successes_b],
        "conversion_rate": [round(rate_a, 4), round(rate_b, 4)],
        "absolute_lift": round(abs_lift, 4),
        "relative_lift_pct": round(rel_lift, 2),
        "z_statistic": round(float(z_stat), 4),
        "p_value": float(p_value),
        "p_value_display": p_value_display,
        "is_significant": is_significant,
        "winner": winner,
        "baseline_rate_source": (
            "Control conversion rate = REAL payment-authorization rate from "
            "this dataset (21,141 of 21,629 orders were not cancelled for "
            "payment failure = 97.74%), from sql/04_funnel_analysis.sql's "
            "'Payment Successful' stage."
        ),
        "treatment_assumption": (
            f"Treatment simulates a {ASSUMED_RELATIVE_FAILURE_REDUCTION:.0%} relative "
            "reduction in the payment-failure rate (not a flat lift on the "
            "success rate, which would be implausible this close to the ceiling)."
        ),
    }
    return results


def results_to_dfs(results: dict):
    """Reshape into a tidy per-group table plus a summary table."""
    groups_df = pd.DataFrame({
        "group": results["group"],
        "group_description": results["group_description"],
        "checkout_attempts": results["checkout_attempts"],
        "successful_checkouts": results["successful_checkouts"],
        "conversion_rate": results["conversion_rate"],
    })

    summary_df = pd.DataFrame([{
        "test_name": results["test_name"],
        "is_simulated": results["is_simulated"],
        "experimental_unit": results["experimental_unit"],
        "conversion_metric": results["conversion_metric"],
        "hypothesis_null": results["hypothesis_null"],
        "hypothesis_alt": results["hypothesis_alt"],
        "random_seed": results["random_seed"],
        "alpha": results["alpha"],
        "absolute_lift": results["absolute_lift"],
        "relative_lift_pct": results["relative_lift_pct"],
        "z_statistic": results["z_statistic"],
        "p_value": results["p_value"],
        "p_value_display": results["p_value_display"],
        "is_significant": results["is_significant"],
        "winner": results["winner"],
        "baseline_rate_source": results["baseline_rate_source"],
        "treatment_assumption": results["treatment_assumption"],
    }])

    return groups_df, summary_df


def main():
    results = simulate_ab_test()
    groups_df, summary_df = results_to_dfs(results)

    groups_path = OUT_DIR / "ab_test_results.csv"
    summary_path = OUT_DIR / "ab_test_summary.csv"

    groups_df.to_csv(groups_path, index=False)
    summary_df.to_csv(summary_path, index=False)

    print("Simulated A/B test complete.")
    print(f"Unit: {results['experimental_unit']}  |  Metric: {results['conversion_metric']}")
    print(groups_df.to_string(index=False))
    print()
    print(json.dumps(results, indent=2))
    print(f"\nWritten to:\n  {groups_path}\n  {summary_path}")


if __name__ == "__main__":
    main()

"""
app.py - Amazon E-Commerce Product Analytics Dashboard

Streamlit + Plotly dashboard. Reads ONLY from CSV files in
data/analytics_outputs/ - it never connects to PostgreSQL and requires no
database credentials, so it can be deployed as-is to Streamlit Cloud.

Run locally:
    streamlit run dashboard/app.py

To regenerate the CSVs this dashboard reads, run (from the repo root, with
PostgreSQL loaded - see README):
    python scripts/export_analytics.py
    python scripts/simulate_discovery_funnel.py
    python scripts/ab_test_simulation.py
"""

from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data" / "analytics_outputs"

st.set_page_config(
    page_title="Amazon E-Commerce Product Analytics",
    page_icon="📦",
    layout="wide",
)


# -----------------------------------------------------------------------
# Data loading (cached, resilient to missing files)
# -----------------------------------------------------------------------
@st.cache_data
def load_csv(filename: str) -> pd.DataFrame | None:
    path = DATA_DIR / filename
    if not path.exists():
        return None
    return pd.read_csv(path)


kpi_df = load_csv("kpi_summary.csv")
cohort_df = load_csv("cohort_retention.csv")
cohort_pivot_df = load_csv("cohort_retention_pivot.csv")
funnel_real_df = load_csv("funnel_fulfillment.csv")
funnel_sim_df = load_csv("funnel_discovery_simulated.csv")
ab_groups_df = load_csv("ab_test_results.csv")
ab_summary_df = load_csv("ab_test_summary.csv")

missing_files = [
    name for name, df in {
        "kpi_summary.csv": kpi_df,
        "cohort_retention.csv": cohort_df,
        "cohort_retention_pivot.csv": cohort_pivot_df,
        "funnel_fulfillment.csv": funnel_real_df,
        "funnel_discovery_simulated.csv": funnel_sim_df,
        "ab_test_results.csv": ab_groups_df,
        "ab_test_summary.csv": ab_summary_df,
    }.items() if df is None
]

st.title("📦 Amazon E-Commerce Product Analytics")
st.caption(
    "Cohort retention, funnel, and A/B testing case study built on a real "
    "PostgreSQL e-commerce dataset (21,629 orders, 2020–2024)."
)

if missing_files:
    st.warning(
        "Some analytics files are missing: " + ", ".join(missing_files) +
        ". Run the export scripts described in the README, then reload."
    )

st.divider()

# -----------------------------------------------------------------------
# KPI section
# -----------------------------------------------------------------------
st.subheader("Key Metrics")

if kpi_df is not None and len(kpi_df) > 0:
    kpi = kpi_df.iloc[0]
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Total Customers", f"{int(kpi['total_customers']):,}")
    k2.metric("Total Orders", f"{int(kpi['total_orders']):,}")
    k3.metric("Total Revenue", f"${kpi['total_revenue']:,.0f}")
    k4.metric("Avg Order Value", f"${kpi['avg_order_value']:,.2f}")

    k5, k6, k7, k8 = st.columns(4)
    pct_ordering = kpi["customers_with_orders"] / kpi["total_customers"] * 100
    k5.metric("Customers Who Ordered", f"{pct_ordering:.1f}%",
              help=f"{int(kpi['customers_with_orders'])} of {int(kpi['total_customers'])} registered customers")

    if funnel_real_df is not None:
        kept_row = funnel_real_df[funnel_real_df["stage"] == "Kept (Not Returned)"]
        if not kept_row.empty:
            k6.metric("Order Completion Rate", f"{kept_row.iloc[0]['conversion_from_start_pct']:.1f}%",
                      help="% of all placed orders that were delivered and not returned")

    if ab_summary_df is not None and len(ab_summary_df) > 0:
        ab_row = ab_summary_df.iloc[0]
        k7.metric("A/B Test Relative Lift (Simulated)", f"{ab_row['relative_lift_pct']:+.2f}%",
                  help="Simulated checkout-attempt test - see A/B Test section below")
        k8.metric("A/B Test p-value (Simulated)", f"{ab_row['p_value_display']}",
                  help=f"Significant at alpha={ab_row['alpha']}: {ab_row['is_significant']}")
else:
    st.info("KPI summary not available.")

st.divider()

# -----------------------------------------------------------------------
# Cohort retention heatmap
# -----------------------------------------------------------------------
st.subheader("📅 Monthly Cohort Retention")
st.caption(
    "**Real analysis, derived acquisition proxy.** Cohort month = the "
    "calendar month of each customer's **first successful order** (this "
    "dataset has no separate signup date, so first purchase is used as the "
    "acquisition proxy - a standard approach for e-commerce cohort "
    "analysis). Both cohort assignment and later 'activity' exclude "
    "**Cancelled** orders (payment never actually succeeded for those), "
    "so retention reflects genuine repeat purchasing, not failed checkouts. "
    "Retention % = customers with a successful order again in a later "
    "month, as a share of the original cohort size."
)

if cohort_pivot_df is not None and len(cohort_pivot_df) > 0:
    pivot = cohort_pivot_df.set_index("cohort_month")
    # Limit displayed month-offset columns to keep the heatmap legible
    max_months = st.slider("Months since acquisition to display", 3, min(pivot.shape[1], 36), 12)
    display_cols = [c for c in pivot.columns if int(c.replace("month_", "")) <= max_months]
    display_pivot = pivot[display_cols]

    fig = px.imshow(
        display_pivot,
        labels=dict(x="Months Since Acquisition", y="Cohort Month", color="Retention %"),
        x=[c.replace("month_", "") for c in display_pivot.columns],
        y=display_pivot.index,
        color_continuous_scale="Blues",
        aspect="auto",
        text_auto=".0f",
    )
    fig.update_layout(height=650, xaxis_title="Months Since Acquisition", yaxis_title="Cohort Month")
    st.plotly_chart(fig, width="stretch")

    with st.expander("View underlying cohort data (long format)"):
        st.dataframe(cohort_df, width="stretch")
else:
    st.info("Cohort retention data not available.")

st.divider()

# -----------------------------------------------------------------------
# Funnel section (real + simulated, clearly separated)
# -----------------------------------------------------------------------
st.subheader("🛒 Funnel Analysis")
st.caption(
    "The **Order Fulfillment Funnel** below is the primary funnel for this "
    "project - it is built entirely from real data. The **Discovery "
    "Funnel** tab is a secondary, clearly-labeled illustrative sketch, "
    "included only to show what a top-of-funnel view could look like; it "
    "is not a measurement."
)

tab_real, tab_sim = st.tabs([
    "✅ PRIMARY — Order Fulfillment Funnel (Real Data)",
    "🧪 Secondary — Discovery Funnel (Simulated / Illustrative)",
])

with tab_real:
    st.success(
        "✅ **Real data.** Built entirely from real `orders`, `payments`, "
        "and `shippings` records in the database - every stage boundary "
        "is cross-checked against at least one other independent column "
        "in the schema (see sql/04_funnel_analysis.sql)."
    )
    if funnel_real_df is not None:
        fig_real = go.Figure(go.Funnel(
            y=funnel_real_df["stage"],
            x=funnel_real_df["orders"],
            textinfo="value+percent initial",
        ))
        fig_real.update_layout(height=450)
        st.plotly_chart(fig_real, width="stretch")
        st.dataframe(funnel_real_df, width="stretch", hide_index=True)
    else:
        st.info("Funnel data not available.")

with tab_sim:
    st.warning(
        "⚠️ **Simulated / illustrative - not observed customer behavior.** "
        "This dataset has no clickstream/event tracking of any kind, so a "
        "View→Cart→Checkout→Purchase funnel cannot be measured here. Only "
        "the **Purchase** stage below is real (it matches the Order "
        "Fulfillment Funnel's completed-order count exactly); View Item / "
        "Add to Cart / Checkout are backed out using generic industry-"
        "average e-commerce conversion benchmarks with a fixed random "
        "seed, and are rounded to the nearest 50 so they are not mistaken "
        "for precise measured counts."
    )
    if funnel_sim_df is not None:
        fig_sim = go.Figure(go.Funnel(
            y=funnel_sim_df["stage"],
            x=funnel_sim_df["estimated_users"],
            textinfo="value+percent initial",
            marker={"color": "orange"},
        ))
        fig_sim.update_layout(height=450)
        st.plotly_chart(fig_sim, width="stretch")
        st.dataframe(funnel_sim_df, width="stretch", hide_index=True)
    else:
        st.info("Simulated funnel data not available.")

st.divider()

# -----------------------------------------------------------------------
# A/B test section
# -----------------------------------------------------------------------
st.subheader("🧪 A/B Test: New Checkout Flow (Simulated)")
st.warning(
    "⚠️ **Simulated experiment - not a real Amazon test.** No such test "
    "was actually run, and there is no experiment-assignment table "
    "anywhere in the schema. The control conversion rate is the REAL "
    "payment-authorization rate observed in this dataset; the treatment "
    "effect is a stated, assumed hypothesis, not a measured fact. Fixed "
    "random seed → fully reproducible."
)

if ab_groups_df is not None and ab_summary_df is not None and len(ab_summary_df) > 0:
    summary = ab_summary_df.iloc[0]

    with st.expander("Experiment design: unit → metric → hypothesis", expanded=True):
        st.markdown(
            f"- **Experimental unit:** {summary['experimental_unit']} "
            "(not a customer/user - each row is one checkout submission)\n"
            f"- **Conversion metric:** {summary['conversion_metric']}\n"
            f"- **Null hypothesis (H0):** {summary['hypothesis_null']}\n"
            f"- **Alternative hypothesis (H1):** {summary['hypothesis_alt']}\n"
            f"- **Control (A):** {ab_groups_df.iloc[0]['group_description']}\n"
            f"- **Treatment (B):** {ab_groups_df.iloc[1]['group_description']}\n"
            f"- **Baseline source:** {summary['baseline_rate_source']}\n"
            f"- **Treatment assumption:** {summary['treatment_assumption']}"
        )

    c1, c2 = st.columns([1, 1])
    with c1:
        fig_ab = px.bar(
            ab_groups_df, x="group", y="conversion_rate", color="group",
            text=ab_groups_df["conversion_rate"].map(lambda x: f"{x:.1%}"),
            labels={"conversion_rate": "Conversion Rate", "group": ""},
        )
        fig_ab.update_layout(showlegend=False, height=400, yaxis_tickformat=".1%")
        st.plotly_chart(fig_ab, width="stretch")

    with c2:
        st.dataframe(
            ab_groups_df[["group", "checkout_attempts", "successful_checkouts", "conversion_rate"]],
            width="stretch", hide_index=True,
        )
        m1, m2 = st.columns(2)
        m1.metric("Absolute Lift", f"{summary['absolute_lift']:+.2%}")
        m2.metric("Relative Lift", f"{summary['relative_lift_pct']:+.2f}%")
        m3, m4 = st.columns(2)
        m3.metric("z-statistic", f"{summary['z_statistic']:.3f}")
        m4.metric("p-value", f"{summary['p_value_display']}")

        if summary["is_significant"]:
            st.success(f"**Winner: {summary['winner']}** (significant at α={summary['alpha']})")
        else:
            st.info(f"**Result: {summary['winner']}** (not significant at α={summary['alpha']})")
else:
    st.info("A/B test data not available.")

st.divider()
st.caption(
    "Data pipeline: PostgreSQL → SQL analysis (sql/) → CSV exports "
    "(scripts/) → this dashboard. See README.md for the full methodology, "
    "setup commands, and an explicit breakdown of what is real vs. "
    "derived vs. simulated in this project."
)

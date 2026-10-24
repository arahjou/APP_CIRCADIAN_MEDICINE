"""Comparison dashboard: direction-aware KPI cards, sleep timing and data coverage.

Data shaping (`build_dashboard_data`) is separate from rendering
(`render_comparison_dashboard`) so it can be tested without Streamlit.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class KPI:
    key: str
    domain: str
    label: str
    table: str
    analysis_type: str
    column: str
    unit: str
    better: str            # "higher", "lower" or "neutral"
    threshold: float       # smallest change shown as improved/worsened
    help: str
    fmt: str = "{:.2f}"


KPIS = [
    KPI("sri", "Sleep", "Sleep regularity (SRI)", "sleep_analysis", "sri_sleep", "SRI", "", "higher", 5,
        "Probability of being in the same sleep/wake state 24 h apart, scaled -100..100. "
        "Higher means more regular sleep timing.", "{:.0f}"),
    KPI("cpd", "Sleep", "Mid-sleep variability (CPD)", "sleep_analysis", "cpd_mid_sleep", "cpd_hours", " h", "lower", 0.25,
        "Composite phase deviation of mid-sleep: how far each night's mid-sleep is from the person's "
        "average and from the previous night. Lower means more stable sleep timing."),
    KPI("duration", "Sleep", "Main sleep duration", "sleep_analysis", "sleep_periods", "duration_minutes", " h", "neutral", 0.25,
        "Mean onset-to-offset length of the main nightly sleep episode (naps excluded). "
        "Not ranked: both short and very long sleep can be unfavourable.", "{:.1f}"),
    KPI("is", "Activity rhythm", "Day-to-day stability (IS)", "activity_analysis", "activity_is_iv", "IS_2day", "", "higher", 0.05,
        "Interdaily stability, 0..1: how similar the 24 h activity pattern is from day to day."),
    KPI("iv", "Activity rhythm", "Fragmentation (IV)", "activity_analysis", "activity_is_iv", "IV_2day", "", "lower", 0.1,
        "Intradaily variability, ~0..2: how often activity switches between rest and activity within a day. "
        "Lower means a more consolidated rhythm."),
    KPI("ra", "Activity rhythm", "Rhythm strength (RA)", "activity_analysis", "activity_l5_m10_ra", "RA", "", "higher", 0.03,
        "Relative amplitude, 0..1: contrast between the most active 10 h and the least active 5 h."),
    KPI("light_night", "Light", "Light during sleep", "sleep_analysis", "sleep_light_exposure", "metric1", " min", "lower", 10,
        "Minutes per night with melanopic EDI of at least 1 lux during the main sleep episode.", "{:.0f}"),
    KPI("light_evening", "Light", "Evening light before sleep", "sleep_analysis", "sleep_light_exposure", "metric2", " min", "lower", 10,
        "Minutes per night of at least 10 lux melanopic EDI in the 3 h before sleep onset.", "{:.0f}"),
    KPI("light_morning", "Light", "Dim mornings after waking", "sleep_analysis", "sleep_light_exposure", "metric3", " min", "lower", 10,
        "Minutes below 250 lux melanopic EDI in the 3 h after waking. Lower means more bright morning light.", "{:.0f}"),
]


def _series(db, record_id: str, kpi: KPI) -> pd.Series:
    """Per-day/night values for one KPI, in display units."""
    if kpi.analysis_type == "sleep_light_exposure":
        rows = db.get_analysis_results(record_id, kpi.table)
        row = next((r for r in rows if r.get("analysis_type") == kpi.analysis_type), None)
        payload = row.get("results") if row else None
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except ValueError:
                payload = None
        values = payload.get(kpi.column) if isinstance(payload, dict) else None
        if not isinstance(values, list) or not values:
            return pd.Series(dtype=float)
        frame = pd.DataFrame(values)
        return pd.Series(pd.to_numeric(frame["minutes"], errors="coerce").to_numpy(), index=frame["date"]).dropna()
    try:
        frame = db.get_analysis_results_as_dataframe(record_id, kpi.table, kpi.analysis_type)
    except Exception:
        frame = None
    if frame is None or frame.empty or kpi.column not in frame:
        return pd.Series(dtype=float)
    if kpi.key == "duration" and "is_main_sleep" in frame:
        frame = frame[frame["is_main_sleep"].astype(bool)]
    values = pd.to_numeric(frame[kpi.column], errors="coerce")
    if kpi.key == "duration":
        values = values / 60
    return values.dropna().reset_index(drop=True)


def judge(kpi: KPI, before: float, after: float) -> str:
    """'improved', 'worsened', 'stable', 'changed' (neutral metrics) or 'n/a'."""
    if pd.isna(before) or pd.isna(after):
        return "n/a"
    delta = after - before
    if abs(delta) < kpi.threshold:
        return "stable"
    if kpi.better == "neutral":
        return "changed"
    return "improved" if (delta > 0) == (kpi.better == "higher") else "worsened"


def build_dashboard_data(db, id1: str, id2: str) -> dict:
    rows, trends = [], {}
    for kpi in KPIS:
        s1, s2 = _series(db, id1, kpi), _series(db, id2, kpi)
        v1 = float(s1.mean()) if not s1.empty else np.nan
        v2 = float(s2.mean()) if not s2.empty else np.nan
        trends[kpi.key] = (s1.tolist(), s2.tolist())
        rows.append({"key": kpi.key, "domain": kpi.domain, "label": kpi.label, "value_1": v1, "value_2": v2,
                     "delta": v2 - v1, "verdict": judge(kpi, v1, v2), "n_1": len(s1), "n_2": len(s2)})
    return {"ids": (id1, id2), "kpis": pd.DataFrame(rows), "trends": trends,
            "sleep_timing": pd.concat([_sleep_timing(db, rid) for rid in (id1, id2)], ignore_index=True)}


def _sleep_timing(db, record_id: str) -> pd.DataFrame:
    """Main sleep onset/offset per night as hours after noon (so midnight = 12)."""
    try:
        frame = db.get_analysis_results_as_dataframe(record_id, "sleep_analysis", "sleep_periods")
    except Exception:
        frame = None
    columns = ["record_id", "night", "onset", "offset", "mid"]
    if frame is None or frame.empty or "Sleep_onset_Time" not in frame:
        return pd.DataFrame(columns=columns)
    if "is_main_sleep" in frame:
        frame = frame[frame["is_main_sleep"].astype(bool)]

    def hours_after_noon(date_col, time_col):
        stamp = pd.to_datetime(frame[date_col].astype(str).str[:10] + " " + frame[time_col].astype(str), errors="coerce")
        return stamp, ((stamp.dt.hour + stamp.dt.minute / 60 - 12) % 24)

    onset_ts, onset = hours_after_noon("Sleep_onset_DATE", "Sleep_onset_Time")
    _, offset = hours_after_noon("Sleep_offset_DATE", "Sleep_offset_TIME")
    night = frame["night"] if "night" in frame else (onset_ts - pd.Timedelta(hours=12)).dt.date
    out = pd.DataFrame({"record_id": record_id, "night": pd.to_datetime(night).dt.strftime("%Y-%m-%d"),
                        "onset": onset, "offset": offset})
    # Episodes that run past the next noon wrap; clip so bars stay readable.
    out.loc[out["offset"] < out["onset"], "offset"] = 24
    out["mid"] = (out["onset"] + out["offset"]) / 2
    return out.dropna().reset_index(drop=True)


def _clock(hours_after_noon: float) -> str:
    total = int(round(((hours_after_noon + 12) % 24) * 60))
    return f"{total // 60:02d}:{total % 60:02d}"


def render_comparison_dashboard(data: dict) -> None:
    import altair as alt
    import streamlit as st

    id1, id2 = data["ids"]
    kpis: pd.DataFrame = data["kpis"]
    counts = kpis["verdict"].value_counts()
    improved, worsened = int(counts.get("improved", 0)), int(counts.get("worsened", 0))
    stable = int(counts.get("stable", 0)) + int(counts.get("changed", 0))
    missing = int(counts.get("n/a", 0))
    summary = (f"{improved} improved, {worsened} worsened, {stable} stable or unranked"
               + (f", {missing} not available" if missing else "") + ".")
    alert = st.success if improved > worsened else st.warning if worsened > improved else st.info
    alert(f"Comparing **{id2}** against baseline **{id1}**: {summary} "
          "Small changes below each metric's threshold count as stable.",
          title="At a glance", icon=":material/insights:")

    by_key = {k.key: k for k in KPIS}
    for domain in dict.fromkeys(k.domain for k in KPIS):
        st.markdown(f"#### {domain}")
        cols = st.columns(sum(k.domain == domain for k in KPIS))
        for col, row in zip(cols, kpis[kpis["domain"] == domain].itertuples(index=False)):
            kpi = by_key[row.key]
            with col:
                value = "N/A" if pd.isna(row.value_2) else kpi.fmt.format(row.value_2) + kpi.unit
                delta = None if pd.isna(row.delta) else kpi.fmt.format(row.delta) + kpi.unit
                if delta is not None and row.verdict == "stable":
                    delta = 0
                baseline = "N/A" if pd.isna(row.value_1) else kpi.fmt.format(row.value_1) + kpi.unit
                spark = data["trends"][row.key][1]
                st.metric(
                    kpi.label, value, delta,
                    delta_color={"higher": "normal", "lower": "inverse"}.get(kpi.better, "off"),
                    delta_description=f"vs {baseline} in {id1}",
                    help=f"{kpi.help}\n\nBased on {row.n_2} values ({id2}) vs {row.n_1} ({id1}). "
                         f"Changes smaller than {kpi.threshold:g}{kpi.unit} are shown as stable.",
                    border=True, height="stretch",
                    chart_data=spark if len(spark) > 1 else None, chart_type="line",
                )

    timing = data["sleep_timing"]
    with st.container(border=True):
        st.markdown("#### Sleep timing per night")
        st.caption("Each bar is the main sleep episode (onset to wake-up); the dot marks mid-sleep. "
                   "Bars lining up vertically mean regular sleep timing.")
        if timing.empty:
            st.info("No sleep periods stored for these records.")
        else:
            ticks = list(range(0, 25, 2))
            x = alt.X("onset:Q", title="Clock time", scale=alt.Scale(domain=[0, 24]),
                      axis=alt.Axis(values=ticks, labelExpr="pad(((datum.value + 12) % 24), 2) + ':00'"))
            timing = timing.assign(onset_clock=timing["onset"].map(_clock), offset_clock=timing["offset"].map(_clock))
            tooltip = ["record_id", "night", alt.Tooltip("onset_clock", title="Onset"),
                       alt.Tooltip("offset_clock", title="Wake-up")]
            base = alt.Chart(timing).encode(y=alt.Y("night:N", title=None, sort="ascending"),
                                            yOffset="record_id:N", color=alt.Color("record_id:N", title="Record"))
            chart = base.mark_bar(height=8, cornerRadius=3).encode(x=x, x2="offset:Q", tooltip=tooltip) + \
                base.mark_point(filled=True, color="black", size=25).encode(x="mid:Q", tooltip=tooltip)
            st.altair_chart(chart, alt="Main sleep episode per night for both records")

    with st.expander("Data behind these numbers"):
        table = kpis.assign(
            value_1=kpis["value_1"].round(2), value_2=kpis["value_2"].round(2), delta=kpis["delta"].round(2)
        )[["domain", "label", "value_1", "value_2", "delta", "verdict", "n_1", "n_2"]]
        st.dataframe(table, hide_index=True, alt="Metric values per record",
                     column_config={"value_1": id1, "value_2": id2, "delta": "Change",
                                    "n_1": f"n ({id1})", "n_2": f"n ({id2})"})

import io
from copy import deepcopy
from datetime import datetime, timedelta, time

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

DEFAULT_FILE = "data_set_1.csv"
REQUIRED_COLUMNS = ["DATE/TIME", "PIMn"]
HISTORY_LIMIT = 30


# -----------------------------
# Data loading and validation
# -----------------------------
@st.cache_data(show_spinner=False)
def load_csv_bytes(file_bytes: bytes) -> pd.DataFrame:
    df = pd.read_csv(io.BytesIO(file_bytes))
    return prepare_dataframe(df)


@st.cache_data(show_spinner=False)
def load_default_file(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    return prepare_dataframe(df)



def prepare_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")

    out = df.copy()
    out["DATE/TIME"] = pd.to_datetime(out["DATE/TIME"], errors="coerce")
    # Strip timezone — the editor works in local wall-clock time only
    if hasattr(out["DATE/TIME"].dt, "tz") and out["DATE/TIME"].dt.tz is not None:
        out["DATE/TIME"] = out["DATE/TIME"].dt.tz_localize(None)
    out = out.dropna(subset=["DATE/TIME"]).sort_values("DATE/TIME").reset_index(drop=True)

    if "SLEEP_STATE" not in out.columns:
        out["SLEEP_STATE"] = infer_sleep_state_from_pimn(out)
    out["SLEEP_STATE"] = pd.to_numeric(out["SLEEP_STATE"], errors="coerce").fillna(0).astype(int)
    out["SLEEP_STATE"] = out["SLEEP_STATE"].clip(0, 1)

    out["PIMn"] = pd.to_numeric(out["PIMn"], errors="coerce")
    out["EDITED"] = False

    return out


def infer_sleep_state_from_pimn(
    data: pd.DataFrame,
    rolling_window: int = 100,
    sleep_threshold: float = 6.0,
    max_wake_gap_hours: float = 2.0,
) -> pd.Series:
    """Infer initial sleep state from PIMn with light cleanup of short wake gaps."""
    out = data.copy()
    out["PIMn"] = pd.to_numeric(out["PIMn"], errors="coerce").fillna(0)
    out["PIMn_avg"] = out["PIMn"].rolling(window=rolling_window, min_periods=1).mean()
    out["Sleep_State"] = (out["PIMn_avg"] < sleep_threshold).astype(int)

    # Fill short wake gaps inside sleep bouts to match analysis behavior.
    transitions = out["Sleep_State"].diff()
    wake_up_indices = transitions[transitions == -1].index
    sleep_onset_indices = transitions[transitions == 1].index
    for wake_idx in wake_up_indices:
        next_sleep_onsets = sleep_onset_indices[sleep_onset_indices > wake_idx]
        if next_sleep_onsets.empty:
            continue
        next_sleep_idx = int(next_sleep_onsets[0])
        wake_time = out.loc[wake_idx, "DATE/TIME"]
        next_sleep_time = out.loc[next_sleep_idx, "DATE/TIME"]
        if pd.isna(wake_time) or pd.isna(next_sleep_time):
            continue
        if next_sleep_time - wake_time < pd.Timedelta(hours=max_wake_gap_hours):
            out.loc[wake_idx:next_sleep_idx - 1, "Sleep_State"] = 1

    return out["Sleep_State"]


# -----------------------------
# Session state helpers
# -----------------------------
def initialize_state(df: pd.DataFrame, source_name: str):
    st.session_state.original_df = df.copy(deep=True)
    st.session_state.df = df.copy(deep=True)
    st.session_state.undo_stack = []
    st.session_state.redo_stack = []
    st.session_state.source_name = source_name
    st.session_state.loaded = True



def push_undo_state(action_label: str):
    snapshot = {
        "label": action_label,
        "df": st.session_state.df.copy(deep=True),
    }
    st.session_state.undo_stack.append(snapshot)
    if len(st.session_state.undo_stack) > HISTORY_LIMIT:
        st.session_state.undo_stack = st.session_state.undo_stack[-HISTORY_LIMIT:]
    st.session_state.redo_stack = []



def undo_last():
    if not st.session_state.undo_stack:
        return False
    current = {
        "label": "redo",
        "df": st.session_state.df.copy(deep=True),
    }
    st.session_state.redo_stack.append(current)
    previous = st.session_state.undo_stack.pop()
    st.session_state.df = previous["df"].copy(deep=True)
    return True



def redo_last():
    if not st.session_state.redo_stack:
        return False
    current = {
        "label": "undo",
        "df": st.session_state.df.copy(deep=True),
    }
    st.session_state.undo_stack.append(current)
    nxt = st.session_state.redo_stack.pop()
    st.session_state.df = nxt["df"].copy(deep=True)
    return True



def reset_to_original():
    st.session_state.df = st.session_state.original_df.copy(deep=True)
    st.session_state.undo_stack = []
    st.session_state.redo_stack = []


# -----------------------------
# Derived views / utilities
# -----------------------------
def infer_epoch_minutes(data: pd.DataFrame) -> float:
    diffs = data["DATE/TIME"].sort_values().diff().dropna()
    if diffs.empty:
        return 1.0
    return max(diffs.mode().iloc[0].total_seconds() / 60.0, 1 / 60)



def add_display_period(data: pd.DataFrame, mode: str) -> pd.DataFrame:
    out = data.copy()
    if mode == "Night (12:00 to 11:59 next day)":
        out["DISPLAY_PERIOD"] = (out["DATE/TIME"] - pd.Timedelta(hours=12)).dt.date
    else:
        out["DISPLAY_PERIOD"] = out["DATE/TIME"].dt.date
    return out



def calculate_segments(data: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    out = data.copy()
    is_sleep = out["SLEEP_STATE"].eq(1)
    groups = is_sleep.ne(is_sleep.shift()).cumsum()
    sleep_groups = groups.where(is_sleep)

    unique_groups = pd.Series(sleep_groups.dropna().unique())
    seg_map = {old: new for new, old in enumerate(unique_groups.tolist(), 1)}

    out["segment_id"] = pd.Series(pd.NA, index=out.index, dtype="Int64")
    if not unique_groups.empty:
        out.loc[is_sleep, "segment_id"] = sleep_groups[is_sleep].map(seg_map).astype("Int64")

    epoch_minutes = infer_epoch_minutes(out)

    seg_rows = []
    for sid in sorted(out["segment_id"].dropna().unique()):
        seg = out[out["segment_id"] == sid]
        start = seg["DATE/TIME"].min()
        end = seg["DATE/TIME"].max()
        n_epochs = len(seg)
        duration_minutes = round(n_epochs * epoch_minutes, 2)
        seg_rows.append(
            {
                "segment_id": int(sid),
                "start": start,
                "end": end,
                "epochs": n_epochs,
                "duration_min": duration_minutes,
                "display_period": seg["DISPLAY_PERIOD"].mode().iloc[0] if "DISPLAY_PERIOD" in seg.columns else start.date(),
            }
        )

    seg_df = pd.DataFrame(seg_rows)
    if not seg_df.empty:
        seg_df["duration_h"] = (seg_df["duration_min"] / 60).round(2)
    return out, seg_df



def period_bounds(selected_period, mode: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    start = pd.Timestamp(selected_period)
    if mode == "Night (12:00 to 11:59 next day)":
        return start + pd.Timedelta(hours=12), start + pd.Timedelta(days=1, hours=11, minutes=59, seconds=59)
    return start, start + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)



def combine_date_and_time(d, t) -> pd.Timestamp:
    return pd.Timestamp(datetime.combine(d, t))



def validate_range(start_ts: pd.Timestamp, end_ts: pd.Timestamp, data: pd.DataFrame):
    if pd.isna(start_ts) or pd.isna(end_ts):
        return False, "Start or end time is invalid."
    if start_ts >= end_ts:
        return False, "Start time must be earlier than end time."
    if start_ts < data["DATE/TIME"].min() or end_ts > data["DATE/TIME"].max():
        return False, "Selected range is outside the available data range."
    return True, ""



def overlap_warning(seg_df: pd.DataFrame, selected_id: int, start_ts: pd.Timestamp, end_ts: pd.Timestamp):
    if seg_df.empty:
        return False
    other = seg_df[seg_df["segment_id"] != selected_id]
    if other.empty:
        return False
    overlaps = other[(other["start"] <= end_ts) & (other["end"] >= start_ts)]
    return not overlaps.empty



def apply_sleep_range(start_ts: pd.Timestamp, end_ts: pd.Timestamp, mark_sleep: int = 1):
    mask = st.session_state.df["DATE/TIME"].between(start_ts, end_ts)
    st.session_state.df.loc[mask, "SLEEP_STATE"] = int(mark_sleep)
    st.session_state.df.loc[mask, "EDITED"] = True



def auto_cleanup_short_gaps(data: pd.DataFrame, max_gap_minutes: int) -> int:
    if max_gap_minutes <= 0:
        return 0

    out, seg_df = calculate_segments(data)
    if len(seg_df) < 2:
        return 0

    epoch_minutes = infer_epoch_minutes(out)
    changes = 0

    for i in range(len(seg_df) - 1):
        left_end = seg_df.iloc[i]["end"]
        right_start = seg_df.iloc[i + 1]["start"]
        gap_mask = (out["DATE/TIME"] > left_end) & (out["DATE/TIME"] < right_start)
        gap_epochs = int(gap_mask.sum())
        gap_minutes = gap_epochs * epoch_minutes
        if 0 < gap_minutes <= max_gap_minutes:
            st.session_state.df.loc[gap_mask, "SLEEP_STATE"] = 1
            st.session_state.df.loc[gap_mask, "EDITED"] = True
            changes += gap_epochs
    return changes



def auto_remove_short_segments(data: pd.DataFrame, min_segment_minutes: int) -> int:
    if min_segment_minutes <= 0:
        return 0

    out, seg_df = calculate_segments(data)
    if seg_df.empty:
        return 0

    removed_epochs = 0
    to_remove = seg_df[seg_df["duration_min"] < min_segment_minutes]["segment_id"].tolist()
    for sid in to_remove:
        mask = out["segment_id"] == sid
        removed_epochs += int(mask.sum())
        st.session_state.df.loc[mask, "SLEEP_STATE"] = 0
        st.session_state.df.loc[mask, "EDITED"] = True
    return removed_epochs



def make_download_df(data: pd.DataFrame) -> pd.DataFrame:
    out = data.copy()
    if "EDITED" not in out.columns:
        out["EDITED"] = False
    return out



def make_segment_export(seg_df: pd.DataFrame) -> pd.DataFrame:
    if seg_df.empty:
        return pd.DataFrame(columns=["segment_id", "start", "end", "duration_min", "duration_h"])
    cols = ["segment_id", "start", "end", "epochs", "duration_min", "duration_h", "display_period"]
    return seg_df[cols].copy()


# -----------------------------
# Embedded editor — public API
# -----------------------------
def run_sleep_editor(df: pd.DataFrame, source_key: str = "uploaded", show_export: bool = True) -> pd.DataFrame:
    """Render the sleep-segment editor inline within another Streamlit page.

    Initialises session state on the first call or when *source_key* changes
    (e.g. a new file was uploaded).  Returns the current — possibly edited —
    DataFrame so the caller can pass it directly to downstream analysis.

    ``source_key`` should uniquely identify the data source (e.g. the uploaded
    file name or the analysis ID) so that switching sources triggers a reset.
    """
    # ----- state initialisation -----
    if st.session_state.get("source_name") != source_key or not st.session_state.get("loaded"):
        try:
            prepared = prepare_dataframe(df)
        except ValueError as e:
            st.warning(f"Sleep editor skipped — {e}")
            return df
        initialize_state(prepared, source_key)

    # ----- sidebar controls -----
    with st.sidebar:
        st.header("🛏️ Sleep Editor")
        hist_col1, hist_col2 = st.columns(2)
        if hist_col1.button("Undo", use_container_width=True,
                            disabled=not st.session_state.undo_stack, key="vis_undo"):
            if undo_last():
                st.rerun()
        if hist_col2.button("Redo", use_container_width=True,
                            disabled=not st.session_state.redo_stack, key="vis_redo"):
            if redo_last():
                st.rerun()
        if st.button("Reset to original", type="secondary", use_container_width=True, key="vis_reset"):
            reset_to_original()
            st.rerun()

        st.subheader("Auto cleanup")
        with st.form("vis_cleanup_form"):
            bridge_gap_min = st.number_input(
                "Bridge wake gaps up to (minutes)", min_value=0, max_value=240, value=5, step=1,
            )
            remove_seg_min = st.number_input(
                "Remove sleep segments shorter than (minutes)", min_value=0, max_value=240, value=10, step=1,
            )
            cleanup_submit = st.form_submit_button("Apply auto cleanup", use_container_width=True)
        if cleanup_submit:
            push_undo_state("auto_cleanup")
            gap_changes = auto_cleanup_short_gaps(st.session_state.df, int(bridge_gap_min))
            seg_changes = auto_remove_short_segments(st.session_state.df, int(remove_seg_min))
            st.success(f"Cleanup applied. Bridged {gap_changes} rows, removed {seg_changes} rows.")
            st.rerun()

    # ----- view options (also in sidebar) -----
    display_mode = st.sidebar.radio(
        "View mode",
        ["Calendar date", "Night (12:00 to 11:59 next day)"],
        index=1,
        key="vis_display_mode",
    )
    plot_signal = st.sidebar.selectbox(
        "Signal to plot",
        options=[col for col in st.session_state.df.columns if col not in ["SLEEP_STATE", "EDITED"]],
        index=(
            [col for col in st.session_state.df.columns].index("PIMn")
            if "PIMn" in st.session_state.df.columns else 0
        ),
        key="vis_plot_signal",
    )

    # ----- working data -----
    working_df = add_display_period(st.session_state.df, display_mode)
    working_df, seg_df = calculate_segments(working_df)
    all_periods = sorted(working_df["DISPLAY_PERIOD"].dropna().unique())

    if not all_periods:
        st.warning("No valid time periods found in the data.")
        return st.session_state.df

    if "vis_selected_period" not in st.session_state or st.session_state.vis_selected_period not in all_periods:
        st.session_state.vis_selected_period = all_periods[0]

    def _step_period(step: int):
        idx = all_periods.index(st.session_state.vis_selected_period)
        st.session_state.vis_selected_period = all_periods[min(max(idx + step, 0), len(all_periods) - 1)]

    # ----- navigation -----
    nav_col1, nav_col2, nav_col3 = st.columns([1, 3, 1])
    with nav_col1:
        st.button("⬅ Previous", on_click=_step_period, args=(-1,), use_container_width=True, key="vis_prev")
    with nav_col2:
        selected_period = st.selectbox(
            f"Select {display_mode.lower()}",
            options=all_periods,
            index=all_periods.index(st.session_state.vis_selected_period),
            key="vis_period_select",
        )
        st.session_state.vis_selected_period = selected_period
    with nav_col3:
        st.button("Next ➡", on_click=_step_period, args=(1,), use_container_width=True, key="vis_next")

    selected_period = st.session_state.vis_selected_period
    period_start, period_end = period_bounds(selected_period, display_mode)
    period_df = working_df[working_df["DATE/TIME"].between(period_start, period_end)]
    period_seg_df = (
        seg_df[seg_df["display_period"] == selected_period].copy()
        if not seg_df.empty else pd.DataFrame()
    )

    # ----- top metrics -----
    metrics = st.columns(5)
    metrics[0].metric("Rows", f"{len(st.session_state.df):,}")
    metrics[1].metric("Epoch (min)", f"{infer_epoch_minutes(st.session_state.df):.2f}")
    metrics[2].metric("Segments in view", 0 if period_seg_df.empty else len(period_seg_df))
    metrics[3].metric("Edited rows", int(st.session_state.df["EDITED"].sum()))
    metrics[4].metric("Undo available", len(st.session_state.undo_stack))

    if seg_df.empty and int(st.session_state.df["SLEEP_STATE"].sum()) == 0:
        st.warning("No sleep bouts detected yet.")
        if st.button("Auto-detect sleep bouts from PIMn", key="vis_autodetect_btn"):
            push_undo_state("autodetect_sleep_bouts")
            st.session_state.df["SLEEP_STATE"] = infer_sleep_state_from_pimn(st.session_state.df)
            st.session_state.df["EDITED"] = st.session_state.df["EDITED"] | st.session_state.df["SLEEP_STATE"].eq(1)
            st.rerun()

    # ----- sidebar: segment actions + export -----
    with st.sidebar:
        st.subheader("Segment actions")
        segment_options = [] if seg_df.empty else seg_df["segment_id"].astype(int).tolist()

        with st.expander("Adjust boundaries", expanded=True):
            if segment_options:
                selected_seg = st.selectbox("Segment", segment_options, key="vis_adjust_segment")
                seg_row = seg_df[seg_df["segment_id"] == selected_seg].iloc[0]
                default_start = seg_row["start"].to_pydatetime()
                default_end = seg_row["end"].to_pydatetime()
                with st.form("vis_adjust_form"):
                    col1, col2 = st.columns(2)
                    with col1:
                        start_date = st.date_input("Start date", value=default_start.date(), key="vis_adj_start_date")
                        start_time = st.time_input("Start time", value=default_start.time(), key="vis_adj_start_time", step=60)
                    with col2:
                        end_date = st.date_input("End date", value=default_end.date(), key="vis_adj_end_date")
                        end_time = st.time_input("End time", value=default_end.time(), key="vis_adj_end_time", step=60)
                    preview_duration = combine_date_and_time(end_date, end_time) - combine_date_and_time(start_date, start_time)
                    st.caption(f"Preview duration: {preview_duration}")
                    adjust_submit = st.form_submit_button("Update boundaries", use_container_width=True)
                if adjust_submit:
                    new_start = combine_date_and_time(start_date, start_time)
                    new_end = combine_date_and_time(end_date, end_time)
                    ok, msg = validate_range(new_start, new_end, st.session_state.df)
                    if not ok:
                        st.error(msg)
                    else:
                        push_undo_state("adjust_boundaries")
                        current_df = calculate_segments(add_display_period(st.session_state.df, display_mode))[0]
                        old_mask = current_df["segment_id"] == selected_seg
                        st.session_state.df.loc[old_mask.fillna(False), "SLEEP_STATE"] = 0
                        st.session_state.df.loc[old_mask.fillna(False), "EDITED"] = True
                        apply_sleep_range(new_start, new_end, mark_sleep=1)
                        if overlap_warning(seg_df, selected_seg, new_start, new_end):
                            st.warning("The updated range overlaps another existing segment.")
                        st.rerun()
            else:
                st.info("No segments available.")

        with st.expander("Create new segment"):
            default_create_start = period_df["DATE/TIME"].min() if not period_df.empty else st.session_state.df["DATE/TIME"].min()
            default_create_end = default_create_start + pd.Timedelta(minutes=30)
            with st.form("vis_create_form"):
                cc1, cc2 = st.columns(2)
                with cc1:
                    c_start_date = st.date_input("New start date", value=default_create_start.date(), key="vis_new_seg_start_date")
                    c_start_time = st.time_input("New start time", value=default_create_start.time(), key="vis_new_seg_start_time", step=60)
                with cc2:
                    c_end_date = st.date_input("New end date", value=default_create_end.date(), key="vis_new_seg_end_date")
                    c_end_time = st.time_input("New end time", value=default_create_end.time(), key="vis_new_seg_end_time", step=60)
                create_submit = st.form_submit_button("Create sleep segment", use_container_width=True)
            if create_submit:
                new_start = combine_date_and_time(c_start_date, c_start_time)
                new_end = combine_date_and_time(c_end_date, c_end_time)
                ok, msg = validate_range(new_start, new_end, st.session_state.df)
                if not ok:
                    st.error(msg)
                else:
                    push_undo_state("create_segment")
                    apply_sleep_range(new_start, new_end, mark_sleep=1)
                    st.rerun()

        with st.expander("Merge segments"):
            if segment_options:
                merge_ids = st.multiselect("Segments to merge", options=segment_options, key="vis_merge_ids")
                if len(merge_ids) >= 2:
                    temp = seg_df[seg_df["segment_id"].isin(merge_ids)].sort_values("start")
                    min_start = temp["start"].min()
                    max_end = temp["end"].max()
                    bridge_min = round((max_end - min_start).total_seconds() / 60, 2)
                    st.caption(f"Range: {min_start} to {max_end} ({bridge_min} min)")
                if st.button("Merge selected", use_container_width=True,
                             disabled=len(merge_ids) < 2, key="vis_merge_btn"):
                    push_undo_state("merge_segments")
                    temp = seg_df[seg_df["segment_id"].isin(merge_ids)]
                    apply_sleep_range(temp["start"].min(), temp["end"].max(), mark_sleep=1)
                    st.rerun()
            else:
                st.info("No segments available.")

        with st.expander("Remove segment"):
            if segment_options:
                rm_id = st.selectbox("Segment to remove", options=segment_options, key="vis_remove_segment")
                rm_row = seg_df[seg_df["segment_id"] == rm_id].iloc[0]
                st.caption(f"Duration: {rm_row['duration_min']} min")
                if st.button("Remove selected segment", use_container_width=True, key="vis_remove_btn"):
                    push_undo_state("remove_segment")
                    current_df = calculate_segments(add_display_period(st.session_state.df, display_mode))[0]
                    rm_mask = current_df["segment_id"] == rm_id
                    st.session_state.df.loc[rm_mask.fillna(False), "SLEEP_STATE"] = 0
                    st.session_state.df.loc[rm_mask.fillna(False), "EDITED"] = True
                    st.rerun()
            else:
                st.info("No segments available.")

        if show_export:
            st.subheader("Export")
            export_df = make_download_df(st.session_state.df)
            export_segments = make_segment_export(seg_df)
            st.download_button(
                "Download corrected CSV",
                data=export_df.to_csv(index=False).encode("utf-8"),
                file_name=f"corrected_{st.session_state.source_name}",
                mime="text/csv",
                use_container_width=True,
                key="vis_dl_csv",
            )
            st.download_button(
                "Download segment summary",
                data=export_segments.to_csv(index=False).encode("utf-8"),
                file_name="sleep_segments_summary.csv",
                mime="text/csv",
                use_container_width=True,
                key="vis_dl_seg",
            )
        else:
            st.subheader("Analysis mode")
            st.caption("Edits are used directly for analysis in this session. Download/export is hidden.")

    # ----- main layout -----
    left_col, right_col = st.columns([2.1, 1.1])

    with left_col:
        st.subheader("Activity and sleep view")
        if period_df.empty:
            st.info("No rows found for the selected period.")
        else:
            fig = go.Figure()
            fig.add_trace(
                go.Scatter(
                    x=period_df["DATE/TIME"],
                    y=period_df[plot_signal],
                    mode="lines",
                    name=plot_signal,
                    line=dict(width=2),
                )
            )
            if not period_seg_df.empty:
                for _, row in period_seg_df.iterrows():
                    fig.add_vrect(
                        x0=row["start"],
                        x1=row["end"],
                        fillcolor="green",
                        opacity=0.18,
                        layer="below",
                        line_width=0,
                        annotation_text=f"Seg {int(row['segment_id'])}<br>{row['duration_h']} h",
                        annotation_position="top left",
                    )
            edited_points = period_df[period_df["EDITED"]]
            if not edited_points.empty:
                fig.add_trace(
                    go.Scatter(
                        x=edited_points["DATE/TIME"],
                        y=edited_points[plot_signal],
                        mode="markers",
                        name="Edited rows",
                        marker=dict(size=6, symbol="circle-open"),
                    )
                )
            fig.update_layout(
                height=500,
                margin=dict(l=40, r=20, t=50, b=40),
                hovermode="x unified",
                plot_bgcolor="white",
                title=f"{display_mode}: {selected_period}",
                xaxis_title="Time",
                yaxis_title=plot_signal,
            )
            fig.update_xaxes(showgrid=True, gridcolor="LightGray")
            fig.update_yaxes(showgrid=True, gridcolor="LightGray")
            st.plotly_chart(fig, use_container_width=True)

    with right_col:
        st.subheader("Segment summary")
        if period_seg_df.empty:
            st.info("No sleep segments in this view.")
        else:
            summary_df = period_seg_df.copy()
            summary_df["start"] = summary_df["start"].dt.strftime("%Y-%m-%d %H:%M")
            summary_df["end"] = summary_df["end"].dt.strftime("%Y-%m-%d %H:%M")
            summary_df["flag"] = summary_df["duration_min"].apply(lambda x: "Short" if x < 15 else "")
            st.dataframe(
                summary_df[["segment_id", "start", "end", "duration_min", "duration_h", "flag"]],
                use_container_width=True,
                hide_index=True,
            )
        st.subheader("Selected period stats")
        if not period_df.empty:
            total_sleep_epochs = int(period_df["SLEEP_STATE"].sum())
            epoch_minutes = infer_epoch_minutes(period_df)
            total_sleep_hours = round((total_sleep_epochs * epoch_minutes) / 60, 2)
            st.write(f"**Rows in view:** {len(period_df):,}")
            st.write(f"**Sleep rows in view:** {total_sleep_epochs:,}")
            st.write(f"**Estimated sleep duration:** {total_sleep_hours} h")
            st.write(f"**Edited rows in view:** {int(period_df['EDITED'].sum())}")

    with st.expander("Preview data in current view"):
        preview_cols = ["DATE/TIME", plot_signal, "SLEEP_STATE", "EDITED"]
        if "segment_id" in period_df.columns:
            preview_cols.append("segment_id")
        st.dataframe(period_df[preview_cols], use_container_width=True, hide_index=True)

    return st.session_state.df


# -----------------------------
# Standalone entry point
# -----------------------------
if __name__ == "__main__":
    st.set_page_config(layout="wide", page_title="Sleep Segment Editor")
    st.title("🛏️ Sleep Segment Editor")
    st.caption("Inspect activity, review sleep segments, edit safely, and export corrected results.")

    with st.sidebar:
        st.header("Data")
        uploaded = st.file_uploader("Upload CSV", type=["csv"])

    if "loaded" not in st.session_state:
        st.session_state.loaded = False

    try:
        if uploaded is not None:
            incoming_name = uploaded.name
            if st.session_state.get("source_name") != incoming_name:
                initialize_state(load_csv_bytes(uploaded.getvalue()), incoming_name)
        elif not st.session_state.loaded:
            initialize_state(load_default_file(DEFAULT_FILE), DEFAULT_FILE)
    except FileNotFoundError:
        st.error("No default file was found. Please upload a CSV file.")
        st.stop()
    except Exception as e:
        st.error(f"Could not load data: {e}")
        st.stop()

    if not st.session_state.loaded:
        st.info("Upload a CSV file to begin.")
        st.stop()

    run_sleep_editor(st.session_state.df, st.session_state.source_name, show_export=True)

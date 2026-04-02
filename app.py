import streamlit as st
import streamlit.components.v1 as components
from datetime import datetime, timedelta
import sqlite3
import os
import json
import pandas as pd
import uuid
# utils
from tools.upload_file import upload_file, get_available_dates, filter_data_by_dates
from tools.database import ActigraphDB
# sleep
from tools.sleep_light_exposure import analyze_sleep_light_exposure
from tools.sleep_on_off_mid import analyze_sleep_periods
from tools.sleep_CPD_ms import build_centered_midpoint_hours, calculate_single_person_cpd
from tools.sleep_SRI import calculate_sri_from_pimn
# activity
from tools.activity_plotter import activity_plotter
from tools.activity_IS_IV import compute_rolling_2day_is_iv_activity
from tools.activity_L5_M10_RA import compute_daily_L5_M10_RA_activity
from tools.activity_cosinor import fit_cosinor_daily_activity
from tools.activity_CPD import calculate_cpd_activity

# light
from tools.light_plotter import light_plotter
from tools.light_IS_IV import compute_rolling_2day_is_iv_light
from tools.light_L5_M10_RA import compute_daily_L5_M10_RA_light
from tools.light_cosinor import fit_cosinor_daily_activity as fit_cosinor_daily_light
from tools.light_CPD import calculate_cpd_light
from tools.llm_conversation import save_analysis, continue_conversation
from tools.settings import get_settings
from tools.app_logging import log_event
from services.analysis_service import data_quality_report
from services.report_service import build_comparison, persist_report_json
from services.ai_pipeline_service import run_ai_pipeline


AI_ANALYSIS_DIRNAME = "ai_analyses"


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _safe_filename_part(value: str) -> str:
    if value is None:
        return "unknown"
    value = str(value).strip()
    if not value:
        return "unknown"
    return "".join(ch if ch.isalnum() or ch in ("-", "_", ".") else "_" for ch in value)


def _save_ai_analysis_snapshot(
    *,
    analysis_text: str,
    username: str,
    period_id_1: str,
    period_id_2: str,
    model: str,
    json_filepath: str,
    anamnesis: str = "",
) -> dict:
    base_dir = os.path.join(os.getcwd(), AI_ANALYSIS_DIRNAME)
    _ensure_dir(base_dir)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = (
        f"{_safe_filename_part(username)}_"
        f"{_safe_filename_part(period_id_1)}_vs_{_safe_filename_part(period_id_2)}_"
        f"{_safe_filename_part(model)}_{timestamp}"
    )

    txt_relpath = os.path.join(AI_ANALYSIS_DIRNAME, f"{base_name}.txt")
    meta_relpath = os.path.join(AI_ANALYSIS_DIRNAME, f"{base_name}.meta.json")

    txt_abspath = save_analysis(analysis_text, filename=txt_relpath)
    meta_abspath = os.path.join(os.getcwd(), meta_relpath)
    meta = {
        "username": username,
        "period_id_1": period_id_1,
        "period_id_2": period_id_2,
        "model": model,
        "json_filepath": json_filepath,
        "anamnesis": anamnesis,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "analysis_txt": txt_abspath,
    }
    with open(meta_abspath, "w") as f:
        json.dump(meta, f, indent=2)

    return meta


def _load_previous_ai_analyses_for_user(username: str) -> list[dict]:
    base_dir = os.path.join(os.getcwd(), AI_ANALYSIS_DIRNAME)
    if not os.path.isdir(base_dir):
        return []

    entries: list[dict] = []
    for name in sorted(os.listdir(base_dir), reverse=True):
        if not name.endswith(".meta.json"):
            continue
        path = os.path.join(base_dir, name)
        try:
            with open(path, "r") as f:
                meta = json.load(f)
            if meta.get("username") != username:
                continue
            entries.append(meta)
        except Exception:
            # Skip malformed metadata
            continue

    def _sort_key(m: dict) -> str:
        return str(m.get("created_at") or "")

    entries.sort(key=_sort_key, reverse=True)
    return entries

def check_login(db: ActigraphDB, username: str, password: str) -> bool:
    return db.verify_user_password(username=username, password=password)


def _is_session_expired(settings) -> bool:
    last_activity = st.session_state.get("last_activity_at")
    if not last_activity:
        return False
    return datetime.now() - last_activity > timedelta(minutes=settings.session_timeout_minutes)

def main():
    settings = get_settings()
    db = ActigraphDB(db_path=settings.db_path)

    # Initialize session state if not already done
    if 'logged_in' not in st.session_state:
        st.session_state['logged_in'] = False
        st.session_state['username'] = ''
        st.session_state['last_activity_at'] = datetime.now()

    if st.session_state.get("logged_in") and _is_session_expired(settings):
        user = st.session_state.get("username", "")
        st.session_state['logged_in'] = False
        st.session_state['username'] = ''
        st.session_state['last_activity_at'] = datetime.now()
        db.add_audit_log("session_expired", username=user, details={"timeout_minutes": settings.session_timeout_minutes})
        st.warning("Session expired due to inactivity. Please log in again.")
        st.rerun()
    
    # --- LOGIN FORM ---
    if not st.session_state['logged_in']:
        st.set_page_config(page_title="Login - Circadian Medicine App", layout="centered")
        st.title("🔐 Login to Circadian Medicine App")
        st.markdown("---")
        st.caption("Research-use only. This application is not a diagnostic medical device.")

        with st.form("login_form"):
            username = st.text_input("Username").lower()
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Login", type="primary")

            if submitted:
                locked, remain = db.is_locked_out(
                    username=username,
                    max_attempts=settings.max_login_attempts,
                    window_minutes=settings.login_window_minutes,
                    lockout_minutes=settings.lockout_minutes,
                )
                if locked:
                    st.error(f"Too many failed attempts. Try again in {max(1, remain // 60)} minute(s).")
                    db.add_audit_log("login_blocked", username=username, details={"remaining_seconds": remain})
                    return

                if check_login(db, username, password):
                    st.session_state['logged_in'] = True
                    st.session_state['username'] = username
                    st.session_state['last_activity_at'] = datetime.now()
                    db.record_login_attempt(username, True)
                    db.add_audit_log("login_success", username=username)
                    log_event("login_success", username=username)
                    st.rerun()  # Rerun the script to show the main app
                else:
                    db.record_login_attempt(username, False)
                    db.add_audit_log("login_failed", username=username)
                    log_event("login_failed", username=username)
                    st.error("😕 Incorrect username or password.")
        if not db.user_exists("admin"):
            st.info("No admin user found. Run: `python scripts/bootstrap_admin.py --username admin --password <strong-password>`")
        return  # Exit if not logged in
    
    # --- MAIN APPLICATION (Only accessible after login) ---
    st.set_page_config(page_title="Circadian Medicine Analysis", page_icon="🔬", layout="wide")
    st.session_state["last_activity_at"] = datetime.now()
    st.warning("Research-only / non-diagnostic output. Clinical decisions require licensed medical judgment.")
    
    # Display a sidebar with user info and logout button
    with st.sidebar:
        st.success(f"Welcome, **{st.session_state['username']}**! 👋")
        if st.button("Log Out", type="primary"):
            db.add_audit_log("logout", username=st.session_state.get("username", ""))
            st.session_state['logged_in'] = False
            st.session_state['username'] = ''
            st.rerun()
    
    image = 'image/Circadian Medicine.png'
    st.image(image, width='stretch')
    st.write('Welcome to Our Data Analysis App! This app allows you to upload actigraph data files, perform comprehensive analyses, and compare results between different records. Please follow the steps below to get started.')
    
    # Create tabs for different functionalities
    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 New Analysis",
        "📁 Previous Analyses",
        "⚖️ Compare Records",
        "🤖 AI Analysis",
    ])
    
    with tab1:
        st.markdown("### Workflow")
        st.progress(0.2, text="Step 1/5: Upload")
        st.caption("Wizard path: Upload → Validate → Analyze → Compare → Evidence Report")
        # Add input fields for ID, Description, and Date
        st.subheader("Analysis Information")
        
        # Create three columns for better layout
        col1, col2, col3 = st.columns(3)
        
        with col1:
            analysis_id = st.text_input("Analysis ID", placeholder="Enter unique ID for this analysis")
            if analysis_id and db.record_exists(analysis_id):
                st.error("⚠️ This ID already exists. Please choose a different ID.")
        
        with col2:
            description = st.text_input("Description", placeholder="Brief description of this analysis")
        
        with col3:
            current_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            st.text_input("Date", value=current_date, disabled=True, help="Automatically captured current date and time")
        
        # Store the values in session state for later use
        if analysis_id:
            st.session_state.analysis_id = analysis_id
        if description:
            st.session_state.description = description
        st.session_state.current_date = current_date
        
        st.divider()  # Add a visual separator
        
        df = st.file_uploader("Upload a file")
    if df is not None:
        # Process the uploaded file
        data = upload_file(df)
        if data is not None:
            st.progress(0.4, text="Step 2/5: Validate")
            dq = data_quality_report(data)
            with st.expander("Data quality check", expanded=True):
                st.write(f"Date coverage (days): **{dq['date_coverage_days']}**")
                st.write(f"Timezone present: **{dq['timezone_present']}**")
                st.write(f"Median sampling interval (minutes): **{dq['sampling_minutes_median']}**")
                if dq["missing_columns"]:
                    st.error(f"Missing expected columns: {', '.join(dq['missing_columns'])}")
                elif dq["ok"]:
                    st.success("Data quality checks passed.")

            # Get available dates from the data
            available_dates = get_available_dates(data)
 # Block for date selection and analysis         
            if available_dates:
                st.subheader("Date Selection")
                st.write(f"Data available for {len(available_dates)} dates: {', '.join(available_dates)}")
                
                # Add date selection widget
                selected_dates = st.multiselect(
                    "Select dates to analyze:",
                    options=available_dates,
                    default=available_dates,  # Select all dates by default
                    help="Choose one or more dates to include in the analysis"
                )
                
                # Add submit button
                submit_button = st.button("Run Analysis", type="primary")
                
                if selected_dates and submit_button:
                    run_id = uuid.uuid4().hex[:12]
                    # Validate required fields
                    if not analysis_id or not description:
                        st.error("❌ Please provide both Analysis ID and Description before running analysis.")
                        st.stop()
                    
                    if db.record_exists(analysis_id):
                        st.error("❌ This Analysis ID already exists. Please choose a different ID.")
                        st.stop()
                    
                    # Save analysis record to database
                    file_name = df.name if hasattr(df, 'name') else 'uploaded_file'
                    success = db.save_analysis_record(
                        analysis_id=analysis_id,
                        description=description,
                        date=current_date,
                        file_name=file_name,
                        selected_dates=selected_dates
                    )
                    
                    if not success:
                        st.error("❌ Failed to save analysis record to database.")
                        st.stop()
                    
                    st.success(f"✅ Analysis record '{analysis_id}' saved to database.")
                    db.add_audit_log(
                        "new_analysis_started",
                        username=st.session_state.get("username", ""),
                        run_id=run_id,
                        details={"analysis_id": analysis_id, "selected_dates": selected_dates},
                    )
                    
                    # Filter data by selected dates
                    filtered_data = filter_data_by_dates(data, selected_dates)
                    
                    st.subheader(f"Analysis for {len(selected_dates)} selected date(s)")
                    
                    # Generate plots and analysis for filtered data
                    fig_activity = activity_plotter(filtered_data)
                    fig_light = light_plotter(filtered_data)
                    st.pyplot(fig_activity)
                    st.pyplot(fig_light)
                    
                    # Get analysis results
                    sleep_light_exposure_results = analyze_sleep_light_exposure(filtered_data)
                    
                    # Save sleep light exposure results to database
                    db.save_sleep_analysis(analysis_id, "sleep_light_exposure", sleep_light_exposure_results)
                    
                    # Display results in a nicely formatted way
                    st.subheader("Sleep and Light Exposure Analysis")
                    
                    st.write("**Metric 1: Minutes of light exposure (MELANOPIC EDI > 1 lux) during sleep by date:**")
                    if isinstance(sleep_light_exposure_results['metric1'], str):
                        st.write(sleep_light_exposure_results['metric1'])
                    else:
                        st.dataframe(sleep_light_exposure_results['metric1'])
                    
                    st.write("**Metric 2: Minutes of bright light (MELANOPIC EDI > 10 lux) in the 3 hours before sleep by date:**")
                    if isinstance(sleep_light_exposure_results['metric2'], str):
                        st.write(sleep_light_exposure_results['metric2'])
                    else:
                        st.dataframe(sleep_light_exposure_results['metric2'])
                    
                    st.write("**Metric 3: Minutes of non-bright light (MELANOPIC EDI < 250 lux) in the 3 hours after waking up by date:**")
                    if isinstance(sleep_light_exposure_results['metric3'], str):
                        st.write(sleep_light_exposure_results['metric3'])
                    else:
                        st.dataframe(sleep_light_exposure_results['metric3'])

                    st.subheader("Derived metrics - sleep periods, CPD of mid sleep, SRI")
                    # Sleep periods analysis
                    sleep_periods_results = analyze_sleep_periods(filtered_data)
                    db.save_sleep_analysis(analysis_id, "sleep_periods", sleep_periods_results)
                    
                    st.write("**Sleep Periods Analysis: plus sleep onset and offset**")
                    if isinstance(sleep_periods_results, str):
                        st.write(sleep_periods_results)
                    else:
                        st.dataframe(sleep_periods_results)
                    
                    # Calculate CPD
                    try:
                        mid_sleep_data = build_centered_midpoint_hours(sleep_periods_results)
                        cpd_mid_sleep_results = calculate_single_person_cpd(mid_sleep_data, date_col="mid_sleep_DATE", midpoint_col="midpoint_hours_centered")
                        db.save_sleep_analysis(analysis_id, "cpd_mid_sleep", cpd_mid_sleep_results)
                        st.write("**Circadian Phase Dispersion (CPD) Analysis:**")
                        st.dataframe(cpd_mid_sleep_results[['mid_sleep_DATE', 'Mid_sleep_Time', 'cpd_hours', 'mean_midpoint_hours', 'median_midpoint_hours']])
                    except Exception as e:
                        st.write(f"Error calculating CPD: {e}")
                    
                    # Calculate SRI
                    try:
                        sri_sleep_results = calculate_sri_from_pimn(
                            filtered_data,  # Use filtered_data instead of data
                            timestamp_col='DATE/TIME',
                            pimn_col='PIMn',
                            window_days=2,
                            slide_interval=1,
                            rolling_window=100,
                            sleep_threshold=6,
                            local_tz="Europe/Berlin"
                        )
                        db.save_sleep_analysis(analysis_id, "sri_sleep", sri_sleep_results)
                        st.write("**Sleep Regularity Index (SRI) Analysis:**")
                        if len(sri_sleep_results) > 0:
                            st.dataframe(sri_sleep_results)
                        else:
                            st.write("No SRI results available - insufficient data for analysis (need at least 2 days).")
                    except Exception as e:
                        st.write(f"Error calculating SRI: {e}")

                    st.subheader("Activity derived metrics: L5, M10, RA, IS, IV, Cosinor fit")
                    # Calculate rolling 2-day IS and IV
                    try:
                        activity_is_iv_results = compute_rolling_2day_is_iv_activity(
                            filtered_data,
                            time_col="DATE/TIME",
                            value_col="PIMn",
                            anchor_hour=12
                        )
                        db.save_activity_analysis(analysis_id, "activity_is_iv", activity_is_iv_results)
                        st.write("**Rolling 2-Day Interdaily Stability (IS) and Intradaily Variability (IV) Analysis:**")
                        if len(activity_is_iv_results) > 0:
                            st.dataframe(activity_is_iv_results)
                        else:
                            st.write("No IS/IV results available - insufficient data for analysis (need at least 2 days).")
                    except Exception as e:
                        st.write(f"Error calculating IS/IV: {e}")
                    # Note: L5, M10, RA calculations can be added similarly if needed
                    try:
                        activity_l5_m10_ra_results = compute_daily_L5_M10_RA_activity(
                            filtered_data,
                            time_col="DATE/TIME",
                            value_col="PIMn",
                            anchor_hour=12
                        )
                        db.save_activity_analysis(analysis_id, "activity_l5_m10_ra", activity_l5_m10_ra_results)
                        st.write("**Daily L5, M10, and Relative Amplitude (RA) Analysis:**")
                        if len(activity_l5_m10_ra_results) > 0:
                            st.dataframe(activity_l5_m10_ra_results)
                        else:
                            st.write("No L5/M10/RA results available - insufficient data for analysis.")
                    except Exception as e:
                        st.write(f"Error calculating L5/M10/RA: {e}")
                    # Cosinor fit analysis and CPD of activity acrophase
                    st.write("**Cosinor Fit Analysis:**")
                    try:
                        activity_cosinor_results = fit_cosinor_daily_activity(
                            filtered_data,
                            datetime_col='DATE/TIME',
                            value_col='PIMn'
                        )
                        db.save_activity_analysis(analysis_id, "activity_cosinor", activity_cosinor_results)
                        st.write("**Daily Cosinor Fit Analysis:**")
                        if len(activity_cosinor_results) > 0:
                            st.dataframe(activity_cosinor_results)
                        else:
                            st.write("No Cosinor fit results available - insufficient data for analysis.")
                    except Exception as e:
                        st.write(f"Error calculating Cosinor fit: {e}")
                    # CPD of activity acrophase
                    try:
                        cpd_activity_acrophase_results = calculate_cpd_activity(
                            activity_cosinor_results,
                            ms_col="acrophase_hours",
                            date_col="date"
                        )
                        db.save_activity_analysis(analysis_id, "cpd_activity_acrophase", cpd_activity_acrophase_results)
                        st.write("**Composite Phase Deviation (CPD) of Activity Acrophase Analysis:**")
                        if len(cpd_activity_acrophase_results) > 0:
                            st.dataframe(cpd_activity_acrophase_results[['date', 'cpd_hours', 'deviation_from_mean_hours', 'deviation_from_prev_hours']])
                        else:
                            st.write("No CPD activity results available - insufficient data for analysis.")
                    except Exception as e:
                        st.write(f"Error calculating CPD of activity acrophase: {e}")
                    # light analysis
                    st.subheader("Light derived metrics: L5, M10, RA, IS, IV, Cosinor fit")
                    
                    # IS & IV for light
                    try:
                        light_is_iv_results = compute_rolling_2day_is_iv_light(
                            filtered_data,
                            time_col="DATE/TIME",
                            value_col="MELANOPIC EDI",
                            anchor_hour=12
                        )
                        db.save_light_analysis(analysis_id, "light_is_iv", light_is_iv_results)
                        st.write("**Rolling 2-Day Interdaily Stability (IS) and Intradaily Variability (IV) for Light:**")
                        if len(light_is_iv_results) > 0:
                            st.dataframe(light_is_iv_results)
                        else:
                            st.write("No light IS/IV results available - insufficient data for analysis (need at least 2 days).")
                    except Exception as e:
                        st.write(f"Error calculating light IS/IV: {e}")
                    
                    # L5 & M10 & RA for light
                    try:
                        light_l5_m10_ra_results = compute_daily_L5_M10_RA_light(
                            filtered_data,
                            time_col="DATE/TIME",
                            value_col="MELANOPIC EDI",
                            anchor_hour=12
                        )
                        db.save_light_analysis(analysis_id, "light_l5_m10_ra", light_l5_m10_ra_results)
                        st.write("**Daily L5, M10, and Relative Amplitude (RA) for Light:**")
                        if len(light_l5_m10_ra_results) > 0:
                            st.dataframe(light_l5_m10_ra_results)
                        else:
                            st.write("No light L5/M10/RA results available - insufficient data for analysis.")
                    except Exception as e:
                        st.write(f"Error calculating light L5/M10/RA: {e}")
                    
                    # Cosinor fit for light
                    try:
                        light_cosinor_results = fit_cosinor_daily_light(
                            filtered_data,
                            datetime_col='DATE/TIME',
                            value_col='MELANOPIC EDI'
                        )
                        db.save_light_analysis(analysis_id, "light_cosinor", light_cosinor_results)
                        st.write("**Daily Cosinor Fit Analysis for Light:**")
                        if len(light_cosinor_results) > 0:
                            st.dataframe(light_cosinor_results)
                        else:
                            st.write("No light Cosinor fit results available - insufficient data for analysis.")
                    except Exception as e:
                        st.write(f"Error calculating light Cosinor fit: {e}")
                    
                    # CPD of light acrophase
                    try:
                        cpd_light_acrophase_results = calculate_cpd_light(
                            light_cosinor_results,
                            ms_col="acrophase_hours",
                            date_col="date"
                        )
                        db.save_light_analysis(analysis_id, "cpd_light_acrophase", cpd_light_acrophase_results)
                        st.write("**Composite Phase Deviation (CPD) of Light Acrophase Analysis:**")
                        if len(cpd_light_acrophase_results) > 0:
                            st.dataframe(cpd_light_acrophase_results[['date', 'cpd_hours', 'deviation_from_mean_hours', 'deviation_from_prev_hours']])
                        else:
                            st.write("No CPD light results available - insufficient data for analysis.")
                    except Exception as e:
                        st.write(f"Error calculating CPD of light acrophase: {e}")
                    
                    # Analysis completion message
                    st.success(f"🎉 Analysis completed successfully! All results have been saved to database with ID: {analysis_id}")
                    db.add_audit_log(
                        "new_analysis_completed",
                        username=st.session_state.get("username", ""),
                        run_id=run_id,
                        details={"analysis_id": analysis_id},
                    )
# End of analysis block
                elif selected_dates and not submit_button:
                    st.info("Click 'Run Analysis' to start the analysis with your selected dates.")
                elif not selected_dates:
                    st.warning("Please select at least one date to analyze.")
            else:
                st.error("No dates found in the uploaded data.")
        else:
            st.write("No data to display.")
    else:
        st.info("Please upload a file to begin analysis.")
    
    with tab3:
        st.subheader("⚖️ Compare Two Analysis Records")
        
        records = db.get_all_records()
        record_ids = [record['id'] for record in records]
        
        col1, col2 = st.columns(2)
        with col1:
            id1 = st.selectbox("Select first record ID", options=record_ids, key="id1")
        with col2:
            id2 = st.selectbox("Select second record ID", options=record_ids, key="id2")
            
        if st.button("Compare Records", type="primary"):
            if id1 and id2:
                if id1 == id2:
                    st.error("Please select two different records to compare.")
                else:
                    with st.spinner("Generating comparison report..."):
                        run_id = uuid.uuid4().hex[:12]
                        report_html, _, _ = build_comparison([id1, id2])
                        db.add_audit_log(
                            "comparison_report_generated",
                            username=st.session_state.get("username", ""),
                            run_id=run_id,
                            details={"id1": id1, "id2": id2},
                        )
                        if report_html:
                            components.html(report_html, height=800, scrolling=True)
                        else:
                            st.error("Could not generate comparison report.")
            else:
                st.warning("Please select two records to compare.")
    
    with tab2:
        st.subheader("📁 Previous Analyses")
        st.write("Select an Analysis ID to view saved results from the database (no new analysis is run).")

        records = db.get_all_records()
        record_ids = [record['id'] for record in records]
        if not record_ids:
            st.info("No analysis records found yet. Run a New Analysis first.")
        else:
            selected_id = st.selectbox("Select analysis ID", options=record_ids, key="previous_analysis_id")
            selected_id_str = str(selected_id) if selected_id is not None else ""

            record = db.get_record_by_id(selected_id_str) if selected_id_str else None
            if not record:
                st.error("Could not load this record from the database.")
            else:
                st.markdown("### 📌 Record Details")
                c1, c2, c3 = st.columns(3)
                with c1:
                    st.write(f"**ID:** {record.get('id', 'Unknown')}")
                    st.write(f"**Description:** {record.get('description', 'Unknown')}")
                with c2:
                    st.write(f"**Created:** {record.get('created_at', 'Unknown')}")
                    st.write(f"**Date:** {record.get('date', 'Unknown')}")
                with c3:
                    st.write(f"**File:** {record.get('file_name', 'Unknown')}")

                selected_dates_raw = record.get("selected_dates")
                try:
                    selected_dates = json.loads(selected_dates_raw) if selected_dates_raw else None
                except Exception:
                    selected_dates = None
                if selected_dates:
                    st.write(f"**Selected dates:** {', '.join(map(str, selected_dates))}")

                st.divider()

                def _show_df(table_name: str, analysis_type: str, title: str, preferred_cols: list[str] | None = None):
                    st.subheader(title)
                    df_res = db.get_analysis_results_as_dataframe(selected_id_str, table_name, analysis_type)
                    if df_res is None or df_res.empty:
                        st.write("No saved results found.")
                        return

                    if preferred_cols:
                        cols = [c for c in preferred_cols if c in df_res.columns]
                        if cols:
                            st.dataframe(df_res[cols])
                            return
                    st.dataframe(df_res)

                # Sleep + light exposure (special-case payload)
                st.subheader("Sleep and Light Exposure Analysis")
                sleep_rows = db.get_analysis_results(selected_id_str, "sleep_analysis")
                sle = next((r for r in sleep_rows if r.get("analysis_type") == "sleep_light_exposure"), None)
                if not sle:
                    st.write("No saved sleep/light exposure results found.")
                else:
                    payload = sle.get("results")
                    if isinstance(payload, dict):
                        for key, label in [
                            ("metric1", "Minutes of light exposure (> 1 lux) during sleep by date"),
                            ("metric2", "Minutes of bright light (> 10 lux) in the 3 hours before sleep by date"),
                            ("metric3", "Minutes of non-bright light (< 250 lux) in the 3 hours after waking by date"),
                        ]:
                            st.write(f"**{label}:**")
                            val = payload.get(key)
                            if isinstance(val, list):
                                st.dataframe(pd.DataFrame(val))
                            else:
                                st.write(val if val is not None else "Unknown")
                    else:
                        st.write(payload)

                _show_df("sleep_analysis", "sleep_periods", "Sleep Periods Analysis")
                _show_df(
                    "sleep_analysis",
                    "cpd_mid_sleep",
                    "Circadian Phase Dispersion (CPD) of Mid-Sleep",
                    preferred_cols=[
                        "mid_sleep_DATE",
                        "Mid_sleep_Time",
                        "cpd_hours",
                        "mean_midpoint_hours",
                        "median_midpoint_hours",
                    ],
                )
                _show_df("sleep_analysis", "sri_sleep", "Sleep Regularity Index (SRI)")

                st.divider()

                _show_df("activity_analysis", "activity_is_iv", "Activity: Interdaily Stability (IS) and Intradaily Variability (IV)")
                _show_df("activity_analysis", "activity_l5_m10_ra", "Activity: L5, M10, and Relative Amplitude (RA)")
                _show_df("activity_analysis", "activity_cosinor", "Activity: Daily Cosinor Fit")
                _show_df(
                    "activity_analysis",
                    "cpd_activity_acrophase",
                    "Activity: CPD of Acrophase",
                    preferred_cols=["date", "cpd_hours", "deviation_from_mean_hours", "deviation_from_prev_hours"],
                )

                st.divider()

                _show_df("light_analysis", "light_is_iv", "Light: Interdaily Stability (IS) and Intradaily Variability (IV)")
                _show_df("light_analysis", "light_l5_m10_ra", "Light: L5, M10, and Relative Amplitude (RA)")
                _show_df("light_analysis", "light_cosinor", "Light: Daily Cosinor Fit")
                _show_df(
                    "light_analysis",
                    "cpd_light_acrophase",
                    "Light: CPD of Acrophase",
                    preferred_cols=["date", "cpd_hours", "deviation_from_mean_hours", "deviation_from_prev_hours"],
                )

    with tab4:
        st.subheader("🤖 AI-Powered Report Analysis")
        st.write("Generate an intelligent analysis of your circadian data comparing two periods using advanced language models.")
        
        records = db.get_all_records()
        record_ids = [record['id'] for record in records]
        
        col1, col2 = st.columns(2)
        with col1:
            ai_id1 = st.selectbox("Select first period ID", options=record_ids, key="ai_id1")
        with col2:
            ai_id2 = st.selectbox("Select second period ID", options=record_ids, key="ai_id2")
        
        # Model selection
        model_option = st.selectbox(
            "Select LLM Model",
            options=settings.allowed_models,
            help="Choose the Ollama model for analysis"
        )

        # Audience selector
        audience_map = {
            "General User (plain language, action plan)": "layperson",
            "Medical Doctor (clinical language, risk factors)": "doctor",
            "Circadian Expert (technical, IS/IV/CPD/cosinor)": "expert",
        }
        audience_label = st.radio(
            "Who is reading this report?",
            options=list(audience_map.keys()),
            horizontal=True,
            help="Adjusts the language and depth of the final AI report",
        )
        audience_key = audience_map[audience_label]

        # Check if this exact AI context already exists in DB (same periods + model + audience)
        existing_ai_run = None
        if ai_id1 and ai_id2 and ai_id1 != ai_id2:
            existing_ai_run = db.get_ai_analysis_run(
                username=st.session_state.get("username") or "unknown",
                period_id_1=ai_id1,
                period_id_2=ai_id2,
                model=model_option,
                audience=audience_key,
            )

        # Anamnesis input — visible for Doctor and Expert audiences
        if audience_key in ("doctor", "expert"):
            st.markdown("**Patient Anamnesis** *(optional — symptoms, relevant history)*")
            if existing_ai_run and existing_ai_run.get("anamnesis"):
                _prefill_anamnesis = existing_ai_run.get("anamnesis")
            else:
                _prefill_anamnesis = db.get_anamnesis(ai_id1) if ai_id1 else ""
            anamnesis_text = st.text_area(
                "Enter patient anamnesis",
                value=_prefill_anamnesis,
                height=120,
                placeholder="e.g. Patient reports fatigue, difficulty waking up, mood changes in the afternoon, reduced concentration...",
                label_visibility="collapsed",
            )
        else:
            anamnesis_text = ""
        
        # Initialize session state for chat
        if 'chat_messages' not in st.session_state:
            st.session_state.chat_messages = []
        if 'json_filepath' not in st.session_state:
            st.session_state.json_filepath = None
        if 'current_analysis_ids' not in st.session_state:
            st.session_state.current_analysis_ids = None
        if 'current_model' not in st.session_state:
            st.session_state.current_model = None
        if 'current_audience' not in st.session_state:
            st.session_state.current_audience = "layperson"
        if 'pipeline_intermediates' not in st.session_state:
            st.session_state.pipeline_intermediates = None
        if 'current_anamnesis' not in st.session_state:
            st.session_state.current_anamnesis = ""

        def _apply_saved_ai_run_to_session(saved_run: dict) -> None:
            st.session_state.current_analysis_ids = (
                saved_run.get("period_id_1"),
                saved_run.get("period_id_2"),
            )
            st.session_state.current_model = saved_run.get("model")
            st.session_state.current_audience = saved_run.get("audience") or "layperson"
            st.session_state.current_anamnesis = saved_run.get("anamnesis", "") or ""
            st.session_state.json_filepath = saved_run.get("json_filepath")

            final_result = saved_run.get("final_result") or ""
            st.session_state.chat_messages = (
                [{"role": "assistant", "content": final_result}] if final_result else []
            )

            pipeline_outputs = saved_run.get("pipeline_outputs")
            if isinstance(pipeline_outputs, dict):
                st.session_state.pipeline_intermediates = {
                    "data_summary": pipeline_outputs.get("data_summary", ""),
                    "search_queries": pipeline_outputs.get("search_queries", []),
                    "raw_abstracts": pipeline_outputs.get("raw_abstracts", ""),
                    "evidence_items": pipeline_outputs.get("evidence_items", []),
                    "lit_summary": pipeline_outputs.get("lit_summary", ""),
                    "symptom_metric_table": pipeline_outputs.get("symptom_metric_table", ""),
                    "claim_to_pmid_map": pipeline_outputs.get("claim_to_pmid_map", {}),
                }
            else:
                st.session_state.pipeline_intermediates = None

        current_user = st.session_state.get("username") or "unknown"
        cached_pair_runs = []
        if ai_id1 and ai_id2 and ai_id1 != ai_id2:
            cached_pair_runs = db.get_ai_analysis_runs_for_pair(
                username=current_user,
                period_id_1=ai_id1,
                period_id_2=ai_id2,
                include_reversed=True,
            )

        if cached_pair_runs:
            st.markdown("**Saved analyses for this period pair**")
            selected_cached_index = st.selectbox(
                "Choose a saved run",
                options=list(range(len(cached_pair_runs))),
                format_func=lambda i: (
                    f"{cached_pair_runs[i].get('period_id_1')} vs {cached_pair_runs[i].get('period_id_2')}"
                    f"  |  model={cached_pair_runs[i].get('model')}"
                    f"  |  audience={cached_pair_runs[i].get('audience')}"
                    f"  |  updated={cached_pair_runs[i].get('updated_at') or cached_pair_runs[i].get('created_at') or 'unknown'}"
                ),
                key="cached_pair_runs_select",
            )
            if st.button("📂 Load Selected Saved Run", type="secondary"):
                selected_run = cached_pair_runs[selected_cached_index]
                _apply_saved_ai_run_to_session(selected_run)
                st.success("✅ Loaded selected saved AI analysis from database.")
                st.rerun()

        st.caption(
            "Use 'Load Selected Saved Run' to avoid LLM cost. "
            "'Generate AI Analysis' always runs a new analysis and overwrites the saved entry for the same IDs + model + audience."
        )

        if existing_ai_run:
            last_updated = existing_ai_run.get("updated_at") or existing_ai_run.get("created_at") or "unknown"
            st.info(f"💾 Saved AI analysis found for this selection (last update: {last_updated}).")
            st.warning("ℹ️ Generating now will overwrite this saved result for the same IDs + model + audience.")
        
        if st.button("🧠 Generate AI Analysis", type="primary"):
            if ai_id1 and ai_id2:
                if ai_id1 == ai_id2:
                    st.error("Please select two different periods to compare.")
                else:
                    try:
                        # Keep anamnesis context consistent with DB overwrite rules:
                        # if user leaves it blank during rerun, retain previously saved text.
                        effective_anamnesis = anamnesis_text.strip()
                        if not effective_anamnesis and existing_ai_run:
                            effective_anamnesis = (existing_ai_run.get("anamnesis") or "").strip()

                        # Reset chat when generating new analysis
                        st.session_state.chat_messages = []
                        st.session_state.current_analysis_ids = (ai_id1, ai_id2)
                        st.session_state.current_model = model_option
                        st.session_state.current_anamnesis = effective_anamnesis

                        # Save anamnesis to DB for both records before running pipeline
                        if effective_anamnesis:
                            db.save_anamnesis(ai_id1, effective_anamnesis)
                            db.save_anamnesis(ai_id2, effective_anamnesis)
                        
                        # Step 1: Generate report data
                        with st.spinner("⏳ Generating report data..."):
                            report_html, df_combined, json_data = build_comparison([ai_id1, ai_id2])
                            
                            if isinstance(report_html, str) and "No data found" in report_html:
                                st.error(report_html)
                            elif json_data is not None:
                                # Step 2: Save JSON
                                json_filepath = persist_report_json(json_data)
                                st.session_state.json_filepath = json_filepath
                                st.success(f"✅ Report data generated and saved to {os.path.basename(json_filepath)}")

                                # Step 3: Run 5-agent pipeline
                                pipeline_status = st.empty()
                                def _pipeline_progress(msg: str):
                                    pipeline_status.info(msg)

                                agent_count = "6" if effective_anamnesis else "5"
                                with st.spinner(f"🤖 Running {agent_count}-agent AI pipeline (2–5 min)..."):
                                    run_id, results = run_ai_pipeline(
                                        json_filepath=json_filepath,
                                        model=model_option,
                                        audience=audience_key,
                                        anamnesis=effective_anamnesis,
                                        progress_callback=_pipeline_progress,
                                    )
                                db.add_audit_log(
                                    "ai_report_generation_attempt",
                                    username=st.session_state.get("username", ""),
                                    run_id=run_id,
                                    details={
                                        "period_1": ai_id1,
                                        "period_2": ai_id2,
                                        "model": model_option,
                                        "audience": audience_key,
                                    },
                                )

                                pipeline_status.empty()

                                analysis = results.get("final_report", "")
                                if "error" in results:
                                    st.warning(f"Pipeline used fallback mode: {results['error']}")

                                # Store intermediates in session state for collapsible display
                                st.session_state.pipeline_intermediates = {
                                    "data_summary":         results.get("data_summary", ""),
                                    "search_queries":       results.get("search_queries", []),
                                    "raw_abstracts":        results.get("raw_abstracts", ""),
                                    "evidence_items":       results.get("evidence_items", []),
                                    "lit_summary":          results.get("lit_summary", ""),
                                    "symptom_metric_table": results.get("symptom_metric_table", ""),
                                    "claim_to_pmid_map":    results.get("claim_to_pmid_map", {}),
                                }

                                if analysis and not analysis.startswith("Error"):
                                    db.add_audit_log(
                                        "ai_report_generated",
                                        username=st.session_state.get("username", ""),
                                        run_id=run_id,
                                        details={
                                            "period_1": ai_id1,
                                            "period_2": ai_id2,
                                            "model": model_option,
                                            "audience": audience_key,
                                            "fallback_used": "error" in results,
                                        },
                                    )
                                    # Persist full AI run to DB (JSON input, all agent outputs, and final report).
                                    save_ok = db.save_ai_analysis_run(
                                        username=st.session_state.get("username") or "unknown",
                                        period_id_1=ai_id1,
                                        period_id_2=ai_id2,
                                        model=model_option,
                                        audience=audience_key,
                                        anamnesis=effective_anamnesis,
                                        json_filepath=json_filepath,
                                        json_input=json_data,
                                        pipeline_outputs=results,
                                        final_result=analysis,
                                        agent_trace=results.get("agent_trace") if isinstance(results, dict) else None,
                                        schema_version="v2",
                                    )
                                    if not save_ok:
                                        st.warning("⚠️ Could not save AI pipeline details to database.")
                                    elif existing_ai_run:
                                        st.info("♻️ Saved AI analysis was replaced for this IDs + model + audience key.")

                                    # Save analysis (persist per-user so it can be reopened later)
                                    _save_ai_analysis_snapshot(
                                        analysis_text=analysis,
                                        username=st.session_state.get("username") or "unknown",
                                        period_id_1=ai_id1,
                                        period_id_2=ai_id2,
                                        model=model_option,
                                        json_filepath=json_filepath,
                                        anamnesis=effective_anamnesis,
                                    )

                                    # Store audience for display context
                                    st.session_state.current_audience = audience_key

                                    # Add initial analysis to chat history
                                    st.session_state.chat_messages = [
                                        {"role": "assistant", "content": analysis}
                                    ]

                                    st.success("✅ AI Analysis completed!")
                                    st.rerun()  # Refresh to show chat interface
                                else:
                                    st.error(f"❌ {analysis}")
                                    st.info("💡 Make sure Ollama is running and the selected model is installed. Run `ollama pull " + model_option + "` in your terminal.")
                    
                    except Exception as e:
                        st.error(f"❌ An error occurred: {str(e)}")
                        st.info("💡 Make sure Ollama is installed and running. Visit https://ollama.ai for installation instructions.")
            else:
                st.warning("Please select two periods to compare.")
        
        # Display chat interface if analysis has been generated
        if st.session_state.chat_messages and st.session_state.json_filepath and st.session_state.current_analysis_ids:
            st.divider()
            
            # Show metadata
            st.markdown("### 📊 Analysis Context")
            col1, col2, col3 = st.columns(3)
            with col1:
                st.write(f"**Periods:** {st.session_state.current_analysis_ids[0]} vs {st.session_state.current_analysis_ids[1]}")
            with col2:
                audience_display = {
                    "layperson": "General User",
                    "doctor": "Medical Doctor",
                    "expert": "Circadian Expert",
                }.get(st.session_state.get("current_audience", "layperson"), "General User")
                st.write(f"**Model:** {st.session_state.current_model}  ·  **Audience:** {audience_display}")
            with col3:
                # Download buttons
                if st.session_state.chat_messages:
                    full_conversation = "\n\n---\n\n".join([
                        f"{'AI Assistant' if msg['role'] == 'assistant' else 'You'}: {msg['content']}"
                        for msg in st.session_state.chat_messages
                    ])
                    st.download_button(
                        label="📥 Download Chat",
                        data=full_conversation,
                        file_name=f"ai_conversation_{st.session_state.current_analysis_ids[0]}_vs_{st.session_state.current_analysis_ids[1]}.txt",
                        mime="text/plain",
                        key="download_chat"
                    )
            
            st.divider()

            # Collapsible pipeline intermediates
            if st.session_state.get("pipeline_intermediates"):
                pi = st.session_state.pipeline_intermediates
                with st.expander("🧾 Evidence Confidence Panel", expanded=True):
                    st.markdown("**Query intents (Agent 2)**")
                    for q in pi.get("search_queries", []):
                        if isinstance(q, dict):
                            st.markdown(
                                f"- topic=`{q.get('topic')}` | population=`{q.get('population')}` | context=`{q.get('context')}`"
                            )
                        else:
                            st.markdown(f"- `{q}`")
                    evidence_items = pi.get("evidence_items", [])
                    st.markdown(
                        f"**Included evidence items:** {len(evidence_items)}  \n"
                        "Filters: fielded query + humans/adults constraints + lexical rank + LLM relevance judge"
                    )
                    if evidence_items:
                        st.dataframe(pd.DataFrame(evidence_items)[["pmid", "year", "score", "query_source", "title"]])

                with st.expander("🔍 View pipeline intermediates", expanded=settings.show_raw_pipeline_traces):
                    st.markdown("**Data summary (Agent 1)**")
                    st.text(pi.get("data_summary", ""))
                    st.markdown("**PubMed abstracts retrieved (Agent 3)**")
                    st.text(pi.get("raw_abstracts", "")[:3000] + ("…" if len(pi.get("raw_abstracts", "")) > 3000 else ""))
                    st.markdown("**Literature synthesis (Agent 4)**")
                    st.text(pi.get("lit_summary", ""))
                    claim_map = pi.get("claim_to_pmid_map", {})
                    if claim_map:
                        st.markdown("**Claim to PMID map (grounding)**")
                        for claim, pmids in claim_map.items():
                            st.markdown(f"- {claim}  \n  PMIDs: {', '.join(pmids)}")
                    symptom_table = pi.get("symptom_metric_table", "")
                    if symptom_table:
                        st.markdown("**Symptom-Metric Correlation (Agent 6)**")
                        st.markdown(symptom_table)

            st.divider()

            # Chat interface
            st.markdown("### 💬 Ask Follow-up Questions")
            st.write("*Examples: What is the impact of these changes on mood? How do these patterns affect cognitive function? What about stress levels?*")

            # Display chat history
            chat_container = st.container()
            with chat_container:
                for message in st.session_state.chat_messages:
                    with st.chat_message(message["role"]):
                        st.markdown(message["content"])

            
            # Chat input
            user_question = st.chat_input("Ask a question about the analysis (e.g., 'How do these changes affect mood and psychology?')")
            
            if user_question:
                # Add user message to chat
                st.session_state.chat_messages.append({"role": "user", "content": user_question})
                
                # Display user message immediately
                with st.chat_message("user"):
                    st.markdown(user_question)
                
                # Get AI response
                with st.chat_message("assistant"):
                    with st.spinner("Thinking..."):
                        # Build conversation history for context (exclude the system message)
                        conversation_history = [
                            {"role": msg["role"], "content": msg["content"]}
                            for msg in st.session_state.chat_messages[:-1]  # Exclude the current question
                        ]
                        
                        response = continue_conversation(
                            user_question=user_question,
                            json_filepath=st.session_state.json_filepath,
                            conversation_history=conversation_history,
                            model=st.session_state.current_model or "phi4:14b",
                            anamnesis=st.session_state.get("current_anamnesis", ""),
                        )
                        
                        if not response.startswith("Error"):
                            st.markdown(response)
                            # Add assistant response to chat
                            st.session_state.chat_messages.append({"role": "assistant", "content": response})
                        else:
                            st.error(response)
            
            # Additional options
            st.divider()
            col1, col2 = st.columns(2)
            with col1:
                if st.button("🔄 Start New Analysis", type="secondary"):
                    st.session_state.chat_messages = []
                    st.session_state.json_filepath = None
                    st.session_state.current_analysis_ids = None
                    st.session_state.current_model = None
                    st.session_state.current_audience = "layperson"
                    st.session_state.pipeline_intermediates = None
                    st.rerun()
            with col2:
                if st.button("�️ Clear Chat History", type="secondary"):
                    # Keep only the initial analysis
                    if st.session_state.chat_messages:
                        st.session_state.chat_messages = [st.session_state.chat_messages[0]]
                    st.rerun()

if __name__ == "__main__":
    main()

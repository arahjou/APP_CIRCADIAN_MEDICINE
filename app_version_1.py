import streamlit as st
from datetime import datetime
import sqlite3
import os
import pandas as pd
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
def main():
    # Initialize database
    db = ActigraphDB()
    
    image = 'image/Circadian Medicine.png'
    st.image(image, width='stretch')
    st.write('I am gathering various tools and resources related to Circadian Medicine here!')
    
    # Create tabs for different functionalities
    tab1, tab2 = st.tabs(["📊 New Analysis", "📋 View Records"])
    
    with tab1:
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
    
    with tab2:
        st.subheader("📋 Analysis Records")
        
        # Get all records from database
        records = db.get_all_records()
        
        if records:
            st.write(f"Found {len(records)} analysis records:")
            
            # Display records in a nice format
            for record in records:
                with st.expander(f"🔍 {record['id']} - {record['description']}", expanded=False):
                    col1, col2, col3 = st.columns(3)
                    
                    with col1:
                        st.write(f"**ID:** {record['id']}")
                        st.write(f"**Description:** {record['description']}")
                    
                    with col2:
                        st.write(f"**Analysis Date:** {record['date']}")
                        st.write(f"**Created:** {record['created_at']}")
                    
                    with col3:
                        if record['file_name']:
                            st.write(f"**File:** {record['file_name']}")
                        if record['selected_dates']:
                            import json
                            try:
                                dates = json.loads(record['selected_dates'])
                                st.write(f"**Dates:** {', '.join(dates)}")
                            except:
                                st.write(f"**Dates:** {record['selected_dates']}")
                    
                    # Show analysis results
                    st.write("**Analysis Results:**")
                    
                    # Create columns for better layout
                    result_col1, result_col2 = st.columns([3, 1])
                    
                    with result_col1:
                        # Sleep analyses
                        sleep_results = db.get_analysis_results(record['id'], 'sleep_analysis')
                        if sleep_results:
                            st.write("🛌 **Sleep Analyses:**")
                            for result in sleep_results:
                                with st.expander(f"📊 {result['analysis_type']}", expanded=False):
                                    # Try to display as DataFrame if possible
                                    try:
                                        if isinstance(result['results'], list) and len(result['results']) > 0:
                                            df = pd.DataFrame(result['results'])
                                            st.dataframe(df, use_container_width=True)
                                        elif isinstance(result['results'], dict):
                                            if len(result['results']) > 0:
                                                df = pd.DataFrame([result['results']])
                                                st.dataframe(df, use_container_width=True)
                                            else:
                                                st.write("No data available")
                                        else:
                                            st.write(result['results'])
                                    except Exception as e:
                                        st.write(f"Raw data: {result['results']}")
                        
                        # Activity analyses
                        activity_results = db.get_analysis_results(record['id'], 'activity_analysis')
                        if activity_results:
                            st.write("🏃 **Activity Analyses:**")
                            for result in activity_results:
                                with st.expander(f"📊 {result['analysis_type']}", expanded=False):
                                    try:
                                        if isinstance(result['results'], list) and len(result['results']) > 0:
                                            df = pd.DataFrame(result['results'])
                                            st.dataframe(df, use_container_width=True)
                                        elif isinstance(result['results'], dict):
                                            if len(result['results']) > 0:
                                                df = pd.DataFrame([result['results']])
                                                st.dataframe(df, use_container_width=True)
                                            else:
                                                st.write("No data available")
                                        else:
                                            st.write(result['results'])
                                    except Exception as e:
                                        st.write(f"Raw data: {result['results']}")
                        
                        # Light analyses
                        light_results = db.get_analysis_results(record['id'], 'light_analysis')
                        if light_results:
                            st.write("💡 **Light Analyses:**")
                            for result in light_results:
                                with st.expander(f"📊 {result['analysis_type']}", expanded=False):
                                    try:
                                        if isinstance(result['results'], list) and len(result['results']) > 0:
                                            df = pd.DataFrame(result['results'])
                                            st.dataframe(df, use_container_width=True)
                                        elif isinstance(result['results'], dict):
                                            if len(result['results']) > 0:
                                                df = pd.DataFrame([result['results']])
                                                st.dataframe(df, use_container_width=True)
                                            else:
                                                st.write("No data available")
                                        else:
                                            st.write(result['results'])
                                    except Exception as e:
                                        st.write(f"Raw data: {result['results']}")
                    
                    with result_col2:
                        st.write("**Actions:**")
                        
                        # Export button
                        if st.button(f"📥 Export Results", key=f"export_{record['id']}", help="Export all analysis results to CSV files"):
                            try:
                                export_files = db.export_analysis_results(record['id'], 'csv')
                                if export_files:
                                    st.success(f"Exported {len(export_files)} analysis results!")
                                    for analysis_type, filename in export_files.items():
                                        st.write(f"📄 {filename}")
                                else:
                                    st.warning("No results to export")
                            except Exception as e:
                                st.error(f"Export failed: {e}")
                        
                        # Raw data download
                        if st.button(f"📋 View Raw JSON", key=f"raw_{record['id']}", help="View raw JSON data"):
                            all_results = {
                                'sleep': sleep_results if 'sleep_results' in locals() else [],
                                'activity': activity_results if 'activity_results' in locals() else [],
                                'light': light_results if 'light_results' in locals() else []
                            }
                            st.json(all_results)
                    
                    # Add delete button
                    if st.button(f"🗑️ Delete Record", key=f"delete_{record['id']}", type="secondary"):
                        if db.delete_record(record['id']):
                            st.success(f"Record '{record['id']}' deleted successfully!")
                            st.rerun()
                        else:
                            st.error(f"Failed to delete record '{record['id']}'")
        else:
            st.info("No analysis records found. Run some analyses to see them here!")
            st.write("💡 **Tip:** Go to the 'New Analysis' tab to create your first analysis record.")
if __name__ == "__main__":
    main()
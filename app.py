import streamlit as st
# utils
from tools.upload_file import upload_file, get_available_dates, filter_data_by_dates
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
def main():
    image = 'image/Circadian Medicine.png'
    st.image(image, width='stretch')
    st.write('I am gathering various tools and resources related to Circadian Medicine here!')
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
                    st.write("**Sleep Periods Analysis: plus sleep onset and offset**")
                    if isinstance(sleep_periods_results, str):
                        st.write(sleep_periods_results)
                    else:
                        st.dataframe(sleep_periods_results)
                    
                    # Calculate CPD
                    try:
                        mid_sleep_data = build_centered_midpoint_hours(sleep_periods_results)
                        cpd_mid_sleep_results = calculate_single_person_cpd(mid_sleep_data, date_col="mid_sleep_DATE", midpoint_col="midpoint_hours_centered")
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
                        st.write("**Composite Phase Deviation (CPD) of Activity Acrophase Analysis:**")
                        if len(cpd_activity_acrophase_results) > 0:
                            st.dataframe(cpd_activity_acrophase_results[['date', 'cpd_hours', 'deviation_from_mean_hours', 'deviation_from_prev_hours']])
                        else:
                            st.write("No CPD activity results available - insufficient data for analysis.")
                    except Exception as e:
                        st.write(f"Error calculating CPD of activity acrophase: {e}")
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


if __name__ == "__main__":
    main()
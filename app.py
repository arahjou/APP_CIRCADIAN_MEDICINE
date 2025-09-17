import streamlit as st
from upload_file import upload_file, get_available_dates, filter_data_by_dates
from plotter_activity import plotter_activity
from plotter_light import plotter_light
from analyze_sleep_light_exposure import analyze_sleep_light_exposure
from sleep_on_off_mid import analyze_sleep_periods
from CPD_mid_sleep import build_centered_midpoint_hours, calculate_single_person_cpd

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
                    fig_activity = plotter_activity(filtered_data)
                    fig_light = plotter_light(filtered_data)
                    st.pyplot(fig_activity)
                    st.pyplot(fig_light)
                    
                    # Get analysis results
                    results = analyze_sleep_light_exposure(filtered_data)
                    
                    # Display results in a nicely formatted way
                    st.subheader("Sleep and Light Exposure Analysis")
                    
                    st.write("**Metric 1: Minutes of light exposure (MELANOPIC EDI > 1 lux) during sleep by date:**")
                    if isinstance(results['metric1'], str):
                        st.write(results['metric1'])
                    else:
                        st.dataframe(results['metric1'])
                    
                    st.write("**Metric 2: Minutes of bright light (MELANOPIC EDI > 10 lux) in the 3 hours before sleep by date:**")
                    if isinstance(results['metric2'], str):
                        st.write(results['metric2'])
                    else:
                        st.dataframe(results['metric2'])
                    
                    st.write("**Metric 3: Minutes of non-bright light (MELANOPIC EDI < 250 lux) in the 3 hours after waking up by date:**")
                    if isinstance(results['metric3'], str):
                        st.write(results['metric3'])
                    else:
                        st.dataframe(results['metric3'])
                    
                    # Sleep periods analysis
                    sleep_results = analyze_sleep_periods(filtered_data)
                    st.write("**Sleep Periods Analysis:**")
                    if isinstance(sleep_results, str):
                        st.write(sleep_results)
                    else:
                        st.dataframe(sleep_results)
                    
                    # Calculate CPD
                    try:
                        mid_sleep_data = build_centered_midpoint_hours(sleep_results)
                        cpd_results = calculate_single_person_cpd(mid_sleep_data, date_col="mid_sleep_DATE", midpoint_col="midpoint_hours_centered")
                        st.write("**Circadian Phase Dispersion (CPD) Analysis:**")
                        st.dataframe(cpd_results[['mid_sleep_DATE', 'Mid_sleep_Time', 'cpd_hours', 'mean_midpoint_hours', 'median_midpoint_hours']])
                    except Exception as e:
                        st.write(f"Error calculating CPD: {e}")
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
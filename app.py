import streamlit as st
from upload_file import upload_file
from plotter_activity import plotter_activity
from plotter_light import plotter_light
from analyze_sleep_light_exposure import analyze_sleep_light_exposure
from sleep_on_off_mid import analyze_sleep_periods
from CPD_mid_sleep_empty import build_centered_midpoint_hours, calculate_single_person_cpd

def main():
    image = 'image/Circadian Medicine.png'
    st.image(image, width='stretch')
    st.write('I am gathering various tools and resources related to Circadian Medicine here!')
    df = st.file_uploader("Upload a file")
    if df is not None:
        data = upload_file(df)
        if data is not None:
            fig_activity = plotter_activity(data)
            fig_light = plotter_light(data)
            st.pyplot(fig_activity)
            st.pyplot(fig_light)
            
            # Get analysis results
            results = analyze_sleep_light_exposure(data)
            
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
            results = analyze_sleep_periods(data)
            st.write("**Sleep Periods Analysis:**")
            if isinstance(results, str):
                st.write(results)
            else:
                st.dataframe(results)
            # Calculate CPD
            try:
                mid_sleep_data = build_centered_midpoint_hours(results)
                cpd_results = calculate_single_person_cpd(mid_sleep_data, date_col="mid_sleep_DATE", midpoint_col="midpoint_hours_centered")
                st.write("**Circadian Phase Dispersion (CPD) Analysis:**")
                st.dataframe(cpd_results[['mid_sleep_DATE', 'Mid_sleep_Time', 'cpd_hours', 'mean_midpoint_hours', 'median_midpoint_hours']])
            except Exception as e:
                st.write(f"Error calculating CPD: {e}")
        else:
            st.write("No data to display.")


if __name__ == "__main__":
    main()
import streamlit as st
from upload_file import upload_file
from plotter_activity import plotter_activity
from plotter_light import plotter_light

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
        else:
            st.write("No data to display.")


if __name__ == "__main__":
    main()
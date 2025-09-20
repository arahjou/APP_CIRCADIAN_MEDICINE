import streamlit as st

# --- USER AUTHENTICATION ---

# In a real app, you'd have a database and hashed passwords
USERS = {
    "user1": "password123",
    "user2": "password456"
}

def check_login(username, password):
    """Returns True if the username and password are correct."""
    return username in USERS and USERS[username] == password

# Initialize session state if not already done
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
    st.session_state['username'] = ''

# --- LOGIN FORM ---

if not st.session_state['logged_in']:
    st.set_page_config(page_title="Login - Streamlit App", layout="centered")
    st.title("🔐 Login to Your App")
    st.markdown("---")

    with st.form("login_form"):
        username = st.text_input("Username").lower()
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login", type="primary")

        if submitted:
            if check_login(username, password):
                st.session_state['logged_in'] = True
                st.session_state['username'] = username
                st.rerun()  # Rerun the script to show the main app
            else:
                st.error("😕 Incorrect username or password.")
else:
    # --- MAIN APPLICATION ---

    # Set page config for the main app
    st.set_page_config(page_title="My Awesome App", page_icon="🚀", layout="wide")

    # Display a sidebar with a logout button
    with st.sidebar:
        st.success(f"Welcome, **{st.session_state['username']}**! 👋")
        if st.button("Log Out", type="primary"):
            st.session_state['logged_in'] = False
            st.session_state['username'] = ''
            st.rerun() # Rerun to show the login page again

    # Main content of your application
    st.title("🚀 Welcome to the Main Application!")
    st.markdown("---")
    st.header("Dashboard")
    st.write("This is the main content area. You can only see this because you are logged in.")

    # Add your Streamlit components here
    st.subheader("Sample Data")
    st.dataframe({
        'Column A': [1, 2, 3, 4, 5],
        'Column B': [10, 20, 30, 40, 50],
        'Column C': ["Apple", "Banana", "Cherry", "Dragonfruit", "Elderberry"]
    })

    st.subheader("Interactive Widget")
    color = st.color_picker('Pick a color', '#00f900')
    st.write('The current color is', color)

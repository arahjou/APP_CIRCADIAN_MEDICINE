### High-Level Overview

Your application will have three main layers:

1.  **Streamlit Frontend:** The user interface where you upload the file and see the results.
2.  **Custom Python Tools:** A set of specialized Python functions that perform the actual data analysis (loading, plotting, calculating metrics). These are your "data crunchers."
3.  **LangChain Agent:** The "brain" of the operation. It uses your local Ollama model to understand your request, decide which data tool to use, and interpret the results to give you a natural language report.



---

### Step 1: Build the User Interface with Streamlit

This is the visible part of your app. You'll create a single Python file (e.g., `app.py`). Its job is to:

* **Create a title:** "Actigraphy Analysis Expert"
* **Add a file uploader:** `st.file_uploader("Upload your ActiGraph CSV file")`
* **Add a button:** `st.button("Analyze My Data")`
* **Create empty containers:** To later display the plot, the key metrics, and the final written analysis from the agent.

---

### Step 2: Create Your Custom Data Analysis "Tools"

This is the most important part. An LLM can't directly read a CSV or run calculations. You need to write standard Python functions that the LLM can *call*. These functions are the **tools**. It's best to put these in a separate file (e.g., `analysis_tools.py`).

You will need to create a function for each distinct task:

* **Tool 1: `load_and_prepare_data(uploaded_file)`**
    * **What it does:** Takes the uploaded file from Streamlit, loads it into a Pandas DataFrame, and performs any necessary cleaning (handling missing values, setting the correct data types, etc.).
    * **Input:** The uploaded file object.
    * **Output:** A clean Pandas DataFrame.

* **Tool 2: `generate_activity_plot(dataframe)`**
    * **What it does:** Takes the DataFrame and uses a library like Matplotlib or Plotly to create a visualization of the activity data (e.g., a 24-hour wrist plot). It saves this plot as an image file (e.g., `plot.png`).
    * **Input:** A Pandas DataFrame.
    * **Output:** The filename of the saved image (e.g., `"plot.png"`).

* **Tool 3: `calculate_actigraphy_metrics(dataframe)`**
    * **What it does:** This is your core number-crunching function. It calculates the key non-parametric metrics from the data. This would include:
        * **Interdaily Stability (IS):** How regular is your activity pattern from day to day.
        * **Intradaily Variability (IV):** How fragmented is your activity within a single day (e.g., frequent transitions between rest and activity).
        * **Relative Amplitude (RA):** The relative difference between your most active 10 hours and least active 5 hours.
        * Other metrics like your "circadian degree of alignment."
    * **Input:** A Pandas DataFrame.
    * **Output:** A Python dictionary containing the results, like `{'interdaily_stability': 0.65, 'intradaily_variability': 0.8, ...}`.

---

### Step 3: Build the LangChain Agent

Now you wire everything together. Inside your Streamlit app's logic (when the "Analyze" button is clicked), you will define and run your agent.

1.  **Initialize the LLM:** Tell LangChain to use your local Ollama model as the "brain."

2.  **Define the Toolbox:** You'll convert the Python functions you wrote in Step 2 into a format LangChain understands as `Tool` objects. You'll also likely want to add a pre-built tool for general knowledge.
    * `load_data_tool`
    * `plot_activity_tool`
    * `calculate_metrics_tool`
    * `web_search_tool` (To find what "good" or "bad" scores are based on scientific literature).

3.  **Create the Agent Executor:** You combine the LLM and the list of tools to create the agent. You'll also give it a master prompt or instruction that tells it its purpose:
    > "You are an expert in analyzing actigraphy data. Your goal is to analyze the user's provided CSV file. You must first load the data, then calculate the key metrics and create a plot. After getting the numerical results, you must search the web to find the typical ranges for these metrics in healthy adults. Finally, you must synthesize all this information into a comprehensive, easy-to-understand report for the user, explaining their results and what they mean."

### The Full Workflow in Action

When the user clicks "Analyze":

1.  The Streamlit app calls the **LangChain Agent** with the main goal.
2.  The **Agent's Brain (Ollama)** thinks: "To achieve this goal, my first step is to load the data." It decides to use the `load_data_tool`.
3.  **LangChain executes** your `load_and_prepare_data` function. The resulting DataFrame is passed back to the agent.
4.  The **Brain** thinks: "Great, I have the data. Now I need the metrics and the plot." It decides to call the `calculate_metrics_tool` and `generate_activity_plot` tools.
5.  **LangChain executes** these functions. The agent now has the numerical results (e.g., `IS = 0.65`) and the plot's filename.
6.  The **Brain** thinks: "The user's IS is 0.65. Is that good? I need context." It decides to use the `web_search_tool` with a query like "typical Interdaily Stability value actigraphy".
7.  **LangChain executes** the search. The results (e.g., "Healthy adults typically have an IS > 0.7...") are passed back.
8.  Finally, the **Brain** has everything it needs. It formulates the final, detailed report, combining the user's specific numbers with the general knowledge from the web search.
9.  The Streamlit app receives this final text report and the plot image from the agent and displays them to the user.

# gemma3:12b
# qwen3:8b
# llama3.2
# phi4:14b
import json
import os

def llm_conversation(abstract, content):
    import ollama
    try:
        response = ollama.chat(
            model="phi4:14b",
            messages=[
                {
                    "role": "system",
                    "content": content
                },
                {
                    "role": "user",
                    "content": abstract
                }
            ],
            stream=False,
            options={
                'temperature': 0.2
            }
        )
        # Ensure that 'text' contains the string content of the message
        text = response['message']['content']
        return text
    except Exception as e:
        print(f"An error occurred: {e}")
        # Handle the error appropriately
        return None


def analyze_circadian_report(json_filepath, model="phi4:14b"):
    """
    Analyzes a circadian medicine report using LLM (via Ollama).
    
    Args:
        json_filepath: Path to the JSON report file
        model: Ollama model to use (default: phi4:14b)
    
    Returns:
        str: LLM analysis of the report
    """
    import ollama
    
    # Load JSON data
    try:
        with open(json_filepath, 'r') as f:
            report_data = json.load(f)
    except Exception as e:
        return f"Error loading JSON file: {e}"
    
    # Create detailed prompt with medical context
    system_prompt = """You are a circadian medicine specialist analyzing sleep and activity data from two time periods.

# Metric Definitions:

## Sleep Metrics:
- **CPD (Circadian Phase Deviation)**: Measures hours from expected circadian timing. Lower values indicate better alignment with natural rhythm (closer to 0 is ideal).
- **SRI (Sleep Regularity Index)**: Scale 0-100. Higher values indicate more consistent sleep schedule. Above 80 is good, below 60 needs improvement.
- **Sleep Duration**: Total sleep time per night in minutes. Optimal range: 7-9 hours (420-540 minutes).

## Activity Metrics:
- **IS (Interdaily Stability)**: Scale 0-1. Measures consistency of daily rhythms across days. Higher is better (>0.6 is good).
- **IV (Intradaily Variability)**: Scale 0-2. Measures fragmentation within days. Lower is better (<0.5 is good, indicates smoother rhythms).
- **M10**: Average activity level during the most active 10 hours. Higher indicates more daytime activity.
- **L5**: Average activity level during the least active 5 hours (typically sleep). Lower is better.
- **RA (Relative Amplitude)**: Calculated as (M10-L5)/(M10+L5). Scale 0-1. Higher indicates stronger day/night rhythm (>0.87 is good).
- **Mesor**: Mean activity level. Represents baseline rhythm intensity.
- **CPD2/Acrophase**: Peak timing of activity rhythm. Indicates when activity peaks occur.

## Light Exposure Metrics:
- **↑ recom. during sleep**: Should be LOW (dark sleep environment protects sleep quality).
- **↑ recom. before sleep**: Should be LOW (avoid bright light before bed to support melatonin production).
- **↓ recom. after waking**: Should be HIGH (bright morning light helps regulate circadian rhythm).
- **Light IS/IV**: Same interpretation as activity IS/IV but for light exposure patterns.
- **Light M10/L5/RA**: Same interpretation as activity metrics but for light exposure.
- **Light Mesor**: Average light exposure level.
- **CPD3**: Peak timing of light exposure rhythm.

# Clinical Significance:
- **Positive changes**: Higher SRI, higher IS, lower IV, lower CPD, appropriate light exposure, higher RA
- **Negative changes**: Lower SRI, lower IS, higher IV, higher CPD, poor light exposure patterns, lower RA"""

    user_prompt = f"""# Report Data:
{json.dumps(report_data, indent=2)}

# Your Task:
Analyze the comparison between Period 1 and Period 2 (Period IDs: {report_data['metadata']['period_ids']}):

1. **Identify Key Changes**: Compare metrics between the two periods. Highlight improvements and concerns.
2. **Clinical Interpretation**: Explain what these differences mean for circadian health and overall wellbeing.
3. **Provide Recommendations**: Give specific, actionable advice based on the data patterns.
4. **Prioritize Actions**: What should be addressed first for maximum impact?

Please provide a comprehensive analysis (400-600 words) that is clear and actionable for both patients and clinicians."""

    # Call Ollama API
    try:
        response = ollama.chat(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": user_prompt
                }
            ],
            stream=False,
            options={
                'temperature': 0.3  # Lower temperature for more factual analysis
            }
        )
        
        # Extract and return the analysis
        analysis = response['message']['content']
        return analysis
    
    except Exception as e:
        return f"Error during LLM analysis: {e}\n\nPlease ensure Ollama is running and the model '{model}' is available."


def save_analysis(analysis_text, filename="llm_analysis.txt"):
    """
    Saves the LLM analysis to a text file.
    
    Args:
        analysis_text: The analysis text to save
        filename: Name of the file to save (default: llm_analysis.txt)
    
    Returns:
        str: Full path to the saved analysis file
    """
    filepath = os.path.join(os.getcwd(), filename)
    with open(filepath, "w") as f:
        f.write(analysis_text)
    return filepath
    
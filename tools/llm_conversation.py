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


def continue_conversation(user_question, json_filepath, conversation_history, model="phi4:14b"):
    """
    Continues the conversation about circadian data with follow-up questions.
    Maintains context from initial analysis and previous questions.
    
    Args:
        user_question: The follow-up question from the user
        json_filepath: Path to the JSON report file (for reference)
        conversation_history: List of previous messages [{"role": "user/assistant", "content": "..."}]
        model: Ollama model to use (default: phi4:14b)
    
    Returns:
        str: LLM response to the question
    """
    import ollama
    
    # Load JSON data for context
    try:
        with open(json_filepath, 'r') as f:
            report_data = json.load(f)
    except Exception as e:
        return f"Error loading report data: {e}"
    
    # System prompt for conversational analysis
    system_prompt = """You are a circadian medicine specialist having a conversation about sleep and activity data analysis.

# Context About the Data:
You have access to a comprehensive circadian medicine report comparing two time periods with metrics including:
- **Sleep metrics**: CPD (Circadian Phase Deviation), SRI (Sleep Regularity Index), Sleep Duration
- **Activity metrics**: IS (Interdaily Stability), IV (Intradaily Variability), M10, L5, RA (Relative Amplitude), Mesor, Acrophase
- **Light exposure metrics**: Light exposure timing and intensity patterns

# Metric Definitions:
- **CPD**: Hours from expected circadian timing (lower = better alignment)
- **SRI**: Sleep regularity 0-100 (higher = more consistent, >80 is good)
- **IS**: Daily rhythm consistency 0-1 (higher = better, >0.6 is good)
- **IV**: Within-day fragmentation 0-2 (lower = smoother, <0.5 is good)
- **M10**: Most active 10 hours (higher = more activity)
- **L5**: Least active 5 hours (lower = better rest)
- **RA**: Relative amplitude (M10-L5)/(M10+L5) (higher = stronger rhythm, >0.87 is good)

# Your Role:
Answer follow-up questions about the circadian data analysis, focusing on:
1. **Psychological impacts**: How circadian patterns affect mood, cognitive function, mental health
2. **Behavioral impacts**: How changes in sleep/activity patterns influence daily functioning
3. **Clinical implications**: What these patterns mean for overall health and wellbeing
4. **Practical advice**: Specific, actionable recommendations based on the data
5. **Deeper insights**: Explain mechanisms, relationships, and long-term effects

# Guidelines:
- Provide evidence-based explanations grounded in circadian biology and psychology
- Explain mechanisms clearly (e.g., how irregular sleep affects cortisol, mood regulation)
- Give specific, actionable advice when appropriate
- Reference the actual data from the report when relevant
- Be conversational but professional
- If asked about topics beyond the data, explain what can/cannot be inferred from the available metrics

Keep responses focused, informative (300-500 words), and directly address the user's question."""

    # Build message history with context
    messages = [{"role": "system", "content": system_prompt}]
    
    # Add conversation history
    messages.extend(conversation_history)
    
    # Add current question with data reference
    current_message = f"""User Question: {user_question}

# Available Report Data:
{json.dumps(report_data, indent=2)}

Please answer the question with specific reference to the data when relevant."""
    
    messages.append({"role": "user", "content": current_message})
    
    # Call Ollama API
    try:
        response = ollama.chat(
            model=model,
            messages=messages,
            stream=False,
            options={
                'temperature': 0.4  # Slightly higher for conversational responses
            }
        )
        
        return response['message']['content']
    
    except Exception as e:
        return f"Error during conversation: {e}\n\nPlease ensure Ollama is running and the model '{model}' is available."
    
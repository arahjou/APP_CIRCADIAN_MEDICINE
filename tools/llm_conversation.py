# gemma3:12b
# qwen3:8b
# llama3.2
# phi4:14b
import json
import os


def _compact_report_for_llm(report_data) -> str:
    """Flatten report metrics into a compact, readable text block for LLM context."""
    metadata = report_data.get("metadata", {}) if isinstance(report_data, dict) else {}
    period_ids = metadata.get("period_ids", "Unknown")

    lines = [f"Period IDs: {period_ids}"]

    sections = report_data.get("sections", {}) if isinstance(report_data, dict) else {}
    if not isinstance(sections, dict) or not sections:
        lines.append("Metrics: Unknown")
        return "\n".join(lines)

    for section_name in sorted(sections.keys()):
        section = sections.get(section_name, {})
        if not isinstance(section, dict):
            continue

        for subgroup_name in sorted(section.keys()):
            items = section.get(subgroup_name, [])
            if not isinstance(items, list):
                continue

            for metric in items:
                if not isinstance(metric, dict):
                    continue
                name = metric.get("Name", "Unknown")
                p1 = metric.get("Period1", "Unknown")
                p2 = metric.get("Period2", "Unknown")
                diff = metric.get("Difference", "Unknown")
                lines.append(f"{section_name} | {subgroup_name} | {name}: P1={p1}, P2={p2}, Δ={diff}")

    return "\n".join(lines)


def _end_user_report_system_prompt() -> str:
    return """You are a circadian health coach.

Audience: an everyday person (not a scientist, not a clinician).
Goal: turn the report into a clear, practical, end-user report that is easy to act on.

Safety / scope:
- Do NOT diagnose conditions.
- Do NOT claim certainty about disorders; use cautious language (e.g., \"can be associated with\", \"may increase risk\").
- Do not provide emergency instructions unless the user asks; keep a brief, non-alarmist safety note.
- Use only information supported by the provided report data. If something is missing/unclear, write "Unknown".

Writing rules:
- Plain language. Avoid medical jargon.
- Avoid acronyms and metric codes in the output. If you must refer to one, write the full phrase in plain English.
- Use short sections and bullet points when helpful.
- If you include numbers, include units when possible and explain what the number means in plain words.

You will be given two periods (Period 1 and Period 2). Compare Period 2 vs Period 1.

Required output structure (use these exact headings):
Summary: <1–2 sentences, what changed overall>

1) What looks off (simple language):
- <2–5 bullets>

2) What looks good (keep doing):
- <2–5 bullets>

3) Actionable recommendations (next 7 days):
- <3–6 bullets, each starts with a verb; include timing when possible>

4) What these patterns can be linked to (symptoms / risk):
- <2–5 bullets; each bullet: pattern -> possible symptoms -> longer-term risks>

End with one short line:
Safety note: <1 sentence encouraging professional help if symptoms are significant/persistent>

INTERNAL INTERPRETATION GUIDE (do not copy verbatim into the output):
- Sleep timing/regularity: more consistent sleep-wake times generally supports mood, energy, and performance.
- Sleep irregularity and misalignment can be associated with: difficulty falling asleep, unrefreshing sleep, daytime sleepiness, low mood/irritability, anxiety, reduced focus, headaches; longer-term associations include metabolic risk (weight gain/insulin resistance), higher blood pressure, and cardiovascular risk.
- Fragmented daily pattern (lots of ups/downs) can be associated with: fatigue, cognitive fog, reduced daytime performance; longer-term: poorer cardiometabolic health.
- Weak day/night contrast (low daytime activity/light or high night-time light/activity) can be associated with: insomnia symptoms and lower daytime alertness; longer-term: mood and metabolic risk.
- Morning bright light exposure tends to help circadian alignment; bright light late evening tends to delay sleep and worsen sleep quality.
"""

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
    
    # Create prompt for an end-user friendly report (not a clinician digest)
    system_prompt = _end_user_report_system_prompt()

    compact_report = _compact_report_for_llm(report_data)
    user_prompt = f"""# Report Data (compact)
{compact_report}

# Task
Compare Period 2 vs Period 1 and write the end-user report using the required structure.
"""

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
                'temperature': 0.2  # Lower temperature for more factual, less speculative output
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

    # System prompt for end-user follow-ups (practical, non-technical)
    system_prompt = _end_user_report_system_prompt() + """

For follow-up Q&A, adapt the structure:
- Start with a direct answer to the user's question in 2–4 sentences.
- Then add 3 short sections:
    What in your data suggests this:
    What to try next:
    What it can be linked to (optional, only if relevant to the question):

Length limit: ~180 words unless the user explicitly asks for more.
"""

    # Build message history with context
    messages = [{"role": "system", "content": system_prompt}]
    
    # Add conversation history
    messages.extend(conversation_history)
    
    # Add current question with compact data reference (avoid dumping full JSON)
    compact_report = _compact_report_for_llm(report_data)
    current_message = f"""User Question: {user_question}

# Available Report Data (compact):
{compact_report}

Please answer the question with specific reference to the data when relevant."""
    
    messages.append({"role": "user", "content": current_message})
    
    # Call Ollama API
    try:
        response = ollama.chat(
            model=model,
            messages=messages,
            stream=False,
            options={
                'temperature': 0.3  # Balanced: helpful but not overly speculative
            }
        )
        
        return response['message']['content']
    
    except Exception as e:
        return f"Error during conversation: {e}\n\nPlease ensure Ollama is running and the model '{model}' is available."
    
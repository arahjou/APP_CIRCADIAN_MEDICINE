# Conversational AI Feature Documentation

## Overview
Enhanced the AI Analysis tab with **conversational capability** allowing users to ask follow-up questions about their circadian data analysis. The system maintains context throughout the conversation and can provide deeper insights on specific topics like psychology, mood, cognitive function, and behavioral impacts.

## New Features

### 1. **Persistent Chat Interface**
- Initial analysis is displayed as the first message
- Chat history is maintained in Streamlit session state
- Full conversation context is preserved across questions
- Clean, intuitive chat UI using Streamlit's native chat components

### 2. **Context-Aware Responses**
- AI remembers all previous questions and answers
- References specific data from the report
- Maintains consistency across the conversation
- Can drill deeper into specific topics

### 3. **Psychology & Behavioral Focus**
The AI is specially trained to discuss:
- **Psychological impacts**: How circadian patterns affect mood, mental health, emotional regulation
- **Cognitive function**: Effects on memory, attention, decision-making, alertness
- **Behavioral patterns**: How sleep/activity changes influence daily functioning
- **Stress response**: Impact on cortisol, HPA axis, stress management
- **Clinical implications**: Long-term health effects and intervention strategies

## Implementation Details

### New Function: `continue_conversation()`

**Location**: `tools/llm_conversation.py`

```python
def continue_conversation(user_question, json_filepath, conversation_history, model="phi4:14b"):
    """
    Continues conversation about circadian data with follow-up questions.
    
    Args:
        user_question: The follow-up question from the user
        json_filepath: Path to JSON report (for data reference)
        conversation_history: List of previous messages
        model: Ollama model to use
    
    Returns:
        str: AI response to the question
    """
```

**Key Features**:
- Loads report data for context
- Comprehensive system prompt with medical/psychological knowledge
- Builds full message history for context continuity
- Includes metric definitions and interpretations
- Temperature set to 0.4 for balanced creativity/accuracy

### Enhanced UI Components

**Session State Variables**:
- `chat_messages`: Stores full conversation history
- `json_filepath`: Path to current analysis data
- `current_analysis_ids`: Tuple of (period1_id, period2_id)
- `current_model`: Selected LLM model

**UI Elements**:
1. **Analysis Context Bar**: Shows periods being compared and model used
2. **Chat History Display**: Scrollable conversation view
3. **Chat Input**: Natural language question input
4. **Download Chat**: Export entire conversation
5. **Action Buttons**:
   - "Start New Analysis": Reset everything
   - "Clear Chat History": Keep initial analysis, clear follow-ups

## Example Use Cases

### Psychology & Mood
```
User: "What is the impact of these changes on mood and psychology?"

AI Response: Discusses how changes in SRI, CPD affect mood regulation,
circadian misalignment impacts on depression/anxiety, cortisol rhythms, etc.
```

### Cognitive Function
```
User: "How do these sleep patterns affect my cognitive performance?"

AI Response: Explains relationship between sleep fragmentation (IV),
cognitive function, attention, memory consolidation, decision-making, etc.
```

### Behavioral Impact
```
User: "What behavioral changes should I expect from these patterns?"

AI Response: Discusses how activity patterns (M10, L5, RA) influence
daily energy levels, motivation, social behavior, exercise capacity, etc.
```

### Stress & Anxiety
```
User: "Could these patterns be contributing to my stress levels?"

AI Response: Analyzes circadian disruption effects on HPA axis,
cortisol awakening response, stress resilience, recovery capacity, etc.
```

### Light Exposure Effects
```
User: "How is my light exposure affecting my mental health?"

AI Response: Explains morning light benefits for mood, evening light
impacts on melatonin and sleep quality, seasonal affective considerations, etc.
```

## Conversation Flow

### Initial Setup:
1. User selects two periods and generates analysis
2. Initial analysis appears as first chat message
3. Session state initialized with analysis data

### Follow-up Questions:
1. User types question in chat input
2. Question added to chat history (displayed immediately)
3. System builds context: report data + conversation history
4. LLM generates response with full context
5. Response displayed and added to chat history
6. Process repeats for subsequent questions

### Context Management:
```
Message History Structure:
[
  {"role": "system", "content": "You are a circadian medicine specialist..."},
  {"role": "assistant", "content": "Initial analysis..."},
  {"role": "user", "content": "Question 1"},
  {"role": "assistant", "content": "Answer 1"},
  {"role": "user", "content": "Question 2"},
  {"role": "assistant", "content": "Answer 2"},
  ...
]
```

## System Prompt Design

The conversational AI includes:

### Medical Knowledge
- Comprehensive metric definitions
- Clinical significance ranges
- Circadian biology principles
- Sleep-wake regulation mechanisms

### Psychological Expertise
- Mood regulation pathways
- Cognitive function relationships
- Behavioral psychology principles
- Stress physiology

### Practical Guidance
- Evidence-based explanations
- Actionable recommendations
- Mechanism explanations (e.g., how irregular sleep → cortisol dysregulation → mood issues)
- Limitations acknowledgment (what can/cannot be inferred)

## Technical Specifications

### Performance
- Response time: 5-15 seconds per question (depends on model)
- Context window: Handles ~10-15 exchanges before potential degradation
- Model options: phi4:14b (best), llama3.2, gemma3:12b, qwen3:8b

### Data Flow
```
User Question → 
Session State (history) → 
Build Context (data + history) → 
LLM Call (Ollama) → 
Response → 
Update Session State → 
Display
```

### Error Handling
- Graceful degradation if Ollama unavailable
- Clear error messages with troubleshooting steps
- Conversation preserved even if a response fails
- Automatic context truncation if too long

## Usage Guide

### For Users:

1. **Generate Initial Analysis**:
   - Select two periods to compare
   - Choose LLM model
   - Click "Generate AI Analysis"
   - Wait for initial analysis (~30-60 seconds)

2. **Ask Follow-up Questions**:
   - Type your question in the chat input
   - Press Enter or click send
   - Wait for response (~5-15 seconds)
   - Continue conversation naturally

3. **Example Questions**:
   - "What is the impact of these changes on my mood?"
   - "How do these patterns affect cognitive function?"
   - "Could this explain my stress levels?"
   - "What about energy and motivation during the day?"
   - "How does this relate to my mental health?"
   - "What mechanisms explain these effects?"
   - "What specific actions should I take first?"

4. **Manage Conversation**:
   - Download chat to save insights
   - Clear history to start fresh questions
   - Start new analysis for different periods

### For Developers:

**Add New Question Templates**:
```python
# Update system prompt in continue_conversation()
# Add new expertise areas or focus topics
# Enhance metric explanations
```

**Customize Response Style**:
```python
# Adjust temperature parameter (0.3-0.5)
# Modify system prompt tone/length
# Add specific response formats
```

**Extend Context Window**:
```python
# Implement conversation summarization
# Add context pruning logic
# Store relevant facts separately
```

## Benefits

### Clinical Value
1. **Deeper Understanding**: Go beyond surface metrics to mechanisms
2. **Personalized Insights**: Ask about your specific concerns
3. **Educational**: Learn circadian biology in context
4. **Actionable**: Get specific advice for your situation

### User Experience
1. **Natural Interaction**: Conversational vs. static report
2. **Exploration**: Drill down on interesting findings
3. **Clarification**: Ask for explanations when confused
4. **Integration**: Connect metrics to real-world impacts

### Practical Applications
1. **Treatment Planning**: Understand which changes matter most
2. **Behavior Change**: Motivation through understanding
3. **Monitoring Progress**: Track how changes affect wellbeing
4. **Prevention**: Identify risks before problems develop

## Future Enhancements

### Potential Additions:
1. **Suggested Questions**: AI proposes relevant follow-ups
2. **Multi-period Trends**: Compare 3+ periods over time
3. **Intervention Suggestions**: Specific protocols based on data
4. **Export Options**: PDF reports with conversation included
5. **Voice Input**: Speak questions instead of typing
6. **Visualization Links**: Generate plots for specific questions
7. **Citation Mode**: Include research references
8. **Comparison Mode**: "How does this compare to optimal?"

### Integration Ideas:
1. **Symptom Tracking**: Connect with mood/energy logs
2. **Goal Setting**: AI-assisted goal creation
3. **Progress Monitoring**: Automated check-ins
4. **Team Collaboration**: Share insights with clinicians

## Troubleshooting

### Common Issues:

**Chat not appearing after analysis**:
- Check browser console for errors
- Verify session state initialized
- Try refreshing page

**Slow responses**:
- Switch to smaller model (llama3.2)
- Check Ollama resource usage
- Restart Ollama service

**Context lost**:
- Conversation too long (>15 exchanges)
- Clear history and ask fresh questions
- Include key context in question

**Generic responses**:
- Ask more specific questions
- Reference specific metrics
- Provide more context about concerns

## Conclusion

The conversational AI feature transforms the static analysis report into an interactive consultation. Users can explore their circadian health data in depth, understanding not just **what** changed, but **why** it matters and **what to do** about it.

This bridges the gap between data and action, making circadian medicine insights accessible, understandable, and actionable for both patients and clinicians.

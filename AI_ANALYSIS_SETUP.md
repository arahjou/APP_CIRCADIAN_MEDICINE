# Quick Start Guide: AI Analysis Feature

## Installation Steps

### 1. Install Ollama
```bash
# macOS
brew install ollama

# Or download from https://ollama.ai
```

### 2. Install Python Package
```bash
pip install ollama
```

### 3. Download LLM Model
```bash
# Recommended model (best quality)
ollama pull phi4:14b

# Alternative models (smaller/faster)
ollama pull llama3.2
ollama pull gemma3:12b
ollama pull qwen3:8b
```

### 4. Start Ollama Service
```bash
# Usually starts automatically, but if needed:
ollama serve
```

## Testing the Installation

### Test Ollama is Working:
```bash
ollama run phi4:14b "Hello, are you working?"
```

### Test in Python:
```python
import ollama

response = ollama.chat(
    model='phi4:14b',
    messages=[{'role': 'user', 'content': 'Hello!'}]
)
print(response['message']['content'])
```

## Using the AI Analysis Feature

### In the Streamlit App:
1. Run your app: `streamlit run app.py`
2. Click on "🤖 AI Analysis" tab
3. Select two period IDs from dropdowns
4. Choose your preferred LLM model
5. Click "🧠 Generate AI Analysis"
6. Wait 30-60 seconds for analysis
7. Review results and download if needed

### Expected Output:
- **Report Metadata**: Period IDs, model used, timestamp
- **AI Analysis**: 400-600 word clinical interpretation including:
  - Key changes between periods
  - Clinical interpretations
  - Actionable recommendations
  - Priority actions
- **Download Options**: Save analysis as TXT, save data as JSON

## Troubleshooting

### Error: "Import ollama could not be resolved"
```bash
pip install ollama
```

### Error: "Make sure Ollama is running"
```bash
# Check if Ollama is running
ps aux | grep ollama

# Start Ollama
ollama serve
```

### Error: "Model not found"
```bash
# List available models
ollama list

# Pull the model
ollama pull phi4:14b
```

### Analysis Takes Too Long
- Try a smaller model: `llama3.2` or `gemma3:12b`
- Ensure sufficient RAM (8GB+ recommended for phi4:14b)
- Close other applications

### Poor Quality Analysis
- Use `phi4:14b` for best quality (requires more RAM)
- Ensure you have valid data in both periods
- Check that comparison periods have sufficient data

## Performance Tips

### Model Selection Guide:
- **phi4:14b**: Best quality, requires 8GB+ RAM, slower (~60 sec)
- **llama3.2**: Good balance, requires 4GB RAM, medium speed (~40 sec)
- **gemma3:12b**: Good quality, requires 6GB RAM, medium speed (~45 sec)
- **qwen3:8b**: Faster, requires 4GB RAM, quick (~30 sec)

### Optimization:
- Keep Ollama running in background for faster responses
- Pre-load models: `ollama run phi4:14b` then Ctrl+D
- Use SSD for better model loading times

## Support

For issues:
1. Check Ollama documentation: https://ollama.ai/docs
2. Verify Python packages: `pip list | grep ollama`
3. Check logs in terminal running Ollama
4. Ensure database has valid records with both period IDs

## Next Steps

After successful setup:
1. Run analysis on your existing records
2. Compare different models to find your preference
3. Save analyses for future reference
4. Share insights with your team

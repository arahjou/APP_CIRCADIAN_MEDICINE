# Circadian Medicine Analysis Platform

A comprehensive Streamlit-based application for analyzing actigraphy data with advanced circadian rhythm metrics and AI-powered insights.

## 🌟 Features

- **📊 Comprehensive Analysis**: Upload and analyze actigraph data files
- **😴 Sleep Metrics**: Sleep onset/offset, mid-sleep time, light exposure during sleep
- **🏃 Activity Analysis**: IS, IV, L5, M10, RA, Cosinor fitting, CPD
- **💡 Light Exposure**: Melanopic EDI analysis with circadian rhythm metrics
- **📈 Comparison Reports**: Compare two analysis periods side-by-side
- **🤖 AI Analysis**: LLM-powered clinical interpretations using local Ollama models
- **💬 Conversational AI**: Ask follow-up questions about your circadian data
- **🗄️ Database Storage**: SQLite-based record management

## 📋 Requirements

- Python 3.8+
- Ollama (for AI features)
- 8GB+ RAM recommended (for AI models)

## 🚀 Installation

### 1. Clone the repository
```bash
git clone https://github.com/arahjou/APP_CIRCADIAN_MEDICINE.git
cd APP_CIRCADIAN_MEDICINE
```

### 2. Install Python dependencies
```bash
pip install -r requirements.txt
```

### 3. Install Ollama (for AI features)
```bash
# macOS
brew install ollama

# Or download from https://ollama.ai
```

### 4. Download AI models
```bash
# Recommended model (best quality, requires 8GB+ RAM)
ollama pull phi4:14b

# Alternative models (smaller/faster)
ollama pull llama3.2
ollama pull gemma3:12b
ollama pull qwen3:8b
```

### 5. Start Ollama service
```bash
ollama serve
```

## 🎯 Usage

### Running the Application
```bash
streamlit run app.py
```

The application will open in your browser at `http://localhost:8501`

### Workflow

1. **Upload Data** (Tab 1: 📊 New Analysis)
   - Enter unique Analysis ID and description
   - Upload your actigraph CSV file
   - Select dates to analyze
   - Click "Run Analysis"
   - All results automatically saved to database

2. **Compare Records** (Tab 2: ⚖️ Compare Records)
   - Select two analysis IDs
   - Generate side-by-side comparison report
   - View detailed metrics changes

3. **AI Analysis** (Tab 3: 🤖 AI Analysis)
   - Select two periods to compare
   - Choose AI model
   - Generate clinical interpretation
   - Ask follow-up questions in chat interface

## 📊 Metrics Calculated

### Sleep & Circadian Metrics
- **CPD (Circadian Phase Dispersion)**: Variability in sleep timing
- **SRI (Sleep Regularity Index)**: Day-to-day sleep consistency (-100 to +100)
- **Sleep Onset/Offset**: Timing of sleep periods
- **Mid-Sleep Time**: Sleep midpoint timing
- **Light Exposure**: During sleep and wake periods

### Activity Metrics
- **IS (Interdaily Stability)**: Day-to-day rhythm regularity (0-1)
- **IV (Intradaily Variability)**: Within-day rhythm fragmentation (0-2)
- **L5**: Average activity during least active 5 hours
- **M10**: Average activity during most active 10 hours
- **RA (Relative Amplitude)**: Circadian rhythm strength (0-1)
- **Cosinor Analysis**: Mesor, Amplitude, Acrophase
- **CPD**: Activity timing variability

### Light Exposure Metrics
- **Melanopic EDI**: Circadian-weighted light exposure
- **IS/IV for Light**: Regularity and fragmentation metrics
- **L5/M10 for Light**: Peak and trough exposure
- **Cosinor for Light**: Daily rhythm parameters

## 📁 Data Format

Expected CSV format with columns:
- `DATE/TIME`: Timestamp
- `PIMn`: Activity measure
- `MELANOPIC EDI`: Light exposure (melanopic lux)
- `WHITE LIGHT (LUX)`: White light illuminance
- `SLEEP/WAKE`: Sleep state indicator

See `data/` folder for example files.

## 🗄️ Database

Analysis results are stored in `Actigraph_record.db` (SQLite):
- Analysis metadata (ID, description, dates)
- Sleep analysis results
- Activity analysis results
- Light analysis results

## 🤖 AI Features

### Models Comparison
- **phi4:14b**: Best quality, requires 8GB+ RAM, ~60 sec
- **llama3.2**: Good balance, 4GB RAM, ~40 sec
- **gemma3:12b**: Good quality, 6GB RAM, ~45 sec
- **qwen3:8b**: Faster, 4GB RAM, ~30 sec

### AI Capabilities
- Clinical interpretation of metric changes
- Psychological and behavioral impact analysis
- Personalized recommendations
- Context-aware follow-up conversations

## 📖 Documentation

Detailed documentation in `docs/`:
- `AI_ANALYSIS_SETUP.md` - AI feature setup guide
- `AI_ANALYSIS_IMPLEMENTATION.md` - Technical implementation details
- `CONVERSATIONAL_AI_FEATURE.md` - Chat feature documentation
- `DATABASE_FEATURES.md` - Database schema and features
- `list.md` - Comprehensive metrics reference

## 🐛 Troubleshooting

### "Import ollama could not be resolved"
```bash
pip install ollama
```

### "Make sure Ollama is running"
```bash
# Check if running
ps aux | grep ollama

# Start service
ollama serve
```

### "Model not found"
```bash
# List available models
ollama list

# Pull required model
ollama pull phi4:14b
```

### Analysis takes too long
- Try smaller model: `llama3.2` or `qwen3:8b`
- Ensure sufficient RAM (8GB+ for phi4:14b)
- Close other applications

## 📜 License

GNU Affero General Public License v3.0 (AGPL-3.0)

See [LICENSE](LICENSE) for details.

## 👥 Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## 📧 Contact

For questions or issues:
- GitHub Issues: [Report here](https://github.com/arahjou/APP_CIRCADIAN_MEDICINE/issues)
- Repository: https://github.com/arahjou/APP_CIRCADIAN_MEDICINE

## 🙏 Acknowledgments

This application implements circadian rhythm analysis methods from published research in chronobiology and sleep medicine.

## 📊 Citation

If you use this tool in your research, please cite:

```bibtex
@software{circadian_medicine_app,
  author = {Rahjouei, Ali},
  title = {Circadian Medicine Analysis Platform},
  year = {2025},
  url = {https://github.com/arahjou/APP_CIRCADIAN_MEDICINE}
}
```

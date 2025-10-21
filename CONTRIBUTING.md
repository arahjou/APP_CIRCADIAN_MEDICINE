# Contributing to Circadian Medicine Analysis Platform

Thank you for your interest in contributing! We welcome contributions from the community.

## 🤝 How to Contribute

### Reporting Bugs
- Use GitHub Issues to report bugs
- Include detailed steps to reproduce
- Provide sample data if possible (anonymized)
- Include error messages and logs

### Suggesting Features
- Open an issue with tag `enhancement`
- Describe the use case
- Explain expected behavior

### Code Contributions

1. **Fork the repository**
```bash
git clone https://github.com/arahjou/APP_CIRCADIAN_MEDICINE.git
cd APP_CIRCADIAN_MEDICINE
```

2. **Create a feature branch**
```bash
git checkout -b feature/your-feature-name
```

3. **Make your changes**
- Follow existing code style
- Add docstrings to new functions
- Include type hints where appropriate
- Test your changes thoroughly

4. **Commit your changes**
```bash
git add .
git commit -m "Add: Brief description of your changes"
```

5. **Push to your fork**
```bash
git push origin feature/your-feature-name
```

6. **Create a Pull Request**
- Provide clear description of changes
- Reference any related issues
- Include screenshots for UI changes

## 📝 Code Style Guidelines

### Python Code
- Follow PEP 8 style guide
- Use meaningful variable names
- Add docstrings to all functions:
```python
def analyze_data(df: pd.DataFrame, threshold: float = 10.0) -> dict:
    """
    Analyze circadian data from DataFrame.
    
    Args:
        df: Input DataFrame with timestamp and values
        threshold: Threshold value for analysis (default: 10.0)
    
    Returns:
        Dictionary containing analysis results
    """
    pass
```

### Documentation
- Update README.md if adding features
- Add inline comments for complex logic
- Update relevant docs in `docs/` folder

### Testing
- Test with various data formats
- Verify edge cases (empty data, single day, etc.)
- Test error handling

## 🔍 Areas for Contribution

### High Priority
- [ ] Add unit tests for core functions
- [ ] Add data validation and error handling
- [ ] Improve documentation with examples
- [ ] Add sample datasets
- [ ] Create user guide with screenshots

### Feature Enhancements
- [ ] Export analysis results to PDF
- [ ] Add data visualization customization
- [ ] Support additional data formats
- [ ] Multi-language support
- [ ] Batch processing for multiple files

### Code Quality
- [ ] Add type hints throughout codebase
- [ ] Improve error messages
- [ ] Add logging functionality
- [ ] Code refactoring for better modularity
- [ ] Performance optimization

## 🧪 Testing Checklist

Before submitting PR:
- [ ] Code runs without errors
- [ ] No breaking changes to existing features
- [ ] Documentation updated
- [ ] Follows code style guidelines
- [ ] Tested with sample data

## 📧 Questions?

Feel free to open an issue for discussion or contact the maintainers.

## 📜 License

By contributing, you agree that your contributions will be licensed under the AGPL-3.0 License.

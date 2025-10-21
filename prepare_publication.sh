#!/bin/bash

# Quick Publication Preparation Script
# Run this to prepare your repository for publication

echo "🔬 Circadian Medicine - Publication Preparation"
echo "================================================"
echo ""

# Color codes
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# 1. Backup current README
echo "1. Backing up current README..."
if [ -f "README.md" ]; then
    mv README.md README_PLANNING.md
    echo -e "${GREEN}✓ Backed up to README_PLANNING.md${NC}"
fi

# 2. Install new README
echo "2. Installing new README..."
if [ -f "README_NEW.md" ]; then
    mv README_NEW.md README.md
    echo -e "${GREEN}✓ New README installed${NC}"
else
    echo -e "${RED}✗ README_NEW.md not found${NC}"
fi

# 3. Remove generated files from git
echo ""
echo "3. Removing generated files from git tracking..."
git rm --cached Actigraph_record.db 2>/dev/null && echo -e "${GREEN}✓ Removed Actigraph_record.db${NC}"
git rm --cached circadian_report.json 2>/dev/null && echo -e "${GREEN}✓ Removed circadian_report.json${NC}"
git rm --cached enhanced_circadian_report.html 2>/dev/null && echo -e "${GREEN}✓ Removed enhanced_circadian_report.html${NC}"
git rm --cached llm_analysis.txt 2>/dev/null && echo -e "${GREEN}✓ Removed llm_analysis.txt${NC}"

# 4. Archive old version
echo ""
echo "4. Archiving old version..."
if [ -f "app_version_1.py" ]; then
    mkdir -p archive
    mv app_version_1.py archive/
    echo -e "${GREEN}✓ Moved app_version_1.py to archive/${NC}"
fi

# 5. Check for sensitive data
echo ""
echo "5. Checking for potential sensitive data..."
echo -e "${YELLOW}⚠ Please manually review these files:${NC}"
find data/ -name "*.csv" -o -name "*.txt" 2>/dev/null | while read file; do
    echo "   - $file"
done

# 6. Create version file
echo ""
echo "6. Creating version file..."
cat > __version__.py << EOF
"""Version information for Circadian Medicine Analysis Platform."""

__version__ = "1.2.0"
__author__ = "Ali Rahjouei"
__description__ = "Circadian Medicine Analysis Platform with AI-powered insights"
__url__ = "https://github.com/arahjou/APP_CIRCADIAN_MEDICINE"
EOF
echo -e "${GREEN}✓ Created __version__.py${NC}"

# 7. Create screenshots directory
echo ""
echo "7. Creating screenshots directory..."
mkdir -p screenshots
cat > screenshots/README.md << EOF
# Screenshots

Add screenshots of the application here:

- main_interface.png - Main application interface
- analysis_results.png - Example analysis results
- comparison_view.png - Comparison between two periods
- ai_chat.png - AI chat interface

## Taking Screenshots

1. Run the app: \`streamlit run app.py\`
2. Navigate to each feature
3. Take screenshots (Cmd+Shift+4 on macOS)
4. Save to this directory with descriptive names
EOF
echo -e "${GREEN}✓ Created screenshots directory${NC}"

# 8. Create tests directory structure
echo ""
echo "8. Setting up tests directory..."
mkdir -p tests
if [ ! -f "tests/__init__.py" ]; then
    touch tests/__init__.py
fi

cat > tests/test_basic.py << 'EOF'
"""Basic tests for core functionality."""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta


def test_imports():
    """Test that all required packages can be imported."""
    import streamlit
    import pandas
    import numpy
    import scipy
    import matplotlib
    assert True


def test_data_creation():
    """Test basic data creation."""
    dates = pd.date_range('2025-01-15', periods=1440, freq='min')
    data = pd.DataFrame({
        'DATE/TIME': dates,
        'PIMn': np.random.uniform(0, 100, 1440),
        'MELANOPIC EDI': np.random.uniform(0, 500, 1440),
    })
    assert len(data) == 1440
    assert 'DATE/TIME' in data.columns


# Add more tests as you develop
EOF
echo -e "${GREEN}✓ Created basic test structure${NC}"

# 9. Format check
echo ""
echo "9. Checking code formatting..."
if command -v black &> /dev/null; then
    echo -e "${YELLOW}Running Black formatter (dry-run)...${NC}"
    black --check . 2>/dev/null || echo -e "${YELLOW}⚠ Code formatting could be improved. Run: black .${NC}"
else
    echo -e "${YELLOW}⚠ Black not installed. Install with: pip install black${NC}"
fi

# 10. Summary
echo ""
echo "================================================"
echo -e "${GREEN}✓ Preparation complete!${NC}"
echo ""
echo "Next steps:"
echo "1. Review changes with: git status"
echo "2. Check data directory for sensitive information"
echo "3. Add screenshots to screenshots/ directory"
echo "4. Run tests with: pytest tests/"
echo "5. Commit changes: git add . && git commit -m 'Prepare for publication'"
echo ""
echo "See PUBLICATION_READINESS.md for complete checklist"
echo ""

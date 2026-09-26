"""
The analysis rules live in backend/app/domain/analysis.py (one copy, shared with the API).
This module forwards to it so the Excel scripts keep using `import analysis as A`.
"""
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
sys.modules[__name__] = importlib.import_module("app.domain.analysis")

"""
SynGrad - Slip Extraction Pipeline Aggregator
Re-exports run_slip_extraction for modularity across audit and lab endpoints.
"""

from typing import Any, Dict, Optional

try:
    from app.v1.endpoints.audit import run_slip_extraction, check_pdf_fraud
except ImportError:
    from backend.app.v1.endpoints.audit import run_slip_extraction, check_pdf_fraud

__all__ = ["run_slip_extraction", "check_pdf_fraud"]

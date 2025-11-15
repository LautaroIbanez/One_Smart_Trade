"""Quantitative analysis modules (indicators, factors, strategies, signal engine)."""
from .factors import cross_timeframe
from .indicators import calculate_all
from .narrative import build_narrative
from .regime import HmmRegimeClassifier, KMeansRegimeClassifier, RegimeClassifier
from .capital_allocation import CapitalAllocationRules, DynamicCapitalAllocator, KellyAllocation
from .regime_playbooks import RegimePlaybook, RegimePlaybookManager
from .regime_transition import RegimeTransitionConfig, RegimeTransitionDetector, RegimeTransitionManager
from .signal_engine import generate_signal

__all__ = [
    "calculate_all",
    "cross_timeframe",
    "generate_signal",
    "build_narrative",
    "HmmRegimeClassifier",
    "KMeansRegimeClassifier",
    "RegimeClassifier",
    "CapitalAllocationRules",
    "DynamicCapitalAllocator",
    "KellyAllocation",
    "RegimePlaybook",
    "RegimePlaybookManager",
    "RegimeTransitionConfig",
    "RegimeTransitionDetector",
    "RegimeTransitionManager",
]

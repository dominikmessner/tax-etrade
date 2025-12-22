"""
Austrian Tax Engine for E-Trade RSUs and ESPP

A tax calculation engine implementing the Austrian moving average cost basis method
(Gleitender Durchschnittspreis) for stocks acquired through RSU vesting and ESPP purchases.
"""

from .models import (
    EventType,
    StockEvent,
    ProcessedEvent,
    YearlyTaxSummary,
    TaxEngineState,
)
from .ecb_rates import ECBRateFetcher, prefetch_ecb_rates
from .tax_engine import TaxEngine
from .sample_data import (
    create_sample_events_with_manual_fx,
    create_sample_events_with_ecb_rates,
)
from .rsu_parser import load_rsu_events

__version__ = "0.1.0"

__all__ = [
    "EventType",
    "StockEvent",
    "ProcessedEvent",
    "YearlyTaxSummary",
    "TaxEngineState",
    "ECBRateFetcher",
    "prefetch_ecb_rates",
    "TaxEngine",
    "create_sample_events_with_manual_fx",
    "create_sample_events_with_ecb_rates",
]

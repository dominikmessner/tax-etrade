"""
Austrian Tax Engine for E-Trade RSUs and ESPP

A tax calculation engine implementing the Austrian moving average cost basis method
(Gleitender Durchschnittspreis) for stocks acquired through RSU vesting and ESPP purchases.
"""

from .ecb_rates import ECBRateFetcher, prefetch_ecb_rates
from .loaders import (
    load_all_events,
    load_espp_events_from_excel,
    load_options_stock_events,
    load_orders_from_excel,
)
from .models import (
    EventType,
    LazyFxRateWarning,
    ProcessedEvent,
    StockEvent,
    TaxEngineState,
    YearlyTaxSummary,
)
from .options_parser import load_options_events
from .rsu_parser import load_rsu_events
from .sample_data import (
    create_sample_events_with_ecb_rates,
    create_sample_events_with_manual_fx,
)
from .tax_engine import TaxEngine, event_sort_key

__version__ = "0.1.0"

__all__ = [
    "EventType",
    "LazyFxRateWarning",
    "StockEvent",
    "ProcessedEvent",
    "YearlyTaxSummary",
    "TaxEngineState",
    "ECBRateFetcher",
    "prefetch_ecb_rates",
    "TaxEngine",
    "event_sort_key",
    "create_sample_events_with_manual_fx",
    "create_sample_events_with_ecb_rates",
    "load_all_events",
    "load_espp_events_from_excel",
    "load_orders_from_excel",
    "load_options_stock_events",
    "load_rsu_events",
    "load_options_events",
]

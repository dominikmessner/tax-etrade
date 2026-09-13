"""
Shared pytest fixtures for tax engine tests.

Provides reusable test data and mocked services to avoid
external dependencies and private data exposure.
"""

from datetime import date
from decimal import Decimal

import pytest

from tax_engine.models import EventType, StockEvent

# =============================================================================
# Sample Stock Events (with explicit FX rates - no ECB calls)
# =============================================================================


@pytest.fixture
def simple_vest_event():
    """A single VEST event with explicit FX rate."""
    return StockEvent(
        event_date=date(2021, 5, 17),
        event_type=EventType.VEST,
        shares=Decimal("100"),
        price_usd=Decimal("50.00"),
        fx_rate=Decimal("0.82"),  # Explicit rate = no ECB fetch
        notes="Test RSU Vest",
    )


@pytest.fixture
def simple_buy_event():
    """A single BUY event with explicit FX rate."""
    return StockEvent(
        event_date=date(2021, 6, 1),
        event_type=EventType.BUY,
        shares=Decimal("50"),
        price_usd=Decimal("40.00"),
        fx_rate=Decimal("0.85"),
        notes="Test ESPP Purchase",
    )


@pytest.fixture
def simple_sell_event():
    """A single SELL event with explicit FX rate."""
    return StockEvent(
        event_date=date(2021, 7, 15),
        event_type=EventType.SELL,
        shares=Decimal("25"),
        price_usd=Decimal("55.00"),
        fx_rate=Decimal("0.84"),
        notes="Test Manual Sale",
    )


@pytest.fixture
def basic_event_sequence():
    """
    A basic sequence of events for testing the tax engine.

    Scenario:
    1. VEST 100 shares @ $50 (FX 0.82) = €4100 total, avg €41.00
    2. BUY 50 shares @ $40 (FX 0.85) = €1700 total, avg €38.67
    3. SELL 25 shares @ $55 (FX 0.84) = €1155 proceeds, gain of €188.25
    """
    return [
        StockEvent(
            event_date=date(2021, 5, 17),
            event_type=EventType.VEST,
            shares=Decimal("100"),
            price_usd=Decimal("50.00"),
            fx_rate=Decimal("0.82"),
            notes="RSU Vest",
        ),
        StockEvent(
            event_date=date(2021, 6, 1),
            event_type=EventType.BUY,
            shares=Decimal("50"),
            price_usd=Decimal("40.00"),
            fx_rate=Decimal("0.85"),
            notes="ESPP Purchase",
        ),
        StockEvent(
            event_date=date(2021, 7, 15),
            event_type=EventType.SELL,
            shares=Decimal("25"),
            price_usd=Decimal("55.00"),
            fx_rate=Decimal("0.84"),
            notes="Partial Sale",
        ),
    ]


@pytest.fixture
def same_day_vest_and_sell():
    """
    Events that happen on the same day (common with sell-to-cover).

    Tests that VEST is processed before SELL on the same date.
    """
    return [
        StockEvent(
            event_date=date(2021, 8, 1),
            event_type=EventType.SELL,  # Listed first to test sorting
            shares=Decimal("20"),
            price_usd=Decimal("45.00"),
            fx_rate=Decimal("0.84"),
            notes="Sell-to-cover",
        ),
        StockEvent(
            event_date=date(2021, 8, 1),
            event_type=EventType.VEST,
            shares=Decimal("50"),
            price_usd=Decimal("45.00"),
            fx_rate=Decimal("0.84"),
            notes="RSU Vest",
        ),
    ]


@pytest.fixture
def multi_year_events():
    """Events spanning multiple years to test yearly summaries."""
    return [
        # 2021: Buy and profitable sell
        StockEvent(
            event_date=date(2021, 3, 1),
            event_type=EventType.BUY,
            shares=Decimal("100"),
            price_usd=Decimal("30.00"),
            fx_rate=Decimal("0.83"),
            notes="ESPP 2021",
        ),
        StockEvent(
            event_date=date(2021, 9, 15),
            event_type=EventType.SELL,
            shares=Decimal("50"),
            price_usd=Decimal("40.00"),
            fx_rate=Decimal("0.85"),
            notes="2021 Sale - Profit",
        ),
        # 2022: Loss
        StockEvent(
            event_date=date(2022, 6, 1),
            event_type=EventType.SELL,
            shares=Decimal("50"),
            price_usd=Decimal("20.00"),
            fx_rate=Decimal("0.95"),
            notes="2022 Sale - Loss",
        ),
    ]


# =============================================================================
# Mock PDF Content for RSU Parser
# =============================================================================


@pytest.fixture
def mock_rsu_pdf_text():
    """
    Returns mock text content that matches RSU PDF format.

    This is what pdfplumber.extract_text() would return from a real PDF.
    """
    return """
    Morgan Stanley at Work

    Stock Plan Account

    Confirmation of Restricted Stock Release

    Release Date 05-17-2021

    Plan Name:              2015 Stock Incentive Plan
    Shares Released         63.0000
    Market Value Per Share  $46.680000
    Market Value            $2,940.84

    This is a sample document.
    """


@pytest.fixture
def mock_rsu_pdf_text_factory():
    """
    Factory to create mock RSU PDF text with custom values.

    Usage:
        text = mock_rsu_pdf_text_factory("03-15-2022", "100.0000", "$55.50")
    """

    def _factory(release_date: str, shares: str, price: str):
        return f"""
    Morgan Stanley at Work

    Stock Plan Account

    Confirmation of Restricted Stock Release

    Release Date {release_date}

    Plan Name:              2015 Stock Incentive Plan
    Shares Released         {shares}
    Market Value Per Share  {price}
    Market Value            $0.00

    This is a sample document.
    """

    return _factory

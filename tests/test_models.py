"""
Unit tests for tax engine data models.

Tests the computed properties and validation logic in models.py
without any external dependencies (ECB API, files, etc).
"""

import pytest
from datetime import date
from decimal import Decimal

from tax_engine.models import (
    EventType,
    StockEvent,
    ProcessedEvent,
    YearlyTaxSummary,
    TaxEngineState,
)


class TestStockEvent:
    """Tests for the StockEvent dataclass."""
    
    def test_price_eur_calculation(self):
        """Test EUR price calculation with explicit FX rate."""
        event = StockEvent(
            event_date=date(2021, 5, 17),
            event_type=EventType.VEST,
            shares=Decimal("100"),
            price_usd=Decimal("50.00"),
            fx_rate=Decimal("0.82"),
        )
        # $50 * 0.82 = €41.00
        assert event.price_eur == Decimal("41.0000")
    
    def test_total_value_eur_calculation(self):
        """Test total EUR value calculation."""
        event = StockEvent(
            event_date=date(2021, 5, 17),
            event_type=EventType.VEST,
            shares=Decimal("100"),
            price_usd=Decimal("50.00"),
            fx_rate=Decimal("0.82"),
        )
        # 100 shares * €41.00 = €4100.00
        assert event.total_value_eur == Decimal("4100.0000")
    
    def test_decimal_conversion_from_int(self):
        """Test that int values are converted to Decimal."""
        event = StockEvent(
            event_date=date(2021, 5, 17),
            event_type=EventType.VEST,
            shares=100,  # int
            price_usd=50,  # int
            fx_rate=0.82,  # float (will be converted via str)
        )
        assert isinstance(event.shares, Decimal)
        assert isinstance(event.price_usd, Decimal)
        assert isinstance(event.fx_rate, Decimal)
    
    def test_decimal_conversion_from_float(self):
        """Test that float values are converted to Decimal via str."""
        event = StockEvent(
            event_date=date(2021, 5, 17),
            event_type=EventType.VEST,
            shares=100.5,
            price_usd=50.25,
            fx_rate=0.8234,
        )
        assert event.shares == Decimal("100.5")
        assert event.price_usd == Decimal("50.25")
    
    def test_resolved_fx_rate_with_explicit_rate(self):
        """Test that explicit FX rate is used when provided."""
        event = StockEvent(
            event_date=date(2021, 5, 17),
            event_type=EventType.VEST,
            shares=Decimal("100"),
            price_usd=Decimal("50.00"),
            fx_rate=Decimal("0.82"),
        )
        assert event.resolved_fx_rate == Decimal("0.82")
    
    def test_event_types(self):
        """Test all event types can be created."""
        for event_type in EventType:
            event = StockEvent(
                event_date=date(2021, 1, 1),
                event_type=event_type,
                shares=Decimal("10"),
                price_usd=Decimal("100"),
                fx_rate=Decimal("0.85"),
            )
            assert event.event_type == event_type
    
    def test_notes_default_empty(self):
        """Test that notes defaults to empty string."""
        event = StockEvent(
            event_date=date(2021, 1, 1),
            event_type=EventType.VEST,
            shares=Decimal("10"),
            price_usd=Decimal("100"),
            fx_rate=Decimal("0.85"),
        )
        assert event.notes == ""
    
    def test_notes_custom(self):
        """Test that custom notes are preserved."""
        event = StockEvent(
            event_date=date(2021, 1, 1),
            event_type=EventType.VEST,
            shares=Decimal("10"),
            price_usd=Decimal("100"),
            fx_rate=Decimal("0.85"),
            notes="RSU Vest Q2 2021"
        )
        assert event.notes == "RSU Vest Q2 2021"
    
    def test_price_eur_rounding(self):
        """Test that EUR price is rounded to 4 decimal places."""
        event = StockEvent(
            event_date=date(2021, 5, 17),
            event_type=EventType.VEST,
            shares=Decimal("1"),
            price_usd=Decimal("33.333333"),
            fx_rate=Decimal("0.333333"),
        )
        # Result should be rounded to 4 decimals
        assert event.price_eur == event.price_eur.quantize(Decimal("0.0001"))


class TestYearlyTaxSummary:
    """Tests for the YearlyTaxSummary dataclass."""
    
    def test_net_gain_with_only_gains(self):
        """Test net gain when only gains exist."""
        summary = YearlyTaxSummary(
            year=2021,
            total_gains=Decimal("1000.00"),
            total_losses=Decimal("0.00"),
        )
        assert summary.net_gain_loss == Decimal("1000.00")
    
    def test_net_loss_with_only_losses(self):
        """Test net loss when only losses exist."""
        summary = YearlyTaxSummary(
            year=2021,
            total_gains=Decimal("0.00"),
            total_losses=Decimal("-500.00"),
        )
        assert summary.net_gain_loss == Decimal("-500.00")
    
    def test_net_gain_loss_offset(self):
        """Test that losses offset gains within the same year."""
        summary = YearlyTaxSummary(
            year=2021,
            total_gains=Decimal("1000.00"),
            total_losses=Decimal("-300.00"),
        )
        assert summary.net_gain_loss == Decimal("700.00")
    
    def test_taxable_gain_positive(self):
        """Test taxable gain when net is positive."""
        summary = YearlyTaxSummary(
            year=2021,
            total_gains=Decimal("1000.00"),
            total_losses=Decimal("-300.00"),
        )
        assert summary.taxable_gain == Decimal("700.00")
    
    def test_taxable_gain_zero_when_net_negative(self):
        """Test that taxable gain is zero when net is negative."""
        summary = YearlyTaxSummary(
            year=2021,
            total_gains=Decimal("200.00"),
            total_losses=Decimal("-500.00"),
        )
        assert summary.net_gain_loss == Decimal("-300.00")
        assert summary.taxable_gain == Decimal("0")
    
    def test_kest_calculation_27_5_percent(self):
        """Test KESt calculation at 27.5% rate."""
        summary = YearlyTaxSummary(
            year=2021,
            total_gains=Decimal("1000.00"),
            total_losses=Decimal("0.00"),
        )
        # 1000 * 0.275 = 275.00
        assert summary.kest_due == Decimal("275.00")
    
    def test_kest_rounding(self):
        """Test that KESt is rounded to 2 decimal places."""
        summary = YearlyTaxSummary(
            year=2021,
            total_gains=Decimal("333.33"),
            total_losses=Decimal("0.00"),
        )
        # 333.33 * 0.275 = 91.66575 -> 91.67 (rounded)
        assert summary.kest_due == Decimal("91.67")
    
    def test_kest_zero_when_no_taxable_gain(self):
        """Test that KESt is zero when there's no taxable gain."""
        summary = YearlyTaxSummary(
            year=2021,
            total_gains=Decimal("100.00"),
            total_losses=Decimal("-200.00"),
        )
        assert summary.kest_due == Decimal("0.00")
    
    def test_default_values(self):
        """Test that gains and losses default to zero."""
        summary = YearlyTaxSummary(year=2021)
        assert summary.total_gains == Decimal("0")
        assert summary.total_losses == Decimal("0")


class TestTaxEngineState:
    """Tests for the TaxEngineState dataclass."""
    
    def test_default_values(self):
        """Test that state initializes with zeros."""
        state = TaxEngineState()
        assert state.total_shares == Decimal("0")
        assert state.avg_cost_eur == Decimal("0")
        assert state.total_portfolio_cost_eur == Decimal("0")
    
    def test_clone(self):
        """Test that clone creates an independent copy."""
        state = TaxEngineState(
            total_shares=Decimal("100"),
            avg_cost_eur=Decimal("50.00"),
            total_portfolio_cost_eur=Decimal("5000.00"),
        )
        cloned = state.clone()
        
        # Values should be equal
        assert cloned.total_shares == state.total_shares
        assert cloned.avg_cost_eur == state.avg_cost_eur
        assert cloned.total_portfolio_cost_eur == state.total_portfolio_cost_eur
        
        # But should be independent
        cloned.total_shares = Decimal("200")
        assert state.total_shares == Decimal("100")


class TestProcessedEvent:
    """Tests for the ProcessedEvent dataclass."""
    
    def test_creation(self):
        """Test ProcessedEvent can be created with all fields."""
        event = StockEvent(
            event_date=date(2021, 5, 17),
            event_type=EventType.VEST,
            shares=Decimal("100"),
            price_usd=Decimal("50.00"),
            fx_rate=Decimal("0.82"),
        )
        
        processed = ProcessedEvent(
            event=event,
            total_shares_after=Decimal("100"),
            avg_cost_eur_after=Decimal("41.00"),
            realized_gain_loss=Decimal("0"),
            cost_change_eur=Decimal("4100.00"),
            total_portfolio_cost_eur=Decimal("4100.00"),
        )
        
        assert processed.event == event
        assert processed.total_shares_after == Decimal("100")
        assert processed.avg_cost_eur_after == Decimal("41.00")
        assert processed.realized_gain_loss == Decimal("0")
    
    def test_default_values(self):
        """Test ProcessedEvent defaults."""
        event = StockEvent(
            event_date=date(2021, 5, 17),
            event_type=EventType.VEST,
            shares=Decimal("100"),
            price_usd=Decimal("50.00"),
            fx_rate=Decimal("0.82"),
        )
        
        processed = ProcessedEvent(
            event=event,
            total_shares_after=Decimal("100"),
            avg_cost_eur_after=Decimal("41.00"),
        )
        
        assert processed.realized_gain_loss == Decimal("0")
        assert processed.cost_change_eur == Decimal("0")
        assert processed.total_portfolio_cost_eur == Decimal("0")

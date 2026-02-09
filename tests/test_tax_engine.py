"""
Unit tests for the TaxEngine core logic.

Tests the moving average cost basis calculations, event processing,
and edge cases without any external dependencies.
"""

from datetime import date
from decimal import Decimal

import pytest

from tax_engine.models import EventType, StockEvent
from tax_engine.tax_engine import TaxEngine


class TestTaxEngineAcquisition:
    """Tests for VEST and BUY processing (acquisitions)."""

    def test_first_vest_sets_avg_cost(self):
        """First VEST should set initial average cost."""
        engine = TaxEngine()
        event = StockEvent(
            event_date=date(2021, 5, 17),
            event_type=EventType.VEST,
            shares=Decimal("100"),
            price_usd=Decimal("50.00"),
            fx_rate=Decimal("0.82"),
        )

        result = engine.process_event(event)

        # 100 shares @ $50 * 0.82 = €41 per share
        assert engine.state.total_shares == Decimal("100")
        assert engine.state.avg_cost_eur == Decimal("41.0000")
        assert engine.state.total_portfolio_cost_eur == Decimal("4100.0000")
        assert result.realized_gain_loss == Decimal("0")

    def test_first_buy_sets_avg_cost(self):
        """First BUY should set initial average cost."""
        engine = TaxEngine()
        event = StockEvent(
            event_date=date(2021, 6, 1),
            event_type=EventType.BUY,
            shares=Decimal("50"),
            price_usd=Decimal("40.00"),
            fx_rate=Decimal("0.85"),
        )

        engine.process_event(event)

        # 50 shares @ $40 * 0.85 = €34 per share
        assert engine.state.total_shares == Decimal("50")
        assert engine.state.avg_cost_eur == Decimal("34.0000")
        assert engine.state.total_portfolio_cost_eur == Decimal("1700.0000")

    def test_second_acquisition_updates_moving_average(self):
        """Second acquisition should recalculate moving average."""
        engine = TaxEngine()

        # First: 100 shares @ €41 = €4100 total
        engine.process_event(
            StockEvent(
                event_date=date(2021, 5, 17),
                event_type=EventType.VEST,
                shares=Decimal("100"),
                price_usd=Decimal("50.00"),
                fx_rate=Decimal("0.82"),
            )
        )

        # Second: 50 shares @ €34 = €1700 total
        # New avg = (4100 + 1700) / (100 + 50) = 5800 / 150 = €38.6667
        engine.process_event(
            StockEvent(
                event_date=date(2021, 6, 1),
                event_type=EventType.BUY,
                shares=Decimal("50"),
                price_usd=Decimal("40.00"),
                fx_rate=Decimal("0.85"),
            )
        )

        assert engine.state.total_shares == Decimal("150")
        assert engine.state.avg_cost_eur == pytest.approx(Decimal("38.6667"), abs=Decimal("0.0001"))
        assert engine.state.total_portfolio_cost_eur == Decimal("5800.0000")

    def test_acquisition_with_zero_shares_existing(self):
        """Acquisition when starting from zero shares."""
        engine = TaxEngine()
        assert engine.state.total_shares == Decimal("0")

        event = StockEvent(
            event_date=date(2021, 5, 17),
            event_type=EventType.VEST,
            shares=Decimal("10"),
            price_usd=Decimal("100.00"),
            fx_rate=Decimal("0.80"),
        )

        engine.process_event(event)
        assert engine.state.total_shares == Decimal("10")


class TestTaxEngineSell:
    """Tests for SELL processing."""

    def test_sell_calculates_gain(self):
        """SELL at higher price should realize a gain."""
        engine = TaxEngine()

        # Acquire 100 shares @ €41
        engine.process_event(
            StockEvent(
                event_date=date(2021, 5, 17),
                event_type=EventType.VEST,
                shares=Decimal("100"),
                price_usd=Decimal("50.00"),
                fx_rate=Decimal("0.82"),
            )
        )

        # Sell 50 shares @ €50 (sell price in EUR = $60 * 0.8333 ≈ €50)
        result = engine.process_event(
            StockEvent(
                event_date=date(2021, 7, 15),
                event_type=EventType.SELL,
                shares=Decimal("50"),
                price_usd=Decimal("60.00"),
                fx_rate=Decimal("0.8333"),
            )
        )

        # Gain = (50 - 41) * 50 = €450 (approximately)
        sell_price_eur = Decimal("60.00") * Decimal("0.8333")  # ≈ €49.998
        expected_gain = (sell_price_eur.quantize(Decimal("0.0001")) - Decimal("41.0000")) * 50

        assert result.realized_gain_loss == pytest.approx(expected_gain, abs=Decimal("0.01"))
        assert engine.state.total_shares == Decimal("50")
        # Avg cost should remain unchanged after sell (Rule B)
        assert engine.state.avg_cost_eur == Decimal("41.0000")

    def test_sell_calculates_loss(self):
        """SELL at lower price should realize a loss."""
        engine = TaxEngine()

        # Acquire 100 shares @ €41
        engine.process_event(
            StockEvent(
                event_date=date(2021, 5, 17),
                event_type=EventType.VEST,
                shares=Decimal("100"),
                price_usd=Decimal("50.00"),
                fx_rate=Decimal("0.82"),
            )
        )

        # Sell 50 shares @ €30 (price dropped)
        result = engine.process_event(
            StockEvent(
                event_date=date(2021, 7, 15),
                event_type=EventType.SELL,
                shares=Decimal("50"),
                price_usd=Decimal("36.59"),  # $36.59 * 0.82 ≈ €30
                fx_rate=Decimal("0.82"),
            )
        )

        # Loss = (30 - 41) * 50 = -€550 (approximately)
        assert result.realized_gain_loss < 0
        assert engine.state.total_shares == Decimal("50")

    def test_sell_avg_cost_unchanged(self):
        """Selling should not change the average cost (Rule B)."""
        engine = TaxEngine()

        # Acquire shares
        engine.process_event(
            StockEvent(
                event_date=date(2021, 5, 17),
                event_type=EventType.VEST,
                shares=Decimal("100"),
                price_usd=Decimal("50.00"),
                fx_rate=Decimal("0.82"),
            )
        )

        avg_before = engine.state.avg_cost_eur

        # Partial sell
        engine.process_event(
            StockEvent(
                event_date=date(2021, 7, 15),
                event_type=EventType.SELL,
                shares=Decimal("30"),
                price_usd=Decimal("55.00"),
                fx_rate=Decimal("0.84"),
            )
        )

        assert engine.state.avg_cost_eur == avg_before

    def test_sell_all_shares_resets_avg_cost(self):
        """Selling all shares should reset average cost to zero."""
        engine = TaxEngine()

        # Acquire 100 shares
        engine.process_event(
            StockEvent(
                event_date=date(2021, 5, 17),
                event_type=EventType.VEST,
                shares=Decimal("100"),
                price_usd=Decimal("50.00"),
                fx_rate=Decimal("0.82"),
            )
        )

        # Sell all 100 shares
        engine.process_event(
            StockEvent(
                event_date=date(2021, 7, 15),
                event_type=EventType.SELL,
                shares=Decimal("100"),
                price_usd=Decimal("55.00"),
                fx_rate=Decimal("0.84"),
            )
        )

        assert engine.state.total_shares == Decimal("0")
        assert engine.state.avg_cost_eur == Decimal("0")
        assert engine.state.total_portfolio_cost_eur == Decimal("0")

    def test_sell_more_than_held_raises_error(self):
        """Attempting to sell more shares than held should raise ValueError."""
        engine = TaxEngine()

        # Acquire 50 shares
        engine.process_event(
            StockEvent(
                event_date=date(2021, 5, 17),
                event_type=EventType.VEST,
                shares=Decimal("50"),
                price_usd=Decimal("50.00"),
                fx_rate=Decimal("0.82"),
            )
        )

        # Try to sell 100 shares (more than held)
        with pytest.raises(ValueError) as exc_info:
            engine.process_event(
                StockEvent(
                    event_date=date(2021, 7, 15),
                    event_type=EventType.SELL,
                    shares=Decimal("100"),
                    price_usd=Decimal("55.00"),
                    fx_rate=Decimal("0.84"),
                )
            )

        assert "Cannot sell" in str(exc_info.value)
        assert "100" in str(exc_info.value)
        assert "50" in str(exc_info.value)

    def test_sell_with_zero_shares_raises_error(self):
        """Selling when no shares held should raise ValueError."""
        engine = TaxEngine()

        with pytest.raises(ValueError) as exc_info:
            engine.process_event(
                StockEvent(
                    event_date=date(2021, 7, 15),
                    event_type=EventType.SELL,
                    shares=Decimal("10"),
                    price_usd=Decimal("55.00"),
                    fx_rate=Decimal("0.84"),
                )
            )

        assert "Cannot sell" in str(exc_info.value)


class TestTaxEngineEventSorting:
    """Tests for event sorting logic."""

    def test_events_sorted_by_date(self):
        """Events should be sorted by date."""
        engine = TaxEngine()
        events = [
            StockEvent(
                event_date=date(2021, 7, 15),
                event_type=EventType.SELL,
                shares=Decimal("10"),
                price_usd=Decimal("55.00"),
                fx_rate=Decimal("0.84"),
            ),
            StockEvent(
                event_date=date(2021, 5, 17),
                event_type=EventType.VEST,
                shares=Decimal("100"),
                price_usd=Decimal("50.00"),
                fx_rate=Decimal("0.82"),
            ),
        ]

        sorted_events = engine._sort_events(events)

        assert sorted_events[0].event_date == date(2021, 5, 17)
        assert sorted_events[1].event_date == date(2021, 7, 15)

    def test_same_day_vest_before_sell(self):
        """On same day, VEST should be processed before SELL."""
        engine = TaxEngine()
        events = [
            StockEvent(
                event_date=date(2021, 8, 1),
                event_type=EventType.SELL,  # Listed first
                shares=Decimal("20"),
                price_usd=Decimal("45.00"),
                fx_rate=Decimal("0.84"),
            ),
            StockEvent(
                event_date=date(2021, 8, 1),
                event_type=EventType.VEST,
                shares=Decimal("50"),
                price_usd=Decimal("45.00"),
                fx_rate=Decimal("0.84"),
            ),
        ]

        sorted_events = engine._sort_events(events)

        # VEST should come first
        assert sorted_events[0].event_type == EventType.VEST
        assert sorted_events[1].event_type == EventType.SELL

    def test_same_day_buy_before_sell(self):
        """On same day, BUY should be processed before SELL."""
        engine = TaxEngine()
        events = [
            StockEvent(
                event_date=date(2021, 8, 1),
                event_type=EventType.SELL,
                shares=Decimal("20"),
                price_usd=Decimal("45.00"),
                fx_rate=Decimal("0.84"),
            ),
            StockEvent(
                event_date=date(2021, 8, 1),
                event_type=EventType.BUY,
                shares=Decimal("50"),
                price_usd=Decimal("45.00"),
                fx_rate=Decimal("0.84"),
            ),
        ]

        sorted_events = engine._sort_events(events)

        assert sorted_events[0].event_type == EventType.BUY
        assert sorted_events[1].event_type == EventType.SELL

    def test_same_day_vest_before_buy_before_sell(self):
        """On same day: VEST < BUY < SELL."""
        engine = TaxEngine()
        events = [
            StockEvent(
                event_date=date(2021, 8, 1),
                event_type=EventType.SELL,
                shares=Decimal("20"),
                price_usd=Decimal("45.00"),
                fx_rate=Decimal("0.84"),
            ),
            StockEvent(
                event_date=date(2021, 8, 1),
                event_type=EventType.BUY,
                shares=Decimal("30"),
                price_usd=Decimal("42.00"),
                fx_rate=Decimal("0.84"),
            ),
            StockEvent(
                event_date=date(2021, 8, 1),
                event_type=EventType.VEST,
                shares=Decimal("50"),
                price_usd=Decimal("45.00"),
                fx_rate=Decimal("0.84"),
            ),
        ]

        sorted_events = engine._sort_events(events)

        assert sorted_events[0].event_type == EventType.VEST
        assert sorted_events[1].event_type == EventType.BUY
        assert sorted_events[2].event_type == EventType.SELL


class TestTaxEngineProcessAll:
    """Tests for process_all and batch processing."""

    def test_process_all_with_basic_sequence(self, basic_event_sequence):
        """Test processing a basic sequence of events."""
        engine = TaxEngine()
        results = engine.process_all(basic_event_sequence)

        assert len(results) == 3
        # After: 100 vest + 50 buy - 25 sell = 125 shares
        assert engine.state.total_shares == Decimal("125")

    def test_process_all_same_day_vest_sell(self, same_day_vest_and_sell):
        """Test that same-day vest+sell works (sell-to-cover scenario)."""
        engine = TaxEngine()

        # Should not raise - VEST is processed before SELL
        results = engine.process_all(same_day_vest_and_sell)

        assert len(results) == 2
        # 50 vest - 20 sell = 30 shares
        assert engine.state.total_shares == Decimal("30")

    def test_reset_clears_state(self):
        """Test that reset() clears all state."""
        engine = TaxEngine()

        # Process some events
        engine.process_event(
            StockEvent(
                event_date=date(2021, 5, 17),
                event_type=EventType.VEST,
                shares=Decimal("100"),
                price_usd=Decimal("50.00"),
                fx_rate=Decimal("0.82"),
            )
        )

        assert engine.state.total_shares == Decimal("100")
        assert len(engine.processed_events) == 1

        # Reset
        engine.reset()

        assert engine.state.total_shares == Decimal("0")
        assert engine.state.avg_cost_eur == Decimal("0")
        assert len(engine.processed_events) == 0

    def test_process_all_resets_first(self, basic_event_sequence):
        """Test that process_all resets state before processing."""
        engine = TaxEngine()

        # Process once
        engine.process_all(basic_event_sequence)
        first_total = engine.state.total_shares

        # Process again - should get same result (was reset)
        engine.process_all(basic_event_sequence)

        assert engine.state.total_shares == first_total


class TestTaxEngineYearlySummary:
    """Tests for yearly tax summary generation."""

    def test_yearly_summary_tracks_gains(self):
        """Test that gains are tracked in yearly summary."""
        engine = TaxEngine()

        # Vest then sell at profit
        engine.process_event(
            StockEvent(
                event_date=date(2021, 5, 17),
                event_type=EventType.VEST,
                shares=Decimal("100"),
                price_usd=Decimal("40.00"),
                fx_rate=Decimal("0.82"),
            )
        )
        engine.process_event(
            StockEvent(
                event_date=date(2021, 7, 15),
                event_type=EventType.SELL,
                shares=Decimal("50"),
                price_usd=Decimal("60.00"),
                fx_rate=Decimal("0.82"),
            )
        )

        summary = engine.get_yearly_summary(2021)
        assert summary is not None
        assert summary.total_gains > 0

    def test_yearly_summary_tracks_losses(self):
        """Test that losses are tracked in yearly summary."""
        engine = TaxEngine()

        # Vest then sell at loss
        engine.process_event(
            StockEvent(
                event_date=date(2021, 5, 17),
                event_type=EventType.VEST,
                shares=Decimal("100"),
                price_usd=Decimal("60.00"),
                fx_rate=Decimal("0.82"),
            )
        )
        engine.process_event(
            StockEvent(
                event_date=date(2021, 7, 15),
                event_type=EventType.SELL,
                shares=Decimal("50"),
                price_usd=Decimal("40.00"),
                fx_rate=Decimal("0.82"),
            )
        )

        summary = engine.get_yearly_summary(2021)
        assert summary is not None
        assert summary.total_losses < 0

    def test_multi_year_summaries(self, multi_year_events):
        """Test summaries across multiple years."""
        engine = TaxEngine()
        engine.process_all(multi_year_events)

        summaries = engine.get_all_yearly_summaries()

        # Should have entries for 2021 and 2022
        years = [s.year for s in summaries]
        assert 2021 in years
        assert 2022 in years

    def test_get_yearly_summary_nonexistent_year(self):
        """Test getting summary for a year with no events."""
        engine = TaxEngine()

        engine.process_event(
            StockEvent(
                event_date=date(2021, 5, 17),
                event_type=EventType.VEST,
                shares=Decimal("100"),
                price_usd=Decimal("50.00"),
                fx_rate=Decimal("0.82"),
            )
        )

        # 2020 has no events
        summary = engine.get_yearly_summary(2020)
        assert summary is None

    def test_acquisition_only_year_no_gains_losses(self):
        """Test that a year with only acquisitions has no gains/losses."""
        engine = TaxEngine()

        engine.process_event(
            StockEvent(
                event_date=date(2021, 5, 17),
                event_type=EventType.VEST,
                shares=Decimal("100"),
                price_usd=Decimal("50.00"),
                fx_rate=Decimal("0.82"),
            )
        )

        summary = engine.get_yearly_summary(2021)
        assert summary.total_gains == Decimal("0")
        assert summary.total_losses == Decimal("0")


class TestFinanzOnlineOutput:
    """Tests for FinanzOnline Kennzahl output in console and HTML report."""

    def _build_engine_with_gain_and_loss(self):
        """Helper: build an engine with a gain in 2021 and a loss in 2022."""
        engine = TaxEngine()
        # 2021: vest 100 @ $40 (€32.80), sell 50 @ $60 (€49.20) → gain
        engine.process_event(
            StockEvent(
                event_date=date(2021, 1, 15),
                event_type=EventType.VEST,
                shares=Decimal("100"),
                price_usd=Decimal("40.00"),
                fx_rate=Decimal("0.82"),
            )
        )
        engine.process_event(
            StockEvent(
                event_date=date(2021, 6, 15),
                event_type=EventType.SELL,
                shares=Decimal("50"),
                price_usd=Decimal("60.00"),
                fx_rate=Decimal("0.82"),
            )
        )
        # 2022: sell 50 @ $20 (€16.40) → loss
        engine.process_event(
            StockEvent(
                event_date=date(2022, 3, 10),
                event_type=EventType.SELL,
                shares=Decimal("50"),
                price_usd=Decimal("20.00"),
                fx_rate=Decimal("0.82"),
            )
        )
        return engine

    def test_print_tax_summary_contains_kennzahl_994(self, capsys):
        """Console output should contain Kennzahl 994 with gains."""
        engine = self._build_engine_with_gain_and_loss()
        engine.print_tax_summary()
        output = capsys.readouterr().out

        assert "Kennzahl 994" in output
        assert "FINANZONLINE" in output

    def test_print_tax_summary_contains_kennzahl_892(self, capsys):
        """Console output should contain Kennzahl 892 with losses."""
        engine = self._build_engine_with_gain_and_loss()
        engine.print_tax_summary()
        output = capsys.readouterr().out

        assert "Kennzahl 892" in output

    def test_print_tax_summary_losses_are_negative(self, capsys):
        """Kennzahl 892 losses should be shown as negative numbers."""
        engine = self._build_engine_with_gain_and_loss()
        engine.print_tax_summary()
        output = capsys.readouterr().out

        # Find the 2022 Kennzahl 892 line — losses must be negative
        for line in output.splitlines():
            if "Kennzahl 892" in line and "2022" not in line:
                continue
            if "Kennzahl 892" in line:
                # The value after € should be negative
                assert "-" in line, "Kennzahl 892 losses must be negative"

    def test_html_report_contains_kennzahl_section(self):
        """HTML report should contain FinanzOnline Kennzahl section."""
        engine = self._build_engine_with_gain_and_loss()
        html = engine.generate_html_content()

        assert "Kennzahl 994" in html
        assert "Kennzahl 892" in html
        assert "FinanzOnline" in html

    def test_html_report_losses_are_negative(self):
        """Kennzahl 892 in HTML should show losses as negative."""
        engine = self._build_engine_with_gain_and_loss()
        html = engine.generate_html_content()

        assert "negative number" in html


class TestTaxEngineEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_fractional_shares(self):
        """Test handling of fractional shares."""
        engine = TaxEngine()

        event = StockEvent(
            event_date=date(2021, 5, 17),
            event_type=EventType.VEST,
            shares=Decimal("63.5432"),
            price_usd=Decimal("46.68"),
            fx_rate=Decimal("0.8214"),
        )

        engine.process_event(event)
        assert engine.state.total_shares == Decimal("63.5432")

    def test_very_small_price(self):
        """Test handling of very small prices."""
        engine = TaxEngine()

        event = StockEvent(
            event_date=date(2021, 5, 17),
            event_type=EventType.VEST,
            shares=Decimal("1000000"),
            price_usd=Decimal("0.0001"),
            fx_rate=Decimal("0.82"),
        )

        engine.process_event(event)
        assert engine.state.total_shares == Decimal("1000000")

    def test_very_large_numbers(self):
        """Test handling of very large numbers."""
        engine = TaxEngine()

        event = StockEvent(
            event_date=date(2021, 5, 17),
            event_type=EventType.VEST,
            shares=Decimal("1000000"),
            price_usd=Decimal("10000.00"),
            fx_rate=Decimal("0.82"),
        )

        engine.process_event(event)
        # Should handle 10 billion EUR portfolio
        assert engine.state.total_portfolio_cost_eur == Decimal("8200000000.0000")

    def test_empty_events_list(self):
        """Test processing empty events list."""
        engine = TaxEngine()
        results = engine.process_all([])

        assert results == []
        assert engine.state.total_shares == Decimal("0")

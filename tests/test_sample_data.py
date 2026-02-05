"""
Test the tax engine using the sample data example.

This test verifies that the engine produces correct results with the sample data,
preserving the original example that was in main.py.
"""

from datetime import date
from decimal import Decimal

import pytest

from tax_engine import (
    TaxEngine,
    create_sample_events_with_ecb_rates,
    prefetch_ecb_rates,
)


def test_sample_data_with_ecb_rates():
    """
    Test the tax engine with sample data using ECB rates.

    This test preserves the original example from main.py and verifies:
    - Transaction ledger calculations (gains/losses)
    - Yearly tax summary
    - Final position state
    """
    # Create events and fetch ECB rates
    events = create_sample_events_with_ecb_rates()
    prefetch_ecb_rates(events)

    # Process events
    engine = TaxEngine()
    engine.process_all(events)

    # Verify final position state
    assert engine.state.total_shares == 63
    assert engine.state.avg_cost_eur == pytest.approx(Decimal("45.7701"), abs=Decimal("0.0001"))
    assert engine.state.total_portfolio_cost_eur == pytest.approx(
        Decimal("2883.5266"), abs=Decimal("0.0001")
    )

    # Verify we have processed events for all stock events
    assert len(engine.processed_events) == 13

    # Verify specific transaction details
    # First transaction: 2020-11-27 BUY
    pe0 = engine.processed_events[0]
    assert pe0.event.event_date == date(2020, 11, 27)
    assert pe0.event.event_type.value == "BUY"
    assert pe0.event.shares == 50
    assert pe0.event.price_usd == pytest.approx(Decimal("38.42"), abs=Decimal("0.01"))
    assert pe0.total_shares_after == 50
    assert pe0.avg_cost_eur_after == pytest.approx(Decimal("32.2267"), abs=Decimal("0.0001"))

    # 2021-02-03 SELL - first profitable sale
    pe1 = engine.processed_events[1]
    assert pe1.event.event_date == date(2021, 2, 3)
    assert pe1.event.event_type.value == "SELL"
    assert pe1.event.shares == 50
    assert pe1.total_shares_after == 0
    assert pe1.realized_gain_loss == pytest.approx(Decimal("421.3150"), abs=Decimal("0.0001"))

    # 2021-05-17 SELL - first loss
    pe3 = engine.processed_events[3]
    assert pe3.event.event_date == date(2021, 5, 17)
    assert pe3.event.event_type.value == "SELL"
    assert pe3.event.shares == 25
    assert pe3.realized_gain_loss == pytest.approx(Decimal("-38.2925"), abs=Decimal("0.0001"))

    # 2022-06-01 SELL - large loss
    pe12 = engine.processed_events[12]
    assert pe12.event.event_date == date(2022, 6, 1)
    assert pe12.event.event_type.value == "SELL"
    assert pe12.event.shares == 205
    assert pe12.realized_gain_loss == pytest.approx(Decimal("-1890.8380"), abs=Decimal("0.0001"))

    # Verify yearly tax summary
    summaries = engine.get_all_yearly_summaries()
    tax_summary = {s.year: s for s in summaries}

    # 2020: No taxable events
    assert 2020 in tax_summary
    summary_2020 = tax_summary[2020]
    assert summary_2020.total_gains == pytest.approx(Decimal("0.00"), abs=Decimal("0.01"))
    assert summary_2020.total_losses == pytest.approx(Decimal("0.00"), abs=Decimal("0.01"))
    assert summary_2020.net_gain_loss == pytest.approx(Decimal("0.00"), abs=Decimal("0.01"))
    assert summary_2020.taxable_gain == pytest.approx(Decimal("0.00"), abs=Decimal("0.01"))
    assert summary_2020.kest_due == pytest.approx(Decimal("0.00"), abs=Decimal("0.01"))

    # 2021: Net gain
    assert 2021 in tax_summary
    summary_2021 = tax_summary[2021]
    assert summary_2021.total_gains == pytest.approx(Decimal("530.98"), abs=Decimal("0.01"))
    assert summary_2021.total_losses == pytest.approx(Decimal("-39.05"), abs=Decimal("0.01"))
    assert summary_2021.net_gain_loss == pytest.approx(Decimal("491.93"), abs=Decimal("0.01"))
    assert summary_2021.taxable_gain == pytest.approx(Decimal("491.93"), abs=Decimal("0.01"))
    assert summary_2021.kest_due == pytest.approx(Decimal("135.28"), abs=Decimal("0.01"))

    # 2022: Net loss
    assert 2022 in tax_summary
    summary_2022 = tax_summary[2022]
    assert summary_2022.total_gains == pytest.approx(Decimal("0.00"), abs=Decimal("0.01"))
    assert summary_2022.total_losses == pytest.approx(Decimal("-1890.84"), abs=Decimal("0.01"))
    assert summary_2022.net_gain_loss == pytest.approx(Decimal("-1890.84"), abs=Decimal("0.01"))
    assert summary_2022.taxable_gain == pytest.approx(Decimal("0.00"), abs=Decimal("0.01"))
    assert summary_2022.kest_due == pytest.approx(Decimal("0.00"), abs=Decimal("0.01"))


def test_sample_data_ledger_output(capsys):
    """
    Test that the ledger output can be printed without errors.
    This ensures the output formatting works correctly.
    """
    events = create_sample_events_with_ecb_rates()
    prefetch_ecb_rates(events)

    engine = TaxEngine()
    engine.process_all(events)

    # Print outputs (captured by capsys)
    engine.print_ledger()
    engine.print_tax_summary()

    # Verify output contains expected content
    captured = capsys.readouterr()
    assert "TRANSACTION LEDGER" in captured.out
    assert "YEARLY TAX SUMMARY" in captured.out
    assert "2020" in captured.out
    assert "2021" in captured.out
    assert "2022" in captured.out

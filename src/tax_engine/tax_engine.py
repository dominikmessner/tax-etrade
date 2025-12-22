"""
Austrian Tax Engine Core Logic.

Implements the moving average cost basis method (Gleitender Durchschnittspreis)
required by Austrian tax law for calculating capital gains on stocks.
"""

from decimal import Decimal, ROUND_HALF_UP
from typing import Optional
from collections import defaultdict

from .models import (
    EventType,
    StockEvent,
    ProcessedEvent,
    YearlyTaxSummary,
    TaxEngineState,
)


class TaxEngine:
    """
    Austrian Tax Engine using Moving Average Cost Basis.
    
    Implements the Gleitender Durchschnittspreis method required by
    Austrian tax law (Finanzamt) for calculating capital gains on stocks.
    
    Rules implemented:
    - Rule A: Moving average recalculated on every acquisition (VEST/BUY)
    - Rule B: Selling doesn't change the average cost, only reduces quantity
    - Rule C: Cannot sell more shares than currently held (depot check)
    """
    
    def __init__(self):
        self.state = TaxEngineState()
        self.processed_events: list[ProcessedEvent] = []
        self.yearly_summaries: dict[int, YearlyTaxSummary] = defaultdict(
            lambda: YearlyTaxSummary(year=0)
        )
    
    def reset(self):
        """Reset the engine to initial state."""
        self.state = TaxEngineState()
        self.processed_events = []
        self.yearly_summaries = defaultdict(lambda: YearlyTaxSummary(year=0))
    
    def _sort_events(self, events: list[StockEvent]) -> list[StockEvent]:
        """
        Sort events by date, with acquisitions before sells on same day.
        
        This is critical for correct processing - if a VEST and SELL happen
        on the same day (common with sell-to-cover), the VEST must be 
        processed first.
        """
        def sort_key(event: StockEvent) -> tuple:
            # Primary: date
            # Secondary: event type priority (VEST=0, BUY=1, SELL=2)
            type_priority = {
                EventType.VEST: 0,
                EventType.BUY: 1,
                EventType.SELL: 2,
            }
            return (event.event_date, type_priority[event.event_type])
        
        return sorted(events, key=sort_key)
    
    def _process_acquisition(self, event: StockEvent) -> ProcessedEvent:
        """
        Process a BUY or VEST event.
        
        Updates the moving average cost basis using the formula:
        new_avg = (old_total_cost + new_cost) / (old_shares + new_shares)
        """
        new_cost_eur = event.total_value_eur
        new_shares = event.shares
        
        # Calculate new average cost (moving average formula)
        old_total_cost = self.state.total_shares * self.state.avg_cost_eur
        new_total_cost = old_total_cost + new_cost_eur
        new_total_shares = self.state.total_shares + new_shares
        
        if new_total_shares > 0:
            new_avg_cost = (new_total_cost / new_total_shares).quantize(
                Decimal("0.0001"), ROUND_HALF_UP
            )
        else:
            new_avg_cost = Decimal("0")
        
        # Update state
        self.state.total_shares = new_total_shares
        self.state.avg_cost_eur = new_avg_cost
        self.state.total_portfolio_cost_eur = new_total_cost.quantize(
            Decimal("0.0001"), ROUND_HALF_UP
        )
        
        return ProcessedEvent(
            event=event,
            total_shares_after=self.state.total_shares,
            avg_cost_eur_after=self.state.avg_cost_eur,
            realized_gain_loss=Decimal("0"),
            cost_change_eur=new_cost_eur,
            total_portfolio_cost_eur=self.state.total_portfolio_cost_eur,
        )
    
    def _process_sell(self, event: StockEvent) -> ProcessedEvent:
        """
        Process a SELL event.
        
        The average cost stays the same (Rule B).
        Calculates realized gain/loss = (sell_price - avg_cost) * shares
        """
        shares_sold = event.shares
        
        # Rule C: Depot check - cannot sell more than we have
        if shares_sold > self.state.total_shares:
            raise ValueError(
                f"Cannot sell {shares_sold} shares on {event.event_date}. "
                f"Only {self.state.total_shares} shares held. "
                f"Check for timing issues with sell-to-cover transactions."
            )
        
        # Calculate realized gain/loss
        sell_price_eur = event.price_eur
        gain_loss = ((sell_price_eur - self.state.avg_cost_eur) * shares_sold).quantize(
            Decimal("0.0001"), ROUND_HALF_UP
        )
        
        # Cost basis removed from portfolio
        cost_removed = (self.state.avg_cost_eur * shares_sold).quantize(
            Decimal("0.0001"), ROUND_HALF_UP
        )
        
        # Update state (avg_cost stays the same per Rule B)
        self.state.total_shares -= shares_sold
        self.state.total_portfolio_cost_eur -= cost_removed
        
        # Handle floating point edge case when selling all shares
        if self.state.total_shares == 0:
            self.state.avg_cost_eur = Decimal("0")
            self.state.total_portfolio_cost_eur = Decimal("0")
        
        return ProcessedEvent(
            event=event,
            total_shares_after=self.state.total_shares,
            avg_cost_eur_after=self.state.avg_cost_eur,
            realized_gain_loss=gain_loss,
            cost_change_eur=-cost_removed,
            total_portfolio_cost_eur=self.state.total_portfolio_cost_eur,
        )
    
    def process_event(self, event: StockEvent) -> ProcessedEvent:
        """Process a single stock event."""
        if event.event_type in (EventType.VEST, EventType.BUY):
            result = self._process_acquisition(event)
        elif event.event_type == EventType.SELL:
            result = self._process_sell(event)
        else:
            raise ValueError(f"Unknown event type: {event.event_type}")
        
        # Track for yearly summary
        year = event.event_date.year
        if year not in self.yearly_summaries:
            self.yearly_summaries[year] = YearlyTaxSummary(year=year)
        
        if result.realized_gain_loss > 0:
            self.yearly_summaries[year].total_gains += result.realized_gain_loss
        elif result.realized_gain_loss < 0:
            self.yearly_summaries[year].total_losses += result.realized_gain_loss
        
        self.processed_events.append(result)
        return result
    
    def process_all(self, events: list[StockEvent]) -> list[ProcessedEvent]:
        """
        Process all events in chronological order.
        
        Sorts events by date (acquisitions before sells on same day),
        then processes each one sequentially.
        """
        self.reset()
        sorted_events = self._sort_events(events)
        
        for event in sorted_events:
            self.process_event(event)
        
        return self.processed_events
    
    def get_yearly_summary(self, year: int) -> Optional[YearlyTaxSummary]:
        """Get the tax summary for a specific year."""
        return self.yearly_summaries.get(year)
    
    def get_all_yearly_summaries(self) -> list[YearlyTaxSummary]:
        """Get all yearly tax summaries, sorted by year."""
        return sorted(self.yearly_summaries.values(), key=lambda s: s.year)
    
    def print_ledger(self):
        """Print the full transaction ledger in a readable format."""
        print("\n" + "=" * 120)
        print("TRANSACTION LEDGER")
        print("=" * 120)
        print(
            f"{'Date':<12} {'Type':<6} {'Shares':>10} {'Price USD':>12} "
            f"{'FX Rate':>10} {'Price EUR':>12} {'Total Qty':>10} "
            f"{'Avg Cost':>12} {'Gain/Loss':>12}"
        )
        print("-" * 120)
        
        for pe in self.processed_events:
            e = pe.event
            shares_str = f"+{e.shares}" if e.event_type != EventType.SELL else f"-{e.shares}"
            gain_str = f"€{pe.realized_gain_loss:,.4f}" if pe.realized_gain_loss != 0 else ""
            
            print(
                f"{e.event_date.isoformat():<12} {e.event_type.value:<6} "
                f"{shares_str:>10} ${e.price_usd:>11,.2f} "
                f"{e.resolved_fx_rate:>10.4f} €{e.price_eur:>11,.4f} "
                f"{pe.total_shares_after:>10} €{pe.avg_cost_eur_after:>11,.4f} "
                f"{gain_str:>12}"
            )
        
        print("=" * 120)
    
    def print_tax_summary(self):
        """Print the yearly tax summary."""
        print("\n" + "=" * 80)
        print("YEARLY TAX SUMMARY")
        print("=" * 80)
        print(
            f"{'Year':<8} {'Gains':>15} {'Losses':>15} "
            f"{'Net G/L':>15} {'Taxable':>15} {'KESt Due':>15}"
        )
        print("-" * 80)
        
        for summary in self.get_all_yearly_summaries():
            print(
                f"{summary.year:<8} €{summary.total_gains:>14,.2f} "
                f"€{summary.total_losses:>14,.2f} €{summary.net_gain_loss:>14,.2f} "
                f"€{summary.taxable_gain:>14,.2f} €{summary.kest_due:>14,.2f}"
            )
        
        print("=" * 80)

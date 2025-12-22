"""
Austrian Tax Engine for E-Trade RSUs and ESPP

Calculates capital gains tax using the Austrian moving average cost basis method
(Gleitender Durchschnittspreis) for stocks acquired through RSU vesting and ESPP purchases.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Optional
from collections import defaultdict
import urllib.request
import xml.etree.ElementTree as ET
from functools import lru_cache


class ECBRateFetcher:
    """
    Fetches USD/EUR exchange rates from the European Central Bank.
    
    Uses the ECB Statistical Data Warehouse API to get official daily rates.
    These are the rates accepted by the Austrian Finanzamt.
    """
    
    # ECB API endpoint for USD/EUR daily exchange rates
    ECB_API_URL = (
        "https://data-api.ecb.europa.eu/service/data/EXR/D.USD.EUR.SP00.A"
        "?startPeriod={start}&endPeriod={end}&format=structurespecificdata"
    )
    
    # Cache for rates (date -> rate)
    _rate_cache: dict[date, Decimal] = {}
    
    @classmethod
    def _fetch_rates_for_period(cls, start_date: date, end_date: date) -> dict[date, Decimal]:
        """Fetch rates from ECB API for a date range."""
        url = cls.ECB_API_URL.format(
            start=start_date.isoformat(),
            end=end_date.isoformat()
        )
        
        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                xml_data = response.read()
        except Exception as e:
            raise RuntimeError(f"Failed to fetch ECB rates: {e}")
        
        # Parse the XML response
        root = ET.fromstring(xml_data)
        
        # ECB uses namespaces in their XML
        namespaces = {
            'generic': 'http://www.sdmx.org/resources/sdmxml/schemas/v2_1/data/structurespecific',
            'message': 'http://www.sdmx.org/resources/sdmxml/schemas/v2_1/message'
        }
        
        rates = {}
        
        # Find all Obs (observation) elements
        for obs in root.iter():
            if obs.tag.endswith('}Obs') or obs.tag == 'Obs':
                time_period = obs.get('TIME_PERIOD')
                obs_value = obs.get('OBS_VALUE')
                
                if time_period and obs_value:
                    rate_date = date.fromisoformat(time_period)
                    # ECB publishes EUR/USD, we need USD/EUR (inverse)
                    eur_usd_rate = Decimal(obs_value)
                    usd_eur_rate = (Decimal("1") / eur_usd_rate).quantize(
                        Decimal("0.0001"), ROUND_HALF_UP
                    )
                    rates[rate_date] = usd_eur_rate
        
        return rates
    
    @classmethod
    def get_rate(cls, target_date: date) -> Decimal:
        """
        Get the USD/EUR exchange rate for a specific date.
        
        If the target date is a weekend or holiday (no rate published),
        returns the most recent available rate before that date.
        """
        # Check cache first
        if target_date in cls._rate_cache:
            return cls._rate_cache[target_date]
        
        # Fetch a range around the target date to handle weekends/holidays
        # Go back 10 days to ensure we get a rate
        start_date = target_date - timedelta(days=10)
        end_date = target_date
        
        rates = cls._fetch_rates_for_period(start_date, end_date)
        cls._rate_cache.update(rates)
        
        # Find the rate for target date or most recent before it
        if target_date in rates:
            return rates[target_date]
        
        # Find the most recent rate before target date
        available_dates = sorted([d for d in rates.keys() if d <= target_date], reverse=True)
        if available_dates:
            closest_date = available_dates[0]
            # Cache this lookup for the target date too
            cls._rate_cache[target_date] = rates[closest_date]
            return rates[closest_date]
        
        raise ValueError(f"No ECB rate available for or before {target_date}")
    
    @classmethod
    def get_rates_bulk(cls, dates: list[date]) -> dict[date, Decimal]:
        """
        Fetch rates for multiple dates efficiently in a single API call.
        
        Returns a dict mapping each requested date to its rate.
        """
        if not dates:
            return {}
        
        # Find date range
        min_date = min(dates) - timedelta(days=10)  # Buffer for weekends
        max_date = max(dates)
        
        # Fetch all rates in range
        rates = cls._fetch_rates_for_period(min_date, max_date)
        cls._rate_cache.update(rates)
        
        # Map each requested date to its rate (or nearest previous)
        result = {}
        sorted_available = sorted(rates.keys())
        
        for target_date in dates:
            if target_date in rates:
                result[target_date] = rates[target_date]
            else:
                # Find nearest previous date
                for d in reversed(sorted_available):
                    if d <= target_date:
                        result[target_date] = rates[d]
                        cls._rate_cache[target_date] = rates[d]
                        break
                else:
                    raise ValueError(f"No ECB rate available for or before {target_date}")
        
        return result
    
    @classmethod
    def clear_cache(cls):
        """Clear the rate cache."""
        cls._rate_cache.clear()


class EventType(Enum):
    """Types of stock events."""
    VEST = "VEST"      # RSU vesting - treated as acquisition at market price
    BUY = "BUY"        # ESPP purchase
    SELL = "SELL"      # Manual sell or sell-to-cover


@dataclass
class StockEvent:
    """
    Represents a single stock event (vest, buy, or sell).
    
    Attributes:
        event_date: The date of the event
        event_type: VEST, BUY, or SELL
        shares: Number of shares (positive for buys/vests, positive for sells too)
        price_usd: Price per share in USD
        fx_rate: USD to EUR exchange rate on that day (optional - will be fetched from ECB if None)
        notes: Optional notes for the transaction
    """
    event_date: date
    event_type: EventType
    shares: Decimal
    price_usd: Decimal
    fx_rate: Optional[Decimal] = None
    notes: str = ""
    _fx_rate_resolved: Decimal = field(default=None, init=False, repr=False)
    
    @property
    def resolved_fx_rate(self) -> Decimal:
        """Get the FX rate, fetching from ECB if not provided."""
        if self._fx_rate_resolved is not None:
            return self._fx_rate_resolved
        
        if self.fx_rate is not None:
            self._fx_rate_resolved = self.fx_rate
        else:
            self._fx_rate_resolved = ECBRateFetcher.get_rate(self.event_date)
        
        return self._fx_rate_resolved
    
    @property
    def price_eur(self) -> Decimal:
        """Calculate the price per share in EUR."""
        return (self.price_usd * self.resolved_fx_rate).quantize(Decimal("0.0001"), ROUND_HALF_UP)
    
    @property
    def total_value_eur(self) -> Decimal:
        """Calculate total transaction value in EUR."""
        return (self.shares * self.price_eur).quantize(Decimal("0.0001"), ROUND_HALF_UP)
    
    def __post_init__(self):
        """Convert numeric fields to Decimal if needed."""
        if not isinstance(self.shares, Decimal):
            self.shares = Decimal(str(self.shares))
        if not isinstance(self.price_usd, Decimal):
            self.price_usd = Decimal(str(self.price_usd))
        if self.fx_rate is not None and not isinstance(self.fx_rate, Decimal):
            self.fx_rate = Decimal(str(self.fx_rate))


def prefetch_ecb_rates(events: list[StockEvent]) -> None:
    """
    Pre-fetch ECB rates for all events that don't have fx_rate specified.
    
    This is more efficient than fetching one at a time, as it makes
    a single API call for the entire date range.
    """
    dates_needed = [e.event_date for e in events if e.fx_rate is None]
    if dates_needed:
        print(f"Fetching ECB rates for {len(dates_needed)} dates...")
        ECBRateFetcher.get_rates_bulk(dates_needed)
        print("Done.")


@dataclass
class ProcessedEvent:
    """
    Result of processing a stock event through the tax engine.
    
    Contains the original event plus calculated values.
    """
    event: StockEvent
    total_shares_after: Decimal
    avg_cost_eur_after: Decimal
    realized_gain_loss: Decimal = Decimal("0")
    cost_change_eur: Decimal = Decimal("0")
    total_portfolio_cost_eur: Decimal = Decimal("0")


@dataclass
class YearlyTaxSummary:
    """Tax summary for a single year."""
    year: int
    total_gains: Decimal = Decimal("0")
    total_losses: Decimal = Decimal("0")
    
    @property
    def net_gain_loss(self) -> Decimal:
        """Net gain/loss for the year (losses can offset gains within same year)."""
        return self.total_gains + self.total_losses
    
    @property
    def taxable_gain(self) -> Decimal:
        """
        Taxable gain after offsetting losses.
        In Austria, losses can offset gains within the same year,
        but cannot be carried forward to future years.
        """
        return max(Decimal("0"), self.net_gain_loss)
    
    @property
    def kest_due(self) -> Decimal:
        """
        KESt (Kapitalertragsteuer) due at 27.5% rate.
        """
        return (self.taxable_gain * Decimal("0.275")).quantize(Decimal("0.01"), ROUND_HALF_UP)


@dataclass 
class TaxEngineState:
    """
    Current state of the tax engine.
    
    Tracks the portfolio position and moving average cost basis.
    """
    total_shares: Decimal = Decimal("0")
    avg_cost_eur: Decimal = Decimal("0")
    total_portfolio_cost_eur: Decimal = Decimal("0")
    
    def clone(self) -> "TaxEngineState":
        """Create a copy of the current state."""
        return TaxEngineState(
            total_shares=self.total_shares,
            avg_cost_eur=self.avg_cost_eur,
            total_portfolio_cost_eur=self.total_portfolio_cost_eur,
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


def create_sample_events_with_manual_fx() -> list[StockEvent]:
    """
    Create sample events with manually specified FX rates (from the original spreadsheet).
    This serves as a test case to verify the engine works correctly.
    """
    return [
        # 2020
        StockEvent(date(2020, 11, 27), EventType.BUY, 50, Decimal("38.42"), Decimal("0.8388"), "ESPP Buy"),
        
        # 2021
        StockEvent(date(2021, 2, 3), EventType.SELL, 50, Decimal("48.85"), Decimal("0.8322"), "Manual Sell"),
        StockEvent(date(2021, 5, 17), EventType.VEST, 30, Decimal("46.68"), Decimal("0.8235"), "RSU Vest"),
        StockEvent(date(2021, 5, 17), EventType.SELL, 25, Decimal("44.82"), Decimal("0.8235"), "RSU Sell (sell-to-cover)"),
        StockEvent(date(2021, 5, 17), EventType.SELL, 2, Decimal("46.22"), Decimal("0.8235"), "RSU Sell"),
        StockEvent(date(2021, 5, 28), EventType.BUY, 50, Decimal("51.74"), Decimal("0.8236"), "ESPP Buy"),
        StockEvent(date(2021, 8, 16), EventType.VEST, 10, Decimal("63.65"), Decimal("0.8495"), "RSU Vest"),
        StockEvent(date(2021, 8, 16), EventType.SELL, 5, Decimal("61.25"), Decimal("0.8495"), "RSU Sell (sell-to-cover)"),
        StockEvent(date(2021, 11, 15), EventType.VEST, 10, Decimal("70.68"), Decimal("0.8738"), "RSU Vest"),
        StockEvent(date(2021, 11, 16), EventType.SELL, 5, Decimal("69.28"), Decimal("0.8797"), "RSU Sell"),
        StockEvent(date(2021, 11, 26), EventType.BUY, 100, Decimal("62.97"), Decimal("0.8857"), "ESPP Buy"),
        
        # 2022
        StockEvent(date(2022, 5, 27), EventType.BUY, 105, Decimal("38.19"), Decimal("0.9327"), "ESPP Buy"),
        StockEvent(date(2022, 6, 1), EventType.SELL, 205, Decimal("39.15"), Decimal("0.9335"), "Manual Sell"),
    ]


def create_sample_events_with_ecb_rates() -> list[StockEvent]:
    """
    Create sample events WITHOUT FX rates - they will be fetched from ECB automatically.
    This demonstrates the automatic rate fetching feature.
    """
    return [
        # 2020
        StockEvent(date(2020, 11, 27), EventType.BUY, 50, Decimal("38.42"), notes="ESPP Buy"),
        
        # 2021
        StockEvent(date(2021, 2, 3), EventType.SELL, 50, Decimal("48.85"), notes="Manual Sell"),
        StockEvent(date(2021, 5, 17), EventType.VEST, 30, Decimal("46.68"), notes="RSU Vest"),
        StockEvent(date(2021, 5, 17), EventType.SELL, 25, Decimal("44.82"), notes="RSU Sell (sell-to-cover)"),
        StockEvent(date(2021, 5, 17), EventType.SELL, 2, Decimal("46.22"), notes="RSU Sell"),
        StockEvent(date(2021, 5, 28), EventType.BUY, 50, Decimal("51.74"), notes="ESPP Buy"),
        StockEvent(date(2021, 8, 16), EventType.VEST, 10, Decimal("63.65"), notes="RSU Vest"),
        StockEvent(date(2021, 8, 16), EventType.SELL, 5, Decimal("61.25"), notes="RSU Sell (sell-to-cover)"),
        StockEvent(date(2021, 11, 15), EventType.VEST, 10, Decimal("70.68"), notes="RSU Vest"),
        StockEvent(date(2021, 11, 16), EventType.SELL, 5, Decimal("69.28"), notes="RSU Sell"),
        StockEvent(date(2021, 11, 26), EventType.BUY, 100, Decimal("62.97"), notes="ESPP Buy"),
        
        # 2022
        StockEvent(date(2022, 5, 27), EventType.BUY, 105, Decimal("38.19"), notes="ESPP Buy"),
        StockEvent(date(2022, 6, 1), EventType.SELL, 205, Decimal("39.15"), notes="Manual Sell"),
    ]


def main():
    """Run the tax engine with sample data using ECB rates."""
    print("Austrian Tax Engine for E-Trade RSUs and ESPP")
    print("Using Moving Average Cost Basis (Gleitender Durchschnittspreis)")
    print()
    
    # Create events without FX rates - they'll be fetched from ECB
    events = create_sample_events_with_ecb_rates()
    
    # Pre-fetch all ECB rates in one API call (more efficient)
    prefetch_ecb_rates(events)
    
    # Create engine and process events
    engine = TaxEngine()
    engine.process_all(events)
    
    # Print results
    engine.print_ledger()
    engine.print_tax_summary()
    
    # Show current state
    print(f"\nCurrent Position: {engine.state.total_shares} shares")
    print(f"Current Avg Cost: €{engine.state.avg_cost_eur:,.4f}")
    print(f"Total Portfolio Cost: €{engine.state.total_portfolio_cost_eur:,.4f}")


if __name__ == "__main__":
    main()

"""
Data models for the Austrian Tax Engine.

Contains all dataclasses and enums used throughout the application.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from enum import Enum


class EventType(Enum):
    """Types of stock events."""

    VEST = "VEST"  # RSU vesting - treated as acquisition at market price
    BUY = "BUY"  # ESPP purchase
    SELL = "SELL"  # Manual sell or sell-to-cover


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
    fx_rate: Decimal | None = None
    notes: str = ""
    _fx_rate_resolved: Decimal | None = field(default=None, init=False, repr=False)

    @property
    def resolved_fx_rate(self) -> Decimal:
        """Get the FX rate, fetching from ECB if not provided."""
        if self._fx_rate_resolved is not None:
            return self._fx_rate_resolved

        if self.fx_rate is not None:
            self._fx_rate_resolved = self.fx_rate
        else:
            # Import here to avoid circular dependency
            from .ecb_rates import ECBRateFetcher

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

    def __post_init__(self) -> None:
        """Convert numeric fields to Decimal if needed."""
        if not isinstance(self.shares, Decimal):
            object.__setattr__(self, "shares", Decimal(str(self.shares)))
        if not isinstance(self.price_usd, Decimal):
            object.__setattr__(self, "price_usd", Decimal(str(self.price_usd)))
        if self.fx_rate is not None and not isinstance(self.fx_rate, Decimal):
            object.__setattr__(self, "fx_rate", Decimal(str(self.fx_rate)))


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

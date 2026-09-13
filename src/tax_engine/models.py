"""
Data models for the Austrian Tax Engine.

Contains all dataclasses and enums used throughout the application.
"""

import warnings
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from enum import Enum

# Precision used for all intermediate EUR amounts and share counts.
MONEY_PRECISION = Decimal("0.0001")


class LazyFxRateWarning(UserWarning):
    """Emitted when an FX rate is fetched on-demand instead of via prefetch_ecb_rates()."""


class EventType(Enum):
    """Types of stock events."""

    VEST = "VEST"  # RSU vesting - treated as acquisition at market price
    BUY = "BUY"  # ESPP purchase
    SELL = "SELL"  # Manual sell or sell-to-cover
    EXERCISE = "EXERCISE"  # Stock option exercise - cost basis = FMV at exercise


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

    def set_resolved_fx_rate(self, rate: Decimal) -> None:
        """Pin the FX rate used for this event (called by prefetch_ecb_rates)."""
        self._fx_rate_resolved = rate

    @property
    def resolved_fx_rate(self) -> Decimal:
        """
        Get the FX rate for this event.

        Uses the explicit ``fx_rate`` if given, otherwise the rate pinned by
        ``prefetch_ecb_rates()``. As a last resort the rate is fetched from the
        ECB on demand, which issues one HTTP request per event and emits a
        ``LazyFxRateWarning`` so callers notice they skipped the prefetch step.
        """
        if self._fx_rate_resolved is not None:
            return self._fx_rate_resolved

        if self.fx_rate is not None:
            self._fx_rate_resolved = self.fx_rate
        else:
            # Import here to avoid circular dependency
            from .ecb_rates import ECBRateFetcher

            warnings.warn(
                f"FX rate for {self.event_date} fetched on demand; call "
                "prefetch_ecb_rates(events) first to batch ECB requests.",
                LazyFxRateWarning,
                stacklevel=2,
            )
            self._fx_rate_resolved = ECBRateFetcher.get_rate(self.event_date)

        return self._fx_rate_resolved

    @property
    def price_eur(self) -> Decimal:
        """Calculate the price per share in EUR."""
        return (self.price_usd * self.resolved_fx_rate).quantize(MONEY_PRECISION, ROUND_HALF_UP)

    @property
    def total_value_eur(self) -> Decimal:
        """Calculate total transaction value in EUR."""
        return (self.shares * self.price_eur).quantize(MONEY_PRECISION, ROUND_HALF_UP)

    def __post_init__(self) -> None:
        """Convert numeric fields to Decimal if needed and validate."""
        if not isinstance(self.shares, Decimal):
            self.shares = Decimal(str(self.shares))
        if not isinstance(self.price_usd, Decimal):
            self.price_usd = Decimal(str(self.price_usd))
        if self.fx_rate is not None and not isinstance(self.fx_rate, Decimal):
            self.fx_rate = Decimal(str(self.fx_rate))

        # Validate: shares and price must be finite and positive. NaN is a valid
        # Decimal literal (e.g. from an empty spreadsheet cell) but ordering
        # comparisons against it raise an opaque InvalidOperation, so reject it
        # explicitly with a readable message.
        for name, value in (("Shares", self.shares), ("Price", self.price_usd)):
            if not value.is_finite():
                raise ValueError(f"{name} must be a finite number, got {value}")
            if value <= 0:
                raise ValueError(f"{name} must be positive, got {value}")
        if self.fx_rate is not None:
            if not self.fx_rate.is_finite():
                raise ValueError(f"FX rate must be a finite number, got {self.fx_rate}")
            if self.fx_rate <= 0:
                raise ValueError(f"FX rate must be positive, got {self.fx_rate}")


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
    # Average cost per share in force when this event was applied. For a SELL
    # this is the basis used to compute realized_gain_loss.
    avg_cost_eur_before: Decimal = Decimal("0")


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

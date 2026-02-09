"""
ECB Exchange Rate Fetcher.

Fetches USD/EUR exchange rates from the European Central Bank
Statistical Data Warehouse API.
"""

import ssl
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING

import certifi

if TYPE_CHECKING:
    from .models import StockEvent


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
        url = cls.ECB_API_URL.format(start=start_date.isoformat(), end=end_date.isoformat())

        try:
            ssl_context = ssl.create_default_context(cafile=certifi.where())
            with urllib.request.urlopen(url, timeout=30, context=ssl_context) as response:
                xml_data = response.read()
        except Exception as e:
            raise RuntimeError(f"Failed to fetch ECB rates: {e}") from e

        # Parse the XML response
        root = ET.fromstring(xml_data)

        # ECB uses namespaces in their XML

        rates = {}

        # Find all Obs (observation) elements
        for obs in root.iter():
            if obs.tag.endswith("}Obs") or obs.tag == "Obs":
                time_period = obs.get("TIME_PERIOD")
                obs_value = obs.get("OBS_VALUE")

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
        # Go back 14 days to handle extended holiday periods (e.g., Christmas + New Year)
        start_date = target_date - timedelta(days=14)
        end_date = target_date

        rates = cls._fetch_rates_for_period(start_date, end_date)
        cls._rate_cache.update(rates)

        # Find the rate for target date or most recent before it
        if target_date in rates:
            return rates[target_date]

        # Find the most recent rate before target date
        available_dates = sorted([d for d in rates if d <= target_date], reverse=True)
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
    def clear_cache(cls) -> None:
        """Clear the rate cache."""
        cls._rate_cache.clear()


def prefetch_ecb_rates(events: list["StockEvent"]) -> None:
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

"""
Sample data for testing the tax engine.

Provides functions to create sample stock events with and without FX rates.
"""

from datetime import date
from decimal import Decimal

from .models import EventType, StockEvent


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

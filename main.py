"""
Austrian Tax Engine for E-Trade RSUs and ESPP

Calculates capital gains tax using the Austrian moving average cost basis method
(Gleitender Durchschnittspreis) for stocks acquired through RSU vesting and ESPP purchases.

Main entry point for the application.
"""

from pathlib import Path
from tax_engine import (
    prefetch_ecb_rates,
    TaxEngine,
)


def load_events_from_excel():
    """
    Load stock events from the BenefitHistory.xlsx file.
    
    TODO: Implement Excel parsing to extract stock events.
    This should parse the ESPP data and create StockEvent objects.
    """
    # Placeholder - to be implemented
    raise NotImplementedError(
        "Excel parsing not yet implemented. "
        "See tests/test_sample_data.py for the sample data example."
    )


def main():
    """Run the tax engine with actual data from Excel files."""
    print("Austrian Tax Engine for E-Trade RSUs and ESPP")
    print("Using Moving Average Cost Basis (Gleitender Durchschnittspreis)")
    print()
    
    # Load events from Excel file
    excel_path = Path("input/espp/BenefitHistory.xlsx")
    if not excel_path.exists():
        print(f"Error: {excel_path} not found")
        print("\nTo run the sample example, use: uv run pytest tests/test_sample_data.py -v -s")
        return
    
    events = load_events_from_excel()
    
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

"""
Demo script to run the tax engine with sample data.

This script demonstrates the tax engine functionality using the sample data
that was previously in main.py. Use this to see the example calculations.
"""

from tax_engine import (
    prefetch_ecb_rates,
    TaxEngine,
    create_sample_events_with_ecb_rates,
)


def main():
    """Run the tax engine with sample data using ECB rates."""
    print("Austrian Tax Engine for E-Trade RSUs and ESPP")
    print("Using Moving Average Cost Basis (Gleitender Durchschnittspreis)")
    print("\n** DEMO MODE: Using sample data **\n")
    
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

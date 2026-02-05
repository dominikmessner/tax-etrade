"""
Austrian Tax Engine Core Logic.

Implements the moving average cost basis method (Gleitender Durchschnittspreis)
required by Austrian tax law for calculating capital gains on stocks.
"""

from collections import defaultdict
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from .models import (
    EventType,
    ProcessedEvent,
    StockEvent,
    TaxEngineState,
    YearlyTaxSummary,
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

    def get_yearly_summary(self, year: int) -> YearlyTaxSummary | None:
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
            shares_sign = "+" if e.event_type != EventType.SELL else "-"
            shares_str = f"{shares_sign}{e.shares:,.0f}"
            gain_str = f"€{pe.realized_gain_loss:,.4f}" if pe.realized_gain_loss != 0 else ""

            print(
                f"{e.event_date.isoformat():<12} {e.event_type.value:<6} "
                f"{shares_str:>10} ${e.price_usd:>11,.2f} "
                f"{e.resolved_fx_rate:>10.4f} €{e.price_eur:>11,.4f} "
                f"{pe.total_shares_after:>10,.0f} €{pe.avg_cost_eur_after:>11,.4f} "
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

    def generate_html_content(self) -> str:
        """Generate HTML content for the tax report."""
        html = []
        html.append("<html><head><style>")
        html.append("body { font-family: sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }")
        html.append("table { border-collapse: collapse; width: 100%; margin-bottom: 20px; font-size: 12px; }")
        html.append("th, td { border: 1px solid #ddd; padding: 6px; text-align: left; }")
        html.append("th { background-color: #f2f2f2; }")
        html.append("h1, h2, h3 { color: #333; }")
        html.append(".gain { color: green; }")
        html.append(".loss { color: red; }")
        html.append("code { background-color: #f4f4f4; padding: 2px 4px; border-radius: 4px; }")
        html.append("</style></head><body>")

        html.append("<h1>Austrian Tax Report</h1>")
        html.append(f"<p>Generated on: {date.today().isoformat()}</p>")

        html.append("<h2>Methodology</h2>")
        html.append("<p>This report calculates capital gains using the <strong>Moving Average Cost Basis</strong> (Gleitender Durchschnittspreis) method as required by Austrian tax law.</p>")
        html.append("<h3>Key Rules:</h3>")
        html.append("<ul>")
        html.append("<li><strong>Acquisitions (VEST/BUY)</strong>: Recalculate the moving average cost.<br><code>New Avg = (Old Total Cost + New Cost) / (Old Shares + New Shares)</code></li>")
        html.append("<li><strong>Sales (SELL)</strong>: Do not change the average cost per share.<br><code>Realized Gain/Loss = (Sell Price - Avg Cost) * Shares Sold</code></li>")
        html.append("<li><strong>Currency</strong>: All values are converted to EUR using the daily ECB reference rate.</li>")
        html.append("</ul>")

        html.append("<h2>Yearly Tax Summary</h2>")
        html.append("<table>")
        html.append("<tr><th>Year</th><th>Total Gains</th><th>Total Losses</th><th>Net Gain/Loss</th><th>Taxable Amount</th><th>KESt Due (27.5%)</th></tr>")

        for summary in self.get_all_yearly_summaries():
            net_style = "gain" if summary.net_gain_loss >= 0 else "loss"
            html.append("<tr>")
            html.append(f"<td>{summary.year}</td>")
            html.append(f"<td>€{summary.total_gains:,.2f}</td>")
            html.append(f"<td>€{summary.total_losses:,.2f}</td>")
            html.append(f"<td class='{net_style}'><strong>€{summary.net_gain_loss:,.2f}</strong></td>")
            html.append(f"<td>€{summary.taxable_gain:,.2f}</td>")
            html.append(f"<td><strong>€{summary.kest_due:,.2f}</strong></td>")
            html.append("</tr>")
        html.append("</table>")

        html.append("<h2>Detailed Transaction Ledger</h2>")
        html.append("<p>The following table documents every transaction and its effect on the portfolio cost basis.</p>")

        html.append("<table>")
        html.append("<tr><th>Date</th><th>Type</th><th>Shares</th><th>Price (USD)</th><th>FX Rate</th><th>Price (EUR)</th><th>Total Value (EUR)</th><th>Portfolio Qty</th><th>Avg Cost (EUR)</th><th>Realized G/L (EUR)</th></tr>")

        for pe in self.processed_events:
            e = pe.event
            shares_sign = "+" if e.event_type != EventType.SELL else "-"
            shares_str = f"{shares_sign}{e.shares:,.0f}"

            gl_str = ""
            if pe.realized_gain_loss != 0:
                gl_str = f"<strong>€{pe.realized_gain_loss:,.2f}</strong>"
            elif e.event_type == EventType.SELL:
                gl_str = "€0.00"

            html.append("<tr>")
            html.append(f"<td>{e.event_date}</td>")
            html.append(f"<td>{e.event_type.value}</td>")
            html.append(f"<td>{shares_str}</td>")
            html.append(f"<td>${e.price_usd:,.2f}</td>")
            html.append(f"<td>{e.resolved_fx_rate:.4f}</td>")
            html.append(f"<td>€{e.price_eur:,.4f}</td>")
            html.append(f"<td>€{e.total_value_eur:,.2f}</td>")
            html.append(f"<td>{pe.total_shares_after:,.0f}</td>")
            html.append(f"<td>€{pe.avg_cost_eur_after:,.4f}</td>")
            html.append(f"<td>{gl_str}</td>")
            html.append("</tr>")
        html.append("</table>")

        html.append("<h2>Calculation Details for Sales</h2>")
        html.append("<p>For every SELL transaction, the gain/loss is calculated as follows:</p>")

        sell_events = [pe for pe in self.processed_events if pe.event.event_type == EventType.SELL]
        if not sell_events:
            html.append("<p><em>No sales transactions found.</em></p>")

        for i, pe in enumerate(sell_events, 1):
            e = pe.event
            if e.shares > 0:
                avg_cost_used = e.price_eur - (pe.realized_gain_loss / e.shares)
            else:
                avg_cost_used = Decimal(0)

            html.append(f"<h3>{i}. Sale on {e.event_date}</h3>")
            html.append("<ul>")
            html.append(f"<li><strong>Sold</strong>: {e.shares:,.0f} shares @ €{e.price_eur:,.4f}</li>")
            html.append(f"<li><strong>Average Cost Basis</strong>: €{avg_cost_used:,.4f}</li>")
            html.append(f"<li><strong>Calculation</strong>: <code>({e.price_eur:,.4f} - {avg_cost_used:,.4f}) * {e.shares:,.0f} = {pe.realized_gain_loss:,.4f}</code></li>")
            html.append(f"<li><strong>Realized Gain/Loss</strong>: <strong>€{pe.realized_gain_loss:,.2f}</strong></li>")
            html.append("</ul>")

        html.append("</body></html>")
        return "".join(html)

    def generate_pdf_report(self, filepath: str):
        """Generate a PDF tax report using Playwright."""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            print("Error: Playwright is not installed. Cannot generate PDF.")
            print("Please install it with: pip install playwright && playwright install")
            return

        html_content = self.generate_html_content()

        try:
            with sync_playwright() as p:
                # Try to launch chromium, if it fails, it might need installation
                try:
                    browser = p.chromium.launch()
                except Exception as e:
                    print(f"Error launching browser: {e}")
                    print("Attempting to install browsers...")
                    import subprocess
                    subprocess.run(["playwright", "install", "chromium"])
                    browser = p.chromium.launch()

                page = browser.new_page()
                page.set_content(html_content)
                page.pdf(path=filepath, format="A4", margin={"top": "2cm", "bottom": "2cm", "left": "2cm", "right": "2cm"})
                browser.close()
        except Exception as e:
            print(f"Failed to generate PDF: {e}")


"""
Austrian Tax Engine Core Logic.

Implements the moving average cost basis method (Gleitender Durchschnittspreis)
required by Austrian tax law for calculating capital gains on stocks.
"""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from html import escape

from .evidence import EvidenceIndex, relevant_events
from .models import (
    MONEY_PRECISION,
    EventType,
    ProcessedEvent,
    StockEvent,
    TaxEngineState,
    YearlyTaxSummary,
)

# Same-day ordering: acquisitions must be applied before sales so that a
# sell-to-cover on vest day has inventory to sell from.
_EVENT_TYPE_PRIORITY: dict[EventType, int] = {
    EventType.VEST: 0,
    EventType.BUY: 1,
    EventType.EXERCISE: 1,
    EventType.SELL: 2,
}

# Share counts from RSU confirmations carry four decimals, so a residual
# position smaller than this is rounding noise rather than a real holding.
_ZERO_POSITION_THRESHOLD = MONEY_PRECISION


def event_sort_key(event: StockEvent) -> tuple[date, int]:
    """Sort key placing events in chronological order, acquisitions before sales."""
    return (event.event_date, _EVENT_TYPE_PRIORITY[event.event_type])


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

    def __init__(self) -> None:
        self.state = TaxEngineState()
        self.processed_events: list[ProcessedEvent] = []
        self.yearly_summaries: dict[int, YearlyTaxSummary] = {}

    def reset(self) -> None:
        """Reset the engine to initial state."""
        self.state = TaxEngineState()
        self.processed_events = []
        self.yearly_summaries = {}

    def _sort_events(self, events: list[StockEvent]) -> list[StockEvent]:
        """
        Sort events by date, with acquisitions before sells on same day.

        This is critical for correct processing - if a VEST and SELL happen
        on the same day (common with sell-to-cover), the VEST must be
        processed first.
        """
        return sorted(events, key=event_sort_key)

    def _process_acquisition(self, event: StockEvent) -> ProcessedEvent:
        """
        Process a BUY, VEST or EXERCISE event.

        Updates the moving average cost basis using the formula:
        new_avg = (old_shares * old_avg + new_cost) / (old_shares + new_shares)

        Gains are computed from the rounded average, so ``total_portfolio_cost_eur``
        can differ from shares x average by a fraction of a cent.
        """
        avg_before = self.state.avg_cost_eur
        new_cost_eur = event.total_value_eur
        new_shares = event.shares

        new_total_cost = self.state.total_shares * avg_before + new_cost_eur
        new_total_shares = self.state.total_shares + new_shares

        if new_total_shares > 0:
            new_avg_cost = (new_total_cost / new_total_shares).quantize(
                MONEY_PRECISION, ROUND_HALF_UP
            )
        else:
            new_avg_cost = Decimal("0")

        self.state.total_shares = new_total_shares
        self.state.avg_cost_eur = new_avg_cost
        self.state.total_portfolio_cost_eur = new_total_cost.quantize(
            MONEY_PRECISION, ROUND_HALF_UP
        )

        return ProcessedEvent(
            event=event,
            total_shares_after=self.state.total_shares,
            avg_cost_eur_after=self.state.avg_cost_eur,
            realized_gain_loss=Decimal("0"),
            cost_change_eur=new_cost_eur,
            total_portfolio_cost_eur=self.state.total_portfolio_cost_eur,
            avg_cost_eur_before=avg_before,
        )

    def _process_sell(self, event: StockEvent) -> ProcessedEvent:
        """
        Process a SELL event.

        The average cost stays the same (Rule B).
        Calculates realized gain/loss = (sell_price - avg_cost) * shares
        """
        shares_sold = event.shares
        avg_before = self.state.avg_cost_eur

        # Rule C: Depot check - cannot sell more than we have
        if shares_sold > self.state.total_shares:
            raise ValueError(
                f"Cannot sell {shares_sold} shares on {event.event_date}. "
                f"Only {self.state.total_shares} shares held. "
                f"Check for timing issues with sell-to-cover transactions."
            )

        # Calculate realized gain/loss
        sell_price_eur = event.price_eur
        gain_loss = ((sell_price_eur - avg_before) * shares_sold).quantize(
            MONEY_PRECISION, ROUND_HALF_UP
        )

        # Cost basis removed from portfolio
        cost_removed = (avg_before * shares_sold).quantize(MONEY_PRECISION, ROUND_HALF_UP)

        # Update state (avg_cost stays the same per Rule B)
        self.state.total_shares -= shares_sold
        self.state.total_portfolio_cost_eur -= cost_removed

        if self.state.total_shares <= _ZERO_POSITION_THRESHOLD:
            self.state.total_shares = Decimal("0")
            self.state.avg_cost_eur = Decimal("0")
            self.state.total_portfolio_cost_eur = Decimal("0")

        return ProcessedEvent(
            event=event,
            total_shares_after=self.state.total_shares,
            avg_cost_eur_after=self.state.avg_cost_eur,
            realized_gain_loss=gain_loss,
            cost_change_eur=-cost_removed,
            total_portfolio_cost_eur=self.state.total_portfolio_cost_eur,
            avg_cost_eur_before=avg_before,
        )

    def process_event(self, event: StockEvent) -> ProcessedEvent:
        """Process a single stock event."""
        if event.event_type in (EventType.VEST, EventType.BUY, EventType.EXERCISE):
            result = self._process_acquisition(event)
        elif event.event_type == EventType.SELL:
            result = self._process_sell(event)
        else:
            raise ValueError(f"Unknown event type: {event.event_type}")

        # Track for yearly summary
        year = event.event_date.year
        summary = self.yearly_summaries.setdefault(year, YearlyTaxSummary(year=year))

        if result.realized_gain_loss > 0:
            summary.total_gains += result.realized_gain_loss
        elif result.realized_gain_loss < 0:
            summary.total_losses += result.realized_gain_loss

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

    def get_opening_position(self, year: int) -> TaxEngineState:
        """
        Portfolio state carried into ``year`` (i.e. as of 1 January).

        This is what a single-year report needs in order to explain where the
        average cost basis used by that year's sales comes from.
        """
        state = TaxEngineState()
        for pe in self.processed_events:
            if pe.event.event_date.year >= year:
                break
            state = TaxEngineState(
                total_shares=pe.total_shares_after,
                avg_cost_eur=pe.avg_cost_eur_after,
                total_portfolio_cost_eur=pe.total_portfolio_cost_eur,
            )
        return state

    def get_closing_position(self, year: int) -> TaxEngineState:
        """Portfolio state at the end of ``year`` (i.e. as of 31 December)."""
        state = TaxEngineState()
        for pe in self.processed_events:
            if pe.event.event_date.year > year:
                break
            state = TaxEngineState(
                total_shares=pe.total_shares_after,
                avg_cost_eur=pe.avg_cost_eur_after,
                total_portfolio_cost_eur=pe.total_portfolio_cost_eur,
            )
        return state

    def print_ledger(self, year: int | None = None, evidence: EvidenceIndex | None = None) -> None:
        """Print the full transaction ledger in a readable format.

        Args:
            year: Optional year filter. If provided, only show transactions from that year,
                preceded by the opening position carried into that year.
            evidence: Optional document index. If provided, each row cites the
                Beleg-Nr. of the document it is based on.
        """
        # Filter events by year if specified
        events_to_print = self.processed_events
        if year is not None:
            events_to_print = [
                pe for pe in self.processed_events if pe.event.event_date.year == year
            ]

        width = 138 if evidence else 120
        print("\n" + "=" * width)
        if year is not None:
            print(f"TRANSACTION LEDGER - {year}")
        else:
            print("TRANSACTION LEDGER")
        print("=" * width)
        header = (
            f"{'Date':<12} {'Type':<6} {'Shares':>10} {'Price USD':>12} "
            f"{'FX Rate':>10} {'Price EUR':>12} {'Total Qty':>10} "
            f"{'Avg Cost':>12} {'Gain/Loss':>12}"
        )
        if evidence:
            header += f" {'Beleg':<17}"
        print(header)
        print("-" * width)

        # Opening position makes a single-year ledger self-explanatory: the first
        # sale of the year uses an average cost that was built up in earlier years.
        if year is not None:
            opening = self.get_opening_position(year)
            print(
                f"{'01.01.' + str(year):<12} {'OPEN':<6} "
                f"{'':>10} {'':>12} {'':>10} {'':>12} "
                f"{opening.total_shares:>10,.0f} €{opening.avg_cost_eur:>11,.4f} {'':>12}"
            )

        for pe in events_to_print:
            e = pe.event
            shares_sign = "+" if e.event_type != EventType.SELL else "-"
            shares_str = f"{shares_sign}{e.shares:,.0f}"
            gain_str = f"€{pe.realized_gain_loss:,.4f}" if pe.realized_gain_loss != 0 else ""

            row = (
                f"{e.event_date.isoformat():<12} {e.event_type.value:<6} "
                f"{shares_str:>10} ${e.price_usd:>11,.2f} "
                f"{e.resolved_fx_rate:>10.4f} €{e.price_eur:>11,.4f} "
                f"{pe.total_shares_after:>10,.0f} €{pe.avg_cost_eur_after:>11,.4f} "
                f"{gain_str:>12}"
            )
            if evidence:
                row += f" {evidence.citation_for(pe):<17}"
            print(row)

        if year is not None:
            closing = self.get_closing_position(year)
            print(
                f"{'31.12.' + str(year):<12} {'CLOSE':<6} "
                f"{'':>10} {'':>12} {'':>10} {'':>12} "
                f"{closing.total_shares:>10,.0f} €{closing.avg_cost_eur:>11,.4f} {'':>12}"
            )

        print("=" * width)

    def print_tax_summary(self, year: int | None = None) -> None:
        """Print the yearly tax summary.

        Args:
            year: Optional year filter. If provided, only show that year's summary.
        """
        # Get all summaries and filter if needed
        all_summaries = self.get_all_yearly_summaries()
        if year is not None:
            summaries_to_print = [s for s in all_summaries if s.year == year]
        else:
            summaries_to_print = all_summaries

        print("\n" + "=" * 80)
        if year is not None:
            print(f"YEARLY TAX SUMMARY - {year}")
        else:
            print("YEARLY TAX SUMMARY")
        print("=" * 80)
        print(
            f"{'Year':<8} {'Gains':>15} {'Losses':>15} "
            f"{'Net G/L':>15} {'Taxable':>15} {'KESt Due':>15}"
        )
        print("-" * 80)

        for summary in summaries_to_print:
            print(
                f"{summary.year:<8} €{summary.total_gains:>14,.2f} "
                f"€{summary.total_losses:>14,.2f} €{summary.net_gain_loss:>14,.2f} "
                f"€{summary.taxable_gain:>14,.2f} €{summary.kest_due:>14,.2f}"
            )

        print("=" * 80)

        # FinanzOnline Kennzahlen
        print("\nFINANZONLINE (Formulars E1 / E1kv)")
        print("-" * 80)
        print("Enter the following values in FinanzOnline for each tax year:")
        print()
        for summary in summaries_to_print:
            print(f"  Year {summary.year}:")
            print(f"    Kennzahl 994 (Gains):  €{summary.total_gains:>12,.2f}")
            print(f"    Kennzahl 892 (Losses): €{summary.total_losses:>12,.2f}")
            print()

    def generate_html_content(
        self, year: int | None = None, evidence: EvidenceIndex | None = None
    ) -> str:
        """Generate HTML content for the tax report.

        Args:
            year: Optional year filter. If provided, the report covers that single
                tax year: it opens with the position carried into the year, lists
                only that year's transactions, and closes with the position at
                31 December.
            evidence: Optional document index. If provided, every transaction cites
                the Beleg-Nr. of its source document and the report ends with a
                document index (Belegverzeichnis).
        """
        html = []
        html.append("<html><head><meta charset='utf-8'><style>")
        html.append(
            "body { font-family: sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }"
        )
        html.append(
            "table { border-collapse: collapse; width: 100%; margin-bottom: 20px; font-size: 12px; }"
        )
        html.append("th, td { border: 1px solid #ddd; padding: 6px; text-align: left; }")
        html.append("th { background-color: #f2f2f2; }")
        html.append("h1, h2, h3 { color: #333; }")
        html.append(".gain { color: green; }")
        html.append(".loss { color: red; }")
        html.append("code { background-color: #f4f4f4; padding: 2px 4px; border-radius: 4px; }")
        # Print/PDF behaviour: repeat table headers, avoid splitting rows.
        html.append("thead { display: table-header-group; }")
        html.append("tr { page-break-inside: avoid; }")
        html.append(".page-break { page-break-before: always; }")
        html.append(
            ".note { background-color: #f9f9f9; border-left: 4px solid #999; "
            "padding: 8px 12px; font-size: 12px; margin-bottom: 16px; }"
        )
        html.append(".beleg { font-family: monospace; font-size: 11px; white-space: nowrap; }")
        html.append(".muted { color: #666; font-size: 11px; }")
        html.append("</style></head><body>")

        if year is not None:
            html.append(f"<h1>Austrian Tax Report {year}</h1>")
            html.append(
                f"<p><strong>Steuerbericht Kapitalvermögen {year}</strong> — "
                f"realized gains and losses from RSU, ESPP and stock option shares.</p>"
            )
        else:
            html.append("<h1>Austrian Tax Report</h1>")
        html.append(f"<p>Generated on: {date.today().isoformat()}</p>")

        if year:
            html.append("<h2>Scope of this report</h2>")
            html.append("<div class='note'>")
            html.append(
                f"<p>This report covers <strong>tax year {year} only</strong> "
                f"(01.01.{year} – 31.12.{year}).</p>"
            )
            html.append(
                "<p>Under the moving average cost basis method the gain on a sale depends on "
                "every earlier acquisition. The full transaction history up to 31.12."
                f"{year} was therefore used to compute the average cost, but only {year} "
                "transactions are reported and taxed here. The position carried into the "
                "year is shown below, and the earlier transactions that produced it are "
                "documented in the appendix.</p>"
            )
            html.append("</div>")

        html.append("<h2>Methodology</h2>")
        html.append(
            "<p>This report calculates capital gains using the <strong>Moving Average Cost Basis</strong> (Gleitender Durchschnittspreis) method as required by Austrian tax law.</p>"
        )
        html.append("<h3>Key Rules:</h3>")
        html.append("<ul>")
        html.append(
            "<li><strong>Acquisitions (VEST/BUY/EXERCISE)</strong>: Recalculate the moving average cost.<br><code>New Avg = (Old Total Cost + New Cost) / (Old Shares + New Shares)</code></li>"
        )
        html.append(
            "<li><strong>Sales (SELL)</strong>: Do not change the average cost per share.<br><code>Realized Gain/Loss = (Sell Price - Avg Cost) * Shares Sold</code></li>"
        )
        html.append(
            "<li><strong>Currency</strong>: All values are converted to EUR using the daily ECB reference rate.</li>"
        )
        html.append("</ul>")

        # --- Opening position --------------------------------------------------
        opening = self.get_opening_position(year) if year is not None else None
        if year is not None and opening is not None:
            html.append(f"<h2>Opening Position on 01.01.{year}</h2>")
            html.append("<table>")
            html.append("<tr><th>Item</th><th>Value</th></tr>")
            html.append(
                f"<tr><td>Shares held (Stückzahl)</td><td>{opening.total_shares:,.0f}</td></tr>"
            )
            html.append(
                f"<tr><td>Moving average cost per share "
                f"(Gleitender Durchschnittspreis)</td>"
                f"<td>€{opening.avg_cost_eur:,.4f}</td></tr>"
            )
            html.append(
                f"<tr><td>Total cost basis (Anschaffungskosten gesamt)</td>"
                f"<td>€{opening.total_portfolio_cost_eur:,.2f}</td></tr>"
            )
            html.append("</table>")
            if opening.total_shares > 0:
                html.append(
                    "<p class='muted'>Derivation of this opening average cost: see appendix "
                    "&quot;Opening Position Derivation&quot;.</p>"
                )

        # Filter summaries by year if specified
        all_summaries = self.get_all_yearly_summaries()
        if year is not None:
            summaries_to_include = [s for s in all_summaries if s.year == year]
        else:
            summaries_to_include = all_summaries

        html.append("<h2>Yearly Tax Summary</h2>")
        html.append("<table>")
        html.append(
            "<thead><tr><th>Year</th><th>Total Gains</th><th>Total Losses</th><th>Net Gain/Loss</th><th>Taxable Amount</th><th>KESt Due (27.5%)</th></tr></thead>"
        )

        for summary in summaries_to_include:
            net_style = "gain" if summary.net_gain_loss >= 0 else "loss"
            html.append("<tr>")
            html.append(f"<td>{summary.year}</td>")
            html.append(f"<td>€{summary.total_gains:,.2f}</td>")
            html.append(f"<td>€{summary.total_losses:,.2f}</td>")
            html.append(
                f"<td class='{net_style}'><strong>€{summary.net_gain_loss:,.2f}</strong></td>"
            )
            html.append(f"<td>€{summary.taxable_gain:,.2f}</td>")
            html.append(f"<td><strong>€{summary.kest_due:,.2f}</strong></td>")
            html.append("</tr>")
        html.append("</table>")

        html.append("<h2>FinanzOnline (Formulars E1 / E1kv)</h2>")
        html.append(
            "<p>Enter the following values in <strong>FinanzOnline</strong> for each tax year:</p>"
        )
        html.append("<table>")
        html.append(
            "<thead><tr><th>Year</th><th>Kennzahl 994 (Gains)</th><th>Kennzahl 892 (Losses)</th></tr></thead>"
        )
        for summary in summaries_to_include:
            html.append("<tr>")
            html.append(f"<td>{summary.year}</td>")
            html.append(f"<td>€{summary.total_gains:,.2f}</td>")
            html.append(f"<td>€{summary.total_losses:,.2f}</td>")
            html.append("</tr>")
        html.append("</table>")
        html.append(
            "<p><em>Kennzahl 994 = total realized gains, "
            "Kennzahl 892 = total realized losses (entered as a negative number).</em></p>"
        )

        # Filter events by year if specified
        events_to_include = self.processed_events
        if year is not None:
            events_to_include = [
                pe for pe in self.processed_events if pe.event.event_date.year == year
            ]

        if year:
            html.append(f"<h2>Detailed Transaction Ledger {year}</h2>")
        else:
            html.append("<h2>Detailed Transaction Ledger</h2>")
        html.append(
            "<p>The following table documents every transaction and its effect on the portfolio cost basis.</p>"
        )

        html.append("<table>")
        header_cells = (
            "<th>Date</th><th>Type</th><th>Shares</th><th>Price (USD)</th><th>FX Rate</th>"
            "<th>Price (EUR)</th><th>Total Value (EUR)</th><th>Portfolio Qty</th>"
            "<th>Avg Cost (EUR)</th><th>Realized G/L (EUR)</th>"
        )
        if evidence:
            header_cells += "<th>Beleg</th>"
        html.append(f"<thead><tr>{header_cells}</tr></thead>")

        if year is not None and opening is not None:
            span_before = 7
            html.append("<tr>")
            html.append(f"<td><strong>01.01.{year}</strong></td>")
            html.append("<td><strong>OPEN</strong></td>")
            html.append(f"<td colspan='{span_before - 2}'><em>Carried forward</em></td>")
            html.append(f"<td>{opening.total_shares:,.0f}</td>")
            html.append(f"<td>€{opening.avg_cost_eur:,.4f}</td>")
            html.append("<td></td>")
            if evidence:
                html.append("<td class='beleg'>see appendix</td>")
            html.append("</tr>")

        for pe in events_to_include:
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
            if evidence:
                html.append(f"<td class='beleg'>{escape(evidence.citation_for(pe))}</td>")
            html.append("</tr>")

        if year is not None:
            closing = self.get_closing_position(year)
            html.append("<tr>")
            html.append(f"<td><strong>31.12.{year}</strong></td>")
            html.append("<td><strong>CLOSE</strong></td>")
            html.append("<td colspan='5'><em>Carried forward to the next year</em></td>")
            html.append(f"<td>{closing.total_shares:,.0f}</td>")
            html.append(f"<td>€{closing.avg_cost_eur:,.4f}</td>")
            html.append("<td></td>")
            if evidence:
                html.append("<td></td>")
            html.append("</tr>")
        html.append("</table>")

        html.append("<h2>Calculation Details for Sales</h2>")
        html.append("<p>For every SELL transaction, the gain/loss is calculated as follows:</p>")

        # Filter sell events by year if specified
        if year is not None:
            sell_events = [
                pe
                for pe in self.processed_events
                if pe.event.event_type == EventType.SELL and pe.event.event_date.year == year
            ]
        else:
            sell_events = [
                pe for pe in self.processed_events if pe.event.event_type == EventType.SELL
            ]
        if not sell_events:
            html.append("<p><em>No sales transactions found.</em></p>")

        for i, pe in enumerate(sell_events, 1):
            e = pe.event
            avg_cost_used = pe.avg_cost_eur_before

            html.append(f"<h3>{i}. Sale on {e.event_date}</h3>")
            html.append("<ul>")
            html.append(
                f"<li><strong>Sold</strong>: {e.shares:,.0f} shares @ €{e.price_eur:,.4f} "
                f"(${e.price_usd:,.2f} × {e.resolved_fx_rate:.4f})</li>"
            )
            html.append(f"<li><strong>Average Cost Basis</strong>: €{avg_cost_used:,.4f}</li>")
            html.append(
                f"<li><strong>Calculation</strong>: <code>({e.price_eur:,.4f} - {avg_cost_used:,.4f}) * {e.shares:,.0f} = {pe.realized_gain_loss:,.4f}</code></li>"
            )
            html.append(
                f"<li><strong>Realized Gain/Loss</strong>: <strong>€{pe.realized_gain_loss:,.2f}</strong></li>"
            )
            if evidence:
                html.append(
                    f"<li><strong>Evidence</strong>: "
                    f"<span class='beleg'>{escape(evidence.citation_for(pe))}</span>"
                    f" — {escape(e.source_citation or 'no source document')}</li>"
                )
            html.append("</ul>")

        # --- Appendix: how the opening average cost came about -----------------
        if year is not None and evidence is not None and opening is not None:
            supporting, _ = relevant_events(self.processed_events, year)
            html.append("<div class='page-break'></div>")
            html.append("<h2>Appendix A — Opening Position Derivation</h2>")
            if not supporting:
                html.append(
                    f"<p><em>No shares were held on 01.01.{year}; every share sold in "
                    f"{year} was also acquired in {year}.</em></p>"
                )
            else:
                html.append(
                    f"<p>The average cost of €{opening.avg_cost_eur:,.4f} per share carried "
                    f"into {year} results from the following earlier transactions "
                    f"(from {supporting[0].event.event_date.isoformat()}, the point at which "
                    f"the depot was last empty, to 31.12.{year - 1}). "
                    f"These transactions are <strong>not</strong> taxed in this report; they "
                    f"are shown only to substantiate the opening cost basis.</p>"
                )
                html.append("<table>")
                html.append(
                    "<thead><tr><th>Date</th><th>Type</th><th>Shares</th><th>Price (USD)</th>"
                    "<th>FX Rate</th><th>Price (EUR)</th><th>Portfolio Qty</th>"
                    "<th>Avg Cost (EUR)</th><th>Beleg</th></tr></thead>"
                )
                for pe in supporting:
                    e = pe.event
                    shares_sign = "+" if e.event_type != EventType.SELL else "-"
                    html.append("<tr>")
                    html.append(f"<td>{e.event_date}</td>")
                    html.append(f"<td>{e.event_type.value}</td>")
                    html.append(f"<td>{shares_sign}{e.shares:,.0f}</td>")
                    html.append(f"<td>${e.price_usd:,.2f}</td>")
                    html.append(f"<td>{e.resolved_fx_rate:.4f}</td>")
                    html.append(f"<td>€{e.price_eur:,.4f}</td>")
                    html.append(f"<td>{pe.total_shares_after:,.0f}</td>")
                    html.append(f"<td>€{pe.avg_cost_eur_after:,.4f}</td>")
                    html.append(f"<td class='beleg'>{escape(evidence.citation_for(pe))}</td>")
                    html.append("</tr>")
                html.append("</table>")

        # --- Appendix: document index -----------------------------------------
        if evidence is not None:
            html.append("<div class='page-break'></div>")
            html.append("<h2>Appendix B — Document Index (Belegverzeichnis)</h2>")
            html.append(
                "<p>Every transaction above is backed by one of the following documents. "
                "The documents are attached to this report under their Beleg-Nr.</p>"
            )
            html.append("<table>")
            html.append(
                "<thead><tr><th>Beleg-Nr.</th><th>Document</th><th>Type</th><th>Date(s)</th>"
                "<th>Transactions</th><th>Role</th></tr></thead>"
            )
            for doc in evidence.documents:
                role = doc.role_long
                if doc.is_primary and not doc.is_supporting:
                    role = f"Primary evidence ({evidence.year})"
                html.append("<tr>")
                html.append(f"<td class='beleg'>{escape(doc.number)}</td>")
                html.append(f"<td>{escape(doc.name)}</td>")
                html.append(f"<td>{escape(doc.kind)}</td>")
                html.append(f"<td>{escape(doc.date_range)}</td>")
                html.append(f"<td>{doc.event_count}</td>")
                html.append(f"<td>{escape(role)}</td>")
                html.append("</tr>")
            html.append("</table>")
            if evidence.missing:
                html.append(
                    "<p class='loss'><strong>Warning:</strong> the following referenced "
                    "documents were not found on disk and are missing from the bundle: "
                    + ", ".join(escape(m) for m in evidence.missing)
                    + "</p>"
                )
            if evidence.undocumented_events:
                html.append(
                    f"<p class='loss'><strong>Warning:</strong> "
                    f"{evidence.undocumented_events} transaction(s) have no source document "
                    f"recorded and are therefore not covered by the document index.</p>"
                )

        html.append("</body></html>")
        return "".join(html)

    def generate_pdf_report(
        self,
        filepath: str,
        year: int | None = None,
        evidence: EvidenceIndex | None = None,
    ) -> bool:
        """Generate a PDF tax report using Playwright.

        Args:
            filepath: Path where the PDF should be saved.
            year: Optional year filter. If provided, only include that year's data.
            evidence: Optional document index used to cite source documents.

        Returns:
            True if the PDF was written, False otherwise. Failures are reported
            on stdout so the caller can decide how to exit.
        """
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            print("Error: Playwright is not installed. Cannot generate PDF.")
            print("Please install it with: pip install playwright && playwright install")
            return False

        html_content = self.generate_html_content(year=year, evidence=evidence)

        try:
            with sync_playwright() as p:
                try:
                    browser = p.chromium.launch()
                except Exception as e:
                    print(f"Error launching browser: {e}")
                    print("Attempting to install browsers...")
                    import subprocess
                    import sys

                    # Use the current interpreter so this works inside a venv
                    # where the `playwright` script may not be on PATH.
                    subprocess.run(
                        [sys.executable, "-m", "playwright", "install", "chromium"], check=True
                    )
                    browser = p.chromium.launch()

                page = browser.new_page()
                page.set_content(html_content)
                page.pdf(
                    path=filepath,
                    format="A4",
                    margin={"top": "2cm", "bottom": "2cm", "left": "2cm", "right": "2cm"},
                )
                browser.close()
        except Exception as e:
            print(f"Failed to generate PDF: {e}")
            return False

        return True

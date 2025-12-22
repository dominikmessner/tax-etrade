# Austrian Tax Engine for E-Trade RSUs and ESPP

Calculates capital gains tax using the Austrian moving average cost basis method (Gleitender Durchschnittspreis) for stocks acquired through RSU vesting and ESPP purchases.

## Quick Start

### Run Demo with Sample Data

To see the tax engine in action with the original sample data:

```bash
# Quick demo (shows full output)
uv run demo.py

# Or run tests
uv run pytest tests/ -v
```

The [demo.py](demo.py) script and [tests/test_sample_data.py](tests/test_sample_data.py) preserve the original example that demonstrates the engine's calculations.

### Run with Actual Data

```bash
uv run main.py
```

**Note:** Excel parsing is not yet implemented. The main.py file is ready to load data from `input/espp/BenefitHistory.xlsx` once the parsing logic is added.

---

# Core logic

Your spreadsheet is basically the "Golden Record" the Finanzamt wants to see. It’s slightly more complex than it needs to be because you're tracking "Cost Change" and "Total Portfolio Cost," but honestly, having that trail makes an audit way easier.

The core logic for the Austrian moving average (Gleitender Durchschnittspreis) is actually quite simple once you strip away the noise. Here is how we should structure the "Engine."

## 1. The Essential Data Schema

Forget the extra columns for a second. To calculate this correctly in Python, every "Event" (Buy, Vest, Sell) needs these inputs:

* **Date:** The date of the event (determines FX rate and order).
* **Type:** `BUY` (ESPP), `VEST` (RSU), or `SELL` (Manual/RSU-Sell).
* **Shares:** Amount.
* **Price_USD:** The price per share in USD.
* **FX_Rate:** The USD/EUR rate on that specific day.

### Computed columns (What the logic generates):

* **Price_EUR:** `Price_USD * FX_Rate`.
* **Total_Qty:** Current inventory of shares.
* **Avg_Cost_EUR:** The magic number.
* **Realized_Gain_Loss:** Only calculated on `SELL` events.

## 2. The Core Requirements (The "Rules")

If we build this, the code must follow these three Austrian tax laws to the letter:

### Rule A: The Moving Average Formula

Whenever you **acquire** shares (Buy or Vest), you recalculate the average.

* **Note:** Your RSUs are treated as a "Buy" at the market price on the day they vest. That value is already taxed as income (Lohnsteuer), so it becomes your "cost basis."

### Rule B: Selling doesn't change the Average

When you **sell**, the average cost per share stays exactly the same. You just reduce the `Total_Qty`.

* **Gain/Loss Calculation:** `(SellPriceEUR - CurrentAvgCost) * SharesSold`.

### Rule C: The "Depot-Check"

You cannot have negative shares. If a sell order is larger than your current holdings, the script should scream at you. This happens often with E-Trade because of "Sell-to-Cover" (where they sell shares automatically to pay the tax), and sometimes the timing in the logs gets messy.

## 3. Proposed Logic Flow

I’d structure the Python script to do this:

1. **Ingestion:** Merge the RSU, ESPP, and Order data into one list.
2. **Sorting:** Sort strictly by `Date`. If two things happen on the same day (like a Vest and a Sell-to-cover), **Vests must come first**.
3. **The Loop:**
* Initialize `total_shares = 0` and `avg_cost = 0`.
* Iterate through every row.
* If `VEST` or `BUY`: Update `avg_cost` using the formula above. Update `total_shares`.
* If `SELL`: Calculate `gain = (price_eur - avg_cost) * shares`. Update `total_shares`.
4. **Tax Aggregation:** Group the `gain` column by year.


## 4. Improvements to your Spreadsheet

Looking at your 2021/2022 data, here's where the logic gets annoying:

* **USD/EUR Rates:** You used 4 decimal places. The Finanzamt usually accepts the official ECB daily rates. We should automate this using an API so you never have to look it up again.
* **Losses:** In 2022, you have a big loss. In Austria, you can offset losses against gains within the *same calendar year*. You can't carry them forward to 2023. The script should handle this "Yearly Reset" for the tax summary automatically.

## Manual spreadsheet

This is an example how the spreadsheet that i wrote by hand looked like:

Date	Type	Shares In	Shares Out	Cost/Share (USD)	USD/EUR Rate	Cost Change (EUR)	Total Shares Held	Total Portfolio Cost (EUR)	Avg. Cost per Share (EUR)	Gain / Loss (EUR)	KESt	Notes	Year
2020-11-27	ESPP Buy	50		$38.42	0.8388	€1,611.33	50	€1,611.33	€32.23	€0.00	€0.00		2020
2021-02-03	Manual Sell		50	$48.85	0.8322	-€1,611.33	0	€0.00	€0.00	€421.31	€115.86		2021
2021-05-17	RSU Vest	30		$46.68	0.8235	€1,153.23	30	€1,153.23	€38.44	€0.00	€0.00		2021
2021-05-17	RSU Sell		25	$44.82	0.8235	-€961.02	5	€192.20	€38.44	-€38.29	€0.00		2021
2021-05-17	RSU Sell		2	$46.22	0.8235	-€76.88	3	€115.32	€38.44	-€0.76	€0.00		2021
2021-05-28	ESPP Buy	50		$51.74	0.8236	€2,130.65	53	€2,245.98	€42.38	€0.00	€0.00		2021
2021-08-16	RSU Vest	10		$63.65	0.8495	€540.71	63	€2,786.68	€44.23	€0.00	€0.00		2021
2021-08-16	RSU Sell		5	$61.25	0.8495	-€221.17	58	€2,565.52	€44.23	€38.99	€10.72		2021
2021-11-15	RSU Vest	10		$70.68	0.8738	€617.60	68	€3,183.12	€46.81	€0.00	€0.00		2021
2021-11-16	RSU Sell		5	$69.28	0.8797	-€234.05	63	€2,949.07	€46.81	€70.68	€19.44		2021
2021-11-26	ESPP Buy	100		$62.97	0.8857	€5,577.25	163	€8,526.32	€52.31	€0.00	€0.00		2021
2022-05-27	ESPP Buy	105		$38.19	0.9327	€3,740.08	268	€12,266.40	€45.77	€0.00	€0.00		2022
2022-06-01	Manual Sell		205	$39.15	0.9335	-€9,382.88	63	€2,883.52	€45.77	-€1,890.84	€0.00		2022

Year	Gains	Losses	Sum G&L
2020	0	0	0
2021	530.9829476	-39.05037	491.9325776
2022	0	-1890.84281	-1890.84281
2023	0	0	0
2024	0	0	0
2025	0	0	0

# Inputs (later)

## ESPP Buy
Go to Benefit History on E-Trade and expand "Employee Stock Purchase Plan (ESPP)"
https://us.etrade.com/etx/sp/stockplan#/myAccount/benefitHistory
Download - Download Expanded

Create an ESPP Buy row for every entry.

Mapping spreadsheet columns to E-Trade:
- Date: Purchase date
- Shares In: Purchased Qty.
- Cost/Share: Purchase Date FMV (expand the row in etrade, ignore the top level Purchase Price)

## RSU Vesting
Open Stock Plan Confirmations and download/open all documents of type Restricted Stock. Make sure to click the View All button on the bottom if there are more than 10 entries.
https://us.etrade.com/etx/sp/stockplan#/myAccount/stockPlanConfirmations
Download all PDFs

Create an "RSU Vest" row for every document.
Mapping spreadsheet columns to E-Trade:

Date: Release Date
Shares In: Shares Released
Cost/Share: Market Value Per Share
Note - sometimes E-Trade merges RSU releases of the same date into a single document and averages the stock price. This shouldn't matter for this step, but in case you wonder why "RSU-sell" orders don't match perfectly with the confirmations, this is why.

## RSU + ESPP Sell
Go to Orders and make a "Manual Sell" row for every entry.
https://us.etrade.com/etx/sp/stockplan#/myAccount/orders

Mapping spreadsheet columns to E-Trade:

Date: Order Date
Shares Out: Sold Qty.
Cost/Share: Execution Price
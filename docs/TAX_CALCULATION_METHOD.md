# Tax Calculation Method

This document explains how the Austrian Tax Engine calculates capital gains tax on stocks acquired through RSU vesting and ESPP purchases.

## Overview

Austrian tax law requires the **Moving Average Cost Basis Method** (German: *Gleitender Durchschnittspreis*) for calculating capital gains on securities. This method continuously recalculates your average cost basis whenever you acquire new shares.

## Key Concepts

### 1. Cost Basis (Anschaffungskosten)

The cost basis is the price you paid for your shares, converted to EUR. For:

- **RSU Vesting**: The fair market value (FMV) at the time of vesting
- **ESPP Purchases**: The purchase price you paid (typically at a discount)

### 2. Moving Average Cost Basis (Gleitender Durchschnittspreis)

Unlike FIFO (First In, First Out) or LIFO (Last In, First Out), the moving average method calculates a weighted average of all your purchase prices. This average is updated every time you acquire new shares.

**Formula:**
```
New Average Cost = (Old Total Cost + New Acquisition Cost) / (Old Shares + New Shares)
```

### 3. Capital Gains Tax (KESt - Kapitalertragsteuer)

Austria taxes capital gains on securities at a flat rate of **27.5%**.

## The Three Core Rules

### Rule A: Acquisitions Update the Average

Every time you acquire shares (RSU vest or ESPP purchase), the average cost is recalculated:

**Example:**
- You hold 100 shares with an average cost of €50 (total cost: €5,000)
- You acquire 50 more shares at €60 each (cost: €3,000)
- New average: (€5,000 + €3,000) / (100 + 50) = **€53.33 per share**

### Rule B: Sales Do NOT Change the Average

When you sell shares, the average cost remains unchanged. Only the quantity decreases.

**Example:**
- You hold 150 shares with an average cost of €53.33
- You sell 30 shares at €70 each
- Realized gain: (€70 - €53.33) × 30 = **€500.10**
- Remaining: 120 shares, still at €53.33 average cost

### Rule C: Depot Check (You Can't Sell More Than You Own)

You cannot sell more shares than you currently hold. The engine validates this for each transaction.

## Currency Conversion

All transactions must be converted to EUR for Austrian tax purposes:

1. **USD to EUR conversion** uses the official ECB (European Central Bank) exchange rate
2. The rate used is from the **transaction date** (or the closest available rate)
3. Exchange rates are fetched from the ECB Statistical Data Warehouse

## Transaction Processing Order

When multiple transactions occur on the same day, they are processed in this order:

1. **VEST** (RSU vesting)
2. **BUY** (ESPP purchases)
3. **SELL** (Stock sales)

This ordering is critical for "sell-to-cover" scenarios where shares vest and are immediately sold on the same day to cover taxes.

## Yearly Tax Summary

At the end of each tax year, the engine calculates:

| Metric | Description |
|--------|-------------|
| **Total Gains** | Sum of all positive realized gains |
| **Total Losses** | Sum of all realized losses (negative) |
| **Net Gain/Loss** | Gains + Losses (losses offset gains) |
| **Taxable Gain** | Max(0, Net Gain/Loss) — losses cannot create a tax credit |
| **KESt Due** | Taxable Gain × 27.5% |

### Loss Offsetting Rules

- Losses can offset gains **within the same year**
- Losses **cannot** be carried forward to future years
- If your net result is negative, your taxable gain is €0

## Practical Example

Let's walk through a complete example:

### Transactions

| Date | Type | Shares | Price (USD) | FX Rate | Price (EUR) |
|------|------|--------|-------------|---------|-------------|
| 2024-03-15 | VEST | 100 | $150.00 | 0.92 | €138.00 |
| 2024-06-01 | VEST | 50 | $180.00 | 0.93 | €167.40 |
| 2024-09-10 | SELL | 80 | $200.00 | 0.91 | €182.00 |
| 2024-12-01 | VEST | 30 | $160.00 | 0.94 | €150.40 |

### Calculation Steps

**Step 1: First VEST (March 15)**
- Shares: 100
- Average cost: €138.00
- Total cost: €13,800.00

**Step 2: Second VEST (June 1)**
- New shares: 50 at €167.40
- New total cost: €13,800 + (50 × €167.40) = €22,170
- Total shares: 150
- New average: €22,170 / 150 = **€147.80**

**Step 3: SELL (September 10)**
- Selling 80 shares at €182.00
- Cost basis: 80 × €147.80 = €11,824
- Proceeds: 80 × €182.00 = €14,560
- **Realized gain: €2,736**
- Remaining: 70 shares at €147.80 average (unchanged!)

**Step 4: Third VEST (December 1)**
- New shares: 30 at €150.40
- Old total cost: 70 × €147.80 = €10,346
- New total cost: €10,346 + (30 × €150.40) = €14,858
- Total shares: 100
- New average: €14,858 / 100 = **€148.58**

### Tax Summary for 2024

| Metric | Amount |
|--------|--------|
| Total Gains | €2,736.00 |
| Total Losses | €0.00 |
| Net Gain/Loss | €2,736.00 |
| Taxable Gain | €2,736.00 |
| **KESt Due** | **€752.40** |

## Important Notes

1. **RSU Income Tax**: The FMV at vesting is also taxable as income (Lohnsteuer), but it is already withheld by Dynatrace. This is separate from the capital gains calculated here.

2. **ESPP Discount**: The discount you receive on ESPP purchases is normally taxable as a benefit-in-kind (Sachbezug). However, under **§ 3 Abs. 1 Z 15 lit. b EStG**, if you hold the shares for at least **5 years**, the discount (up to €3,000 per year) can be **tax-free**. Dynatrace's ESPP qualifies for this benefit. The discount taxation is handled by Dynatrace's payroll. This software only calculates capital gains (KESt) when you sell.

3. **Sell-to-Cover**: When shares are sold to cover taxes at vesting, the vest happens first (establishing cost basis), then the immediate sale is processed.

4. **Rounding**: The engine uses 4 decimal places for calculations to maintain precision.

## Legal References

- § 27 EStG (Einkommensteuergesetz) - Capital gains taxation
- § 27a EStG - Special tax rate for capital income (27.5%)
- BMF (Bundesministerium für Finanzen) guidelines on cost basis calculation

## Disclaimer

This document explains the methodology used by this software. It is not tax advice. Tax laws change, and individual circumstances vary. Always consult a qualified Austrian tax advisor (Steuerberater) for your specific situation.

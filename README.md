# NIFTY 50 High-Frequency Options Multi-Strategy Paper Trading Engine

An ultra-lightweight, zero-dependency algorithmic execution and paper trading platform designed for Indian Equity Derivatives (NSE: NIFTY). The platform decouples live WebSocket market feed broadcasting from an isolated 10-strategy execution loop, calculating real-world statutory taxes (STT, GST, SEBI, Stamp Duty), modeling 0.25% fill slippage, and serving live telemetry to a browser dashboard with sub-30 MB resident memory footprint.

---

## Architectural Topology

```
                  ┌─────────────────────────────────────────┐
                  │          Angel One SmartAPI             │
                  │        SmartWebSocketV2 (NFO)           │
                  └────────────────────┬────────────────────┘
                                       │ Raw Binary / JSON Ticks
                                       ▼
                  ┌─────────────────────────────────────────┐
                  │                server.py                │
                  │        (Feed Producer Process)          │
                  │   - Instrument Master Caching (12h TTL) │
                  │   - Mode 1 LTP Streaming (50 Token Chunks)│
                  │   - HTTP Broadcaster (Port 5555)        │
                  └────────────────────┬────────────────────┘
                                       │ HTTP Loopback (JSON Snapshot)
                                       │ http://127.0.0.1:5555/
                                       ▼
                  ┌─────────────────────────────────────────┐
                  │         multi_strategy_bot.py           │
                  │        (Consumer Quant Engine)          │
                  │   - Anchored O(1) TWAP/VWAP Tracker     │
                  │   - 15-Minute Dynamic ORB Freezer       │
                  │   - Statutory Tax & Slippage Engine     │
                  │   - 10 x Independent Strategy Lifecycles│
                  └───────────┬─────────────────┬───────────┘
                              │                 │
           Thread-Safe State  │                 │ Append-Only Audits
      http://127.0.0.1:5556/  │                 │ (Per-Strategy Isolation)
                              ▼                 ▼
          ┌───────────────────────┐   ┌───────────────────────────┐
          │ strategy_dashboard.html│  │ logs/trades_S*.csv        │
          │ (Vanilla JS Dashboard)│   │  - Entry/Exit Timestamps  │
          └───────────────────────┘   │  - Regulatory Cost Arrays │
                                      │  - Net Realized Alpha     │
                                      └───────────────────────────┘

```

---

## Mathematical & Quantitative Models

### 1. Indian Statutory Regulatory Drag & Cost Matrix

Standard paper trading systems artificially inflate returns by only considering flat brokerage fees. This engine implements the updated Indian Union Budget statutory fee structure for NSE Equity Options (F&O):

$$\text{Total Frictional Deductions} = B + \text{STT} + C_{\text{NSE}} + C_{\text{SEBI}} + D_{\text{Stamp}} + T_{\text{GST}}$$

Where:

* **Gross Premium Turnovers:**

$$\text{Turnover}_{\text{Buy}} = \text{Qty} \times P_{\text{Buy}}$$


$$\text{Turnover}_{\text{Sell}} = \text{Qty} \times P_{\text{Sell}}$$


$$\text{Turnover}_{\text{Total}} = \text{Turnover}_{\text{Buy}} + \text{Turnover}_{\text{Sell}}$$


* **Flat Brokerage ($B$):** ₹20.00 per executed order leg ($\text{Round-Turn} = ₹40.00$).
* **Securities Transaction Tax ($\text{STT}$):** Levied exclusively on the sell-side premium turnover at 0.10%:

$$\text{STT} = \text{Turnover}_{\text{Sell}} \times 0.0010$$


* **Exchange Transaction Surcharge ($C_{\text{NSE}}$):** 0.03503% on total premium turnover:

$$C_{\text{NSE}} = \text{Turnover}_{\text{Total}} \times 0.0003503$$


* **SEBI Regulatory Turnover Fee ($C_{\text{SEBI}}$):** ₹10 per Crore (0.0001%):

$$C_{\text{SEBI}} = \text{Turnover}_{\text{Total}} \times 0.000001$$


* **State Stamp Duty ($D_{\text{Stamp}}$):** 0.003% applied strictly to buy-side turnover:

$$D_{\text{Stamp}} = \text{Turnover}_{\text{Buy}} \times 0.00003$$


* **Goods and Services Tax ($T_{\text{GST}}$):** 18% applied over taxable broker and exchange services:

$$T_{\text{GST}} = (B + C_{\text{NSE}} + C_{\text{SEBI}}) \times 0.18$$



### 2. Execution Price Slippage Model

To emulate real limit/market order book matching latency, synthetic fills adjust by 0.25% against the favor of the trade:


$$P_{\text{Exec, Buy}} = P_{\text{Market, LTP}} \times (1 + 0.0025)$$

$$P_{\text{Exec, Sell}} = P_{\text{Market, LTP}} \times (1 - 0.0025)$$

### 3. Anchored Time-Weighted Moving Average (Proxy-VWAP)

Because continuous cash indices like NIFTY 50 (`token: 99926000`) do not transmit raw transaction volumes over consolidated broadcast pipes, true Volume-Weighted Average Price is approximated via an $O(1)$ memory, continuous time-weighted moving aggregate starting at market open ($09:15\text{ IST}$):

$$\text{VWAP}_t = \frac{1}{N} \sum_{k=1}^{N} \text{Spot}_k$$

This eliminates rolling-window slice overhead, prevents computational drift, and uses zero additional heap allocations.

---

## Strategy Catalog

```
┌────┬──────────────────────┬──────────┬───────────────────────────────┬───────────────────────────────┐
│ ID │ Strategy Name        │ Time     │ Entry Rules                   │ Exit Rules                    │
├────┼──────────────────────┼──────────┼───────────────────────────────┼───────────────────────────────┤
│ S1 │ 09:20 Short Straddle │ 09:20    │ Sell ATM CE + Sell ATM PE     │ 25% Leg SL (trail winner to   │
│    │                      │          │ (Delta Neutral)               │ cost), Target ₹2500, Max ₹1800│
├────┼──────────────────────┼──────────┼───────────────────────────────┼───────────────────────────────┤
│ S2 │ 09:30 Short Strangle │ 09:30    │ Sell ATM+100 CE +             │ 30% Leg SL, Trail ₹700 when   │
│    │                      │          │ Sell ATM-100 PE               │ peak hits ₹1800, Max ₹1500    │
├────┼──────────────────────┼──────────┼───────────────────────────────┼───────────────────────────────┤
│ S3 │ Iron Condor          │ 09:35    │ Sell ATM±150 CE/PE            │ Exit on Short Strike breach   │
│    │                      │          │ Buy ATM±250 CE/PE Wings       │ (ATM±150), Target ₹1600       │
├────┼──────────────────────┼──────────┼───────────────────────────────┼───────────────────────────────┤
│ S4 │ VWAP Call Momentum   │ >09:40   │ Spot > VWAP + 15 pts &        │ SL -15 pts (trail to cost at  │
│    │                      │          │ Spot >= Day_High - 5 pts      │ +18 pts), Target +35 pts      │
├────┼──────────────────────┼──────────┼───────────────────────────────┼───────────────────────────────┤
│ S5 │ VWAP Put Momentum    │ >09:40   │ Spot < VWAP - 15 pts &        │ SL -15 pts (trail to cost at  │
│    │                      │          │ Spot <= Day_Low + 5 pts       │ +18 pts), Target +35 pts      │
├────┼──────────────────────┼──────────┼───────────────────────────────┼───────────────────────────────┤
│ S6 │ Bull Put Spread      │ >09:45   │ Spot > VWAP + 10 pts          │ Target 75% credit collected,  │
│    │                      │          │ Sell ATM PE / Buy ATM-100 PE  │ SL 100% credit (min ₹900)     │
├────┼──────────────────────┼──────────┼───────────────────────────────┼───────────────────────────────┤
│ S7 │ Bear Call Spread     │ >09:45   │ Spot < VWAP - 10 pts          │ Target 75% credit collected,  │
│    │                      │          │ Sell ATM CE / Buy ATM+100 CE  │ SL 100% credit (min ₹900)     │
├────┼──────────────────────┼──────────┼───────────────────────────────┼───────────────────────────────┤
│ S8 │ 09:45 Straddle Buy   │ 09:45    │ Buy ATM CE + Buy ATM PE       │ 90-Min Time Stop (Theta trap),│
│    │                      │          │ (Volatility Expansion)        │ Target +₹2800, SL -₹1400      │
├────┼──────────────────────┼──────────┼───────────────────────────────┼───────────────────────────────┤
│ S9 │ 15-Min ORB Scalper   │ >09:30   │ Breakout of 09:15-09:30 range │ Target +₹1500, SL -₹800,      │
│    │                      │          │ (Spot > ORB_H+5 / < ORB_L-5)  │ Exit if crosses ORB Midpoint  │
├────┼──────────────────────┼──────────┼───────────────────────────────┼───────────────────────────────┤
│ S10│ Mean Reversion Fade  │ >10:00   │ Spot stretches ±60 pts        │ Target Spot touches VWAP ±8,  │
│    │                      │          │ away from VWAP                │ Target +₹1800, SL -₹1000      │
└────┴──────────────────────┴──────────┴───────────────────────────────┴───────────────────────────────┘

```

---

## Directory Layout

```
nifty-options-quant-engine/
│
├── config/
│   ├── __init__.py
│   └── settings.py               # Immutable parameters (Frictional rates, Lot sizes, Endpoints)
│
├── core/
│   ├── __init__.py
│   ├── brokerage_calculator.py   # NSE/SEBI/GST statutory calculation engine
│   ├── execution_engine.py       # Slip fill emulator (0.25% market impact model)
│   ├── market_state.py           # O(1) mathematical telemetry engine (VWAP, ORB, High/Low)
│   └── models.py                 # Pure domain primitives (PositionLeg, TradeAuditRecord)
│
├── strategies/
│   ├── __init__.py
│   ├── base.py                   # Strategy lifecycle interface with append-only CSV writer
│   ├── s1_short_straddle.py
│   ├── s2_short_strangle.py
│   ├── s3_iron_condor.py
│   ├── s4_vwap_call_momentum.py
│   ├── s5_vwap_put_momentum.py
│   ├── s6_bull_put_spread.py
│   ├── s7_bear_call_spread.py
│   ├── s8_straddle_buy.py
│   ├── s9_orb_scalper.py
│   └── s10_mean_reversion.py
│
├── dashboards/
│   ├── index.html                # Live option chain browser (Calls | Strike | Puts)
│   └── strategy_dashboard.html   # Live 10-strategy monitor connecting to Port 5556
│
├── logs/
│   └── .gitkeep                  # Isolated trade CSV logs stream here
│
├── server.py                     # Independent Producer: WebSocket client & JSON broadcaster
└── multi_strategy_bot.py         # Independent Consumer: Automated execution engine

```

---

## Installation & Setup

### Environment Requirements

* Python 3.9 or higher (standard library focus).
* Supported Operating Systems: Ubuntu/Debian, CentOS, macOS, Windows 10/11, Android (via Termux).

### 1. Clone the Repository

```bash
git clone https://github.com/pihuflex-tech/nifty-options-quant-engine.git
cd nifty-options-quant-engine

```

### 2. Set Up Virtual Environment & Dependencies

```bash
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

```

*Note: `multi_strategy_bot.py` requires zero external libraries. `requirements.txt` is needed only for `server.py` to communicate with the broker:*

```text
smartapi-python>=1.4.8
pyotp>=2.8.0
websocket-client>=1.6.0

```

---

## Operating Instructions

The system runs as two decoupled, non-blocking processes over localhost.

### Step 1: Start the Feed Producer

Connects to Angel One SmartAPI WebSocket 2.0, downloads/caches the instrument master, and broadcasts the current snapshot over port `5555`.

```bash
python3 server.py

```

### Step 2: Launch the Consumer Multi-Strategy Bot

Consumes `[http://127.0.0.1:5555/](http://127.0.0.1:5555/)`, executes strategy state machines, writes audit trails, and hosts the dashboard server on port `5556`.

```bash
python3 multi_strategy_bot.py

```

### Step 3: Open the Visual Telemetry Dashboard

Open `dashboards/strategy_dashboard.html` in any web browser.

* Direct URL: `file:///path/to/nifty-options-quant-engine/dashboards/strategy_dashboard.html`
* Telemetry polls `[http://127.0.0.1:5556/](http://127.0.0.1:5556/)` every 500ms to render strategy statuses, active legs, execution fills, stop-loss triggers, open MTM, and statutory fees.

---

## Automation Guide (Headless Termux & Linux)

### Android Termux Deployment

Termux allows 24/7 low-power deployment directly on Android devices without rooting.

1. **Install Core Utilities:**
```bash
pkg update && pkg install python git cronie termux-api termux-services -y

```


2. **Prevent Android CPU Throttling:**
```bash
termux-wake-lock

```


3. **Automate Daily Market Open Execution (`crontab`):**
```bash
EDITOR=nano crontab -e

```


Add the following line to schedule the bot at 09:14 AM Monday through Friday:
```cron
14 9 * * 1-5 cd $HOME/nifty-options-quant-engine && python3 multi_strategy_bot.py >> $HOME/nifty-options-quant-engine/logs/cron.log 2>&1

```


4. **Start the Cron Daemon:**
```bash
crond

```



---

## 3-Month Trade Log Audit & CSV Schema

Every strategy writes to its own isolated file under `logs/` (e.g., `logs/trades_S1_short_straddle.csv`), guaranteeing independent accounting and zero data lock contention.

### CSV Column Reference

| Column Header | Data Type | Description |
| --- | --- | --- |
| `StrategyID` | `VARCHAR(4)` | Unique strategy identifier (`S1` to `S10`) |
| `StrategyName` | `VARCHAR(32)` | System strategy label |
| `EntryDate` | `YYYY-MM-DD` | Calendar date order was filled |
| `EntryTime` | `HH:MM:SS` | Real-time entry execution timestamp |
| `ExitDate` | `YYYY-MM-DD` | Calendar date position was liquidated |
| `ExitTime` | `HH:MM:SS` | Real-time liquidation execution timestamp |
| `Symbol` | `VARCHAR(32)` | Full option symbol (e.g., `NIFTY_24500_CE`) |
| `Side` | `BUY / SELL` | Trade direction of the leg |
| `Qty` | `INTEGER` | Executed quantity (65 units = 1 lot) |
| `EntryPrice` | `FLOAT(2)` | Execution fill price including 0.25% slippage |
| `ExitPrice` | `FLOAT(2)` | Liquidation fill price including 0.25% slippage |
| `GrossPnL` | `FLOAT(2)` | Raw trading P&L before any fees |
| `Brokerage` | `FLOAT(2)` | Round-turn brokerage cost (₹40/leg) |
| `STT` | `FLOAT(2)` | Securities Transaction Tax (0.1% on Sell turnover) |
| `ExchangeCharges` | `FLOAT(2)` | NSE turnover surcharge (0.03503%) |
| `GST` | `FLOAT(2)` | 18% GST on broker and exchange charges |
| `TotalCharges` | `FLOAT(2)` | Sum of all regulatory and brokerage deductions |
| `NetPnL` | `FLOAT(2)` | Realized net return ($\text{GrossPnL} - \text{TotalCharges}$) |
| `ExitReason` | `VARCHAR(32)` | Trigger mechanism (`TARGET_MET`, `SL_HIT`, `EOD_SQUAREOFF`) |

### Performance Optimization Framework (Post 90-Day Analysis)

After logging 60 to 65 operational market days, calculate the following metrics per CSV to validate each strategy's statistical edge:

1. **System Expectancy ($E$):**

$$E = (W \times \overline{\text{Win}}) - (L \times \overline{\text{Loss}})$$



*Where $W$ is Win Rate, $L$ is Loss Rate ($1-W$), $\overline{\text{Win}}$ is Average Net Win, and $\overline{\text{Loss}}$ is Average Net Loss.*
*Action:* If $E \le 0$, the edge does not overcome the statutory tax burden. Disable the setup.
2. **Profit Factor ($PF$):**

$$PF = \frac{\sum \text{Gross Net Profits}}{\sum \text{Gross Net Losses}}$$



*Action:* $PF > 1.5$ indicates a stable system. If $1.0 < PF < 1.2$, widen the profit target or filter chop via India VIX.
3. **Maximum Adverse Excursion (MAE) Analysis:**
Inspect the intraday drawdowns of winning trades. If winning trades rarely pull back beyond 35% of the stop loss, tighten the initial stop level to increase position leverage safely.

---

## Disclaimer

This software is developed strictly for **quantitative research, backtesting, and paper trading simulation**. It contains no live broker order placement routines. Derivative trading in the National Stock Exchange of India (NSE) involves substantial risk of financial loss. Ensure compliance with all SEBI guidelines and algorithmic trading regulations before connecting this logic to real-money capital.
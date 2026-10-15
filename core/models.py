from dataclasses import dataclass

@dataclass
class PositionLeg:
    symbol: str
    strike: int
    option_type: str         # "CE" or "PE"
    side: str                # "BUY" or "SELL"
    entry_price: float       # Slipped fill price
    qty: int
    raw_entry_price: float   # Benchmark LTP at entry
    entry_date: str          # YYYY-MM-DD
    entry_time: str          # HH:MM:SS
    current_ltp: float = 0.0
    sl_price: float = 0.0
    is_open: bool = True

@dataclass
class TradeAuditRecord:
    strategy_id: str
    strategy_name: str
    entry_date: str          # Exact day opened
    entry_time: str          # Exact time opened
    exit_date: str           # Exact day closed
    exit_time: str           # Exact time closed
    symbol: str
    side: str
    qty: int
    entry_price: float
    exit_price: float
    gross_pnl: float
    charges: float
    net_pnl: float
    exit_reason: str
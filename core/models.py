from dataclasses import dataclass

@dataclass
class PositionLeg:
    symbol: str
    strike: int
    option_type: str
    side: str
    entry_price: float
    qty: int
    raw_entry_price: float
    entry_date: str = ""
    entry_time: str = ""
    current_ltp: float = 0.0
    sl_price: float = 0.0
    target_price: float = 0.0
    is_open: bool = True
    sl_shifted_to_cost: bool = False

@dataclass
class TradeAuditRecord:
    strategy_id: str
    strategy_name: str
    entry_date: str
    entry_time: str
    exit_date: str
    exit_time: str
    symbol: str
    side: str
    qty: int
    entry_price: float
    exit_price: float
    gross_pnl: float
    charges: float
    net_pnl: float
    exit_reason: str
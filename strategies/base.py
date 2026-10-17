import os
import csv
from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Dict, Any, Optional

from config.settings import CONFIG
from core.models import PositionLeg, TradeAuditRecord
from core.execution_engine import apply_slippage
from core.brokerage_calculator import calculate_exact_costs, calculate_detailed_statutory_costs
from core.market_state import MarketStateManager

class BaseStrategy(ABC):
    def __init__(self, strategy_id: str, name: str, log_file: str):
        self.strategy_id = strategy_id
        self.name = name
        self.log_file = log_file
        self.csv_path = log_file  # Alias for backward compatibility
        self.active: bool = False
        self.completed_today: bool = False
        self.legs: List[PositionLeg] = []
        self.realized_pnl: float = 0.0
        self.peak_pnl: float = -1e9
        self.charges_paid: float = 0.0
        self.entry_date: str = ""
        self.entry_timestamp: str = ""
        self.exit_reason: str = ""
        self.current_trading_date: str = ""
        self._ensure_log_file()

    def check_new_day(self, today_date: str):
        """Resets strategy state when a new trading session begins."""
        if self.current_trading_date != today_date:
            self.current_trading_date = today_date
            self.active = False
            self.completed_today = False
            self.legs = []
            self.realized_pnl = 0.0
            self.peak_pnl = -1e9
            self.charges_paid = 0.0
            self.entry_date = ""
            self.entry_timestamp = ""
            self.exit_reason = ""

    def _ensure_log_file(self):
        dirname = os.path.dirname(self.log_file)
        if dirname:
            os.makedirs(dirname, exist_ok=True)
        if not os.path.exists(self.log_file):
            with open(self.log_file, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow([
                    "StrategyID", "StrategyName", "EntryDate", "EntryTime",
                    "ExitDate", "ExitTime", "Symbol", "Side", "Qty",
                    "EntryPrice", "ExitPrice", "GrossPnL", "Brokerage",
                    "STT", "ExchangeCharges", "GST", "TotalCharges", "NetPnL", "ExitReason"
                ])

    def refresh_leg_prices(self, contracts: Any):
        """
        Updates current LTP for all active position legs using the market contracts feed.
        """
        if not contracts or not self.legs:
            return

        for leg in self.legs:
            if not leg.is_open:
                continue

            # First attempt: search via MarketStateManager
            info = MarketStateManager.find_contract(contracts, int(leg.strike), leg.option_type)
            if info and info[1] > 0:
                leg.current_ltp = info[1]
                continue

            # Second attempt: check if contracts is a dict keyed directly by symbol
            if isinstance(contracts, dict) and leg.symbol in contracts:
                val = contracts[leg.symbol]
                if isinstance(val, (int, float)) and float(val) > 0:
                    leg.current_ltp = float(val)
                elif isinstance(val, dict) and val.get("ltp") is not None and float(val["ltp"]) > 0:
                    leg.current_ltp = float(val["ltp"])
            # Third attempt: check list input
            elif isinstance(contracts, list):
                for item in contracts:
                    if isinstance(item, (list, tuple)) and len(item) >= 2 and item[0] == leg.symbol:
                        try:
                            px = float(item[1])
                            if px > 0:
                                leg.current_ltp = px
                                break
                        except (ValueError, TypeError):
                            pass
                    elif isinstance(item, dict) and item.get("symbol") == leg.symbol:
                        try:
                            px = float(item.get("ltp", 0))
                            if px > 0:
                                leg.current_ltp = px
                                break
                        except (ValueError, TypeError):
                            pass

    def is_leg_sl_hit(self, leg: PositionLeg) -> bool:
        if not leg.is_open or leg.sl_price <= 0 or leg.current_ltp <= 0:
            return False
        if leg.side == "SELL":
            return leg.current_ltp >= leg.sl_price
        return leg.current_ltp <= leg.sl_price

    def is_leg_target_hit(self, leg: PositionLeg) -> bool:
        if not leg.is_open or leg.target_price <= 0 or leg.current_ltp <= 0:
            return False
        if leg.side == "SELL":
            return leg.current_ltp <= leg.target_price
        return leg.current_ltp >= leg.target_price

    def get_open_mtm(self) -> float:
        if not self.active:
            return 0.0
        mtm = 0.0
        for leg in self.legs:
            if leg.is_open:
                ref_ltp = leg.current_ltp if leg.current_ltp > 0 else leg.raw_entry_price
                if leg.side == "SELL":
                    diff = leg.entry_price - ref_ltp
                else:
                    diff = ref_ltp - leg.entry_price
                mtm += diff * leg.qty
        return round(mtm, 2)

    def close_single_leg(self, leg: PositionLeg, reason: str, contracts: Any, now_dt: Optional[datetime] = None):
        if not leg.is_open:
            return

        self.refresh_leg_prices(contracts)
        ref_ltp = leg.current_ltp if leg.current_ltp > 0 else leg.raw_entry_price
        exit_side = "BUY" if leg.side == "SELL" else "SELL"
        exit_px = apply_slippage(ref_ltp, exit_side)

        gross = (exit_px - leg.entry_price) * leg.qty if leg.side == "BUY" else (leg.entry_price - exit_px) * leg.qty
        costs = calculate_exact_costs(qty=leg.qty, entry_px=leg.entry_price, exit_px=exit_px, side=leg.side)
        charges = costs["total_charges"]
        net_leg = gross - charges

        leg.is_open = False
        self.realized_pnl += net_leg
        self.charges_paid += charges

        now = now_dt or datetime.now()
        rec = TradeAuditRecord(
            strategy_id=self.strategy_id,
            strategy_name=self.name,
            entry_date=leg.entry_date or self.entry_date or now.strftime("%Y-%m-%d"),
            entry_time=leg.entry_time or self.entry_timestamp or now.strftime("%H:%M:%S"),
            exit_date=now.strftime("%Y-%m-%d"),
            exit_time=now.strftime("%H:%M:%S"),
            symbol=leg.symbol,
            side=leg.side,
            qty=leg.qty,
            entry_price=leg.entry_price,
            exit_price=exit_px,
            gross_pnl=round(gross, 2),
            charges=round(charges, 2),
            net_pnl=round(net_leg, 2),
            exit_reason=reason
        )
        self._write_trade_log(rec, costs)

        if not any(l.is_open for l in self.legs):
            self.active = False
            self.completed_today = True
            self.exit_reason = reason

    def close_all_legs(self, reason: str, contracts: Any, now_dt: Optional[datetime] = None):
        for leg in self.legs:
            if leg.is_open:
                self.close_single_leg(leg, reason, contracts, now_dt=now_dt)
        self.active = False
        self.completed_today = True
        self.exit_reason = reason

    def to_dict(self) -> Dict[str, Any]:
        status = "ACTIVE" if self.active else ("CLOSED" if self.completed_today else "IDLE")
        legs_data = []
        for l in self.legs:
            ref_ltp = l.current_ltp if l.current_ltp > 0 else l.raw_entry_price
            leg_pnl = (l.entry_price - ref_ltp) * l.qty if l.side == "SELL" else (ref_ltp - l.entry_price) * l.qty
            legs_data.append({
                "symbol": l.symbol,
                "strike": l.strike,
                "option_type": l.option_type,
                "side": l.side,
                "qty": l.qty,
                "entry_date": l.entry_date or self.entry_date or "--",
                "entry_time": l.entry_time or self.entry_timestamp or "--:--:--",
                "entry_price": l.entry_price,
                "current_ltp": l.current_ltp,
                "sl_price": l.sl_price,
                "target_price": l.target_price,
                "is_open": l.is_open,
                "leg_pnl": round(leg_pnl, 2) if l.is_open else 0.0
            })

        return {
            "id": self.strategy_id,
            "name": self.name,
            "status": status,
            "entry_date": self.entry_date or "--",
            "entry_time": self.entry_timestamp or "--:--:--",
            "exit_reason": self.exit_reason or "-",
            "open_mtm": self.get_open_mtm(),
            "realized_pnl": round(self.realized_pnl, 2),
            "charges_paid": round(self.charges_paid, 2),
            "net_pnl": round(self.realized_pnl - self.charges_paid, 2),
            "csv_path": self.log_file,
            "legs": legs_data
        }

    def _write_trade_log(self, rec: TradeAuditRecord, costs: dict):
        with open(self.log_file, "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow([
                rec.strategy_id, rec.strategy_name, rec.entry_date, rec.entry_time,
                rec.exit_date, rec.exit_time, rec.symbol, rec.side, rec.qty,
                rec.entry_price, rec.exit_price, rec.gross_pnl, costs["brokerage"],
                costs["stt"], costs["exchange_charges"], costs["gst"], rec.charges,
                rec.net_pnl, rec.exit_reason
            ])

    @abstractmethod
    def evaluate(self, spot: float, market: MarketStateManager, contracts: Any, now_dt: Optional[datetime] = None):
        """Evaluates entry and exit logic on every market tick."""
        pass
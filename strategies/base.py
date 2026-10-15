import os
import csv
from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Dict
from core.models import PositionLeg, TradeAuditRecord
from core.execution_engine import apply_slippage
from core.brokerage_calculator import calculate_exact_costs
from core.market_state import MarketStateManager

class BaseStrategy(ABC):
    def __init__(self, strategy_id: str, name: str, csv_path: str):
        self.strategy_id = strategy_id
        self.name = name
        self.csv_path = csv_path
        self.active: bool = False
        self.completed_today: bool = False
        self.legs: List[PositionLeg] = []
        self.peak_pnl: float = -1e9
        self.realized_pnl: float = 0.0
        self.charges_paid: float = 0.0
        self.entry_date: str = ""       # YYYY-MM-DD
        self.entry_timestamp: str = ""  # HH:MM:SS
        self.exit_reason: str = ""
        self._init_csv()

    def _init_csv(self):
        os.makedirs(os.path.dirname(self.csv_path) or ".", exist_ok=True)
        if not os.path.isfile(self.csv_path):
            with open(self.csv_path, mode="w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "StrategyID", "StrategyName",
                    "EntryDate", "EntryTime",
                    "ExitDate", "ExitTime",
                    "Symbol", "Side", "Qty",
                    "EntryPrice", "ExitPrice",
                    "GrossPnL", "Brokerage", "STT", "ExchangeCharges", "GST", "TotalCharges",
                    "NetPnL", "ExitReason"
                ])

    def _write_audit_row(self, rec: TradeAuditRecord, cost_breakdown: dict):
        with open(self.csv_path, mode="a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                rec.strategy_id, rec.strategy_name,
                rec.entry_date, rec.entry_time,
                rec.exit_date, rec.exit_time,
                rec.symbol, rec.side, rec.qty,
                rec.entry_price, rec.exit_price,
                rec.gross_pnl,
                cost_breakdown["brokerage"],
                cost_breakdown["stt"],
                cost_breakdown["exchange_charges"],
                cost_breakdown["gst"],
                rec.charges,
                rec.net_pnl,
                rec.exit_reason
            ])

    def refresh_leg_prices(self, contracts: Dict):
        for leg in self.legs:
            if leg.is_open:
                info = MarketStateManager.find_contract(contracts, int(leg.strike), leg.option_type)
                if info:
                    leg.current_ltp = info[1]

    def close_single_leg(self, leg: PositionLeg, reason: str, contracts: Dict):
        if not leg.is_open:
            return
            
        now = datetime.now()
        exit_date = now.strftime("%Y-%m-%d")
        exit_time = now.strftime("%H:%M:%S")

        info = MarketStateManager.find_contract(contracts, int(leg.strike), leg.option_type)
        curr_px = info[1] if info else (leg.current_ltp if leg.current_ltp > 0 else leg.raw_entry_price)
        exit_side = "BUY" if leg.side == "SELL" else "SELL"
        exit_px = apply_slippage(curr_px, exit_side)

        gross = (leg.entry_price - exit_px) * leg.qty if leg.side == "SELL" else (exit_px - leg.entry_price) * leg.qty
        cost_details = calculate_exact_costs(leg.qty, leg.entry_price, exit_px, leg.side)
        charges = cost_details["total_charges"]
        net_leg = gross - charges

        self.realized_pnl += net_leg
        self.charges_paid += charges
        leg.is_open = False

        # Preserves the exact day and time the leg was entered
        rec = TradeAuditRecord(
            strategy_id=self.strategy_id,
            strategy_name=self.name,
            entry_date=leg.entry_date,
            entry_time=leg.entry_time,
            exit_date=exit_date,
            exit_time=exit_time,
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
        self._write_audit_row(rec, cost_details)

        if not any(l.is_open for l in self.legs):
            self.active = False
            self.completed_today = True
            self.exit_reason = reason

    def close_all_legs(self, reason: str, contracts: Dict):
        if not self.active and not any(l.is_open for l in self.legs):
            return
        for leg in self.legs:
            if leg.is_open:
                self.close_single_leg(leg, reason, contracts)
        self.active = False
        self.completed_today = True
        self.exit_reason = reason

    def get_open_mtm(self) -> float:
        if not self.active:
            return 0.0
        mtm = 0.0
        for leg in self.legs:
            if leg.is_open:
                ref_ltp = leg.current_ltp if leg.current_ltp > 0 else leg.raw_entry_price
                if leg.side == "SELL":
                    mtm += (leg.entry_price - ref_ltp) * leg.qty
                else:
                    mtm += (ref_ltp - leg.entry_price) * leg.qty
        return round(mtm, 2)

    def to_dict(self) -> dict:
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
                "entry_date": l.entry_date,
                "entry_time": l.entry_time,
                "entry_price": l.entry_price,
                "current_ltp": l.current_ltp,
                "sl_price": l.sl_price,
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
            "csv_path": self.csv_path,
            "legs": legs_data
        }

    @abstractmethod
    def evaluate(self, spot: float, market: MarketStateManager, contracts: Dict):
        pass
import os
import csv
from datetime import datetime
from config.settings import CONFIG
from core.models import TradeAuditRecord
from core.execution_engine import apply_slippage
from core.brokerage_calculator import calculate_detailed_statutory_costs

class BaseStrategy:
    def __init__(self, strategy_id: str, name: str, log_file: str):
        self.strategy_id = strategy_id
        self.name = name
        self.log_file = log_file
        self.active = False
        self.completed_today = False
        self.legs = []
        self.realized_pnl = 0.0
        self.peak_pnl = 0.0
        self.entry_date = ""
        self.entry_timestamp = ""
        self.current_trading_date = ""
        self._ensure_log_file()

    def check_new_day(self, today_date: str):
        if self.current_trading_date != today_date:
            self.current_trading_date = today_date
            self.active = False
            self.completed_today = False
            self.legs = []
            self.realized_pnl = 0.0
            self.peak_pnl = 0.0
            self.entry_date = ""
            self.entry_timestamp = ""

    def _ensure_log_file(self):
        os.makedirs(os.path.dirname(self.log_file), exist_ok=True)
        if not os.path.exists(self.log_file):
            with open(self.log_file, "w", newline="") as f:
                csv.writer(f).writerow([
                    "StrategyID", "StrategyName", "EntryDate", "EntryTime",
                    "ExitDate", "ExitTime", "Symbol", "Side", "Qty",
                    "EntryPrice", "ExitPrice", "GrossPnL", "Brokerage",
                    "STT", "ExchangeCharges", "GST", "TotalCharges", "NetPnL", "ExitReason"
                ])

    def refresh_leg_prices(self, contracts: list):
        c_map = {}
        for c in contracts:
            if len(c) >= 2:
                try:
                    px = float(c[1])
                    if px > 0:
                        c_map[c[0]] = px
                except (ValueError, TypeError):
                    continue
        for leg in self.legs:
            if leg.is_open and leg.symbol in c_map:
                leg.current_ltp = c_map[leg.symbol]

    def is_leg_sl_hit(self, leg) -> bool:
        if not leg.is_open or leg.sl_price <= 0 or leg.current_ltp <= 0:
            return False
        if leg.side == "SELL":
            return leg.current_ltp >= leg.sl_price
        return leg.current_ltp <= leg.sl_price

    def is_leg_target_hit(self, leg) -> bool:
        if not leg.is_open or leg.target_price <= 0 or leg.current_ltp <= 0:
            return False
        if leg.side == "SELL":
            return leg.current_ltp <= leg.target_price
        return leg.current_ltp >= leg.target_price

    def get_open_mtm(self) -> float:
        mtm = 0.0
        for leg in self.legs:
            if leg.is_open and leg.current_ltp > 0:
                diff = (leg.current_ltp - leg.entry_price) if leg.side == "BUY" else (leg.entry_price - leg.current_ltp)
                mtm += diff * leg.qty
        return round(mtm, 2)

    def close_single_leg(self, leg, reason: str, contracts: list):
        if not leg.is_open:
            return
        self.refresh_leg_prices(contracts)
        ref_ltp = leg.current_ltp if leg.current_ltp > 0 else leg.raw_entry_price
        exit_side = "BUY" if leg.side == "SELL" else "SELL"
        exit_px = apply_slippage(ref_ltp, exit_side)

        gross = (exit_px - leg.entry_price) * leg.qty if leg.side == "BUY" else (leg.entry_price - exit_px) * leg.qty
        costs = calculate_detailed_statutory_costs(leg.entry_price, exit_px, leg.qty)
        charges = costs["total_charges"]
        net_leg = gross - charges

        leg.is_open = False
        self.realized_pnl += net_leg

        now = datetime.now()
        rec = TradeAuditRecord(
            strategy_id=self.strategy_id,
            strategy_name=self.name,
            entry_date=leg.entry_date,
            entry_time=leg.entry_time,
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

    def close_all_legs(self, reason: str, contracts: list):
        for leg in self.legs:
            if leg.is_open:
                self.close_single_leg(leg, reason, contracts)
        self.active = False
        self.completed_today = True

    def _write_trade_log(self, rec: TradeAuditRecord, costs: dict):
        with open(self.log_file, "a", newline="") as f:
            csv.writer(f).writerow([
                rec.strategy_id, rec.strategy_name, rec.entry_date, rec.entry_time,
                rec.exit_date, rec.exit_time, rec.symbol, rec.side, rec.qty,
                rec.entry_price, rec.exit_price, rec.gross_pnl, costs["brokerage"],
                costs["stt"], costs["exchange_charges"], costs["gst"], rec.charges,
                rec.net_pnl, rec.exit_reason
            ])
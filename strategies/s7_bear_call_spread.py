# S7: strategies/s7_bear_call_spread.py
from datetime import datetime
from typing import Optional
from strategies.base import BaseStrategy
from core.models import PositionLeg
from core.execution_engine import apply_slippage
from config.settings import CONFIG

class S7BearCallSpread(BaseStrategy):
    def __init__(self):
        super().__init__("S7", "Bear Call Spread", "logs/trades_S7_bear_call_spread.csv")
        self.target_pnl: float = 1200.0
        self.sl_pnl: float = -1200.0

    def check_new_day(self, today_date: str):
        super().check_new_day(today_date)
        if self.current_trading_date == today_date and not self.active and not self.completed_today:
            self.target_pnl = 1200.0
            self.sl_pnl = -1200.0

    def evaluate(self, spot, market, contracts, now_dt: Optional[datetime] = None):
        now = now_dt or datetime.now()
        t_str, sec_str, today_date = now.strftime("%H:%M"), now.strftime("%H:%M:%S"), now.strftime("%Y-%m-%d")
        self.check_new_day(today_date)

        if self.active:
            self.refresh_leg_prices(contracts)
            total_mtm = self.get_open_mtm() + self.realized_pnl

            if t_str >= CONFIG.AUTO_SQUAREOFF:
                self.close_all_legs("EOD_SQUAREOFF", contracts, now_dt=now)
            elif total_mtm >= self.target_pnl:
                self.close_all_legs("TARGET_75PCT_CREDIT", contracts, now_dt=now)
            elif total_mtm <= self.sl_pnl:
                self.close_all_legs("SPREAD_SL_HIT", contracts, now_dt=now)
            return

        if not self.completed_today and spot > 0 and market.vwap > 0 and "09:45" <= t_str < "14:30":
            if spot < (market.vwap - 10.0):
                atm = market.get_atm_strike(spot)
                s_ce = market.find_contract(contracts, atm, "CE")
                b_ce = market.find_contract(contracts, atm + 100, "CE")
                if s_ce and b_ce and s_ce[1] > 0 and b_ce[1] > 0:
                    sell_px = apply_slippage(s_ce[1], "SELL")
                    buy_px = apply_slippage(b_ce[1], "BUY")
                    net_credit = (sell_px - buy_px) * CONFIG.NIFTY_LOT_SIZE
                    if net_credit > 0:
                        self.target_pnl = round(net_credit * 0.75, 2)
                        self.sl_pnl = -round(max(net_credit, 900.0), 2)
                        self.entry_date, self.entry_timestamp = today_date, sec_str
                        self.legs = [
                            PositionLeg(
                                symbol=s_ce[0], strike=atm, option_type="CE", side="SELL",
                                entry_price=sell_px, qty=CONFIG.NIFTY_LOT_SIZE, raw_entry_price=s_ce[1],
                                entry_date=today_date, entry_time=sec_str, current_ltp=s_ce[1],
                                sl_price=0.0, is_open=True
                            ),
                            PositionLeg(
                                symbol=b_ce[0], strike=atm + 100, option_type="CE", side="BUY",
                                entry_price=buy_px, qty=CONFIG.NIFTY_LOT_SIZE, raw_entry_price=b_ce[1],
                                entry_date=today_date, entry_time=sec_str, current_ltp=b_ce[1],
                                sl_price=0.0, is_open=True
                            )
                        ]
                        self.active = True
# S8: strategies/s8_straddle_buy.py
import time
from datetime import datetime
from typing import Optional
from strategies.base import BaseStrategy
from core.models import PositionLeg
from core.execution_engine import apply_slippage
from config.settings import CONFIG

class S8StraddleBuy(BaseStrategy):
    def __init__(self):
        super().__init__("S8", "09:45 Straddle Buy", "logs/trades_S8_straddle_buy.csv")
        self.entry_epoch: float = 0.0

    def check_new_day(self, today_date: str):
        super().check_new_day(today_date)
        if self.current_trading_date == today_date and not self.active and not self.completed_today:
            self.entry_epoch = 0.0

    def evaluate(self, spot, market, contracts, now_dt: Optional[datetime] = None):
        now = now_dt or datetime.now()
        t_str, sec_str, today_date = now.strftime("%H:%M"), now.strftime("%H:%M:%S"), now.strftime("%Y-%m-%d")
        self.check_new_day(today_date)

        if self.active:
            self.refresh_leg_prices(contracts)
            total_mtm = self.get_open_mtm() + self.realized_pnl
            elapsed_seconds = (time.time() - self.entry_epoch) if self.entry_epoch > 0 else 0

            if t_str >= CONFIG.AUTO_SQUAREOFF:
                self.close_all_legs("EOD_SQUAREOFF", contracts, now_dt=now)
            elif total_mtm >= 2800.0:
                self.close_all_legs("VOL_EXPANSION_TARGET", contracts, now_dt=now)
            elif total_mtm <= -1400.0:
                self.close_all_legs("THETA_BLEED_SL", contracts, now_dt=now)
            elif elapsed_seconds >= 5400:  # 90 minutes limit
                self.close_all_legs("90MIN_TIME_STOP", contracts, now_dt=now)
            return

        if not self.completed_today and spot > 0 and "09:45" <= t_str < "14:00":
            atm = market.get_atm_strike(spot)
            ce = market.find_contract(contracts, atm, "CE")
            pe = market.find_contract(contracts, atm, "PE")
            if ce and pe and ce[1] > 0 and pe[1] > 0:
                self.entry_epoch = time.time()
                self.entry_date, self.entry_timestamp = today_date, sec_str
                self.legs = [
                    PositionLeg(
                        symbol=ce[0], strike=atm, option_type="CE", side="BUY",
                        entry_price=apply_slippage(ce[1], "BUY"), qty=CONFIG.NIFTY_LOT_SIZE,
                        raw_entry_price=ce[1], entry_date=today_date, entry_time=sec_str,
                        current_ltp=ce[1], sl_price=0.0, is_open=True
                    ),
                    PositionLeg(
                        symbol=pe[0], strike=atm, option_type="PE", side="BUY",
                        entry_price=apply_slippage(pe[1], "BUY"), qty=CONFIG.NIFTY_LOT_SIZE,
                        raw_entry_price=pe[1], entry_date=today_date, entry_time=sec_str,
                        current_ltp=pe[1], sl_price=0.0, is_open=True
                    )
                ]
                self.active = True
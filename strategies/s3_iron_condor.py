# S3: strategies/s3_iron_condor.py
from datetime import datetime
from typing import Optional
from strategies.base import BaseStrategy
from core.models import PositionLeg
from core.execution_engine import apply_slippage
from config.settings import CONFIG

class S3IronCondor(BaseStrategy):
    def __init__(self):
        super().__init__("S3", "Iron Condor", "logs/trades_S3_iron_condor.csv")
        self.entry_atm: int = 0

    def check_new_day(self, today_date: str):
        super().check_new_day(today_date)
        if self.current_trading_date == today_date and not self.active and not self.completed_today:
            self.entry_atm = 0

    def evaluate(self, spot, market, contracts, now_dt: Optional[datetime] = None):
        now = now_dt or datetime.now()
        t_str, sec_str, today_date = now.strftime("%H:%M"), now.strftime("%H:%M:%S"), now.strftime("%Y-%m-%d")
        self.check_new_day(today_date)

        if self.active:
            self.refresh_leg_prices(contracts)
            total_mtm = self.get_open_mtm() + self.realized_pnl

            if t_str >= CONFIG.AUTO_SQUAREOFF:
                self.close_all_legs("EOD_SQUAREOFF", contracts, now_dt=now)
            elif self.entry_atm > 0 and (spot >= (self.entry_atm + 150) or spot <= (self.entry_atm - 150)):
                self.close_all_legs("SHORT_STRIKE_BREACHED", contracts, now_dt=now)
            elif total_mtm >= 1600.0:
                self.close_all_legs("TARGET_MET", contracts, now_dt=now)
            elif total_mtm <= -1400.0:
                self.close_all_legs("MAX_LOSS_HIT", contracts, now_dt=now)
            return

        if not self.completed_today and spot > 0 and "09:35" <= t_str < "14:30":
            atm = market.get_atm_strike(spot)
            cs = market.find_contract(contracts, atm + 150, "CE")
            ps = market.find_contract(contracts, atm - 150, "PE")
            cb = market.find_contract(contracts, atm + 250, "CE")
            pb = market.find_contract(contracts, atm - 250, "PE")
            if all(x and x[1] > 0 for x in (cs, ps, cb, pb)):
                self.entry_atm = atm
                self.entry_date, self.entry_timestamp = today_date, sec_str
                specs = [
                    (cs, atm + 150, "CE", "SELL"),
                    (ps, atm - 150, "PE", "SELL"),
                    (cb, atm + 250, "CE", "BUY"),
                    (pb, atm - 250, "PE", "BUY"),
                ]
                self.legs = [
                    PositionLeg(
                        symbol=c[0], strike=st, option_type=ot, side=sd,
                        entry_price=apply_slippage(c[1], sd), qty=CONFIG.NIFTY_LOT_SIZE,
                        raw_entry_price=c[1], entry_date=today_date, entry_time=sec_str,
                        current_ltp=c[1], sl_price=0.0, is_open=True
                    )
                    for c, st, ot, sd in specs
                ]
                self.active = True
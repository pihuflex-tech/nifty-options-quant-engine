# S2: strategies/s2_short_strangle.py
from datetime import datetime
from typing import Optional
from strategies.base import BaseStrategy
from core.models import PositionLeg
from core.execution_engine import apply_slippage
from config.settings import CONFIG

class S2ShortStrangle(BaseStrategy):
    def __init__(self):
        super().__init__("S2", "09:30 Short Strangle", "logs/trades_S2_short_strangle.csv")

    def evaluate(self, spot, market, contracts, now_dt: Optional[datetime] = None):
        now = now_dt or datetime.now()
        t_str, sec_str, today_date = now.strftime("%H:%M"), now.strftime("%H:%M:%S"), now.strftime("%Y-%m-%d")
        self.check_new_day(today_date)

        if self.active:
            self.refresh_leg_prices(contracts)
            if t_str >= CONFIG.AUTO_SQUAREOFF:
                self.close_all_legs("EOD_SQUAREOFF", contracts, now_dt=now)
                return

            for leg in self.legs:
                if self.is_leg_sl_hit(leg):
                    self.close_single_leg(leg, "LEG_30PCT_SL_HIT", contracts, now_dt=now)

            if not self.active:
                return

            total_mtm = self.get_open_mtm() + self.realized_pnl
            self.peak_pnl = max(self.peak_pnl, total_mtm)
            if total_mtm <= -1500.0:
                self.close_all_legs("MAX_LOSS_HIT", contracts, now_dt=now)
            elif self.peak_pnl >= 1800.0 and (self.peak_pnl - total_mtm) >= 700.0:
                self.close_all_legs("TRAILING_SL_HIT", contracts, now_dt=now)
            return

        if not self.completed_today and spot > 0 and "09:30" <= t_str < "14:45":
            atm = market.get_atm_strike(spot)
            ce = market.find_contract(contracts, atm + 100, "CE")
            pe = market.find_contract(contracts, atm - 100, "PE")
            if ce and pe and ce[1] > 0 and pe[1] > 0:
                c_fill = apply_slippage(ce[1], "SELL")
                p_fill = apply_slippage(pe[1], "SELL")
                self.entry_date, self.entry_timestamp = today_date, sec_str
                self.legs = [
                    PositionLeg(
                        symbol=ce[0], strike=atm + 100, option_type="CE", side="SELL",
                        entry_price=c_fill, qty=CONFIG.NIFTY_LOT_SIZE, raw_entry_price=ce[1],
                        entry_date=today_date, entry_time=sec_str, current_ltp=ce[1],
                        sl_price=round(c_fill * 1.30, 2), is_open=True
                    ),
                    PositionLeg(
                        symbol=pe[0], strike=atm - 100, option_type="PE", side="SELL",
                        entry_price=p_fill, qty=CONFIG.NIFTY_LOT_SIZE, raw_entry_price=pe[1],
                        entry_date=today_date, entry_time=sec_str, current_ltp=pe[1],
                        sl_price=round(p_fill * 1.30, 2), is_open=True
                    )
                ]
                self.active = True
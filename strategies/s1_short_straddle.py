# S1: strategies/s1_short_straddle.py
from datetime import datetime
from typing import Optional
from strategies.base import BaseStrategy
from core.models import PositionLeg
from core.execution_engine import apply_slippage
from config.settings import CONFIG

class S1ShortStraddle(BaseStrategy):
    def __init__(self):
        super().__init__("S1", "09:20 Short Straddle", "logs/trades_S1_short_straddle.csv")

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
                    reason = "COST_SL_HIT" if leg.sl_shifted_to_cost else "LEG_25PCT_SL_HIT"
                    self.close_single_leg(leg, reason, contracts, now_dt=now)
                    if not leg.sl_shifted_to_cost:
                        for other in self.legs:
                            if other.is_open:
                                other.sl_price = max(other.entry_price, other.raw_entry_price)
                                other.sl_shifted_to_cost = True
                        break

            if not self.active:
                return

            total_mtm = self.get_open_mtm() + self.realized_pnl
            if total_mtm >= 2500.0:
                self.close_all_legs("PROFIT_TARGET_HIT", contracts, now_dt=now)
            elif total_mtm <= -1800.0:
                self.close_all_legs("COMBINED_MAX_LOSS", contracts, now_dt=now)
            return

        if not self.completed_today and spot > 0 and "09:20" <= t_str < "14:45":
            atm = market.get_atm_strike(spot)
            ce = market.find_contract(contracts, atm, "CE")
            pe = market.find_contract(contracts, atm, "PE")
            if ce and pe and ce[1] > 0 and pe[1] > 0:
                c_fill = apply_slippage(ce[1], "SELL")
                p_fill = apply_slippage(pe[1], "SELL")
                self.entry_date, self.entry_timestamp = today_date, sec_str
                self.legs = [
                    PositionLeg(
                        symbol=ce[0], strike=atm, option_type="CE", side="SELL",
                        entry_price=c_fill, qty=CONFIG.NIFTY_LOT_SIZE, raw_entry_price=ce[1],
                        entry_date=today_date, entry_time=sec_str, current_ltp=ce[1],
                        sl_price=round(c_fill * 1.25, 2), is_open=True
                    ),
                    PositionLeg(
                        symbol=pe[0], strike=atm, option_type="PE", side="SELL",
                        entry_price=p_fill, qty=CONFIG.NIFTY_LOT_SIZE, raw_entry_price=pe[1],
                        entry_date=today_date, entry_time=sec_str, current_ltp=pe[1],
                        sl_price=round(p_fill * 1.25, 2), is_open=True
                    )
                ]
                self.active = True
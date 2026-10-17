# S4: strategies/s4_vwap_call_momentum.py
from datetime import datetime
from typing import Optional
from strategies.base import BaseStrategy
from core.models import PositionLeg
from core.execution_engine import apply_slippage
from config.settings import CONFIG

class S4VWAPCallMomentum(BaseStrategy):
    def __init__(self):
        super().__init__("S4", "VWAP Call Momentum", "logs/trades_S4_vwap_call.csv")

    def evaluate(self, spot, market, contracts, now_dt: Optional[datetime] = None):
        now = now_dt or datetime.now()
        t_str, sec_str, today_date = now.strftime("%H:%M"), now.strftime("%H:%M:%S"), now.strftime("%Y-%m-%d")
        self.check_new_day(today_date)

        if self.active and self.legs:
            self.refresh_leg_prices(contracts)
            leg = self.legs[0]

            # Trailing stop to cost when leg gains +18 pts
            if leg.is_open and leg.current_ltp >= (leg.entry_price + 18.0) and leg.sl_price < leg.entry_price:
                leg.sl_price = leg.entry_price + 1.0
                leg.sl_shifted_to_cost = True

            if t_str >= CONFIG.AUTO_SQUAREOFF:
                self.close_all_legs("EOD_SQUAREOFF", contracts, now_dt=now)
            elif leg.is_open and leg.current_ltp >= (leg.entry_price + 35.0):
                self.close_all_legs("TARGET_35PTS_HIT", contracts, now_dt=now)
            elif leg.is_open and (leg.current_ltp <= leg.sl_price or (market.vwap > 0 and spot < market.vwap)):
                reason = "COST_SL_HIT" if leg.sl_shifted_to_cost and leg.current_ltp <= leg.sl_price else "SL_OR_VWAP_CROSS"
                self.close_all_legs(reason, contracts, now_dt=now)
            return

        if not self.completed_today and spot > 0 and market.vwap > 0 and "09:40" <= t_str < "14:30":
            if market.day_high is not None and spot > (market.vwap + 15.0) and spot >= (market.day_high - 5.0):
                atm = market.get_atm_strike(spot)
                ce = market.find_contract(contracts, atm, "CE")
                if ce and ce[1] > 0:
                    fill = apply_slippage(ce[1], "BUY")
                    self.entry_date, self.entry_timestamp = today_date, sec_str
                    self.legs = [
                        PositionLeg(
                            symbol=ce[0], strike=atm, option_type="CE", side="BUY",
                            entry_price=fill, qty=CONFIG.NIFTY_LOT_SIZE, raw_entry_price=ce[1],
                            entry_date=today_date, entry_time=sec_str, current_ltp=ce[1],
                            sl_price=round(fill - 15.0, 2), target_price=round(fill + 35.0, 2), is_open=True
                        )
                    ]
                    self.active = True
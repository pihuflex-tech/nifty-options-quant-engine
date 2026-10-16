# S4: strategies/s4_vwap_call.py
from datetime import datetime
from strategies.base import BaseStrategy
from core.models import PositionLeg
from core.execution_engine import apply_slippage
from config.settings import CONFIG

class S4VWAPCallMomentum(BaseStrategy):
    def __init__(self):
        super().__init__("S4", "VWAP Call Momentum", "logs/trades_S4_vwap_call.csv")

    def evaluate(self, spot, market, contracts):
        now = datetime.now()
        t_str, sec_str, today_date = now.strftime("%H:%M"), now.strftime("%H:%M:%S"), now.strftime("%Y-%m-%d")
        self.check_new_day(today_date)

        if self.active:
            self.refresh_leg_prices(contracts)
            if t_str >= CONFIG.AUTO_SQUAREOFF:
                self.close_all_legs("EOD_SQUAREOFF", contracts)
                return
            if market.vwap > 0 and spot < market.vwap:
                self.close_all_legs("SPOT_BELOW_VWAP", contracts)
                return
            for leg in self.legs:
                if self.is_leg_sl_hit(leg):
                    self.close_single_leg(leg, "SL_20PCT_HIT", contracts)
                elif self.is_leg_target_hit(leg):
                    self.close_single_leg(leg, "TARGET_35PCT_HIT", contracts)
            return

        if not self.completed_today and spot > 0 and market.vwap > 0 and "09:25" <= t_str < "14:30":
            if spot > (market.vwap + 15.0) and abs(market.day_high - spot) <= 10.0:
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
                            sl_price=round(fill * 0.80, 2), target_price=round(fill * 1.35, 2), is_open=True
                        )
                    ]
                    self.active = True
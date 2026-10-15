from datetime import datetime
from strategies.base import BaseStrategy
from core.models import PositionLeg
from core.execution_engine import apply_slippage
from config.settings import CONFIG

class S4VWAPCallMomentum(BaseStrategy):
    def __init__(self):
        super().__init__("S4", "VWAP Call Momentum", "logs/trades_S4_vwap_call.csv")

    def evaluate(self, spot, market, contracts):
        t_str = datetime.now().strftime("%H:%M")
        sec_str = datetime.now().strftime("%H:%M:%S")

        if self.active:
            self.refresh_leg_prices(contracts)
            leg = self.legs[0]

            if leg.current_ltp >= (leg.entry_price + 18.0) and leg.sl_price < leg.entry_price:
                leg.sl_price = leg.entry_price + 1.0

            if t_str >= CONFIG.AUTO_SQUAREOFF:
                self.close_all_legs("EOD_SQUAREOFF", contracts)
            elif leg.current_ltp <= leg.sl_price or spot < market.vwap:
                self.close_all_legs("SL_OR_VWAP_CROSS", contracts)
            elif leg.current_ltp >= (leg.entry_price + 35.0):
                self.close_all_legs("TARGET_35PTS_HIT", contracts)
            return

        if not self.completed_today and "09:40" <= t_str < "14:30":
            if market.day_high is not None and spot > (market.vwap + 15.0) and spot >= (market.day_high - 5.0):
                atm = market.get_atm_strike(spot)
                ce = market.find_contract(contracts, atm, "CE")
                if ce:
                    fill_px = apply_slippage(ce[1], "BUY")
                    self.legs = [PositionLeg(ce[0], atm, "CE", "BUY", fill_px, CONFIG.NIFTY_LOT_SIZE, ce[1], ce[1], round(fill_px - 15.0, 2))]
                    self.active, self.entry_timestamp = True, sec_str
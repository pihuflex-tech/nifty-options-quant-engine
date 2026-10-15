from datetime import datetime
from strategies.base import BaseStrategy
from core.models import PositionLeg
from core.execution_engine import apply_slippage
from config.settings import CONFIG

class S9ORBScalper(BaseStrategy):
    def __init__(self):
        super().__init__("S9", "15-Min ORB Scalper", "logs/trades_S9_orb_scalper.csv")

    def evaluate(self, spot, market, contracts):
        t_str = datetime.now().strftime("%H:%M")
        sec_str = datetime.now().strftime("%H:%M:%S")

        if self.active:
            self.refresh_leg_prices(contracts)
            total_mtm = self.get_open_mtm() + self.realized_pnl
            orb_mid = (market.orb_high + market.orb_low) / 2.0 if (market.orb_high and market.orb_low) else 0.0

            if t_str >= CONFIG.AUTO_SQUAREOFF:
                self.close_all_legs("EOD_SQUAREOFF", contracts)
            elif total_mtm >= 1500.0:
                self.close_all_legs("ORB_SCALP_TARGET", contracts)
            elif total_mtm <= -800.0:
                self.close_all_legs("ORB_STOP_LOSS", contracts)
            elif orb_mid > 0 and self.legs[0].option_type == "CE" and spot < orb_mid:
                self.close_all_legs("ORB_MIDPOINT_REVERSAL", contracts)
            elif orb_mid > 0 and self.legs[0].option_type == "PE" and spot > orb_mid:
                self.close_all_legs("ORB_MIDPOINT_REVERSAL", contracts)
            return

        if not self.completed_today and market.orb_set and "09:30" <= t_str < "14:00":
            atm = market.get_atm_strike(spot)
            if market.orb_high is not None and spot > (market.orb_high + 5.0):
                ce = market.find_contract(contracts, atm, "CE")
                if ce:
                    self.legs = [PositionLeg(ce[0], atm, "CE", "BUY", apply_slippage(ce[1], "BUY"), CONFIG.NIFTY_LOT_SIZE, ce[1], ce[1])]
                    self.active, self.entry_timestamp = True, sec_str
            elif market.orb_low is not None and spot < (market.orb_low - 5.0):
                pe = market.find_contract(contracts, atm, "PE")
                if pe:
                    self.legs = [PositionLeg(pe[0], atm, "PE", "BUY", apply_slippage(pe[1], "BUY"), CONFIG.NIFTY_LOT_SIZE, pe[1], pe[1])]
                    self.active, self.entry_timestamp = True, sec_str
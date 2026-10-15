import time
from datetime import datetime
from strategies.base import BaseStrategy
from core.models import PositionLeg
from core.execution_engine import apply_slippage
from config.settings import CONFIG

class S8StraddleBuy(BaseStrategy):
    def __init__(self):
        super().__init__("S8", "09:45 Straddle Buy", "logs/trades_S8_straddle_buy.csv")
        self.entry_epoch: float = 0.0

    def evaluate(self, spot, market, contracts):
        t_str = datetime.now().strftime("%H:%M")
        sec_str = datetime.now().strftime("%H:%M:%S")

        if self.active:
            self.refresh_leg_prices(contracts)
            total_mtm = self.get_open_mtm() + self.realized_pnl
            elapsed_seconds = time.time() - self.entry_epoch

            if t_str >= CONFIG.AUTO_SQUAREOFF:
                self.close_all_legs("EOD_SQUAREOFF", contracts)
            elif total_mtm >= 2800.0:
                self.close_all_legs("VOL_EXPANSION_TARGET", contracts)
            elif total_mtm <= -1400.0:
                self.close_all_legs("THETA_BLEED_SL", contracts)
            elif elapsed_seconds >= 5400:  # 90 minutes limit
                self.close_all_legs("90MIN_TIME_STOP", contracts)
            return

        if not self.completed_today and "09:45" <= t_str < "10:15":
            atm = market.get_atm_strike(spot)
            ce = market.find_contract(contracts, atm, "CE")
            pe = market.find_contract(contracts, atm, "PE")
            if ce and pe:
                self.entry_epoch = time.time()
                self.legs = [
                    PositionLeg(ce[0], atm, "CE", "BUY", apply_slippage(ce[1], "BUY"), CONFIG.NIFTY_LOT_SIZE, ce[1], ce[1]),
                    PositionLeg(pe[0], atm, "PE", "BUY", apply_slippage(pe[1], "BUY"), CONFIG.NIFTY_LOT_SIZE, pe[1], pe[1])
                ]
                self.active, self.entry_timestamp = True, sec_str
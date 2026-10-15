from datetime import datetime
from strategies.base import BaseStrategy
from core.models import PositionLeg
from core.execution_engine import apply_slippage
from config.settings import CONFIG

class S10MeanReversion(BaseStrategy):
    def __init__(self):
        super().__init__("S10", "Mean Reversion Fade", "logs/trades_S10_mean_reversion.csv")

    def evaluate(self, spot, market, contracts):
        t_str = datetime.now().strftime("%H:%M")
        sec_str = datetime.now().strftime("%H:%M:%S")

        if self.active:
            self.refresh_leg_prices(contracts)
            total_mtm = self.get_open_mtm() + self.realized_pnl

            if t_str >= CONFIG.AUTO_SQUAREOFF:
                self.close_all_legs("EOD_SQUAREOFF", contracts)
            elif abs(spot - market.vwap) <= 8.0:
                self.close_all_legs("REVERTED_TO_VWAP", contracts)
            elif total_mtm >= 1800.0:
                self.close_all_legs("PROFIT_TARGET_HIT", contracts)
            elif total_mtm <= -1000.0:
                self.close_all_legs("TREND_BLOWOUT_SL", contracts)
            return

        if not self.completed_today and "10:00" <= t_str < "14:30":
            diff = spot - market.vwap
            atm = market.get_atm_strike(spot)
            if diff >= 60.0:
                pe = market.find_contract(contracts, atm, "PE")
                if pe:
                    self.legs = [PositionLeg(pe[0], atm, "PE", "BUY", apply_slippage(pe[1], "BUY"), CONFIG.NIFTY_LOT_SIZE, pe[1], pe[1])]
                    self.active, self.entry_timestamp = True, sec_str
            elif diff <= -60.0:
                ce = market.find_contract(contracts, atm, "CE")
                if ce:
                    self.legs = [PositionLeg(ce[0], atm, "CE", "BUY", apply_slippage(ce[1], "BUY"), CONFIG.NIFTY_LOT_SIZE, ce[1], ce[1])]
                    self.active, self.entry_timestamp = True, sec_str
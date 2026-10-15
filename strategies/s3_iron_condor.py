from datetime import datetime
from strategies.base import BaseStrategy
from core.models import PositionLeg
from core.execution_engine import apply_slippage
from config.settings import CONFIG

class S3IronCondor(BaseStrategy):
    def __init__(self):
        super().__init__("S3", "Iron Condor", "logs/trades_S3_iron_condor.csv")
        self.entry_atm: int = 0

    def evaluate(self, spot, market, contracts):
        t_str = datetime.now().strftime("%H:%M")
        sec_str = datetime.now().strftime("%H:%M:%S")

        if self.active:
            self.refresh_leg_prices(contracts)
            total_mtm = self.get_open_mtm() + self.realized_pnl

            if t_str >= CONFIG.AUTO_SQUAREOFF:
                self.close_all_legs("EOD_SQUAREOFF", contracts)
            elif spot >= (self.entry_atm + 150) or spot <= (self.entry_atm - 150):
                self.close_all_legs("SHORT_STRIKE_BREACHED", contracts)
            elif total_mtm >= 1600.0:
                self.close_all_legs("TARGET_REACHED", contracts)
            elif total_mtm <= -1200.0:
                self.close_all_legs("MAX_LOSS_HIT", contracts)
            return

        if not self.completed_today and "09:35" <= t_str < "14:30":
            atm = market.get_atm_strike(spot)
            s_ce = market.find_contract(contracts, atm + 150, "CE")
            b_ce = market.find_contract(contracts, atm + 250, "CE")
            s_pe = market.find_contract(contracts, atm - 150, "PE")
            b_pe = market.find_contract(contracts, atm - 250, "PE")
            if s_ce and b_ce and s_pe and b_pe:
                self.entry_atm = atm
                self.legs = [
                    PositionLeg(s_ce[0], atm + 150, "CE", "SELL", apply_slippage(s_ce[1], "SELL"), CONFIG.NIFTY_LOT_SIZE, s_ce[1], s_ce[1]),
                    PositionLeg(b_ce[0], atm + 250, "CE", "BUY", apply_slippage(b_ce[1], "BUY"), CONFIG.NIFTY_LOT_SIZE, b_ce[1], b_ce[1]),
                    PositionLeg(s_pe[0], atm - 150, "PE", "SELL", apply_slippage(s_pe[1], "SELL"), CONFIG.NIFTY_LOT_SIZE, s_pe[1], s_pe[1]),
                    PositionLeg(b_pe[0], atm - 250, "PE", "BUY", apply_slippage(b_pe[1], "BUY"), CONFIG.NIFTY_LOT_SIZE, b_pe[1], b_pe[1]),
                ]
                self.active, self.entry_timestamp = True, sec_str
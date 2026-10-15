from datetime import datetime
from strategies.base import BaseStrategy
from core.models import PositionLeg
from core.execution_engine import apply_slippage
from config.settings import CONFIG

class S1ShortStraddle(BaseStrategy):
    def __init__(self):
        super().__init__("S1", "09:20 Short Straddle", "logs/trades_S1_short_straddle.csv")

    def evaluate(self, spot, market, contracts):
        t_str = datetime.now().strftime("%H:%M")
        sec_str = datetime.now().strftime("%H:%M:%S")

        if self.active:
            self.refresh_leg_prices(contracts)
            for leg in self.legs:
                if leg.is_open and leg.current_ltp >= leg.sl_price:
                    self.close_single_leg(leg, "LEG_25PCT_SL_HIT", contracts)
                    for other in self.legs:
                        if other.is_open:
                            other.sl_price = other.entry_price

            if not self.active:
                return

            total_mtm = self.get_open_mtm() + self.realized_pnl
            if t_str >= CONFIG.AUTO_SQUAREOFF:
                self.close_all_legs("EOD_SQUAREOFF", contracts)
            elif total_mtm >= 2500.0:
                self.close_all_legs("PROFIT_TARGET_HIT", contracts)
            elif total_mtm <= -1800.0:
                self.close_all_legs("COMBINED_MAX_LOSS", contracts)
            return

        if not self.completed_today and "09:20" <= t_str < "14:45":
            atm = market.get_atm_strike(spot)
            ce = market.find_contract(contracts, atm, "CE")
            pe = market.find_contract(contracts, atm, "PE")
            if ce and pe:
                ce_fill = apply_slippage(ce[1], "SELL")
                pe_fill = apply_slippage(pe[1], "SELL")
                self.legs = [
                    PositionLeg(ce[0], atm, "CE", "SELL", ce_fill, CONFIG.NIFTY_LOT_SIZE, ce[1], ce[1], round(ce_fill * 1.25, 2)),
                    PositionLeg(pe[0], atm, "PE", "SELL", pe_fill, CONFIG.NIFTY_LOT_SIZE, pe[1], pe[1], round(pe_fill * 1.25, 2))
                ]
                self.active, self.entry_timestamp = True, sec_str
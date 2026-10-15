from datetime import datetime
from strategies.base import BaseStrategy
from core.models import PositionLeg
from core.execution_engine import apply_slippage
from config.settings import CONFIG

class S6BullPutSpread(BaseStrategy):
    def __init__(self):
        super().__init__("S6", "Bull Put Spread", "logs/trades_S6_bull_put_spread.csv")
        self.target_pnl: float = 1200.0
        self.sl_pnl: float = -1200.0

    def evaluate(self, spot, market, contracts):
        t_str = datetime.now().strftime("%H:%M")
        sec_str = datetime.now().strftime("%H:%M:%S")

        if self.active:
            self.refresh_leg_prices(contracts)
            total_mtm = self.get_open_mtm() + self.realized_pnl

            if t_str >= CONFIG.AUTO_SQUAREOFF:
                self.close_all_legs("EOD_SQUAREOFF", contracts)
            elif total_mtm <= self.sl_pnl:
                self.close_all_legs("SPREAD_SL_HIT", contracts)
            elif total_mtm >= self.target_pnl:
                self.close_all_legs("TARGET_75PCT_CREDIT", contracts)
            return

        if not self.completed_today and "09:45" <= t_str < "14:30":
            if spot > (market.vwap + 10.0):
                atm = market.get_atm_strike(spot)
                s_pe = market.find_contract(contracts, atm, "PE")
                b_pe = market.find_contract(contracts, atm - 100, "PE")
                if s_pe and b_pe:
                    sell_px = apply_slippage(s_pe[1], "SELL")
                    buy_px = apply_slippage(b_pe[1], "BUY")
                    net_credit = (sell_px - buy_px) * CONFIG.NIFTY_LOT_SIZE
                    if net_credit > 400.0:
                        self.target_pnl = round(net_credit * 0.75, 2)
                        self.sl_pnl = -round(max(net_credit, 900.0), 2)
                        self.legs = [
                            PositionLeg(s_pe[0], atm, "PE", "SELL", sell_px, CONFIG.NIFTY_LOT_SIZE, s_pe[1], s_pe[1]),
                            PositionLeg(b_pe[0], atm - 100, "PE", "BUY", buy_px, CONFIG.NIFTY_LOT_SIZE, b_pe[1], b_pe[1])
                        ]
                        self.active, self.entry_timestamp = True, sec_str
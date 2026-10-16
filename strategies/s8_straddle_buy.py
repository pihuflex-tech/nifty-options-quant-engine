# S8: strategies/s8_straddle_buy.py
from datetime import datetime
from strategies.base import BaseStrategy
from core.models import PositionLeg
from core.execution_engine import apply_slippage
from config.settings import CONFIG

class S8StraddleBuy(BaseStrategy):
    def __init__(self):
        super().__init__("S8", "09:45 Straddle Buy", "logs/trades_S8_straddle_buy.csv")

    def evaluate(self, spot, market, contracts):
        now = datetime.now()
        t_str, sec_str, today_date = now.strftime("%H:%M"), now.strftime("%H:%M:%S"), now.strftime("%Y-%m-%d")
        self.check_new_day(today_date)

        if self.active:
            self.refresh_leg_prices(contracts)
            total_mtm = self.get_open_mtm() + self.realized_pnl
            if t_str >= CONFIG.AUTO_SQUAREOFF:
                self.close_all_legs("EOD_SQUAREOFF", contracts)
            elif total_mtm >= 2800.0:
                self.close_all_legs("TARGET_HIT", contracts)
            elif total_mtm <= -1600.0:
                self.close_all_legs("MAX_LOSS_HIT", contracts)
            return

        if not self.completed_today and spot > 0 and "09:45" <= t_str < "14:00":
            atm = market.get_atm_strike(spot)
            ce = market.find_contract(contracts, atm, "CE")
            pe = market.find_contract(contracts, atm, "PE")
            if ce and pe and ce[1] > 0 and pe[1] > 0:
                self.entry_date, self.entry_timestamp = today_date, sec_str
                self.legs = [
                    PositionLeg(
                        symbol=ce[0], strike=atm, option_type="CE", side="BUY",
                        entry_price=apply_slippage(ce[1], "BUY"), qty=CONFIG.NIFTY_LOT_SIZE,
                        raw_entry_price=ce[1], entry_date=today_date, entry_time=sec_str,
                        current_ltp=ce[1], sl_price=0.0, is_open=True
                    ),
                    PositionLeg(
                        symbol=pe[0], strike=atm, option_type="PE", side="BUY",
                        entry_price=apply_slippage(pe[1], "BUY"), qty=CONFIG.NIFTY_LOT_SIZE,
                        raw_entry_price=pe[1], entry_date=today_date, entry_time=sec_str,
                        current_ltp=pe[1], sl_price=0.0, is_open=True
                    )
                ]
                self.active = True
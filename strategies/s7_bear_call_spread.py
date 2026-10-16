# S7: strategies/s7_bear_call_spread.py
from datetime import datetime
from strategies.base import BaseStrategy
from core.models import PositionLeg
from core.execution_engine import apply_slippage
from config.settings import CONFIG

class S7BearCallSpread(BaseStrategy):
    def __init__(self):
        super().__init__("S7", "Bear Call Spread", "logs/trades_S7_bear_call_spread.csv")

    def evaluate(self, spot, market, contracts):
        now = datetime.now()
        t_str, sec_str, today_date = now.strftime("%H:%M"), now.strftime("%H:%M:%S"), now.strftime("%Y-%m-%d")
        self.check_new_day(today_date)

        if self.active:
            self.refresh_leg_prices(contracts)
            total_mtm = self.get_open_mtm() + self.realized_pnl
            if t_str >= CONFIG.AUTO_SQUAREOFF:
                self.close_all_legs("EOD_SQUAREOFF", contracts)
            elif total_mtm >= 1500.0:
                self.close_all_legs("TARGET_HIT", contracts)
            elif total_mtm <= -1200.0:
                self.close_all_legs("MAX_LOSS_HIT", contracts)
            return

        if not self.completed_today and spot > 0 and market.vwap > 0 and "09:30" <= t_str < "14:30":
            if spot < market.vwap:
                atm = market.get_atm_strike(spot)
                cs = market.find_contract(contracts, atm, "CE")
                cb = market.find_contract(contracts, atm + 100, "CE")
                if cs and cb and cs[1] > 0 and cb[1] > 0:
                    self.entry_date, self.entry_timestamp = today_date, sec_str
                    self.legs = [
                        PositionLeg(
                            symbol=cs[0], strike=atm, option_type="CE", side="SELL",
                            entry_price=apply_slippage(cs[1], "SELL"), qty=CONFIG.NIFTY_LOT_SIZE,
                            raw_entry_price=cs[1], entry_date=today_date, entry_time=sec_str,
                            current_ltp=cs[1], sl_price=0.0, is_open=True
                        ),
                        PositionLeg(
                            symbol=cb[0], strike=atm + 100, option_type="CE", side="BUY",
                            entry_price=apply_slippage(cb[1], "BUY"), qty=CONFIG.NIFTY_LOT_SIZE,
                            raw_entry_price=cb[1], entry_date=today_date, entry_time=sec_str,
                            current_ltp=cb[1], sl_price=0.0, is_open=True
                        )
                    ]
                    self.active = True
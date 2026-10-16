# S6: strategies/s6_bull_put_spread.py
from datetime import datetime
from strategies.base import BaseStrategy
from core.models import PositionLeg
from core.execution_engine import apply_slippage
from config.settings import CONFIG

class S6BullPutSpread(BaseStrategy):
    def __init__(self):
        super().__init__("S6", "Bull Put Spread", "logs/trades_S6_bull_put_spread.csv")

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
            if spot > market.vwap:
                atm = market.get_atm_strike(spot)
                ps = market.find_contract(contracts, atm, "PE")
                pb = market.find_contract(contracts, atm - 100, "PE")
                if ps and pb and ps[1] > 0 and pb[1] > 0:
                    self.entry_date, self.entry_timestamp = today_date, sec_str
                    self.legs = [
                        PositionLeg(
                            symbol=ps[0], strike=atm, option_type="PE", side="SELL",
                            entry_price=apply_slippage(ps[1], "SELL"), qty=CONFIG.NIFTY_LOT_SIZE,
                            raw_entry_price=ps[1], entry_date=today_date, entry_time=sec_str,
                            current_ltp=ps[1], sl_price=0.0, is_open=True
                        ),
                        PositionLeg(
                            symbol=pb[0], strike=atm - 100, option_type="PE", side="BUY",
                            entry_price=apply_slippage(pb[1], "BUY"), qty=CONFIG.NIFTY_LOT_SIZE,
                            raw_entry_price=pb[1], entry_date=today_date, entry_time=sec_str,
                            current_ltp=pb[1], sl_price=0.0, is_open=True
                        )
                    ]
                    self.active = True
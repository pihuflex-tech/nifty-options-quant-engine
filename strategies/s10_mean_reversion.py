# S10: strategies/s10_mean_reversion.py
from datetime import datetime
from strategies.base import BaseStrategy
from core.models import PositionLeg
from core.execution_engine import apply_slippage
from config.settings import CONFIG

class S10MeanReversion(BaseStrategy):
    def __init__(self):
        super().__init__("S10", "Mean Reversion Fade", "logs/trades_S10_mean_reversion.csv")

    def evaluate(self, spot, market, contracts):
        now = datetime.now()
        t_str, sec_str, today_date = now.strftime("%H:%M"), now.strftime("%H:%M:%S"), now.strftime("%Y-%m-%d")
        self.check_new_day(today_date)

        if self.active:
            self.refresh_leg_prices(contracts)
            total_mtm = self.get_open_mtm() + self.realized_pnl
            if t_str >= CONFIG.AUTO_SQUAREOFF:
                self.close_all_legs("EOD_SQUAREOFF", contracts)
            elif market.vwap > 0 and abs(spot - market.vwap) <= 10.0:
                self.close_all_legs("VWAP_REVERSION_COMPLETE", contracts)
            elif total_mtm >= 1600.0:
                self.close_all_legs("TARGET_HIT", contracts)
            elif total_mtm <= -1100.0:
                self.close_all_legs("MAX_LOSS_HIT", contracts)
            return

        if not self.completed_today and spot > 0 and market.vwap > 0 and "09:30" <= t_str < "14:30":
            diff = spot - market.vwap
            opt_type = "PE" if diff >= 60.0 else ("CE" if diff <= -60.0 else None)
            if opt_type:
                atm = market.get_atm_strike(spot)
                c = market.find_contract(contracts, atm, opt_type)
                if c and c[1] > 0:
                    fill = apply_slippage(c[1], "BUY")
                    self.entry_date, self.entry_timestamp = today_date, sec_str
                    self.legs = [
                        PositionLeg(
                            symbol=c[0], strike=atm, option_type=opt_type, side="BUY",
                            entry_price=fill, qty=CONFIG.NIFTY_LOT_SIZE, raw_entry_price=c[1],
                            entry_date=today_date, entry_time=sec_str, current_ltp=c[1],
                            sl_price=0.0, is_open=True
                        )
                    ]
                    self.active = True
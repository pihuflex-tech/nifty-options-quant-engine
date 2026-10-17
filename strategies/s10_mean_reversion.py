# S10: strategies/s10_mean_reversion.py
from datetime import datetime
from typing import Optional
from strategies.base import BaseStrategy
from core.models import PositionLeg
from core.execution_engine import apply_slippage
from config.settings import CONFIG

class S10MeanReversion(BaseStrategy):
    def __init__(self):
        super().__init__("S10", "Mean Reversion Fade", "logs/trades_S10_mean_reversion.csv")

    def evaluate(self, spot, market, contracts, now_dt: Optional[datetime] = None):
        now = now_dt or datetime.now()
        t_str, sec_str, today_date = now.strftime("%H:%M"), now.strftime("%H:%M:%S"), now.strftime("%Y-%m-%d")
        self.check_new_day(today_date)

        if self.active:
            self.refresh_leg_prices(contracts)
            total_mtm = self.get_open_mtm() + self.realized_pnl

            if t_str >= CONFIG.AUTO_SQUAREOFF:
                self.close_all_legs("EOD_SQUAREOFF", contracts, now_dt=now)
            elif market.vwap > 0 and abs(spot - market.vwap) <= 8.0:
                self.close_all_legs("REVERTED_TO_VWAP", contracts, now_dt=now)
            elif total_mtm >= 1800.0:
                self.close_all_legs("PROFIT_TARGET_HIT", contracts, now_dt=now)
            elif total_mtm <= -1000.0:
                self.close_all_legs("TREND_BLOWOUT_SL", contracts, now_dt=now)
            return

        if not self.completed_today and spot > 0 and market.vwap > 0 and "10:00" <= t_str < "14:30":
            diff = spot - market.vwap
            atm = market.get_atm_strike(spot)
            if diff >= 60.0:
                pe = market.find_contract(contracts, atm, "PE")
                if pe and pe[1] > 0:
                    fill = apply_slippage(pe[1], "BUY")
                    self.entry_date, self.entry_timestamp = today_date, sec_str
                    self.legs = [
                        PositionLeg(
                            symbol=pe[0], strike=atm, option_type="PE", side="BUY",
                            entry_price=fill, qty=CONFIG.NIFTY_LOT_SIZE, raw_entry_price=pe[1],
                            entry_date=today_date, entry_time=sec_str, current_ltp=pe[1],
                            sl_price=0.0, is_open=True
                        )
                    ]
                    self.active = True
            elif diff <= -60.0:
                ce = market.find_contract(contracts, atm, "CE")
                if ce and ce[1] > 0:
                    fill = apply_slippage(ce[1], "BUY")
                    self.entry_date, self.entry_timestamp = today_date, sec_str
                    self.legs = [
                        PositionLeg(
                            symbol=ce[0], strike=atm, option_type="CE", side="BUY",
                            entry_price=fill, qty=CONFIG.NIFTY_LOT_SIZE, raw_entry_price=ce[1],
                            entry_date=today_date, entry_time=sec_str, current_ltp=ce[1],
                            sl_price=0.0, is_open=True
                        )
                    ]
                    self.active = True
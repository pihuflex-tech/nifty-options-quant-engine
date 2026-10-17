# S9: strategies/s9_orb_scalper.py
from datetime import datetime
from typing import Optional
from strategies.base import BaseStrategy
from core.models import PositionLeg
from core.execution_engine import apply_slippage
from config.settings import CONFIG

class S9ORBScalper(BaseStrategy):
    def __init__(self):
        super().__init__("S9", "15-Min ORB Scalper", "logs/trades_S9_orb_scalper.csv")

    def evaluate(self, spot, market, contracts, now_dt: Optional[datetime] = None):
        now = now_dt or datetime.now()
        t_str, sec_str, today_date = now.strftime("%H:%M"), now.strftime("%H:%M:%S"), now.strftime("%Y-%m-%d")
        self.check_new_day(today_date)

        if self.active:
            self.refresh_leg_prices(contracts)
            total_mtm = self.get_open_mtm() + self.realized_pnl
            orb_mid = (market.orb_high + market.orb_low) / 2.0 if (market.orb_high is not None and market.orb_low is not None) else 0.0

            if t_str >= CONFIG.AUTO_SQUAREOFF:
                self.close_all_legs("EOD_SQUAREOFF", contracts, now_dt=now)
            elif total_mtm >= 1500.0:
                self.close_all_legs("ORB_SCALP_TARGET", contracts, now_dt=now)
            elif total_mtm <= -800.0:
                self.close_all_legs("ORB_STOP_LOSS", contracts, now_dt=now)
            elif orb_mid > 0 and self.legs and self.legs[0].option_type == "CE" and spot < orb_mid:
                self.close_all_legs("ORB_MIDPOINT_REVERSAL", contracts, now_dt=now)
            elif orb_mid > 0 and self.legs and self.legs[0].option_type == "PE" and spot > orb_mid:
                self.close_all_legs("ORB_MIDPOINT_REVERSAL", contracts, now_dt=now)
            return

        is_orb_ready = market.orb_set or getattr(market, "orb_ready", False)
        if not self.completed_today and spot > 0 and is_orb_ready and "09:30" <= t_str < "14:00":
            atm = market.get_atm_strike(spot)
            if market.orb_high is not None and spot > (market.orb_high + 5.0):
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
            elif market.orb_low is not None and spot < (market.orb_low - 5.0):
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
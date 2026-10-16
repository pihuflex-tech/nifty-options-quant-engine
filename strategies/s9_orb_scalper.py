# S9: strategies/s9_orb_scalper.py
from datetime import datetime
from strategies.base import BaseStrategy
from core.models import PositionLeg
from core.execution_engine import apply_slippage
from config.settings import CONFIG

class S9ORBScalper(BaseStrategy):
    def __init__(self):
        super().__init__("S9", "15-Min ORB Scalper", "logs/trades_S9_orb_scalper.csv")

    def evaluate(self, spot, market, contracts):
        now = datetime.now()
        t_str, sec_str, today_date = now.strftime("%H:%M"), now.strftime("%H:%M:%S"), now.strftime("%Y-%m-%d")
        self.check_new_day(today_date)

        if self.active:
            self.refresh_leg_prices(contracts)
            if t_str >= CONFIG.AUTO_SQUAREOFF:
                self.close_all_legs("EOD_SQUAREOFF", contracts)
                return
            for leg in self.legs:
                if self.is_leg_sl_hit(leg):
                    self.close_single_leg(leg, "ORB_SL_20PCT_HIT", contracts)
                elif self.is_leg_target_hit(leg):
                    self.close_single_leg(leg, "ORB_TARGET_30PCT_HIT", contracts)
            return

        if not self.completed_today and spot > 0 and market.orb_ready and "09:30" <= t_str < "14:30":
            atm = market.get_atm_strike(spot)
            opt_type = "CE" if spot > market.orb_high > 0 else ("PE" if 0 < market.orb_low and spot < market.orb_low else None)
            if opt_type:
                c = market.find_contract(contracts, atm, opt_type)
                if c and c[1] > 0:
                    fill = apply_slippage(c[1], "BUY")
                    self.entry_date, self.entry_timestamp = today_date, sec_str
                    self.legs = [
                        PositionLeg(
                            symbol=c[0], strike=atm, option_type=opt_type, side="BUY",
                            entry_price=fill, qty=CONFIG.NIFTY_LOT_SIZE, raw_entry_price=c[1],
                            entry_date=today_date, entry_time=sec_str, current_ltp=c[1],
                            sl_price=round(fill * 0.80, 2), target_price=round(fill * 1.30, 2), is_open=True
                        )
                    ]
                    self.active = True
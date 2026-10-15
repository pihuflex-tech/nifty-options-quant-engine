from typing import Dict, Optional, Tuple
from config.settings import CONFIG

class MarketStateManager:
    def __init__(self):
        self.spot_sum: float = 0.0
        self.tick_count: int = 0
        self.day_high: Optional[float] = None
        self.day_low: Optional[float] = None
        self.orb_high: Optional[float] = None
        self.orb_low: Optional[float] = None
        self.orb_set: bool = False

    def update(self, spot: float, time_str: str):
        self.spot_sum += spot
        self.tick_count += 1

        if self.day_high is None or spot > self.day_high:
            self.day_high = spot
        if self.day_low is None or spot < self.day_low:
            self.day_low = spot

        if time_str >= CONFIG.ORB_END and not self.orb_set and self.day_high is not None and self.day_low is not None:
            self.orb_high = self.day_high
            self.orb_low = self.day_low
            self.orb_set = True

    @property
    def vwap(self) -> float:
        if self.tick_count == 0:
            return 0.0
        return round(self.spot_sum / self.tick_count, 2)

    @staticmethod
    def get_atm_strike(spot: float) -> int:
        return int(round(spot / 50.0) * 50)

    @staticmethod
    def find_contract(contracts: Dict, strike: int, opt_type: str) -> Optional[Tuple[str, float]]:
        if not contracts:
            return None
        s_key = str(strike)
        opt_type = opt_type.upper()

        if s_key in contracts and isinstance(contracts[s_key], dict):
            c = contracts[s_key].get(opt_type)
            if c and c.get("ltp") is not None and float(c["ltp"]) > 0:
                return c.get("symbol", f"NIFTY_{strike}_{opt_type}"), float(c["ltp"])

        for k, v in contracts.items():
            if isinstance(v, dict):
                if opt_type in v and isinstance(v[opt_type], dict):
                    try:
                        if int(float(k)) == strike:
                            c = v[opt_type]
                            if c.get("ltp") is not None and float(c["ltp"]) > 0:
                                return c.get("symbol", f"NIFTY_{strike}_{opt_type}"), float(c["ltp"])
                    except ValueError:
                        pass
                elif v.get("strike") is not None and v.get("option_type", v.get("opt_type", "")).upper() == opt_type:
                    try:
                        if int(float(v["strike"])) == strike and v.get("ltp") is not None and float(v["ltp"]) > 0:
                            return v.get("symbol", f"NIFTY_{strike}_{opt_type}"), float(v["ltp"])
                    except ValueError:
                        pass
        return None
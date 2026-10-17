from typing import Dict, Optional, Tuple, Any, Union, List
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

    def reset(self):
        """Resets all intraday tracking metrics for a new session."""
        self.spot_sum = 0.0
        self.tick_count = 0
        self.day_high = None
        self.day_low = None
        self.orb_high = None
        self.orb_low = None
        self.orb_set = False

    def update(self, spot: float, time_str: str):
        if spot <= 0:
            return
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
    def orb_ready(self) -> bool:
        """Alias for orb_set for backward and cross-module compatibility."""
        return self.orb_set

    @property
    def vwap(self) -> float:
        if self.tick_count == 0:
            return 0.0
        return round(self.spot_sum / self.tick_count, 2)

    @staticmethod
    def get_atm_strike(spot: float) -> int:
        if spot <= 0:
            return 0
        return int(round(spot / 50.0) * 50)

    @staticmethod
    def find_contract(contracts: Any, strike: int, opt_type: str) -> Optional[Tuple[str, float]]:
        """
        Locates an option contract tuple (symbol, ltp) for a given strike and option type (CE/PE).
        Supports multiple schema variants:
          1. Dict keyed by strike: {"24500": {"CE": {"symbol": "...", "ltp": 120.0}}}
          2. Dict keyed by token: {"token1": {"strike": 24500, "option_type": "CE", "ltp": 120.0}}
          3. Dict keyed by symbol: {"NIFTY_24500_CE": {"ltp": 120.0}} or {"NIFTY_24500_CE": 120.0}
          4. List of contract dicts: [{"strike": 24500, "option_type": "CE", "ltp": 120.0, "symbol": "..."}]
          5. List of tuples/lists: [("NIFTY_24500_CE", 120.0)]
        """
        if not contracts:
            return None

        strike = int(strike)
        opt_type = str(opt_type).strip().upper()
        expected_symbol_sub = f"{strike}_{opt_type}"

        # Case 4 & 5: List input
        if isinstance(contracts, list):
            for item in contracts:
                if isinstance(item, dict):
                    st = item.get("strike")
                    ot = item.get("option_type", item.get("opt_type", ""))
                    if st is not None:
                        try:
                            if int(float(st)) == strike and str(ot).strip().upper() == opt_type:
                                ltp = item.get("ltp")
                                if ltp is not None and float(ltp) > 0:
                                    return item.get("symbol", f"NIFTY_{strike}_{opt_type}"), float(ltp)
                        except (ValueError, TypeError):
                            pass
                    sym = item.get("symbol", "")
                    if expected_symbol_sub in sym:
                        ltp = item.get("ltp")
                        if ltp is not None and float(ltp) > 0:
                            return sym, float(ltp)
                elif isinstance(item, (list, tuple)) and len(item) >= 2:
                    sym = str(item[0])
                    if expected_symbol_sub in sym:
                        try:
                            px = float(item[1])
                            if px > 0:
                                return sym, px
                        except (ValueError, TypeError):
                            pass
            return None

        # Case 1, 2, 3: Dict input
        if isinstance(contracts, dict):
            s_key = str(strike)
            # Case 1: contracts[strike][opt_type]
            if s_key in contracts and isinstance(contracts[s_key], dict):
                c = contracts[s_key].get(opt_type)
                if isinstance(c, dict):
                    ltp = c.get("ltp")
                    if ltp is not None and float(ltp) > 0:
                        return c.get("symbol", f"NIFTY_{strike}_{opt_type}"), float(ltp)
                elif isinstance(c, (int, float)) and float(c) > 0:
                    return f"NIFTY_{strike}_{opt_type}", float(c)

            # Case 2: contracts[token] = {strike, option_type, ltp}
            for k, v in contracts.items():
                if isinstance(v, dict):
                    # Check if keyed by strike with nested CE/PE
                    if opt_type in v and isinstance(v[opt_type], dict):
                        try:
                            if int(float(k)) == strike:
                                c = v[opt_type]
                                if c.get("ltp") is not None and float(c["ltp"]) > 0:
                                    return c.get("symbol", f"NIFTY_{strike}_{opt_type}"), float(c["ltp"])
                        except (ValueError, TypeError):
                            pass
                    # Check token dictionary fields
                    st = v.get("strike")
                    ot = v.get("option_type", v.get("opt_type", ""))
                    if st is not None:
                        try:
                            if int(float(st)) == strike and str(ot).strip().upper() == opt_type:
                                ltp = v.get("ltp")
                                if ltp is not None and float(ltp) > 0:
                                    return v.get("symbol", f"NIFTY_{strike}_{opt_type}"), float(ltp)
                        except (ValueError, TypeError):
                            pass
                    # Symbol substring match
                    sym = v.get("symbol", k)
                    if expected_symbol_sub in sym:
                        ltp = v.get("ltp")
                        if ltp is not None and float(ltp) > 0:
                            return sym, float(ltp)
                elif isinstance(v, (int, float)) and float(v) > 0:
                    # Keyed by symbol directly: {"NIFTY_24500_CE": 120.0}
                    if expected_symbol_sub in k:
                        return k, float(v)

        return None
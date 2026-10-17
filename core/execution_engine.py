from config.settings import CONFIG

def apply_slippage(price: float, side: str) -> float:
    if price <= 0:
        return 0.0
    if str(side).strip().upper() == "BUY":
        return round(price * (1.0 + CONFIG.SLIPPAGE_PCT), 2)
    return round(price * (1.0 - CONFIG.SLIPPAGE_PCT), 2)
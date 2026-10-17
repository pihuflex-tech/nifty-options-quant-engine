from typing import Dict, Union
from config.settings import CONFIG

def calculate_exact_costs(qty: int, entry_px: float, exit_px: float, side: str = "BUY") -> Dict[str, float]:
    """
    Computes exact statutory and brokerage costs per executed round-turn leg 
    according to current Indian Union Budget rates for NSE Equity Options.
    """
    qty = int(qty)
    entry_px = float(entry_px)
    exit_px = float(exit_px)
    side_clean = str(side).strip().upper()

    buy_px = entry_px if side_clean == "BUY" else exit_px
    sell_px = exit_px if side_clean == "BUY" else entry_px

    buy_turnover = round(qty * buy_px, 2)
    sell_turnover = round(qty * sell_px, 2)
    total_turnover = round(buy_turnover + sell_turnover, 2)

    brokerage = round(CONFIG.BROKERAGE_PER_ORDER * 2.0, 2)  # Entry + Exit
    stt = round(sell_turnover * CONFIG.STT_SELL_PCT, 2)
    exchange_charges = round(total_turnover * CONFIG.EXCHANGE_TURNOVER_PCT, 2)
    sebi_charges = round(total_turnover * CONFIG.SEBI_TURNOVER_PCT, 2)
    stamp_duty = round(buy_turnover * CONFIG.STAMP_DUTY_BUY_PCT, 2)

    taxable_services = brokerage + exchange_charges + sebi_charges
    gst = round(taxable_services * CONFIG.GST_PCT, 2)

    total_charges = round(brokerage + stt + exchange_charges + sebi_charges + stamp_duty + gst, 2)

    return {
        "brokerage": brokerage,
        "stt": stt,
        "exchange_charges": exchange_charges,
        "sebi_charges": sebi_charges,
        "stamp_duty": stamp_duty,
        "gst": gst,
        "total_charges": total_charges,
        "buy_turnover": buy_turnover,
        "sell_turnover": sell_turnover,
        "total_turnover": total_turnover
    }

def calculate_detailed_statutory_costs(entry_px: float, exit_px: float, qty: int, side: str = "BUY") -> Dict[str, float]:
    """
    Alternative signature compatibility wrapper for calculate_exact_costs.
    """
    return calculate_exact_costs(qty=qty, entry_px=entry_px, exit_px=exit_px, side=side)
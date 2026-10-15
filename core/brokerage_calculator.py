from config.settings import CONFIG

def calculate_exact_costs(qty: int, entry_px: float, exit_px: float, side: str) -> dict:
    buy_px = entry_px if side.upper() == "BUY" else exit_px
    sell_px = exit_px if side.upper() == "BUY" else entry_px

    buy_turnover = round(qty * buy_px, 2)
    sell_turnover = round(qty * sell_px, 2)
    total_turnover = buy_turnover + sell_turnover

    brokerage = CONFIG.BROKERAGE_PER_ORDER * 2.0  # Entry + Exit
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
        "total_charges": total_charges
    }
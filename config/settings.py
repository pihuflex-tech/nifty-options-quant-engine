import os
from dataclasses import dataclass

# Automatically load .env if present (Zero-dependency standard library implementation)
_env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
if os.path.isfile(_env_path):
    try:
        with open(_env_path, "r", encoding="utf-8") as _f:
            for _line in _f:
                _line = _line.strip()
                if _line and not _line.startswith("#") and "=" in _line:
                    _k, _v = _line.split("=", 1)
                    os.environ.setdefault(_k.strip(), _v.strip())
    except Exception:
        pass

@dataclass(frozen=True)
class TradingConfig:
    FEED_HOST: str = os.getenv("FEED_HOST", "127.0.0.1")
    FEED_PORT: int = int(os.getenv("FEED_PORT", 5555))
    FEED_URL: str = f"http://{FEED_HOST}:{FEED_PORT}/"
    
    BOT_STATE_HOST: str = os.getenv("BOT_STATE_HOST", "127.0.0.1")
    BOT_STATE_PORT: int = int(os.getenv("BOT_STATE_PORT", 5556))
    
    POLL_INTERVAL: float = float(os.getenv("POLL_INTERVAL", 0.5))

    # Nifty 50 Specifications
    NIFTY_LOT_SIZE: int = 65
    SLIPPAGE_PCT: float = 0.0025        # 0.25% fill slippage

    # Official NSE F&O Regulatory Rates (Union Budget Compliant)
    BROKERAGE_PER_ORDER: float = 20.0   # Flat Rs 20 per order leg
    STT_SELL_PCT: float = 0.0010        # 0.1% on Option Premium Turnover (Sell side)
    EXCHANGE_TURNOVER_PCT: float = 0.0003503  # 0.03503% NSE transaction fee
    SEBI_TURNOVER_PCT: float = 0.000001       # Rs 10 per crore
    STAMP_DUTY_BUY_PCT: float = 0.00003       # 0.003% on Buy premium turnover
    GST_PCT: float = 0.18               # 18% on (Brokerage + Exchange + SEBI)

    # Intraday Timings (IST)
    MARKET_OPEN: str = "09:15"
    ORB_END: str = "09:30"
    AUTO_SQUAREOFF: str = "15:15"
    BOT_SHUTDOWN: str = "15:25"

CONFIG = TradingConfig()
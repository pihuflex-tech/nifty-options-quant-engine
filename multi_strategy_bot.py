import os
import sys
import time
import json
import threading
import traceback
from datetime import datetime
from urllib.request import urlopen, Request
from urllib.error import URLError
from http.server import HTTPServer, BaseHTTPRequestHandler

# Lock working directory to script location
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from config.settings import CONFIG
from core.market_state import MarketStateManager

from strategies.s1_short_straddle import S1ShortStraddle
from strategies.s2_short_strangle import S2ShortStrangle
from strategies.s3_iron_condor import S3IronCondor
from strategies.s4_vwap_call_momentum import S4VWAPCallMomentum
from strategies.s5_vwap_put_momentum import S5VWAPPutMomentum
from strategies.s6_bull_put_spread import S6BullPutSpread
from strategies.s7_bear_call_spread import S7BearCallSpread
from strategies.s8_straddle_buy import S8StraddleBuy
from strategies.s9_orb_scalper import S9ORBScalper
from strategies.s10_mean_reversion import S10MeanReversion

# Thread-safe synchronization lock and state payload
STATE_LOCK = threading.Lock()

LIVE_BOT_STATE = {
    "timestamp": "",
    "spot": 0.0,
    "atm": 0,
    "vwap": 0.0,
    "day_high": 0.0,
    "day_low": 0.0,
    "orb_high": None,
    "orb_low": None,
    "orb_set": False,
    "open_mtm": 0.0,
    "realized_pnl": 0.0,
    "charges_paid": 0.0,
    "net_pnl": 0.0,
    "active_count": 0,
    "strategies": []
}

class BotStateHandler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        with STATE_LOCK:
            payload = json.dumps(LIVE_BOT_STATE).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format, *args):
        return  # Suppress HTTP GET polling logs

def start_state_server():
    try:
        server = HTTPServer((CONFIG.BOT_STATE_HOST, CONFIG.BOT_STATE_PORT), BotStateHandler)
        server.serve_forever()
    except Exception as e:
        print(f"[!] Dashboard HTTP server error on {CONFIG.BOT_STATE_HOST}:{CONFIG.BOT_STATE_PORT}: {e}")

def main():
    market = MarketStateManager()
    strategies = [
        S1ShortStraddle(),
        S2ShortStrangle(),
        S3IronCondor(),
        S4VWAPCallMomentum(),
        S5VWAPPutMomentum(),
        S6BullPutSpread(),
        S7BearCallSpread(),
        S8StraddleBuy(),
        S9ORBScalper(),
        S10MeanReversion(),
    ]

    http_thread = threading.Thread(target=start_state_server, daemon=True)
    http_thread.start()

    print(f"[*] Base Directory : {BASE_DIR}")
    print(f"[*] Consuming Feed : {CONFIG.FEED_URL}")
    print(f"[*] Dashboard API  : http://{CONFIG.BOT_STATE_HOST}:{CONFIG.BOT_STATE_PORT}/")

    cached_contracts = {}

    while True:
        try:
            now = datetime.now()
            t_str = now.strftime("%H:%M")

            if t_str >= CONFIG.BOT_SHUTDOWN:
                for strat in strategies:
                    if strat.active:
                        strat.close_all_legs("EOD_SQUAREOFF", cached_contracts)
                print(f"[*] {CONFIG.BOT_SHUTDOWN} IST Reached — All positions squared off. Bot stopping.")
                break

            req = Request(CONFIG.FEED_URL, headers={"User-Agent": "NiftyLiveQuant/4.0"})
            with urlopen(req, timeout=1.5) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            spot_obj = data.get("spot", {})
            spot = float(spot_obj.get("ltp", 0.0)) if isinstance(spot_obj, dict) else float(spot_obj or 0.0)
            contracts = data.get("contracts", {})
            if contracts:
                cached_contracts = contracts

            if spot <= 0.0:
                time.sleep(CONFIG.POLL_INTERVAL)
                continue

            market.update(spot, t_str)

            for strat in strategies:
                strat.evaluate(spot, market, contracts)

            strat_snapshots = [s.to_dict() for s in strategies]
            total_open_mtm = round(sum(s.get("open_mtm", 0.0) for s in strat_snapshots), 2)
            total_realized = round(sum(s.get("realized_pnl", 0.0) for s in strat_snapshots), 2)
            total_charges = round(sum(s.get("charges_paid", 0.0) for s in strat_snapshots), 2)
            total_net = round(total_realized - total_charges, 2)
            active_count = sum(1 for s in strat_snapshots if s.get("status") == "ACTIVE")

            with STATE_LOCK:
                LIVE_BOT_STATE["timestamp"] = now.strftime("%Y-%m-%d %H:%M:%S")
                LIVE_BOT_STATE["spot"] = round(spot, 2)
                LIVE_BOT_STATE["atm"] = market.get_atm_strike(spot)
                LIVE_BOT_STATE["vwap"] = market.vwap
                LIVE_BOT_STATE["day_high"] = round(market.day_high, 2) if market.day_high is not None else 0.0
                LIVE_BOT_STATE["day_low"] = round(market.day_low, 2) if market.day_low is not None else 0.0
                LIVE_BOT_STATE["orb_high"] = round(market.orb_high, 2) if market.orb_high is not None else None
                LIVE_BOT_STATE["orb_low"] = round(market.orb_low, 2) if market.orb_low is not None else None
                LIVE_BOT_STATE["orb_set"] = market.orb_set
                LIVE_BOT_STATE["open_mtm"] = total_open_mtm
                LIVE_BOT_STATE["realized_pnl"] = total_realized
                LIVE_BOT_STATE["charges_paid"] = total_charges
                LIVE_BOT_STATE["net_pnl"] = total_net
                LIVE_BOT_STATE["active_count"] = active_count
                LIVE_BOT_STATE["strategies"] = strat_snapshots

            time.sleep(CONFIG.POLL_INTERVAL)

        except (URLError, ConnectionRefusedError):
            time.sleep(2.0)
        except KeyboardInterrupt:
            print("\n[*] Bot stopped manually. CSV logs saved.")
            break
        except Exception as e:
            print(f"[!] Error in main loop: {e}")
            traceback.print_exc()
            time.sleep(0.5)

if __name__ == "__main__":
    main()
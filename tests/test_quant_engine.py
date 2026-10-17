import os
import sys
import unittest
import json
import time
import csv
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from config.settings import CONFIG
from core.brokerage_calculator import calculate_exact_costs, calculate_detailed_statutory_costs
from core.execution_engine import apply_slippage
from core.market_state import MarketStateManager
from core.models import PositionLeg, TradeAuditRecord

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
from multi_strategy_bot import LIVE_BOT_STATE, STATE_LOCK

class TestBrokerageCalculator(unittest.TestCase):
    def test_buy_side_costs(self):
        costs = calculate_exact_costs(qty=65, entry_px=100.0, exit_px=120.0, side="BUY")
        self.assertEqual(costs["brokerage"], 40.0)
        self.assertEqual(costs["buy_turnover"], 6500.0)
        self.assertEqual(costs["sell_turnover"], 7800.0)
        self.assertEqual(costs["total_turnover"], 14300.0)
        self.assertEqual(costs["stt"], 7.80)
        self.assertEqual(costs["stamp_duty"], 0.20)
        self.assertEqual(costs["exchange_charges"], round(14300 * 0.0003503, 2))
        self.assertGreater(costs["gst"], 0)
        self.assertGreater(costs["total_charges"], costs["brokerage"] + costs["stt"])

    def test_sell_side_costs(self):
        costs = calculate_exact_costs(qty=65, entry_px=150.0, exit_px=120.0, side="SELL")
        self.assertEqual(costs["buy_turnover"], 7800.0)
        self.assertEqual(costs["sell_turnover"], 9750.0)
        self.assertEqual(costs["stt"], round(9750 * 0.0010, 2))
        self.assertEqual(costs["stamp_duty"], round(7800 * 0.00003, 2))

    def test_alias_compatibility(self):
        c1 = calculate_exact_costs(qty=65, entry_px=100.0, exit_px=110.0, side="BUY")
        c2 = calculate_detailed_statutory_costs(entry_px=100.0, exit_px=110.0, qty=65, side="BUY")
        self.assertEqual(c1, c2)

class TestExecutionEngine(unittest.TestCase):
    def test_apply_slippage_buy(self):
        px = 100.0
        slipped = apply_slippage(px, "BUY")
        self.assertEqual(slipped, 100.25)

    def test_apply_slippage_sell(self):
        px = 100.0
        slipped = apply_slippage(px, "SELL")
        self.assertEqual(slipped, 99.75)

    def test_apply_slippage_zero(self):
        self.assertEqual(apply_slippage(0.0, "BUY"), 0.0)
        self.assertEqual(apply_slippage(-5.0, "SELL"), 0.0)

class TestMarketStateManager(unittest.TestCase):
    def test_vwap_and_day_range(self):
        mgr = MarketStateManager()
        self.assertEqual(mgr.vwap, 0.0)
        mgr.update(24500.0, "09:16")
        mgr.update(24600.0, "09:20")
        self.assertEqual(mgr.vwap, 24550.0)
        self.assertEqual(mgr.day_high, 24600.0)
        self.assertEqual(mgr.day_low, 24500.0)

    def test_orb_freezing_and_alias(self):
        mgr = MarketStateManager()
        mgr.update(24500.0, "09:16")
        mgr.update(24650.0, "09:25")
        mgr.update(24450.0, "09:29")
        self.assertFalse(mgr.orb_set)
        self.assertFalse(mgr.orb_ready)

        mgr.update(24520.0, "09:30")
        self.assertTrue(mgr.orb_set)
        self.assertTrue(mgr.orb_ready)
        self.assertEqual(mgr.orb_high, 24650.0)
        self.assertEqual(mgr.orb_low, 24450.0)

        # Later ticks do NOT alter ORB
        mgr.update(24800.0, "10:00")
        self.assertEqual(mgr.orb_high, 24650.0)
        self.assertEqual(mgr.day_high, 24800.0)

    def test_reset(self):
        mgr = MarketStateManager()
        mgr.update(24500.0, "09:16")
        mgr.reset()
        self.assertEqual(mgr.tick_count, 0)
        self.assertEqual(mgr.spot_sum, 0.0)
        self.assertIsNone(mgr.day_high)
        self.assertIsNone(mgr.day_low)

    def test_atm_strike(self):
        self.assertEqual(MarketStateManager.get_atm_strike(24524.0), 24500)
        self.assertEqual(MarketStateManager.get_atm_strike(24526.0), 24550)
        self.assertEqual(MarketStateManager.get_atm_strike(24500.0), 24500)

    def test_find_contract_multi_format(self):
        contracts_dict = {
            "24500": {
                "CE": {"symbol": "NIFTY_24500_CE", "ltp": 125.5},
                "PE": {"symbol": "NIFTY_24500_PE", "ltp": 95.0}
            }
        }
        res_ce = MarketStateManager.find_contract(contracts_dict, 24500, "CE")
        self.assertIsNotNone(res_ce)
        self.assertEqual(res_ce[0], "NIFTY_24500_CE")
        self.assertEqual(res_ce[1], 125.5)

        contracts_list = [
            {"symbol": "NIFTY_24600_PE", "strike": 24600, "option_type": "PE", "ltp": 140.0}
        ]
        res_pe = MarketStateManager.find_contract(contracts_list, 24600, "PE")
        self.assertIsNotNone(res_pe)
        self.assertEqual(res_pe[0], "NIFTY_24600_PE")
        self.assertEqual(res_pe[1], 140.0)

class TestStrategiesLifecycle(unittest.TestCase):
    def setUp(self):
        self.market = MarketStateManager()
        self.contracts = {
            "24500": {
                "CE": {"symbol": "NIFTY_24500_CE", "ltp": 120.0},
                "PE": {"symbol": "NIFTY_24500_PE", "ltp": 110.0}
            },
            "24550": {
                "CE": {"symbol": "NIFTY_24550_CE", "ltp": 95.0},
                "PE": {"symbol": "NIFTY_24550_PE", "ltp": 135.0}
            },
            "24600": {
                "CE": {"symbol": "NIFTY_24600_CE", "ltp": 80.0},
                "PE": {"symbol": "NIFTY_24600_PE", "ltp": 160.0}
            },
            "24400": {
                "CE": {"symbol": "NIFTY_24400_CE", "ltp": 180.0},
                "PE": {"symbol": "NIFTY_24400_PE", "ltp": 70.0}
            },
            "24650": {
                "CE": {"symbol": "NIFTY_24650_CE", "ltp": 60.0},
                "PE": {"symbol": "NIFTY_24650_PE", "ltp": 190.0}
            },
            "24350": {
                "CE": {"symbol": "NIFTY_24350_CE", "ltp": 220.0},
                "PE": {"symbol": "NIFTY_24350_PE", "ltp": 50.0}
            },
            "24750": {
                "CE": {"symbol": "NIFTY_24750_CE", "ltp": 35.0},
                "PE": {"symbol": "NIFTY_24750_PE", "ltp": 250.0}
            },
            "24250": {
                "CE": {"symbol": "NIFTY_24250_CE", "ltp": 290.0},
                "PE": {"symbol": "NIFTY_24250_PE", "ltp": 30.0}
            }
        }

    def test_all_strategies_to_dict(self):
        strats = [
            S1ShortStraddle(), S2ShortStrangle(), S3IronCondor(),
            S4VWAPCallMomentum(), S5VWAPPutMomentum(), S6BullPutSpread(),
            S7BearCallSpread(), S8StraddleBuy(), S9ORBScalper(), S10MeanReversion()
        ]
        for s in strats:
            d = s.to_dict()
            self.assertIn("id", d)
            self.assertIn("name", d)
            self.assertIn("status", d)
            self.assertIn("open_mtm", d)
            self.assertIn("realized_pnl", d)
            self.assertIn("charges_paid", d)
            self.assertIn("net_pnl", d)
            self.assertIn("legs", d)

    def test_s1_entry_and_sl_trail(self):
        s1 = S1ShortStraddle()
        sim_time = datetime(2026, 10, 17, 9, 21, 0)
        s1.check_new_day("2026-10-17")

        # Feed tick during operational window (09:21)
        s1.evaluate(24500.0, self.market, self.contracts, now_dt=sim_time)
        self.assertTrue(s1.active)
        self.assertEqual(len(s1.legs), 2)
        ce_leg = s1.legs[0]
        pe_leg = s1.legs[1]

        # Trigger SL on CE leg (25% above entry)
        spike_contracts = {
            "24500": {
                "CE": {"symbol": "NIFTY_24500_CE", "ltp": 200.0},
                "PE": {"symbol": "NIFTY_24500_PE", "ltp": 100.0}
            }
        }
        s1.evaluate(24500.0, self.market, spike_contracts, now_dt=sim_time)
        self.assertFalse(ce_leg.is_open)
        self.assertTrue(pe_leg.sl_shifted_to_cost)
        self.assertEqual(pe_leg.sl_price, max(pe_leg.entry_price, pe_leg.raw_entry_price))

    def test_s2_short_strangle_and_trailing(self):
        s2 = S2ShortStrangle()
        sim_time = datetime(2026, 10, 17, 9, 31, 0)
        s2.check_new_day("2026-10-17")

        s2.evaluate(24500.0, self.market, self.contracts, now_dt=sim_time)
        self.assertTrue(s2.active)
        self.assertEqual(len(s2.legs), 2)
        self.assertEqual(s2.legs[0].strike, 24600)  # ATM + 100
        self.assertEqual(s2.legs[1].strike, 24400)  # ATM - 100

        # Simulate profit peak hitting 1900 with legs intact (SL prices are ~104 and ~91)
        s2.peak_pnl = 1900.0
        # When realized_pnl is 800.0, total_mtm is ~1034.0 (1900 - 1034 = 866 >= 700 pullback), trailing SL triggers
        s2.realized_pnl = 800.0
        steady_contracts = {
            "24600": {"CE": {"symbol": "NIFTY_24600_CE", "ltp": 78.0}},
            "24400": {"PE": {"symbol": "NIFTY_24400_PE", "ltp": 68.0}}
        }
        s2.evaluate(24500.0, self.market, steady_contracts, now_dt=sim_time)
        self.assertFalse(s2.active)
        self.assertEqual(s2.exit_reason, "TRAILING_SL_HIT")

    def test_s3_short_strike_breach(self):
        s3 = S3IronCondor()
        sim_time = datetime(2026, 10, 17, 9, 36, 0)
        s3.check_new_day("2026-10-17")

        s3.evaluate(24500.0, self.market, self.contracts, now_dt=sim_time)
        self.assertTrue(s3.active)
        self.assertEqual(s3.entry_atm, 24500)

        # Breach short strike: Spot goes to 24500 + 155 = 24655
        s3.evaluate(24655.0, self.market, self.contracts, now_dt=sim_time)
        self.assertFalse(s3.active)
        self.assertTrue(s3.completed_today)
        self.assertEqual(s3.exit_reason, "SHORT_STRIKE_BREACHED")

    def test_s4_vwap_call_momentum_trail_and_target(self):
        s4 = S4VWAPCallMomentum()
        sim_time = datetime(2026, 10, 17, 9, 45, 0)
        s4.check_new_day("2026-10-17")

        self.market.spot_sum = 24500.0 * 5
        self.market.tick_count = 5  # VWAP = 24500.0
        self.market.day_high = 24530.0

        # Spot = 24525 (> VWAP+15 and >= day_high-5)
        s4.evaluate(24525.0, self.market, self.contracts, now_dt=sim_time)
        self.assertTrue(s4.active)
        leg = s4.legs[0]
        initial_sl = leg.sl_price

        # Price advances +20 pts (> +18) -> trailing stop triggers
        gain_contracts = {
            "24500": {"CE": {"symbol": "NIFTY_24500_CE", "ltp": leg.entry_price + 20.0}}
        }
        s4.evaluate(24535.0, self.market, gain_contracts, now_dt=sim_time)
        self.assertTrue(leg.sl_shifted_to_cost)
        self.assertGreater(leg.sl_price, initial_sl)

        # Price advances +36 pts (> +35) -> target hit
        target_contracts = {
            "24500": {"CE": {"symbol": "NIFTY_24500_CE", "ltp": leg.entry_price + 36.0}}
        }
        s4.evaluate(24550.0, self.market, target_contracts, now_dt=sim_time)
        self.assertFalse(s4.active)
        self.assertEqual(s4.exit_reason, "TARGET_35PTS_HIT")

    def test_s6_bull_put_spread(self):
        s6 = S6BullPutSpread()
        sim_time = datetime(2026, 10, 17, 9, 50, 0)
        s6.check_new_day("2026-10-17")

        self.market.spot_sum = 24500.0 * 5
        self.market.tick_count = 5  # VWAP = 24500.0

        # Spot = 24515 (> VWAP + 10)
        s6.evaluate(24515.0, self.market, self.contracts, now_dt=sim_time)
        self.assertTrue(s6.active)
        self.assertGreater(s6.target_pnl, 0)
        self.assertLessEqual(s6.sl_pnl, -900.0)

    def test_s8_time_stop(self):
        s8 = S8StraddleBuy()
        sim_time = datetime(2026, 10, 17, 9, 46, 0)
        s8.check_new_day("2026-10-17")

        s8.evaluate(24500.0, self.market, self.contracts, now_dt=sim_time)
        self.assertTrue(s8.active)

        # Simulate 95 minutes elapsed
        s8.entry_epoch = time.time() - 5700
        s8.evaluate(24500.0, self.market, self.contracts, now_dt=sim_time)
        self.assertFalse(s8.active)
        self.assertEqual(s8.exit_reason, "90MIN_TIME_STOP")

    def test_s9_orb_scalper_midpoint_reversal(self):
        s9 = S9ORBScalper()
        sim_time = datetime(2026, 10, 17, 9, 32, 0)
        s9.check_new_day("2026-10-17")

        self.market.orb_high = 24520.0
        self.market.orb_low = 24480.0
        self.market.orb_set = True

        # Breakout high: spot = 24530 (> 24520 + 5)
        s9.evaluate(24530.0, self.market, self.contracts, now_dt=sim_time)
        self.assertTrue(s9.active)
        self.assertEqual(s9.legs[0].option_type, "CE")

        # Spot drops below midpoint (< 24500) -> midpoint reversal exit
        s9.evaluate(24495.0, self.market, self.contracts, now_dt=sim_time)
        self.assertFalse(s9.active)
        self.assertEqual(s9.exit_reason, "ORB_MIDPOINT_REVERSAL")

    def test_s10_mean_reversion_touches_vwap(self):
        s10 = S10MeanReversion()
        sim_time = datetime(2026, 10, 17, 10, 5, 0)
        s10.check_new_day("2026-10-17")

        self.market.spot_sum = 24500.0 * 10
        self.market.tick_count = 10  # VWAP = 24500.0

        # Stretch spot up by +65 pts: spot = 24565.0
        s10.evaluate(24565.0, self.market, self.contracts, now_dt=sim_time)
        self.assertTrue(s10.active)
        self.assertEqual(s10.legs[0].option_type, "PE")

        # Reverts to VWAP +- 8 (e.g. 24505.0)
        s10.evaluate(24505.0, self.market, self.contracts, now_dt=sim_time)
        self.assertFalse(s10.active)
        self.assertEqual(s10.exit_reason, "REVERTED_TO_VWAP")

    def test_csv_log_written(self):
        s1 = S1ShortStraddle()
        test_csv = "logs/test_trades_audit.csv"
        s1.log_file = test_csv
        s1.csv_path = test_csv
        if os.path.exists(test_csv):
            os.remove(test_csv)
        s1._ensure_log_file()

        sim_time = datetime(2026, 10, 17, 9, 21, 0)
        s1.check_new_day("2026-10-17")
        s1.evaluate(24500.0, self.market, self.contracts, now_dt=sim_time)
        # Close all legs
        s1.close_all_legs("TEST_CLOSE", self.contracts, now_dt=sim_time)
        self.assertTrue(os.path.exists(test_csv))
        with open(test_csv, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            header = next(reader)
            self.assertEqual(header[0], "StrategyID")
            self.assertEqual(header[-1], "ExitReason")
            row = next(reader)
            self.assertEqual(row[0], "S1")
            self.assertEqual(row[-1], "TEST_CLOSE")
        if os.path.exists(test_csv):
            os.remove(test_csv)

class TestLiveBotState(unittest.TestCase):
    def test_bot_state_json_serializable(self):
        with STATE_LOCK:
            LIVE_BOT_STATE["spot"] = 24550.0
            LIVE_BOT_STATE["atm"] = 24550
            LIVE_BOT_STATE["strategies"] = [S1ShortStraddle().to_dict()]
            serialized = json.dumps(LIVE_BOT_STATE)
            self.assertIn("spot", serialized)
            self.assertIn("strategies", serialized)

if __name__ == "__main__":
    unittest.main()

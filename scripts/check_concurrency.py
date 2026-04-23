#!/usr/bin/env python3
"""
SQLite concurrency check for simulated trade execution.

Runs against a temporary database, not backend/my_database.db.
"""

from __future__ import annotations

import os
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))


def run_pair(fn):
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(fn) for _ in range(2)]
        results = []
        for future in as_completed(futures):
            try:
                results.append(("ok", future.result()))
            except Exception as exc:
                results.append(("err", str(exc)))
        return results


def assert_one_success(results, label):
    successes = [r for r in results if r[0] == "ok"]
    failures = [r for r in results if r[0] == "err"]
    assert len(successes) == 1 and len(failures) == 1, f"{label}: expected 1 success/1 failure, got {results}"
    return successes, failures


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="cs348-concurrency-") as tmp:
        os.environ["CS348_DATABASE_PATH"] = str(Path(tmp) / "concurrency.db")

        import database as db

        db.init_db()

        buyer = db.create_user("buyer", "password123", starting_cash=100.0)
        buy_results = run_pair(lambda: db.execute_simulated_market_order(
            buyer["id"], "TST", 1, "buy", 80.0
        ))
        assert_one_success(buy_results, "double-buy")
        buyer_account = db.get_user_account(buyer["id"])
        buyer_orders = db.get_user_orders(buyer["id"])
        assert buyer_account["cash"] == 20.0, f"double-buy: expected $20 cash, got {buyer_account}"
        assert len(buyer_orders) == 1, f"double-buy: expected 1 order, got {len(buyer_orders)}"

        seller = db.create_user("seller", "password123", starting_cash=100.0)
        db.execute_simulated_market_order(seller["id"], "TST", 10, "buy", 1.0)
        sell_results = run_pair(lambda: db.execute_simulated_market_order(
            seller["id"], "TST", 7, "sell", 1.0
        ))
        assert_one_success(sell_results, "double-sell")
        seller_position = db.get_user_position(seller["id"], "TST")
        assert seller_position and seller_position["quantity"] == 3, (
            f"double-sell: expected 3 shares, got {seller_position}"
        )

        user_a = db.create_user("usera", "password123", starting_cash=100.0)
        user_b = db.create_user("userb", "password123", starting_cash=100.0)
        with ThreadPoolExecutor(max_workers=2) as pool:
            cross_results = [
                pool.submit(db.execute_simulated_market_order, user_a["id"], "XYZ", 1, "buy", 50.0),
                pool.submit(db.execute_simulated_market_order, user_b["id"], "XYZ", 1, "buy", 50.0),
            ]
            for future in as_completed(cross_results):
                future.result()
        assert db.get_user_account(user_a["id"])["cash"] == 50.0
        assert db.get_user_account(user_b["id"])["cash"] == 50.0

    print("concurrency checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

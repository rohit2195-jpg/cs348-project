"""
server.py — Flask API for the stock trading terminal
Manual CORS handling (no flask-cors) for full Chrome compatibility.

Endpoints:
  GET  /api/account          — Alpaca account summary
  GET  /api/portfolio        — Local DB positions with live prices injected
  GET  /api/orders           — Order history from local DB
  GET  /api/quote/<symbol>   — Live price for a single symbol
  GET  /api/chart            — Portfolio vs SPY chart data (20d)
  GET  /api/chart/<symbol>   — Single stock price history
  POST /api/buy              — Place a buy order  { symbol, quantity }
  POST /api/sell             — Place a sell order { symbol, quantity }
"""

import os
from datetime import datetime
from flask import Flask, jsonify, request, make_response
import traceback
import threading
import time

import database as db
import trading
from validation import (
    ValidationError,
    normalize_symbol,
    parse_alpaca_order_id,
    parse_date_string,
    parse_enum,
    parse_optional_float,
    parse_positive_int,
    parse_symbol_list,
    validate_notes,
)

app = Flask(__name__)
db.init_db()


# ── Background order settler ───────────────────────────────────────────────────
# Runs on server startup and every 30s. Checks all pending orders in the local
# DB against Alpaca and settles them automatically — works even if the browser
# is closed. This means after-hours orders placed today will auto-fill tomorrow
# morning when the market opens, with no user action required.

def settle_pending_orders():
    """Check every pending order in the DB and settle if Alpaca has filled/canceled it."""
    orders = db.get_all_orders()
    pending = [o for o in orders if o["status"] == "pending"]

    if not pending:
        return

    print(f"[settler] checking {len(pending)} pending order(s)...")

    for o in pending:
        # We need the Alpaca order ID — stored in a new column we'll add below.
        # For now, look up by matching symbol+qty+timestamp via Alpaca's order list.
        alpaca_id = db.get_alpaca_order_id(o["id"])
        if not alpaca_id:
            print(f"[settler] order #{o['id']} has no alpaca_id, skipping")
            continue

        try:
            result = trading.wait_for_fill(alpaca_id, timeout=3)
            status = result["status"]

            if status == "filled":
                filled_price = result["filled_price"]
                db.fill_order(o["id"])
                today = o["timestamp"][:10]

                if o["trade_type"] == "buy":
                    pos = db.get_position(o["symbol"])
                    if pos:
                        new_qty = pos["quantity"] + o["quantity"]
                        avg     = ((pos["purchasePrice"] * pos["quantity"]) +
                                   (filled_price * o["quantity"])) / new_qty
                        db.upsert_position(o["symbol"], round(avg, 4), new_qty, today)
                    else:
                        db.upsert_position(o["symbol"], filled_price, o["quantity"], today)
                else:  # sell
                    pos = db.get_position(o["symbol"])
                    if pos:
                        new_qty = pos["quantity"] - o["quantity"]
                        db.upsert_position(o["symbol"], pos["purchasePrice"], new_qty, pos["purchaseDate"])

                print(f"[settler] ✓ order #{o['id']} {o['trade_type']} {o['symbol']} filled @ ${filled_price}")

            elif status in ("canceled", "rejected", "expired", "done_for_day"):
                db.cancel_order_db(o["id"])
                print(f"[settler] ✗ order #{o['id']} {o['symbol']} {status}")

            else:
                print(f"[settler] order #{o['id']} {o['symbol']} still {status}")

        except Exception as e:
            print(f"[settler] error checking order #{o['id']}: {e}")


def check_watchlist_targets():
    """
    Check every watchlist entry that has an untriggered target price.
    Called by the background settler every 30s.
    Fetches live prices in a single batch call to avoid hammering the API.
    """
    active = db.get_watchlist_active()
    if not active:
        return

    symbols = [w["symbol"] for w in active]
    try:
        prices = trading.get_latest_prices(symbols)
    except Exception as e:
        print(f"[watchlist] price fetch error: {e}")
        return

    for w in active:
        sym   = w["symbol"]
        price = prices.get(sym)
        if price is None:
            continue

        target    = w["target_price"]
        direction = w["target_direction"]

        hit = (direction == "above" and price >= target) or               (direction == "below" and price <= target)

        if hit:
            db.mark_watchlist_triggered(sym, price)
            print(f"[watchlist] 🎯 {sym} target hit! "
                  f"price={price:.2f} target={target:.2f} ({direction})")


def background_settler():
    """Runs forever in a daemon thread. Settles pending orders every 30s."""
    # Give Flask a moment to finish starting up
    time.sleep(3)
    while True:
        try:
            settle_pending_orders()
            check_watchlist_targets()
        except Exception as e:
            print(f"[settler] unexpected error: {e}")
        time.sleep(30)


# Start settler thread on server startup
_settler_thread = threading.Thread(target=background_settler, daemon=True)
_settler_thread.start()
print("[settler] background order settler started (runs every 30s)")


# ── CORS — applied manually to every response ─────────────────────────────────
# flask-cors has issues with Chrome when Flask's debug reloader is active.
# Manually injecting headers on every response is the most reliable approach.

def _cors(response):
    response.headers["Access-Control-Allow-Origin"]  = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PATCH, DELETE, OPTIONS"
    return response

@app.after_request
def apply_cors(response):
    return _cors(response)

# Chrome sends an OPTIONS preflight before every POST — handle it globally
@app.before_request
def handle_preflight():
    if request.method == "OPTIONS":
        resp = make_response("", 204)
        return _cors(resp)


# ── Helpers ───────────────────────────────────────────────────────────────────

def err(msg: str, code: int = 400):
    return jsonify({"error": msg}), code


def get_json_body():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise ValidationError("Request body must be valid JSON")
    return body


def require_value(value, field_name: str):
    if value in (None, ""):
        raise ValidationError(f"{field_name} is required")
    return value


# ── Health check ───────────────────────────────────────────────────────────────

@app.route("/", methods=["GET"])
def hello_world():
    print("[health] hello world endpoint hit")
    return "hello world", 200


# ── Account ───────────────────────────────────────────────────────────────────

@app.route("/api/account", methods=["GET"])
def get_account():
    try:
        acct = trading.get_account()
        return jsonify({
            "buying_power":    float(acct.buying_power),
            "equity":          float(acct.equity),
            "portfolio_value": float(acct.portfolio_value),
            "cash":            float(acct.cash),
            "market_open":     trading.is_market_open(),
        })
    except Exception as e:
        return err(str(e), 500)


# ── Portfolio ──────────────────────────────────────────────────────────────────

@app.route("/api/portfolio", methods=["GET"])
def get_portfolio():
    try:
        rows    = db.get_portfolio()
        symbols = [r.symbol for r in rows]
        prices  = trading.get_latest_prices(symbols) if symbols else {}

        positions = []
        for r in rows:
            current = prices.get(r.symbol, 0.0)
            pl  = (current - r.purchasePrice) * r.quantity
            pct = ((current - r.purchasePrice) / r.purchasePrice * 100) if r.purchasePrice else 0
            positions.append({
                "symbol":        r.symbol,
                "quantity":      r.quantity,
                "avg_price":     r.purchasePrice,
                "current_price": current,
                "market_value":  round(current * r.quantity, 2),
                "pl":            round(pl, 2),
                "pl_pct":        round(pct, 2),
                "purchase_date": r.purchaseDate,
            })
        return jsonify(positions)
    except Exception as e:
        return err(str(e), 500)


# ── Orders ─────────────────────────────────────────────────────────────────────

@app.route("/api/orders", methods=["GET"])
def get_orders():
    try:
        return jsonify(db.get_all_orders())
    except Exception as e:
        return err(str(e), 500)


# ── Quote ──────────────────────────────────────────────────────────────────────

@app.route("/api/quote/<symbol>", methods=["GET"])
def get_quote(symbol):
    try:
        symbol = normalize_symbol(symbol)
        price = trading.get_latest_price(symbol)
        return jsonify({"symbol": symbol, "price": price})
    except ValidationError as e:
        return err(str(e))
    except Exception as e:
        return err(str(e), 500)


# ── Charts ─────────────────────────────────────────────────────────────────────

@app.route("/api/chart", methods=["GET"])
def get_portfolio_chart():
    try:
        holdings = db.get_portfolio_for_chart()
        days     = parse_positive_int(request.args.get("days", 20), "days")
        data     = trading.get_portfolio_vs_spy(holdings, days=days)
        return jsonify(data)
    except ValidationError as e:
        return err(str(e))
    except Exception as e:
        return err(str(e), 500)


@app.route("/api/chart/<symbol>", methods=["GET"])
def get_symbol_chart(symbol):
    try:
        symbol = normalize_symbol(symbol)
        days = parse_positive_int(request.args.get("days", 30), "days")
        data = trading.get_price_history(symbol, days=days)
        return jsonify(data)
    except ValidationError as e:
        return err(str(e))
    except Exception as e:
        traceback.print_exc()
        return err(str(e), 500)


# ── Buy ────────────────────────────────────────────────────────────────────────

@app.route("/api/buy", methods=["POST"])
def buy():
    try:
        body     = get_json_body()
        symbol   = normalize_symbol(body.get("symbol"))
        quantity = parse_positive_int(body.get("quantity"), "quantity")
    except ValidationError as e:
        return err(str(e))

    # Must get a valid price before recording the order
    try:
        price = trading.get_latest_price(symbol)
    except Exception as e:
        return err(f"Could not get price for {symbol}: {e}")

    if price <= 0:
        return err(f"Invalid price ${price} for {symbol}. Cannot place order.")

    # Record as pending in local DB
    order_id = db.create_order(symbol, price, quantity, "buy")

    try:
        # Submit to Alpaca
        alpaca_order = trading.buy_stock(symbol, quantity)

        # Store Alpaca UUID immediately so the background settler can find it
        db.set_alpaca_order_id(order_id, str(alpaca_order.id))

        # Poll until filled (or timeout after 10s)
        result = trading.wait_for_fill(str(alpaca_order.id))

        if result["status"] == "filled":
            filled_price = result["filled_price"]
            db.fill_order(order_id)

            # Only update portfolio once confirmed filled
            today = datetime.now().strftime("%Y-%m-%d")
            pos   = db.get_position(symbol)
            if pos:
                new_qty = pos["quantity"] + quantity
                avg     = ((pos["purchasePrice"] * pos["quantity"]) + (filled_price * quantity)) / new_qty
                db.upsert_position(symbol, round(avg, 4), new_qty, today)
            else:
                db.upsert_position(symbol, filled_price, quantity, today)

            return jsonify({
                "success":      True,
                "order_id":     order_id,
                "symbol":       symbol,
                "quantity":     quantity,
                "filled_price": filled_price,
                "message":      f"Bought {quantity}x {symbol} @ ${filled_price:.2f}",
            })

        elif result["status"] in ("canceled", "rejected", "expired"):
            # Alpaca rejected — cancel our local record, don't touch portfolio
            db.cancel_order_db(order_id)
            return err(f"Order {result['status']} by Alpaca. Portfolio unchanged.")

        else:
            # Still pending after timeout (e.g. after-hours) — leave as pending
            # Portfolio is NOT updated until a /api/sync call confirms the fill
            return jsonify({
                "success":         False,
                "pending":         True,
                "order_id":        order_id,
                "alpaca_order_id": str(alpaca_order.id),
                "trade_type":      "buy",
                "symbol":          symbol,
                "quantity":        quantity,
                "message":         f"Order submitted but still pending (market may be closed). "
                                   f"Portfolio will update once filled.",
            })

    except Exception as e:
        db.cancel_order_db(order_id)
        return err(f"Alpaca order failed: {e}", 500)


# ── Sell ───────────────────────────────────────────────────────────────────────

@app.route("/api/sell", methods=["POST"])
def sell():
    try:
        body     = get_json_body()
        symbol   = normalize_symbol(body.get("symbol"))
        quantity = parse_positive_int(body.get("quantity"), "quantity")
    except ValidationError as e:
        return err(str(e))

    pos = db.get_position(symbol)
    if not pos:
        return err(f"No position in {symbol}")
    if quantity > pos["quantity"]:
        return err(f"Insufficient shares. You hold {pos['quantity']}.")

    # Must get a valid price before recording the order
    try:
        price = trading.get_latest_price(symbol)
    except Exception as e:
        return err(f"Could not get price for {symbol}: {e}")

    if price <= 0:
        return err(f"Invalid price ${price} for {symbol}. Cannot place order.")

    # Record as pending in local DB
    order_id = db.create_order(symbol, price, quantity, "sell")

    try:
        alpaca_order = trading.sell_stock(symbol, quantity)

        # Store Alpaca UUID immediately so the background settler can find it
        db.set_alpaca_order_id(order_id, str(alpaca_order.id))

        # Poll until filled (or timeout)
        result = trading.wait_for_fill(str(alpaca_order.id))

        if result["status"] == "filled":
            filled_price = result["filled_price"]
            db.fill_order(order_id)

            # Only remove from portfolio once confirmed filled
            new_qty = pos["quantity"] - quantity
            db.upsert_position(symbol, pos["purchasePrice"], new_qty, pos["purchaseDate"])

            return jsonify({
                "success":      True,
                "order_id":     order_id,
                "symbol":       symbol,
                "quantity":     quantity,
                "filled_price": filled_price,
                "message":      f"Sold {quantity}x {symbol} @ ${filled_price:.2f}",
            })

        elif result["status"] in ("canceled", "rejected", "expired"):
            db.cancel_order_db(order_id)
            return err(f"Order {result['status']} by Alpaca. Portfolio unchanged.")

        else:
            # Still pending after timeout — portfolio unchanged until confirmed
            return jsonify({
                "success":         False,
                "pending":         True,
                "order_id":        order_id,
                "alpaca_order_id": str(alpaca_order.id),
                "trade_type":      "sell",
                "symbol":          symbol,
                "quantity":        quantity,
                "message":         f"Sell order submitted but still pending (market may be closed). "
                                   f"Portfolio will update once filled.",
            })

    except Exception as e:
        db.cancel_order_db(order_id)
        return err(f"Alpaca order failed: {e}", 500)




# ── Sync pending orders ────────────────────────────────────────────────────────
# Call this after a pending order to check if it has since been filled.
# The frontend calls this automatically after receiving pending:true.

@app.route("/api/sync", methods=["POST"])
def sync_order():
    """
    Check a pending local order against Alpaca and settle it if filled.
    Body: { "order_id": int, "alpaca_order_id": str, "trade_type": "buy"|"sell" }
    """
    try:
        body            = get_json_body()
        local_order_id  = parse_positive_int(body.get("order_id"), "order_id")
        alpaca_order_id = parse_alpaca_order_id(body.get("alpaca_order_id"))
        trade_type      = parse_enum(require_value(body.get("trade_type"), "trade_type"), {"buy", "sell"}, "trade_type")
        symbol          = normalize_symbol(body.get("symbol"))
        quantity        = parse_positive_int(body.get("quantity"), "quantity")
    except ValidationError as e:
        return err(str(e))

    print(f"[sync] order_id={local_order_id} alpaca_id={alpaca_order_id} type={trade_type} sym={symbol} qty={quantity}")

    try:
        result = trading.wait_for_fill(alpaca_order_id, timeout=5)
    except Exception as e:
        traceback.print_exc()
        return err(f"Could not check Alpaca order: {e}", 500)

    if result["status"] == "filled":
        filled_price = result["filled_price"]
        db.fill_order(local_order_id)
        today = datetime.now().strftime("%Y-%m-%d")

        if trade_type == "buy":
            pos = db.get_position(symbol)
            if pos:
                new_qty = pos["quantity"] + quantity
                avg     = ((pos["purchasePrice"] * pos["quantity"]) + (filled_price * quantity)) / new_qty
                db.upsert_position(symbol, round(avg, 4), new_qty, today)
            else:
                db.upsert_position(symbol, filled_price, quantity, today)
        else:  # sell
            pos = db.get_position(symbol)
            if pos:
                new_qty = pos["quantity"] - quantity
                db.upsert_position(symbol, pos["purchasePrice"], new_qty, pos["purchaseDate"])

        return jsonify({
            "settled":       True,
            "status":        "filled",
            "filled_price":  filled_price,
            "message":       f"Order filled @ ${filled_price:.2f}. Portfolio updated.",
        })

    elif result["status"] in ("canceled", "rejected", "expired"):
        db.cancel_order_db(local_order_id)
        return jsonify({
            "settled": True,
            "status":  result["status"],
            "message": f"Order was {result['status']}. Portfolio unchanged.",
        })

    else:
        return jsonify({
            "settled": False,
            "status":  result["status"],
            "message": "Order still pending.",
        })



# ── Watchlist endpoints ───────────────────────────────────────────────────────

@app.route("/api/watchlist", methods=["GET"])
def get_watchlist():
    """All watchlist entries with live prices injected."""
    try:
        entries = db.get_watchlist()
        if not entries:
            return jsonify([])
        prices = trading.get_latest_prices([e["symbol"] for e in entries])
        for e in entries:
            e["current_price"] = prices.get(e["symbol"])
            # Calculate % distance from target
            if e["target_price"] and e["current_price"]:
                e["target_distance_pct"] = round(
                    (e["current_price"] - e["target_price"]) / e["target_price"] * 100, 2
                )
            else:
                e["target_distance_pct"] = None
        return jsonify(entries)
    except Exception as e:
        traceback.print_exc()
        return err(str(e), 500)


@app.route("/api/watchlist", methods=["POST"])
def add_watchlist():
    """
    Add or update a watchlist entry.
    Body: { symbol, target_price?, target_direction?, notes? }
    target_direction: "above" | "below"
    """
    try:
        body             = get_json_body()
        symbol           = normalize_symbol(body.get("symbol"))
        target_price     = parse_optional_float(body.get("target_price"), "target_price")
        target_direction = parse_enum(body.get("target_direction"), {"above", "below"}, "target_direction")
        notes            = validate_notes(body.get("notes", ""))
    except ValidationError as e:
        return err(str(e))

    if (target_price is None) != (target_direction is None):
        return err("target_price and target_direction must both be set, or both omitted")
    if target_price is not None and target_price <= 0:
        return err("target_price must be greater than 0")

    # Verify symbol exists on Alpaca
    try:
        current_price = trading.get_latest_price(symbol)
    except Exception as e:
        return err(f"Could not verify symbol '{symbol}': {e}")

    try:
        entry = db.add_to_watchlist(
            symbol           = symbol,
            target_price     = target_price,
            target_direction = target_direction,
            notes            = notes,
        )
        entry["current_price"] = current_price
        return jsonify({"success": True, "entry": entry})
    except Exception as e:
        traceback.print_exc()
        return err(str(e), 500)


@app.route("/api/watchlist/<symbol>", methods=["DELETE"])
def remove_watchlist(symbol):
    try:
        symbol = normalize_symbol(symbol)
        removed = db.remove_from_watchlist(symbol)
        if not removed:
            return err(f"{symbol} not in watchlist", 404)
        return jsonify({"success": True})
    except ValidationError as e:
        return err(str(e))
    except Exception as e:
        return err(str(e), 500)


@app.route("/api/watchlist/<symbol>", methods=["PATCH"])
def update_watchlist(symbol):
    """Update target price, direction, or notes."""
    try:
        symbol           = normalize_symbol(symbol)
        body             = get_json_body()
        target_price     = parse_optional_float(body.get("target_price"), "target_price")
        target_direction = parse_enum(body.get("target_direction"), {"above", "below"}, "target_direction")
        notes            = validate_notes(body.get("notes"))
        if target_price is not None and target_price <= 0:
            return err("target_price must be greater than 0")
        entry = db.update_watchlist_entry(
            symbol           = symbol,
            target_price     = target_price,
            target_direction = target_direction,
            notes            = notes,
        )
        if not entry:
            return err(f"{symbol} not in watchlist", 404)
        return jsonify({"success": True, "entry": entry})
    except ValidationError as e:
        return err(str(e))
    except Exception as e:
        traceback.print_exc()
        return err(str(e), 500)


@app.route("/api/watchlist/alerts", methods=["GET"])
def get_alerts():
    """Unread (triggered but not dismissed) alerts — used for badge count."""
    try:
        return jsonify(db.get_unread_alerts())
    except Exception as e:
        return err(str(e), 500)


@app.route("/api/watchlist/<symbol>/dismiss", methods=["POST"])
def dismiss_alert(symbol):
    """Mark an alert as seen without removing the watchlist entry."""
    try:
        db.dismiss_watchlist_alert(normalize_symbol(symbol))
        return jsonify({"success": True})
    except ValidationError as e:
        return err(str(e))
    except Exception as e:
        return err(str(e), 500)


# ── Filter & Report endpoints ──────────────────────────────────────────────────

@app.route("/api/symbols", methods=["GET"])
def get_symbols():
    """
    All unique symbols from portfolio + order history.
    Used to build dynamic dropdowns in the frontend.
    """
    try:
        return jsonify(db.get_symbols())
    except Exception as e:
        return err(str(e), 500)


@app.route("/api/filter/orders", methods=["GET"])
def filter_orders():
    """
    Filtered order history. All query params optional:
      symbols     — comma-separated e.g. AAPL,TSLA
      trade_type  — buy | sell
      status      — filled | pending | canceled
      date_from   — YYYY-MM-DD
      date_to     — YYYY-MM-DD  (inclusive)
      price_min   — float
      price_max   — float
    """
    try:
        symbols     = parse_symbol_list(request.args.get("symbols", ""))
        trade_type  = parse_enum(request.args.get("trade_type"), {"buy", "sell"}, "trade_type")
        status      = parse_enum(request.args.get("status"), {"filled", "pending", "canceled"}, "status")
        date_from   = parse_date_string(request.args.get("date_from"), "date_from")
        date_to     = parse_date_string(request.args.get("date_to"), "date_to")
        price_min   = parse_optional_float(request.args.get("price_min"), "price_min")
        price_max   = parse_optional_float(request.args.get("price_max"), "price_max")
        if date_from and date_to and date_from > date_to:
            return err("date_from must be on or before date_to")
        if price_min is not None and price_max is not None and price_min > price_max:
            return err("price_min must be less than or equal to price_max")

        orders = db.filter_orders(
            symbols=symbols, trade_type=trade_type, status=status,
            date_from=date_from, date_to=date_to,
            price_min=price_min, price_max=price_max,
        )
        return jsonify({
            "results": orders,
            "count":   len(orders),
            "filters": {
                "symbols": symbols, "trade_type": trade_type, "status": status,
                "date_from": date_from, "date_to": date_to,
                "price_min": price_min, "price_max": price_max,
            }
        })
    except ValidationError as e:
        return err(str(e))
    except Exception as e:
        traceback.print_exc()
        return err(str(e), 500)


@app.route("/api/filter/portfolio", methods=["GET"])
def filter_portfolio():
    """
    Filtered portfolio. All query params optional:
      symbols   — comma-separated
      pl_min    — P/L % minimum
      pl_max    — P/L % maximum
      val_min   — market value minimum ($)
      val_max   — market value maximum ($)
    """
    try:
        symbols     = parse_symbol_list(request.args.get("symbols", ""))
        pl_min      = parse_optional_float(request.args.get("pl_min"), "pl_min")
        pl_max      = parse_optional_float(request.args.get("pl_max"), "pl_max")
        val_min     = parse_optional_float(request.args.get("val_min"), "val_min")
        val_max     = parse_optional_float(request.args.get("val_max"), "val_max")
        if pl_min is not None and pl_max is not None and pl_min > pl_max:
            return err("pl_min must be less than or equal to pl_max")
        if val_min is not None and val_max is not None and val_min > val_max:
            return err("val_min must be less than or equal to val_max")

        # Fetch live prices for all held symbols to calculate P/L
        all_positions = db.get_portfolio()
        all_symbols   = [r.symbol for r in all_positions]
        prices        = trading.get_latest_prices(all_symbols) if all_symbols else {}

        positions = db.filter_portfolio(
            symbols=symbols, pl_min=pl_min, pl_max=pl_max,
            val_min=val_min, val_max=val_max, prices=prices,
        )
        return jsonify({
            "results": positions,
            "count":   len(positions),
            "filters": {
                "symbols": symbols,
                "pl_min": pl_min, "pl_max": pl_max,
                "val_min": val_min, "val_max": val_max,
            }
        })
    except ValidationError as e:
        return err(str(e))
    except Exception as e:
        traceback.print_exc()
        return err(str(e), 500)


@app.route("/api/report/snapshot", methods=["GET"])
def portfolio_snapshot():
    """
    Returns the current portfolio snapshot (plain DB values, no live prices).
    Used by the before/after diff report — call before and after making changes.
    """
    try:
        snapshot = db.get_portfolio_snapshot()
        prices   = trading.get_latest_prices([r["symbol"] for r in snapshot]) if snapshot else {}
        for row in snapshot:
            row["current_price"] = prices.get(row["symbol"], 0.0)
            row["market_value"]  = round(row["current_price"] * row["quantity"], 2)
            row["pl_pct"]        = round(
                (row["current_price"] - row["avg_price"]) / row["avg_price"] * 100, 2
            ) if row["avg_price"] else 0
        return jsonify({
            "snapshot":   snapshot,
            "taken_at":   datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total_value": round(sum(r["market_value"] for r in snapshot), 2),
        })
    except Exception as e:
        traceback.print_exc()
        return err(str(e), 500)

# ── Entry point ────────────────────────────────────────────────────────────────
# use_reloader=False prevents the double-process issue that breaks CORS in Chrome

if __name__ == "__main__":
    host = os.getenv("APP_HOST", "127.0.0.1")
    port = int(os.getenv("APP_PORT", "5000"))
    debug = os.getenv("APP_DEBUG", "true").lower() in {"1", "true", "yes", "on"}
    app.run(host=host, port=port, debug=debug, use_reloader=False)

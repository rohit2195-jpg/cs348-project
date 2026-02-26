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

from flask import Flask, jsonify, request, make_response
from datetime import datetime

import database as db
import trading

app = Flask(__name__)
db.init_db()


# ── CORS — applied manually to every response ─────────────────────────────────
# flask-cors has issues with Chrome when Flask's debug reloader is active.
# Manually injecting headers on every response is the most reliable approach.

def _cors(response):
    response.headers["Access-Control-Allow-Origin"]  = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
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
        price = trading.get_latest_price(symbol.upper())
        return jsonify({"symbol": symbol.upper(), "price": price})
    except Exception as e:
        return err(str(e), 500)


# ── Charts ─────────────────────────────────────────────────────────────────────

@app.route("/api/chart", methods=["GET"])
def get_portfolio_chart():
    try:
        holdings = db.get_portfolio_for_chart()
        days     = int(request.args.get("days", 20))
        data     = trading.get_portfolio_vs_spy(holdings, days=days)
        return jsonify(data)
    except Exception as e:
        return err(str(e), 500)


@app.route("/api/chart/<symbol>", methods=["GET"])
def get_symbol_chart(symbol):
    try:
        days = int(request.args.get("days", 30))
        data = trading.get_price_history(symbol.upper(), days=days)
        return jsonify(data)
    except Exception as e:
        return err(str(e), 500)


# ── Buy ────────────────────────────────────────────────────────────────────────

@app.route("/api/buy", methods=["POST"])
def buy():
    body     = request.get_json(force=True)
    symbol   = (body.get("symbol") or "").upper().strip()
    quantity = body.get("quantity")

    if not symbol:
        return err("symbol is required")
    try:
        quantity = int(quantity)
        assert quantity > 0
    except Exception:
        return err("quantity must be a positive integer")

    try:
        price = trading.get_latest_price(symbol)
    except Exception:
        price = 0.0

    order_id = db.create_order(symbol, price, quantity, "buy")
    try:
        alpaca_order  = trading.buy_stock(symbol, quantity)
        filled_price  = float(alpaca_order.filled_avg_price or price)
        db.fill_order(order_id)

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
    except Exception as e:
        db.cancel_order_db(order_id)
        return err(f"Alpaca order failed: {e}", 500)


# ── Sell ───────────────────────────────────────────────────────────────────────

@app.route("/api/sell", methods=["POST"])
def sell():
    body     = request.get_json(force=True)
    symbol   = (body.get("symbol") or "").upper().strip()
    quantity = body.get("quantity")

    if not symbol:
        return err("symbol is required")
    try:
        quantity = int(quantity)
        assert quantity > 0
    except Exception:
        return err("quantity must be a positive integer")

    pos = db.get_position(symbol)
    if not pos:
        return err(f"No position in {symbol}")
    if quantity > pos["quantity"]:
        return err(f"Insufficient shares. You hold {pos['quantity']}.")

    try:
        price = trading.get_latest_price(symbol)
    except Exception:
        price = 0.0

    order_id = db.create_order(symbol, price, quantity, "sell")
    try:
        trading.sell_stock(symbol, quantity)
        db.fill_order(order_id)

        new_qty = pos["quantity"] - quantity
        db.upsert_position(symbol, pos["purchasePrice"], new_qty, pos["purchaseDate"])

        return jsonify({
            "success":  True,
            "order_id": order_id,
            "symbol":   symbol,
            "quantity": quantity,
            "price":    price,
            "message":  f"Sold {quantity}x {symbol} @ ${price:.2f}",
        })
    except Exception as e:
        db.cancel_order_db(order_id)
        return err(f"Alpaca order failed: {e}", 500)


# ── Entry point ────────────────────────────────────────────────────────────────
# use_reloader=False prevents the double-process issue that breaks CORS in Chrome

if __name__ == "__main__":
    app.run(debug=True, port=5000, use_reloader=False)
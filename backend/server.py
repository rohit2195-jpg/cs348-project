"""
server.py — Flask API for the multi-user trading simulator.
Alpaca is used for market data only; account state and trade execution are local.
"""

import os
import threading
import time
import traceback
from collections import defaultdict
from datetime import datetime
from functools import wraps
from urllib.parse import urlparse

from flask import Flask, jsonify, make_response, request

import database as db
import trading
from validation import (
    ValidationError,
    normalize_symbol,
    parse_date_string,
    parse_enum,
    parse_optional_float,
    parse_positive_int,
    parse_symbol_list,
    validate_notes,
)

app = Flask(__name__)
db.init_db()

SESSION_COOKIE = "CS348_SESSION"
ALLOWED_ORIGINS = {
    "http://localhost:5173",
    "http://127.0.0.1:5173",
}
_user_locks = defaultdict(threading.Lock)
_user_locks_guard = threading.Lock()


def _is_allowed_origin(origin: str | None) -> bool:
    if not origin:
        return False
    if origin in ALLOWED_ORIGINS:
        return True
    parsed = urlparse(origin)
    return parsed.scheme in {"http", "https"} and parsed.hostname in {"localhost", "127.0.0.1"}


def _cors(response):
    origin = request.headers.get("Origin")
    if _is_allowed_origin(origin):
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
        response.headers["Access-Control-Allow-Credentials"] = "true"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PATCH, DELETE, OPTIONS"
    return response


@app.after_request
def apply_cors(response):
    return _cors(response)


@app.before_request
def handle_preflight():
    if request.method == "OPTIONS":
        resp = make_response("", 204)
        return _cors(resp)


def err(msg: str, code: int = 400):
    return jsonify({"error": msg}), code


def _get_user_lock(user_id: int):
    with _user_locks_guard:
        return _user_locks[user_id]


def get_json_body():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise ValidationError("Request body must be valid JSON")
    return body


def current_user():
    auth_header = request.headers.get("Authorization", "")
    token = None
    if auth_header.lower().startswith("bearer "):
        token = auth_header.split(" ", 1)[1].strip()
    if not token:
        token = request.cookies.get(SESSION_COOKIE)
    return db.get_user_by_session(token)


def require_user():
    user = current_user()
    if not user:
        return None, err("Authentication required", 401)
    return user, None


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user, failure = require_user()
        if failure:
            return failure
        return fn(user, *args, **kwargs)

    return wrapper


def _set_session_cookie(response, token: str | None):
    if token:
        response.set_cookie(
            SESSION_COOKIE,
            token,
            httponly=True,
            samesite="Lax",
            secure=False,
            max_age=14 * 24 * 60 * 60,
        )
    else:
        response.delete_cookie(SESSION_COOKIE, httponly=True, samesite="Lax")
    return response


def _account_payload(user: dict) -> dict:
    holdings = db.get_user_positions(user["id"])
    prices = trading.get_latest_prices([row["symbol"] for row in holdings]) if holdings else {}
    portfolio_value = round(
        sum(prices.get(row["symbol"], 0.0) * row["quantity"] for row in holdings),
        2,
    )
    account = db.get_user_account(user["id"])
    equity = round(account["cash"] + portfolio_value, 2)
    return {
        "username": user["username"],
        "cash": account["cash"],
        "buying_power": account["cash"],
        "portfolio_value": portfolio_value,
        "equity": equity,
        "market_open": trading.is_market_open(),
    }


def check_watchlist_targets():
    active = db.get_all_active_watchlist_entries()
    if not active:
        return

    symbols = sorted({row["symbol"] for row in active})
    try:
        prices = trading.get_latest_prices(symbols)
    except Exception as exc:
        print(f"[watchlist] price fetch error: {exc}")
        return

    for row in active:
        price = prices.get(row["symbol"])
        if price is None:
            continue
        target = row["target_price"]
        direction = row["target_direction"]
        hit = (direction == "above" and price >= target) or (direction == "below" and price <= target)
        if hit:
            db.mark_user_watchlist_triggered(row["user_id"], row["symbol"], price)
            print(f"[watchlist] user={row['user_id']} {row['symbol']} target hit @ {price:.2f}")


def background_watchlist_worker():
    time.sleep(2)
    while True:
        try:
            check_watchlist_targets()
        except Exception as exc:
            print(f"[watchlist] unexpected error: {exc}")
        time.sleep(30)


_watchlist_thread = threading.Thread(target=background_watchlist_worker, daemon=True)
_watchlist_thread.start()


@app.route("/", methods=["GET"])
def hello_world():
    return "hello world", 200


@app.route("/api/register", methods=["POST"])
def register():
    try:
        body = get_json_body()
        username = (body.get("username") or "").strip()
        password = body.get("password") or ""
        user = db.create_user(username, password)
        token = db.create_user_session(user["id"])
        response = jsonify({"success": True, "user": user, "token": token})
        return _set_session_cookie(response, token)
    except ValidationError as exc:
        return err(str(exc))
    except ValueError as exc:
        return err(str(exc))
    except Exception as exc:
        return err(str(exc), 500)


@app.route("/api/login", methods=["POST"])
def login():
    try:
        body = get_json_body()
        username = (body.get("username") or "").strip()
        password = body.get("password") or ""
        user = db.authenticate_user(username, password)
        if not user:
            return err("Invalid username or password", 401)
        token = db.create_user_session(user["id"])
        response = jsonify({"success": True, "user": user, "token": token})
        return _set_session_cookie(response, token)
    except ValidationError as exc:
        return err(str(exc))
    except Exception as exc:
        return err(str(exc), 500)


@app.route("/api/logout", methods=["POST"])
def logout():
    db.delete_user_session(request.cookies.get(SESSION_COOKIE))
    response = jsonify({"success": True})
    return _set_session_cookie(response, None)


@app.route("/api/session", methods=["GET"])
def session_status():
    try:
        user = current_user()
        if not user:
            return jsonify({"authenticated": False}), 200
        return jsonify({
            "authenticated": True,
            "user": user,
            "account": _account_payload(user),
        })
    except Exception as exc:
        traceback.print_exc()
        return err(str(exc), 500)


@app.route("/api/account", methods=["GET"])
@login_required
def get_account(user):
    try:
        return jsonify(_account_payload(user))
    except Exception as exc:
        return err(str(exc), 500)


@app.route("/api/portfolio", methods=["GET"])
@login_required
def get_portfolio(user):
    try:
        holdings = db.get_user_positions(user["id"])
        prices = trading.get_latest_prices([row["symbol"] for row in holdings]) if holdings else {}
        positions = []
        for row in holdings:
            current = prices.get(row["symbol"], 0.0)
            pl = (current - row["purchasePrice"]) * row["quantity"]
            pct = ((current - row["purchasePrice"]) / row["purchasePrice"] * 100) if row["purchasePrice"] else 0
            positions.append({
                "symbol": row["symbol"],
                "quantity": row["quantity"],
                "avg_price": row["purchasePrice"],
                "current_price": current,
                "market_value": round(current * row["quantity"], 2),
                "pl": round(pl, 2),
                "pl_pct": round(pct, 2),
                "purchase_date": row["purchaseDate"],
            })
        return jsonify(positions)
    except Exception as exc:
        return err(str(exc), 500)


@app.route("/api/orders", methods=["GET"])
@login_required
def get_orders(user):
    try:
        return jsonify(db.get_user_orders(user["id"]))
    except Exception as exc:
        return err(str(exc), 500)


@app.route("/api/quote/<symbol>", methods=["GET"])
def get_quote(symbol):
    try:
        symbol = normalize_symbol(symbol)
        return jsonify({"symbol": symbol, "price": trading.get_latest_price(symbol)})
    except ValidationError as exc:
        return err(str(exc))
    except Exception as exc:
        return err(str(exc), 500)


@app.route("/api/chart", methods=["GET"])
@login_required
def get_portfolio_chart(user):
    try:
        holdings = db.get_user_positions(user["id"])
        days = parse_positive_int(request.args.get("days", 20), "days")
        return jsonify(trading.get_portfolio_vs_spy(holdings, days=days))
    except ValidationError as exc:
        return err(str(exc))
    except Exception as exc:
        return err(str(exc), 500)


@app.route("/api/chart/<symbol>", methods=["GET"])
def get_symbol_chart(symbol):
    try:
        symbol = normalize_symbol(symbol)
        days = parse_positive_int(request.args.get("days", 30), "days")
        return jsonify(trading.get_price_history(symbol, days=days))
    except ValidationError as exc:
        return err(str(exc))
    except Exception as exc:
        traceback.print_exc()
        return err(str(exc), 500)


def _execute_trade(user_id: int, symbol: str, quantity: int, trade_type: str):
    price = trading.get_latest_price(symbol)
    if price <= 0:
        raise ValueError(f"Invalid price ${price} for {symbol}. Cannot place order.")
    with _get_user_lock(user_id):
        return db.execute_simulated_market_order(user_id, symbol, quantity, trade_type, price)


@app.route("/api/buy", methods=["POST"])
@login_required
def buy(user):
    try:
        body = get_json_body()
        symbol = normalize_symbol(body.get("symbol"))
        quantity = parse_positive_int(body.get("quantity"), "quantity")
        result = _execute_trade(user["id"], symbol, quantity, "buy")
        return jsonify({
            "success": True,
            "order_id": result["order"]["id"],
            "symbol": symbol,
            "quantity": quantity,
            "filled_price": result["order"]["price"],
            "cash": result["cash"],
            "message": f"Bought {quantity}x {symbol} @ ${result['order']['price']:.2f}",
        })
    except ValidationError as exc:
        return err(str(exc))
    except ValueError as exc:
        return err(str(exc))
    except db.TradeConcurrencyError as exc:
        return err(str(exc), 409)
    except Exception as exc:
        traceback.print_exc()
        return err(str(exc), 500)


@app.route("/api/sell", methods=["POST"])
@login_required
def sell(user):
    try:
        body = get_json_body()
        symbol = normalize_symbol(body.get("symbol"))
        quantity = parse_positive_int(body.get("quantity"), "quantity")
        result = _execute_trade(user["id"], symbol, quantity, "sell")
        return jsonify({
            "success": True,
            "order_id": result["order"]["id"],
            "symbol": symbol,
            "quantity": quantity,
            "filled_price": result["order"]["price"],
            "cash": result["cash"],
            "message": f"Sold {quantity}x {symbol} @ ${result['order']['price']:.2f}",
        })
    except ValidationError as exc:
        return err(str(exc))
    except ValueError as exc:
        return err(str(exc))
    except db.TradeConcurrencyError as exc:
        return err(str(exc), 409)
    except Exception as exc:
        traceback.print_exc()
        return err(str(exc), 500)


@app.route("/api/sync", methods=["POST"])
@login_required
def sync_order(_user):
    return jsonify({
        "settled": True,
        "status": "filled",
        "message": "Orders are filled immediately in simulator mode.",
    })


@app.route("/api/watchlist", methods=["GET"])
@login_required
def get_watchlist(user):
    try:
        entries = db.get_user_watchlist(user["id"])
        prices = trading.get_latest_prices([e["symbol"] for e in entries]) if entries else {}
        for entry in entries:
            entry["current_price"] = prices.get(entry["symbol"])
            if entry["target_price"] and entry["current_price"]:
                entry["target_distance_pct"] = round(
                    (entry["current_price"] - entry["target_price"]) / entry["target_price"] * 100,
                    2,
                )
            else:
                entry["target_distance_pct"] = None
        return jsonify(entries)
    except Exception as exc:
        traceback.print_exc()
        return err(str(exc), 500)


@app.route("/api/watchlist", methods=["POST"])
@login_required
def add_watchlist(user):
    try:
        body = get_json_body()
        symbol = normalize_symbol(body.get("symbol"))
        target_price = parse_optional_float(body.get("target_price"), "target_price")
        target_direction = parse_enum(body.get("target_direction"), {"above", "below"}, "target_direction")
        notes = validate_notes(body.get("notes", ""))
        if (target_price is None) != (target_direction is None):
            return err("target_price and target_direction must both be set, or both omitted")
        if target_price is not None and target_price <= 0:
            return err("target_price must be greater than 0")
        current_price = trading.get_latest_price(symbol)
        entry = db.add_user_watchlist(
            user["id"],
            symbol=symbol,
            target_price=target_price,
            target_direction=target_direction,
            notes=notes,
        )
        entry["current_price"] = current_price
        return jsonify({"success": True, "entry": entry})
    except ValidationError as exc:
        return err(str(exc))
    except Exception as exc:
        traceback.print_exc()
        return err(str(exc), 500)


@app.route("/api/watchlist/<symbol>", methods=["DELETE"])
@login_required
def remove_watchlist(user, symbol):
    try:
        symbol = normalize_symbol(symbol)
        removed = db.remove_user_watchlist(user["id"], symbol)
        if not removed:
            return err(f"{symbol} not in watchlist", 404)
        return jsonify({"success": True})
    except ValidationError as exc:
        return err(str(exc))
    except Exception as exc:
        return err(str(exc), 500)


@app.route("/api/watchlist/<symbol>", methods=["PATCH"])
@login_required
def update_watchlist(user, symbol):
    try:
        symbol = normalize_symbol(symbol)
        body = get_json_body()
        target_price = parse_optional_float(body.get("target_price"), "target_price")
        target_direction = parse_enum(body.get("target_direction"), {"above", "below"}, "target_direction")
        notes = validate_notes(body.get("notes"))
        if (target_price is None) != (target_direction is None):
            return err("target_price and target_direction must both be set, or both omitted")
        if target_price is not None and target_price <= 0:
            return err("target_price must be greater than 0")
        entry = db.update_user_watchlist_entry(
            user["id"],
            symbol=symbol,
            target_price=target_price,
            target_direction=target_direction,
            notes=notes,
        )
        if not entry:
            return err(f"{symbol} not in watchlist", 404)
        return jsonify({"success": True, "entry": entry})
    except ValidationError as exc:
        return err(str(exc))
    except Exception as exc:
        traceback.print_exc()
        return err(str(exc), 500)


@app.route("/api/watchlist/alerts", methods=["GET"])
@login_required
def get_alerts(user):
    try:
        return jsonify(db.get_user_unread_alerts(user["id"]))
    except Exception as exc:
        return err(str(exc), 500)


@app.route("/api/watchlist/<symbol>/dismiss", methods=["POST"])
@login_required
def dismiss_alert(user, symbol):
    try:
        db.dismiss_user_watchlist_alert(user["id"], normalize_symbol(symbol))
        return jsonify({"success": True})
    except ValidationError as exc:
        return err(str(exc))
    except Exception as exc:
        return err(str(exc), 500)


@app.route("/api/symbols", methods=["GET"])
@login_required
def get_symbols(user):
    try:
        return jsonify(db.get_user_symbols(user["id"]))
    except Exception as exc:
        return err(str(exc), 500)


@app.route("/api/filter/orders", methods=["GET"])
@login_required
def filter_orders(user):
    try:
        symbols = parse_symbol_list(request.args.get("symbols", ""))
        trade_type = parse_enum(request.args.get("trade_type"), {"buy", "sell"}, "trade_type")
        status = parse_enum(request.args.get("status"), {"filled", "canceled"}, "status")
        date_from = parse_date_string(request.args.get("date_from"), "date_from")
        date_to = parse_date_string(request.args.get("date_to"), "date_to")
        price_min = parse_optional_float(request.args.get("price_min"), "price_min")
        price_max = parse_optional_float(request.args.get("price_max"), "price_max")
        if date_from and date_to and date_from > date_to:
            return err("date_from must be on or before date_to")
        if price_min is not None and price_max is not None and price_min > price_max:
            return err("price_min must be less than or equal to price_max")
        orders = db.filter_user_orders(
            user["id"],
            symbols=symbols,
            trade_type=trade_type,
            status=status,
            date_from=date_from,
            date_to=date_to,
            price_min=price_min,
            price_max=price_max,
        )
        return jsonify({
            "results": orders,
            "count": len(orders),
            "filters": {
                "symbols": symbols,
                "trade_type": trade_type,
                "status": status,
                "date_from": date_from,
                "date_to": date_to,
                "price_min": price_min,
                "price_max": price_max,
            },
        })
    except ValidationError as exc:
        return err(str(exc))
    except Exception as exc:
        traceback.print_exc()
        return err(str(exc), 500)


@app.route("/api/filter/portfolio", methods=["GET"])
@login_required
def filter_portfolio(user):
    try:
        symbols = parse_symbol_list(request.args.get("symbols", ""))
        pl_min = parse_optional_float(request.args.get("pl_min"), "pl_min")
        pl_max = parse_optional_float(request.args.get("pl_max"), "pl_max")
        val_min = parse_optional_float(request.args.get("val_min"), "val_min")
        val_max = parse_optional_float(request.args.get("val_max"), "val_max")
        if pl_min is not None and pl_max is not None and pl_min > pl_max:
            return err("pl_min must be less than or equal to pl_max")
        if val_min is not None and val_max is not None and val_min > val_max:
            return err("val_min must be less than or equal to val_max")
        all_positions = db.get_user_positions(user["id"])
        all_symbols = [row["symbol"] for row in all_positions]
        prices = trading.get_latest_prices(all_symbols) if all_symbols else {}
        positions = db.filter_user_portfolio(
            user["id"],
            symbols=symbols,
            pl_min=pl_min,
            pl_max=pl_max,
            val_min=val_min,
            val_max=val_max,
            prices=prices,
        )
        return jsonify({
            "results": positions,
            "count": len(positions),
            "filters": {
                "symbols": symbols,
                "pl_min": pl_min,
                "pl_max": pl_max,
                "val_min": val_min,
                "val_max": val_max,
            },
        })
    except ValidationError as exc:
        return err(str(exc))
    except Exception as exc:
        traceback.print_exc()
        return err(str(exc), 500)


@app.route("/api/report/snapshot", methods=["GET"])
@login_required
def portfolio_snapshot(user):
    try:
        snapshot = db.get_user_portfolio_snapshot(user["id"])
        prices = trading.get_latest_prices([row["symbol"] for row in snapshot]) if snapshot else {}
        for row in snapshot:
            row["current_price"] = prices.get(row["symbol"], 0.0)
            row["market_value"] = round(row["current_price"] * row["quantity"], 2)
            row["pl_pct"] = round(
                (row["current_price"] - row["avg_price"]) / row["avg_price"] * 100,
                2,
            ) if row["avg_price"] else 0
        return jsonify({
            "snapshot": snapshot,
            "taken_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total_value": round(sum(row["market_value"] for row in snapshot), 2),
        })
    except Exception as exc:
        traceback.print_exc()
        return err(str(exc), 500)


if __name__ == "__main__":
    host = os.getenv("APP_HOST", "127.0.0.1")
    port = int(os.getenv("APP_PORT", "5000"))
    debug = os.getenv("APP_DEBUG", "true").lower() in {"1", "true", "yes", "on"}
    app.run(host=host, port=port, debug=debug, threaded=True, use_reloader=False)

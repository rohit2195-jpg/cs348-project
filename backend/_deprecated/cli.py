"""
cli.py — Live auto-refreshing terminal dashboard
Uses curses for in-place rendering. Refreshes every 15s automatically.

Layout:
┌─────────────────────────────────────────────────────────┐
│  HEADER: account summary + market status                │
├──────────────────────┬──────────────────────────────────┤
│  PORTFOLIO           │  SPARKLINE CHARTS                │
│  (live P/L)          │  stock vs SPY                    │
├──────────────────────┴──────────────────────────────────┤
│  RECENT ORDERS                                          │
├─────────────────────────────────────────────────────────┤
│  INPUT BAR  (buy / sell / quote / refresh / quit)       │
└─────────────────────────────────────────────────────────┘

Controls:
  b  → buy stock
  s  → sell stock
  q  → quote a symbol
  r  → force refresh
  ESC/x → quit
"""

import curses
import time
import threading
from datetime import datetime

import database as db
import trading

REFRESH_INTERVAL = 15  # seconds between auto-refresh

# ── Shared state (updated by background thread) ───────────────────────────────
state = {
    "account": None,
    "positions": [],          # list of dicts with live price injected
    "orders": [],
    "chart_data": None,       # result of get_portfolio_vs_spy
    "market_open": False,
    "last_update": None,
    "error": None,
    "loading": True,
}
state_lock = threading.Lock()


def fetch_all():
    """Background fetch — updates shared state atomically."""
    try:
        acct = trading.get_account()
        portfolio_rows = db.get_portfolio()
        symbols = [r.symbol for r in portfolio_rows]
        prices = trading.get_latest_prices(symbols) if symbols else {}

        positions = []
        for r in portfolio_rows:
            current = prices.get(r.symbol, 0.0)
            pl = (current - r.purchasePrice) * r.quantity
            pct = ((current - r.purchasePrice) / r.purchasePrice * 100) if r.purchasePrice else 0
            positions.append({
                "symbol": r.symbol,
                "qty": r.quantity,
                "avg": r.purchasePrice,
                "current": current,
                "pl": pl,
                "pct": pct,
                "value": current * r.quantity,
            })

        orders = db.get_all_orders()[:10]  # last 10

        chart_data = None
        if symbols:
            holdings = db.get_portfolio_for_chart()
            chart_data = trading.get_portfolio_vs_spy(holdings, days=20)

        market_open = trading.is_market_open()

        with state_lock:
            state["account"] = acct
            state["positions"] = positions
            state["orders"] = orders
            state["chart_data"] = chart_data
            state["market_open"] = market_open
            state["last_update"] = datetime.now().strftime("%H:%M:%S")
            state["error"] = None
            state["loading"] = False

    except Exception as e:
        with state_lock:
            state["error"] = str(e)
            state["loading"] = False


def background_refresh():
    while True:
        fetch_all()
        time.sleep(REFRESH_INTERVAL)


# ── Sparkline renderer ────────────────────────────────────────────────────────

def sparkline(values: list, width: int) -> str:
    """Render a list of floats as a unicode sparkline of given width."""
    BLOCKS = "▁▂▃▄▅▆▇█"
    if not values or width < 2:
        return " " * width
    # downsample or upsample to width
    if len(values) > width:
        step = len(values) / width
        values = [values[int(i * step)] for i in range(width)]
    mn, mx = min(values), max(values)
    span = mx - mn or 1
    chars = [BLOCKS[min(int((v - mn) / span * (len(BLOCKS) - 1)), len(BLOCKS) - 1)] for v in values]
    return "".join(chars)


def chart_lines(series_a: list, series_b: list, label_a: str, label_b: str,
                width: int, height: int) -> list:
    """
    Render two series as stacked sparklines with labels.
    Returns list of strings (one per line).
    """
    lines = []
    spark_w = width - len(label_a) - 3
    if series_a:
        vals_a = [d["value"] for d in series_a]
        lines.append(f"{label_a}: {sparkline(vals_a, spark_w)}")
    if series_b:
        vals_b = [d["value"] for d in series_b]
        lines.append(f"{label_b}: {sparkline(vals_b, spark_w)}")
    return lines


# ── Panel drawing helpers ─────────────────────────────────────────────────────

def safe_addstr(win, y, x, text, attr=0):
    try:
        win.addstr(y, x, text, attr)
    except curses.error:
        pass


def draw_box_title(win, title: str):
    win.box()
    h, w = win.getmaxyx()
    safe_addstr(win, 0, 2, f" {title} ", curses.A_BOLD)


def draw_header(win, s: dict):
    win.erase()
    draw_box_title(win, "ACCOUNT")
    h, w = win.getmaxyx()
    acct = s["account"]
    market_str = "● OPEN" if s["market_open"] else "● CLOSED"
    market_attr = curses.color_pair(2) if s["market_open"] else curses.color_pair(3)

    if acct:
        bp = float(acct.buying_power)
        eq = float(acct.equity)
        pv = float(acct.portfolio_value)
        cash = float(acct.cash)
        row = (f"  Equity: ${eq:>12,.2f}   Portfolio: ${pv:>12,.2f}"
               f"   Buying Power: ${bp:>12,.2f}   Cash: ${cash:>10,.2f}")
        safe_addstr(win, 1, 0, row[:w - 1])

    upd = f" Updated: {s['last_update']} " if s["last_update"] else ""
    safe_addstr(win, 1, w - len(market_str) - len(upd) - 3, upd, curses.color_pair(6))
    safe_addstr(win, 1, w - len(market_str) - 2, market_str, market_attr | curses.A_BOLD)
    win.noutrefresh()


def draw_portfolio(win, positions: list):
    win.erase()
    draw_box_title(win, "PORTFOLIO")
    h, w = win.getmaxyx()

    headers = f"  {'SYM':<6} {'QTY':>5} {'AVG':>8} {'PRICE':>8} {'VALUE':>10} {'P/L':>10} {'%':>7}"
    safe_addstr(win, 1, 0, headers[:w - 1], curses.A_BOLD | curses.color_pair(6))

    for i, p in enumerate(positions):
        if i + 2 >= h - 1:
            break
        color = curses.color_pair(2) if p["pl"] >= 0 else curses.color_pair(3)
        pl_str = f"+${p['pl']:,.2f}" if p["pl"] >= 0 else f"-${abs(p['pl']):,.2f}"
        pct_str = f"{p['pct']:+.1f}%"
        row = (f"  {p['symbol']:<6} {p['qty']:>5} "
               f"${p['avg']:>7.2f} ${p['current']:>7.2f} "
               f"${p['value']:>9,.2f} {pl_str:>10} {pct_str:>7}")
        safe_addstr(win, i + 2, 0, row[:w - 1], color)

    if not positions:
        safe_addstr(win, 2, 2, "No positions.", curses.color_pair(6))
    win.noutrefresh()


def draw_charts(win, chart_data):
    win.erase()
    draw_box_title(win, "CHARTS  (20d)")
    h, w = win.getmaxyx()

    if not chart_data or not chart_data.get("portfolio"):
        safe_addstr(win, 2, 2, "No chart data yet.", curses.color_pair(6))
        win.noutrefresh()
        return

    chart_w = w - 6
    lines = chart_lines(
        chart_data["portfolio"], chart_data["spy"],
        "Portfolio", "SPY     ",
        chart_w, h,
    )
    for i, line in enumerate(lines[:h - 3]):
        color = curses.color_pair(4) if i == 0 else curses.color_pair(5)
        safe_addstr(win, i + 2, 2, line[:w - 4], color | curses.A_BOLD)

    # per-stock sparklines
    row = len(lines) + 3
    for sym, data in (chart_data.get("stocks") or {}).items():
        if row >= h - 1:
            break
        if data:
            vals = [d["close"] for d in data]
            spark = sparkline(vals, chart_w - len(sym) - 3)
            first, last = vals[0], vals[-1]
            color = curses.color_pair(2) if last >= first else curses.color_pair(3)
            safe_addstr(win, row, 2, f"{sym}: {spark}"[:w - 4], color)
            row += 1

    win.noutrefresh()


def draw_orders(win, orders: list):
    win.erase()
    draw_box_title(win, "RECENT ORDERS")
    h, w = win.getmaxyx()

    headers = f"  {'ID':>4} {'SYM':<6} {'TYPE':<5} {'QTY':>5} {'PRICE':>8} {'STATUS':<9} TIME"
    safe_addstr(win, 1, 0, headers[:w - 1], curses.A_BOLD | curses.color_pair(6))

    for i, o in enumerate(orders):
        if i + 2 >= h - 1:
            break
        type_color = curses.color_pair(2) if o["trade_type"] == "buy" else curses.color_pair(3)
        status_color = (curses.color_pair(2) if o["status"] == "filled"
                        else curses.color_pair(5) if o["status"] == "pending"
                        else curses.color_pair(6))
        row = (f"  {o['id']:>4} {o['symbol']:<6} {o['trade_type'].upper():<5} "
               f"{o['quantity']:>5} ${o['price']:>7.2f} {o['status']:<9} {o['timestamp']}")
        safe_addstr(win, i + 2, 0, row[:w - 1], type_color)

    if not orders:
        safe_addstr(win, 2, 2, "No orders yet.", curses.color_pair(6))
    win.noutrefresh()


def draw_status_bar(win, msg: str = "", error: str = ""):
    win.erase()
    h, w = win.getmaxyx()
    controls = "  [b]uy  [s]ell  [q]uote  [r]efresh  [x]quit"
    safe_addstr(win, 0, 0, controls, curses.A_BOLD)
    if error:
        safe_addstr(win, 0, len(controls) + 2, f"ERR: {error}"[:w - len(controls) - 4], curses.color_pair(3))
    elif msg:
        safe_addstr(win, 0, len(controls) + 2, msg[:w - len(controls) - 4], curses.color_pair(2))
    win.noutrefresh()


# ── Input prompts (drawn in-place at bottom) ─────────────────────────────────

def prompt_string(stdscr, prompt: str) -> str:
    """Read a string from the user in the status bar area."""
    h, w = stdscr.getmaxyx()
    curses.echo()
    curses.curs_set(1)
    stdscr.addstr(h - 1, 0, " " * (w - 1))
    stdscr.addstr(h - 1, 0, prompt)
    stdscr.refresh()
    try:
        val = stdscr.getstr(h - 1, len(prompt), 20).decode("utf-8").strip()
    except Exception:
        val = ""
    curses.noecho()
    curses.curs_set(0)
    return val


def do_buy(stdscr, status_win) -> str:
    symbol = prompt_string(stdscr, "Buy symbol: ").upper()
    if not symbol:
        return "Canceled."
    qty_str = prompt_string(stdscr, f"Quantity of {symbol}: ")
    try:
        qty = int(qty_str)
        assert qty > 0
    except Exception:
        return "Invalid quantity."

    try:
        price = trading.get_latest_price(symbol)
    except Exception:
        price = 0.0

    confirm = prompt_string(stdscr, f"Buy {qty}x {symbol} @ ~${price:.2f}? [y/n]: ")
    if confirm.lower() != "y":
        return "Order canceled."

    order_id = db.create_order(symbol, price, qty, "buy")
    try:
        alpaca_order = trading.buy_stock(symbol, qty)
        filled_price = float(alpaca_order.filled_avg_price or price)
        db.fill_order(order_id)
        pos = db.get_position(symbol)
        today = datetime.now().strftime("%Y-%m-%d")
        if pos:
            new_qty = pos["quantity"] + qty
            avg = ((pos["purchasePrice"] * pos["quantity"]) + (filled_price * qty)) / new_qty
            db.upsert_position(symbol, round(avg, 4), new_qty, today)
        else:
            db.upsert_position(symbol, filled_price, qty, today)
        return f"✓ Bought {qty}x {symbol}"
    except Exception as e:
        db.cancel_order_db(order_id)
        return f"✗ Order failed: {e}"


def do_sell(stdscr, status_win) -> str:
    symbol = prompt_string(stdscr, "Sell symbol: ").upper()
    if not symbol:
        return "Canceled."
    pos = db.get_position(symbol)
    if not pos:
        return f"No position in {symbol}."
    qty_str = prompt_string(stdscr, f"Sell qty (hold {pos['quantity']}): ")
    try:
        qty = int(qty_str)
        assert 0 < qty <= pos["quantity"]
    except Exception:
        return f"Invalid qty. Max {pos['quantity']}."

    try:
        price = trading.get_latest_price(symbol)
    except Exception:
        price = 0.0

    confirm = prompt_string(stdscr, f"Sell {qty}x {symbol} @ ~${price:.2f}? [y/n]: ")
    if confirm.lower() != "y":
        return "Order canceled."

    order_id = db.create_order(symbol, price, qty, "sell")
    try:
        trading.sell_stock(symbol, qty)
        db.fill_order(order_id)
        new_qty = pos["quantity"] - qty
        db.upsert_position(symbol, pos["purchasePrice"], new_qty, pos["purchaseDate"])
        return f"✓ Sold {qty}x {symbol}"
    except Exception as e:
        db.cancel_order_db(order_id)
        return f"✗ Order failed: {e}"


def do_quote(stdscr) -> str:
    symbol = prompt_string(stdscr, "Quote symbol: ").upper()
    if not symbol:
        return ""
    try:
        price = trading.get_latest_price(symbol)
        return f"{symbol}: ${price:.2f}"
    except Exception as e:
        return f"Quote error: {e}"


# ── Main dashboard loop ───────────────────────────────────────────────────────

def dashboard(stdscr):
    curses.curs_set(0)
    curses.noecho()
    stdscr.nodelay(True)  # non-blocking getch
    stdscr.keypad(True)

    # Color pairs
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_WHITE, -1)
    curses.init_pair(2, curses.COLOR_GREEN, -1)   # profit / buy
    curses.init_pair(3, curses.COLOR_RED, -1)     # loss / sell
    curses.init_pair(4, curses.COLOR_CYAN, -1)    # portfolio line
    curses.init_pair(5, curses.COLOR_YELLOW, -1)  # SPY / pending
    curses.init_pair(6, curses.COLOR_WHITE, -1)   # dim

    # Start background refresh thread
    t = threading.Thread(target=background_refresh, daemon=True)
    t.start()

    status_msg = ""
    last_draw = 0

    while True:
        h, w = stdscr.getmaxyx()

        # Layout heights
        HDR_H = 3
        ORDERS_H = 7
        STATUS_H = 1
        MID_H = h - HDR_H - ORDERS_H - STATUS_H - 2
        PORTFOLIO_W = w // 2
        CHART_W = w - PORTFOLIO_W

        # Create sub-windows
        hdr_win      = stdscr.subwin(HDR_H,       w,            0,            0)
        port_win     = stdscr.subwin(MID_H,        PORTFOLIO_W,  HDR_H,        0)
        chart_win    = stdscr.subwin(MID_H,        CHART_W,      HDR_H,        PORTFOLIO_W)
        orders_win   = stdscr.subwin(ORDERS_H,     w,            HDR_H + MID_H, 0)
        status_win   = stdscr.subwin(STATUS_H,     w,            h - 1,        0)

        now = time.time()
        if now - last_draw > 0.5:  # redraw at most 2x/sec
            with state_lock:
                s = dict(state)

            if s["loading"]:
                stdscr.erase()
                safe_addstr(stdscr, h // 2, w // 2 - 10, "Loading data...", curses.color_pair(5))
                stdscr.noutrefresh()
            else:
                draw_header(hdr_win, s)
                draw_portfolio(port_win, s["positions"])
                draw_charts(chart_win, s["chart_data"])
                draw_orders(orders_win, s["orders"])
                draw_status_bar(status_win, status_msg, s.get("error", ""))

            curses.doupdate()
            last_draw = now

        # Handle input (non-blocking)
        try:
            key = stdscr.getch()
        except Exception:
            key = -1

        if key == ord("x") or key == 27:  # ESC or x
            break
        elif key == ord("r"):
            status_msg = "Refreshing..."
            threading.Thread(target=fetch_all, daemon=True).start()
        elif key == ord("b"):
            status_msg = do_buy(stdscr, status_win)
            threading.Thread(target=fetch_all, daemon=True).start()
        elif key == ord("s"):
            status_msg = do_sell(stdscr, status_win)
            threading.Thread(target=fetch_all, daemon=True).start()
        elif key == ord("q"):
            status_msg = do_quote(stdscr)

        time.sleep(0.05)


def main():
    db.init_db()
    curses.wrapper(dashboard)


if __name__ == "__main__":
    main()
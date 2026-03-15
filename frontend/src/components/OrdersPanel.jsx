// OrdersPanel.jsx — Right panel: order history
import { fmt } from './helpers';

function OrdersPanel({ orders, loading }) {
  return (
    <div className="panel">
      <div className="panel-title">▸ ORDER HISTORY</div>
      <div className="panel-scroll">
        {loading && <div className="loading" style={{ fontSize: 14 }}>LOADING<span className="blink">_</span></div>}
        {!loading && orders.length === 0 && <div className="empty">// NO ORDERS</div>}
        {!loading && orders.length > 0 && (
          <>
            <div className="order-row hdr">
              <span>ID</span><span>SYM</span><span>TYPE</span>
              <span>QTY</span><span>PRICE</span><span>STATUS</span><span>TIME</span>
            </div>
            {orders.slice(0, 30).map((o) => (
              <div className="order-row" key={o.id}>
                <span className="neutral">#{o.id}</span>
                <span className="sym" style={{ fontSize: 12 }}>{o.symbol}</span>
                <span><span className={`badge ${o.trade_type}`}>{o.trade_type.toUpperCase()}</span></span>
                <span>{o.quantity}</span>
                <span>${fmt(o.price)}</span>
                <span className={`badge ${o.status}`}>{o.status}</span>
                <span className="neutral" style={{ fontSize: 11 }}>{o.timestamp.slice(11)}</span>
              </div>
            ))}
          </>
        )}
      </div>
    </div>
  );
}

export default OrdersPanel;
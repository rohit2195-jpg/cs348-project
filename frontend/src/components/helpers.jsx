// helpers.jsx — Shared formatting utilities
import { Fragment } from 'react';

export const fmt   = (n) => n?.toFixed(2) ?? "—";
export const fmtK  = (n) => n != null
  ? `$${n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
  : "—";
export const sign  = (n) => n >= 0 ? "+" : "";

export const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="custom-tooltip">
      <div style={{ color: "var(--text-dim)", fontSize: 10, marginBottom: 4 }}>{label}</div>
      {payload.map((p) => (
        <div key={p.dataKey} style={{ color: p.color }}>
          {p.name}: {p.value != null ? `$${p.value.toLocaleString()}` : "—"}
        </div>
      ))}
    </div>
  );
};
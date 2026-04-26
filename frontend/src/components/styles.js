// styles.js — All dashboard CSS.
// Uses CSS variables injected by ThemeProvider in Settings.jsx.

export const styles = `
  @import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=VT323&display=swap');

  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  html, body, #root {
    height: 100%; width: 100%;
    background: var(--bg); color: var(--text);
    font-family: 'Share Tech Mono', monospace;
    font-size: 13px;
    overflow: hidden;
  }

  body::before {
    content: ''; position: fixed; inset: 0;
    background: repeating-linear-gradient(0deg, transparent, transparent 2px,
      var(--scanline, rgba(0,0,0,0.15)) 2px, var(--scanline, rgba(0,0,0,0.15)) 4px);
    pointer-events: none; z-index: 9999;
  }
  body::after {
    content: ''; position: fixed; inset: 0;
    background: radial-gradient(ellipse at center, transparent 60%, var(--vignette, rgba(0,0,0,0.7)) 100%);
    pointer-events: none; z-index: 9998;
  }
  html.light-theme body::before, html.light-theme body::after { display: none; }
  html.light-theme .header-title { text-shadow: none; letter-spacing: 2px; }
  html.light-theme .market-badge { animation: none; }
  html.light-theme .blink { animation: none; opacity: 1; }

  .app {
    height: 100dvh; display: grid;
    grid-template-rows: 52px minmax(0, 1fr) minmax(200px, 24vh);
    grid-template-columns: 1fr 1fr;
    gap: 1px; background: var(--border); padding: 1px;
    overflow: hidden;
  }

  .header {
    grid-column: 1 / -1; background: var(--bg);
    display: flex; align-items: center; gap: 28px;
    padding: 0 16px; border-bottom: 1px solid var(--border);
    min-width: 0;
  }
  .header-main,
  .header-stats,
  .header-actions {
    display: flex;
    align-items: center;
    min-width: 0;
  }
  .header-main { gap: 12px; flex: 0 1 auto; }
  .header-stats { gap: 28px; flex: 1 1 auto; }
  .header-actions { gap: 8px; margin-left: auto; flex: 0 0 auto; }
  .header-title {
    font-family: 'VT323', monospace; font-size: 28px; letter-spacing: 3px;
    color: var(--accent); text-shadow: var(--title-shadow); flex-shrink: 0;
  }
  .header-stat { display: flex; flex-direction: column; gap: 1px; }
  .header-stat-label { color: var(--text-dim); font-size: 10px; letter-spacing: 1px; text-transform: uppercase; }
  .header-stat-value { font-size: 15px; font-weight: bold; color: var(--text); }
  .market-badge { font-size: 11px; letter-spacing: 2px; padding: 3px 10px; border: 1px solid; animation: pulse 2s infinite; }
  .market-badge.open   { color: var(--profit); border-color: var(--profit); }
  .market-badge.closed { color: var(--loss); border-color: var(--loss); animation: none; }
  @keyframes pulse { 0%,100%{ opacity:1 } 50%{ opacity:0.4 } }
  .last-update { font-size: 10px; color: var(--text-dim); margin-left: 4px; }

  .panel { background: var(--bg); overflow: hidden; display: flex; flex-direction: column; min-width: 0; min-height: 0; }
  .panel-title {
    font-family: 'VT323', monospace; font-size: 18px; letter-spacing: 2px;
    color: var(--accent2); padding: 6px 12px;
    border-bottom: 1px solid var(--border); background: var(--panel); flex-shrink: 0;
  }
  .panel-scroll { overflow-y: auto; flex: 1; min-height: 0; padding: 8px 0; }
  .panel-table-scroll,
  .order-table-scroll,
  .report-table-scroll,
  .watchlist-table-scroll {
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
  }
  .panel-table-scroll .tbl,
  .report-table-scroll .rp-table,
  .watchlist-table-scroll .wl-table {
    min-width: 640px;
  }
  .order-table-scroll .order-table {
    min-width: 420px;
  }
  .panel-scroll::-webkit-scrollbar { width: 4px; }
  .panel-scroll::-webkit-scrollbar-thumb { background: var(--dim); }

  .tbl { width: 100%; border-collapse: collapse; }
  .tbl th { font-size: 10px; letter-spacing: 1px; color: var(--text-dim); text-align: right; padding: 3px 12px; border-bottom: 1px solid var(--dim); text-transform: uppercase; }
  .tbl th:first-child { text-align: left; }
  .tbl td { padding: 5px 12px; text-align: right; border-bottom: 1px solid var(--panel); font-variant-numeric: tabular-nums; transition: background 0.15s; }
  .tbl td:first-child { text-align: left; }
  .tbl tr:hover td { background: var(--panel); }

  .sym     { color: var(--accent); font-weight: bold; font-size: 14px; }
  .profit  { color: var(--profit); }
  .loss    { color: var(--loss); }
  .neutral { color: var(--text-dim); }

  .order-table { min-width: 0; }
  .order-row { display: grid; grid-template-columns: 36px 52px 44px 44px 72px 68px 1fr; gap: 4px; padding: 4px 12px; border-bottom: 1px solid var(--panel); font-size: 12px; }
  .order-row.hdr { color: var(--text-dim); font-size: 10px; letter-spacing: 1px; text-transform: uppercase; background: var(--panel); }
  .order-row:not(.hdr):hover { background: var(--panel); }

  .badge { padding: 1px 6px; border: 1px solid; font-size: 10px; letter-spacing: 1px; }
  .badge.buy      { color: var(--profit); border-color: var(--accent3); }
  .badge.sell     { color: var(--loss);   border-color: var(--loss); }
  .badge.filled   { color: var(--profit); border-color: transparent; }
  .badge.pending  { color: var(--warn);   border-color: transparent; }
  .badge.canceled { color: var(--text-dim); border-color: transparent; }

  .lower-panel {
    grid-column: 1 / -1;
    display: grid;
    grid-template-rows: minmax(0, 1fr) auto;
    min-width: 0;
    min-height: 0;
    background: var(--border);
    gap: 1px;
  }
  .charts-panel { background: var(--bg); border-top: 1px solid var(--border); display: flex; flex-direction: column; min-width: 0; min-height: 0; }
  .charts-inner { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1px; flex: 1; background: var(--border); min-width: 0; min-height: 0; }
  .chart-block { background: var(--bg); padding: 6px 10px 8px; display: flex; flex-direction: column; min-width: 0; min-height: 0; }
  .chart-label { font-size: 10px; letter-spacing: 2px; color: var(--text-dim); text-transform: uppercase; margin-bottom: 4px; }
  .chart-legend { display: flex; gap: 14px; align-items: center; margin-top: 4px; font-size: 10px; color: var(--text-dim); flex-wrap: wrap; }

  .statusbar {
    background:
      linear-gradient(90deg, var(--panel), transparent 65%),
      var(--bg);
    border-top: 1px solid var(--border);
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px 16px;
    padding: 8px 12px;
    font-size: 12px;
    min-height: 46px;
    min-width: 0;
  }
  .statusbar-left, .statusbar-right {
    display: flex;
    align-items: center;
    gap: 8px;
    min-width: 0;
    flex-wrap: wrap;
  }
  .statusbar-left { flex: 1 1 auto; }
  .statusbar-right { flex: 0 1 auto; justify-content: flex-end; }
  .status-label {
    color: var(--text-dim);
    font-size: 10px;
    letter-spacing: 2px;
    text-transform: uppercase;
    margin-right: 4px;
  }
  .cmd-btn { background: transparent; border: 1px solid var(--accent3); color: var(--accent2); font-family: 'Share Tech Mono', monospace; font-size: 12px; letter-spacing: 1px; padding: 2px 10px; cursor: pointer; transition: all 0.1s; text-transform: uppercase; }
  .cmd-btn { flex: 0 0 auto; white-space: nowrap; }
  .cmd-btn:hover, .cmd-btn.active { background: var(--accent3); color: var(--bg); border-color: var(--accent); }
  .cmd-shortcut { opacity: 0.7; margin-right: 4px; }
  .cmd-btn-watch { position: relative; padding-right: 28px; }
  .watch-alert {
    position: absolute;
    top: -7px;
    right: -7px;
    min-width: 16px;
    height: 16px;
    padding: 0 4px;
    border-radius: 999px;
    background: var(--loss);
    color: #fff;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    font-size: 9px;
    line-height: 1;
  }
  .flash-msg { font-size: 11px; letter-spacing: 1px; color: var(--profit); }
  .flash-msg.err { color: var(--loss); }
  .flash-msg.idle { color: var(--text-dim); opacity: 0.9; }
  .kbd-hint { font-size: 10px; color: var(--text-dim); letter-spacing: 1px; opacity: 0.6; }

  @media (max-width: 1080px) {
    .app {
      grid-template-columns: 1fr;
      grid-template-rows: 52px minmax(0, 1fr) minmax(0, 1fr) minmax(240px, auto);
    }
    .charts-inner { grid-template-columns: 1fr; }
    .statusbar { align-items: flex-start; }
    .statusbar-right { justify-content: flex-start; }
    .kbd-hint { width: 100%; }
  }

  @media (max-width: 768px) {
    html, body, #root {
      min-height: 100%;
      overflow-x: hidden;
      overflow-y: auto;
    }

    .app {
      min-height: 100dvh;
      height: auto;
      grid-template-rows: auto minmax(0, auto) minmax(0, auto) auto;
    }

    .panel-portfolio,
    .panel-orders {
      min-height: 0;
      max-height: clamp(180px, 24dvh, 220px);
    }
    .panel-portfolio .panel-scroll,
    .panel-orders .panel-scroll {
      min-height: 0;
      overflow-y: auto;
      -webkit-overflow-scrolling: touch;
    }
    .panel-portfolio .panel-table-scroll,
    .panel-orders .order-table-scroll {
      min-height: 0;
    }

    .header {
      align-items: stretch;
      flex-wrap: wrap;
      gap: 10px 12px;
      padding: 10px 12px;
    }
    .header-main,
    .header-actions {
      width: 100%;
      justify-content: space-between;
    }
    .header-main {
      align-items: flex-start;
      gap: 10px;
    }
    .header-stats {
      width: 100%;
      gap: 10px;
      flex-wrap: wrap;
      overflow-x: auto;
      padding-bottom: 2px;
    }
    .header-stat {
      min-width: 108px;
      padding: 6px 8px;
      border: 1px solid var(--border);
      background: var(--panel);
      flex: 0 0 auto;
    }
    .header-title {
      font-size: 24px;
      letter-spacing: 2px;
    }
    .market-badge {
      margin-left: 0;
      white-space: nowrap;
    }
    .last-update {
      margin-left: 0;
      align-self: center;
    }
    .header-actions {
      justify-content: flex-end;
    }

    .lower-panel {
      grid-template-rows: auto minmax(0, 1fr);
    }
    .statusbar {
      order: -1;
      position: sticky;
      bottom: 0;
      z-index: 4;
      padding: 10px 12px;
      align-items: flex-start;
    }
    .statusbar-left,
    .statusbar-right {
      width: 100%;
    }
    .statusbar-right {
      gap: 6px;
    }
    .status-label,
    .kbd-hint,
    .cmd-shortcut {
      display: none;
    }
    .charts-panel {
      min-height: 0;
    }
    .charts-inner {
      grid-template-columns: 1fr;
    }
    .chart-block {
      padding: 8px 10px;
    }

    .modal-overlay {
      align-items: flex-start;
      padding: 12px;
      overflow-y: auto;
    }
    .modal {
      min-width: 0;
      width: min(100%, 460px);
      margin: auto;
      padding: 18px 16px;
    }
    .modal-actions {
      flex-direction: column-reverse;
    }
    .quote-search-row {
      flex-direction: column;
    }
    .quote-search-row .cmd-btn {
      width: 100%;
      min-height: 44px;
    }
    .btn-confirm,
    .btn-cancel {
      width: 100%;
      min-height: 44px;
    }
  }

  .modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.85); display: flex; align-items: center; justify-content: center; z-index: 1000; }
  .modal { background: var(--bg); border: 1px solid var(--accent2); box-shadow: 0 0 40px rgba(0,0,0,0.5); padding: 24px 28px; min-width: 360px; max-width: 460px; width: 100%; }
  .modal-title { font-family: 'VT323', monospace; font-size: 22px; letter-spacing: 3px; margin-bottom: 20px; color: var(--accent); text-shadow: 0 0 8px var(--accent); }
  .field { margin-bottom: 14px; }
  .field label { display: block; font-size: 10px; letter-spacing: 1px; color: var(--text-dim); text-transform: uppercase; margin-bottom: 4px; }
  .field input { width: 100%; background: transparent; border: 1px solid var(--accent3); color: var(--text); font-family: 'Share Tech Mono', monospace; font-size: 14px; padding: 6px 10px; outline: none; letter-spacing: 1px; text-transform: uppercase; transition: border-color 0.15s; }
  .field input:focus { border-color: var(--accent); box-shadow: 0 0 8px var(--panel); }
  .quote-search-row { display: flex; gap: 8px; }
  .modal-preview { font-size: 12px; color: var(--text-dim); margin-bottom: 16px; letter-spacing: 1px; min-height: 18px; }
  .modal-actions { display: flex; gap: 10px; }
  .modal-error { color: var(--loss); font-size: 11px; margin-top: 8px; letter-spacing: 1px; }
  .btn-confirm { flex: 1; background: var(--dim); border: 1px solid var(--accent); color: var(--accent); font-family: 'Share Tech Mono', monospace; font-size: 13px; letter-spacing: 2px; padding: 8px; cursor: pointer; text-transform: uppercase; transition: all 0.1s; }
  .btn-confirm:hover { background: var(--accent); color: var(--bg); }
  .btn-confirm:disabled { opacity: 0.4; cursor: not-allowed; }
  .btn-cancel { flex: 1; background: transparent; border: 1px solid var(--accent3); color: var(--text-dim); font-family: 'Share Tech Mono', monospace; font-size: 13px; letter-spacing: 2px; padding: 8px; cursor: pointer; text-transform: uppercase; transition: all 0.1s; }
  .btn-cancel:hover { border-color: var(--loss); color: var(--loss); }
  .live-quote { font-family: 'VT323', monospace; font-size: 32px; color: var(--accent); text-shadow: 0 0 12px var(--accent); letter-spacing: 2px; text-align: center; padding: 12px 0; }

  .custom-tooltip { background: var(--bg); border: 1px solid var(--accent3); padding: 6px 10px; font-family: 'Share Tech Mono', monospace; font-size: 11px; color: var(--text); }
  .blink { animation: blink 1s step-start infinite; }
  @keyframes blink { 50% { opacity: 0; } }
  .loading { display: flex; align-items: center; justify-content: center; height: 100%; color: var(--text-dim); letter-spacing: 3px; font-family: 'VT323', monospace; font-size: 20px; }
  .empty { color: var(--text-dim); font-size: 11px; padding: 12px; letter-spacing: 1px; }
`;

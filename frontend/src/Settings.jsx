// Settings.jsx
// Theme context + settings drawer.
// Themes: 3 dark (phosphor) + 3 light (paper, bloomberg, slate)

import { useState, useEffect, createContext, useContext } from "react";

// ── Theme definitions ─────────────────────────────────────────────────────────

export const THEMES = {
  // ── Dark ──────────────────────────────────────────────────────────────────
  green: {
    name: "GREEN PHOSPHOR", key: "green", light: false,
    vars: {
      "--accent":       "#00ff41", "--accent2":  "#00cc33", "--accent3":  "#008f11",
      "--dim":          "#003b00", "--bg":       "#000300",
      "--panel":        "rgba(0,255,65,0.04)", "--border": "rgba(0,255,65,0.2)",
      "--profit":       "#00ff41", "--loss":     "#ff3131", "--warn":     "#ffb000",
      "--text":         "#00ff41", "--text-dim": "#008f11",
      "--scanline":     "rgba(0,0,0,0.15)", "--vignette": "rgba(0,0,0,0.7)",
      "--title-shadow": "0 0 10px #00ff41, 0 0 20px #00cc33",
    },
  },
  white: {
    name: "WHITE PHOSPHOR", key: "white", light: false,
    vars: {
      "--accent":       "#e8e8e8", "--accent2":  "#bbbbbb", "--accent3":  "#666666",
      "--dim":          "#222222", "--bg":       "#0a0a0a",
      "--panel":        "rgba(232,232,232,0.04)", "--border": "rgba(232,232,232,0.18)",
      "--profit":       "#7fff7f", "--loss":     "#ff6b6b", "--warn":     "#ffd080",
      "--text":         "#e8e8e8", "--text-dim": "#555555",
      "--scanline":     "rgba(0,0,0,0.12)", "--vignette": "rgba(0,0,0,0.7)",
      "--title-shadow": "0 0 8px #aaaaaa",
    },
  },
  amber: {
    name: "AMBER PHOSPHOR", key: "amber", light: false,
    vars: {
      "--accent":       "#ffb000", "--accent2":  "#cc8800", "--accent3":  "#7a5000",
      "--dim":          "#2a1a00", "--bg":       "#070400",
      "--panel":        "rgba(255,176,0,0.04)", "--border": "rgba(255,176,0,0.2)",
      "--profit":       "#aaff44", "--loss":     "#ff4444", "--warn":     "#ffffff",
      "--text":         "#ffb000", "--text-dim": "#7a5000",
      "--scanline":     "rgba(0,0,0,0.15)", "--vignette": "rgba(0,0,0,0.7)",
      "--title-shadow": "0 0 10px #ffb000, 0 0 20px #cc8800",
    },
  },

  // ── Light ─────────────────────────────────────────────────────────────────
  light: {
    name: "LIGHT — PAPER", key: "light", light: true,
    vars: {
      "--accent":       "#111111", "--accent2":  "#333333", "--accent3":  "#999999",
      "--dim":          "#dddddd", "--bg":       "#f5f2eb",
      "--panel":        "rgba(0,0,0,0.04)", "--border": "rgba(0,0,0,0.12)",
      "--profit":       "#1a7a1a", "--loss":     "#c0000a", "--warn":     "#8a5f00",
      "--text":         "#111111", "--text-dim": "#777777",
      "--scanline":     "transparent", "--vignette": "transparent",
      "--title-shadow": "none",
    },
  },
  bloomberg: {
    name: "LIGHT — BLOOMBERG", key: "bloomberg", light: true,
    vars: {
      "--accent":       "#f15a22", "--accent2":  "#cc4400", "--accent3":  "#999999",
      "--dim":          "#e8e8e8", "--bg":       "#ffffff",
      "--panel":        "rgba(241,90,34,0.05)", "--border": "rgba(0,0,0,0.1)",
      "--profit":       "#007a00", "--loss":     "#d10000", "--warn":     "#b86e00",
      "--text":         "#1a1a1a", "--text-dim": "#666666",
      "--scanline":     "transparent", "--vignette": "transparent",
      "--title-shadow": "none",
    },
  },
  slate: {
    name: "LIGHT — SLATE", key: "slate", light: true,
    vars: {
      "--accent":       "#2563eb", "--accent2":  "#1d4ed8", "--accent3":  "#94a3b8",
      "--dim":          "#e2e8f0", "--bg":       "#f8fafc",
      "--panel":        "rgba(37,99,235,0.04)", "--border": "rgba(37,99,235,0.15)",
      "--profit":       "#16a34a", "--loss":     "#dc2626", "--warn":     "#d97706",
      "--text":         "#0f172a", "--text-dim": "#64748b",
      "--scanline":     "transparent", "--vignette": "transparent",
      "--title-shadow": "none",
    },
  },
};

const STORAGE_KEY = "terminal_theme";

// ── Context ───────────────────────────────────────────────────────────────────

const ThemeContext = createContext(null);
const DEFAULT_THEME = "light";

export function ThemeProvider({ children }) {
  const [themeKey, setThemeKey] = useState(() => {
    try { return localStorage.getItem(STORAGE_KEY) || DEFAULT_THEME; }
    catch { return DEFAULT_THEME; }
  });

  useEffect(() => {
    const theme = THEMES[themeKey] || THEMES[DEFAULT_THEME];
    const root  = document.documentElement;
    Object.entries(theme.vars).forEach(([k, v]) => root.style.setProperty(k, v));
    // Toggle light-mode class so App.jsx can suppress CRT effects
    root.classList.toggle("light-theme", !!theme.light);
    try { localStorage.setItem(STORAGE_KEY, themeKey); } catch {}
  }, [themeKey]);

  return (
    <ThemeContext.Provider value={{ themeKey, setThemeKey, theme: THEMES[themeKey] }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  return useContext(ThemeContext);
}

// ── Settings Panel ────────────────────────────────────────────────────────────

const panelStyles = `
  .settings-overlay {
    position: fixed; inset: 0;
    background: rgba(0,0,0,0.55);
    z-index: 2000;
    display: flex;
    justify-content: flex-end;
  }

  .settings-drawer {
    width: 340px; height: 100%;
    background: var(--bg);
    border-left: 1px solid var(--border);
    box-shadow: -8px 0 40px rgba(0,0,0,0.4);
    display: flex; flex-direction: column;
    animation: sdIn 0.18s ease-out;
  }
  @keyframes sdIn { from { transform: translateX(100%); } to { transform: translateX(0); } }

  .settings-header {
    display: flex; align-items: center; justify-content: space-between;
    padding: 14px 18px;
    border-bottom: 1px solid var(--border);
    background: var(--panel);
  }

  .settings-title {
    font-family: 'VT323', monospace;
    font-size: 22px; letter-spacing: 3px;
    color: var(--accent);
    text-shadow: var(--title-shadow);
  }

  .settings-close {
    background: transparent;
    border: 1px solid var(--accent3);
    color: var(--accent3);
    font-family: 'Share Tech Mono', monospace;
    font-size: 13px; padding: 3px 10px;
    cursor: pointer; letter-spacing: 1px; transition: all 0.1s;
  }
  .settings-close:hover { border-color: var(--loss); color: var(--loss); }

  .settings-body { flex: 1; overflow-y: auto; padding: 20px 18px; }

  .settings-section-label {
    font-size: 10px; letter-spacing: 2px;
    color: var(--text-dim); text-transform: uppercase;
    margin-bottom: 12px; padding-bottom: 6px;
    border-bottom: 1px solid var(--border);
  }

  .theme-group-label {
    font-size: 9px; letter-spacing: 2px; text-transform: uppercase;
    color: var(--text-dim); opacity: 0.6;
    margin: 16px 0 8px; padding-left: 2px;
  }
  .theme-group-label:first-child { margin-top: 0; }

  .theme-grid { display: flex; flex-direction: column; gap: 8px; margin-bottom: 24px; }

  .theme-card {
    display: flex; align-items: center; gap: 12px;
    padding: 10px 12px;
    border: 1px solid var(--border);
    cursor: pointer; transition: all 0.12s;
    background: transparent; text-align: left; width: 100%;
    font-family: 'Share Tech Mono', monospace;
  }
  .theme-card:hover { border-color: var(--accent2); background: var(--panel); }
  .theme-card.active { border-color: var(--accent); background: var(--panel); }

  .theme-swatch {
    width: 40px; height: 32px;
    border: 1px solid rgba(128,128,128,0.2);
    flex-shrink: 0;
    display: flex; align-items: center; justify-content: center;
    font-size: 14px; font-family: monospace;
  }

  .theme-info { flex: 1; }
  .theme-name {
    font-size: 12px; letter-spacing: 1px;
    color: var(--text); display: block; margin-bottom: 2px;
  }
  .theme-desc { font-size: 10px; color: var(--text-dim); letter-spacing: 0.5px; }

  .theme-check { font-size: 14px; color: var(--accent); opacity: 0; transition: opacity 0.1s; }
  .theme-card.active .theme-check { opacity: 1; }

  .settings-info {
    font-size: 11px; color: var(--text-dim);
    letter-spacing: 0.5px; line-height: 1.7;
    padding: 12px; border: 1px solid var(--border); background: var(--panel);
  }
`;

const THEME_META = {
  green:     { bg: "#000300", fg: "#00ff41", label: "▓▓▓", desc: "Classic CRT green" },
  white:     { bg: "#0a0a0a", fg: "#e8e8e8", label: "▓▓▓", desc: "High-contrast white" },
  amber:     { bg: "#070400", fg: "#ffb000", label: "▓▓▓", desc: "Vintage amber display" },
  light:     { bg: "#f5f2eb", fg: "#111111", label: "▓▓▓", desc: "Warm paper / off-white" },
  bloomberg: { bg: "#ffffff", fg: "#f15a22", label: "▓▓▓", desc: "White + orange accent" },
  slate:     { bg: "#f8fafc", fg: "#2563eb", label: "▓▓▓", desc: "Clean slate + blue" },
};

const DARK_THEMES  = ["green", "white", "amber"];
const LIGHT_THEMES = ["light", "bloomberg", "slate"];

export function SettingsPanel({ onClose }) {
  const { themeKey, setThemeKey } = useTheme();

  const renderCard = (key) => {
    const t    = THEMES[key];
    const meta = THEME_META[key];
    return (
      <button
        key={key}
        className={`theme-card ${themeKey === key ? "active" : ""}`}
        onClick={() => setThemeKey(key)}
      >
        <div className="theme-swatch" style={{ background: meta.bg, color: meta.fg }}>
          {meta.label}
        </div>
        <div className="theme-info">
          <span className="theme-name">{t.name}</span>
          <span className="theme-desc">{meta.desc}</span>
        </div>
        <span className="theme-check">✓</span>
      </button>
    );
  };

  return (
    <>
      <style>{panelStyles}</style>
      <div className="settings-overlay" onClick={(e) => e.target === e.currentTarget && onClose()}>
        <div className="settings-drawer">
          <div className="settings-header">
            <span className="settings-title">SETTINGS<span className="blink">_</span></span>
            <button className="settings-close" onClick={onClose}>[X] CLOSE</button>
          </div>

          <div className="settings-body">
            <div className="settings-section-label">Color Scheme</div>
            <div className="theme-grid">
              <div className="theme-group-label">── Dark</div>
              {DARK_THEMES.map(renderCard)}
              <div className="theme-group-label">── Light</div>
              {LIGHT_THEMES.map(renderCard)}
            </div>

            <div className="settings-section-label">About</div>
            <div className="settings-info">
              Theme preference saved to localStorage — persists across reloads.
              <br /><br />
              Auto-refresh every <strong style={{ color: "var(--accent)" }}>15s</strong>.
              Press <strong style={{ color: "var(--accent)" }}>[ R ]</strong> to force refresh.
            </div>
          </div>
        </div>
      </div>
    </>
  );
}

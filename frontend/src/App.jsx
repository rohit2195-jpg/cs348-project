import { useEffect, useState } from 'react';
import { ThemeProvider } from './Settings';
import Dashboard from './components/Dashboard';
import { apiJson, setAuthToken } from './components/Config';

function AuthScreen({ onAuthenticated }) {
  const [mode, setMode] = useState("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const submit = async () => {
    setLoading(true);
    setError("");
    try {
      const data = await apiJson(`/${mode === "login" ? "login" : "register"}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      setAuthToken(data.token);
      onAuthenticated(data.user);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-shell">
      <div className="auth-card">
        <div className="auth-accent" />
        <div className="auth-header">
          <div className="auth-kicker">PAPER TRADING SIMULATOR</div>
          <h1 className="auth-title">CS 348 Project Stock Trading Simulator</h1>
          <p className="auth-copy">
            Sign in or create a local account to manage a simulated brokerage portfolio.
          </p>
        </div>

        <div className="auth-meta" aria-label="Simulator account details">
          <span><strong>SIM CASH</strong>$100,000</span>
          <span><strong>ACCOUNT</strong>LOCAL</span>
          <span><strong>DATA</strong>ALPACA</span>
        </div>

        <div className="auth-form">
          <div className="auth-toggle" role="tablist" aria-label="Authentication mode">
            <button
              className={mode === "login" ? "active" : ""}
              onClick={() => setMode("login")}
              type="button"
            >
              Sign In
            </button>
            <button
              className={mode === "register" ? "active" : ""}
              onClick={() => setMode("register")}
              type="button"
            >
              Register
            </button>
          </div>

          <label className="auth-label">
            USERNAME
            <input
              className="auth-input"
              value={username}
              onChange={(e) => setUsername(e.target.value.toLowerCase())}
              maxLength={32}
              autoComplete="username"
            />
          </label>

          <label className="auth-label">
            PASSWORD
            <input
              className="auth-input"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && submit()}
              autoComplete={mode === "login" ? "current-password" : "new-password"}
            />
          </label>

          {error && <div className="auth-error">{error}</div>}

          <button className="auth-submit" onClick={submit} disabled={loading}>
            {loading ? "CONNECTING_" : mode === "login" ? "Sign In" : "Create Portfolio"}
          </button>

          <div className="auth-info">
            New accounts start with $100,000 in simulated cash. Trades are local, while market prices come from Alpaca.
          </div>
        </div>
      </div>
    </div>
  );
}

export default function App() {
  const [checking, setChecking] = useState(true);
  const [user, setUser] = useState(null);

  useEffect(() => {
    const loadSession = async () => {
      try {
        const data = await apiJson("/session");
        if (data.authenticated) {
          setUser(data.user);
        }
      } catch {
        setAuthToken(null);
        setUser(null);
      } finally {
        setChecking(false);
      }
    };
    loadSession();
  }, []);

  return (
    <ThemeProvider>
      <style>{authStyles}</style>
      {checking ? (
        <div className="auth-shell"><div className="auth-loading">CONNECTING_</div></div>
      ) : user ? (
        <Dashboard user={user} onLogout={() => {
          setAuthToken(null);
          setUser(null);
        }} />
      ) : (
        <AuthScreen onAuthenticated={setUser} />
      )}
    </ThemeProvider>
  );
}

const authStyles = `
  .auth-card,
  .auth-card * {
    box-sizing: border-box;
  }

  .auth-shell {
    min-height: 100dvh;
    display: grid;
    place-items: center;
    background:
      linear-gradient(90deg, color-mix(in srgb, var(--border) 45%, transparent) 1px, transparent 1px),
      linear-gradient(0deg, color-mix(in srgb, var(--border) 36%, transparent) 1px, transparent 1px),
      radial-gradient(circle at 18% 12%, color-mix(in srgb, var(--panel) 90%, transparent), transparent 30%),
      radial-gradient(circle at 82% 88%, color-mix(in srgb, var(--accent3) 15%, transparent), transparent 28%),
      var(--bg);
    background-size: 42px 42px, 42px 42px, auto, auto, auto;
    padding: 24px;
  }

  .auth-card {
    position: relative;
    width: min(620px, 100%);
    border: 1px solid var(--border);
    background: color-mix(in srgb, var(--bg) 92%, white);
    padding: 34px 36px 30px;
    box-shadow: 0 24px 70px rgba(20, 18, 12, 0.16);
    overflow: hidden;
  }

  .auth-accent {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 5px;
    background: linear-gradient(90deg, var(--accent), var(--accent3), var(--border));
  }

  .auth-header {
    text-align: center;
    max-width: 500px;
    margin: 0 auto;
  }

  .auth-kicker {
    font-size: 10px;
    letter-spacing: 0.24em;
    color: var(--accent2);
    margin-bottom: 14px;
    text-transform: uppercase;
  }

  .auth-title {
    margin: 0 0 12px;
    font-family: 'VT323', monospace;
    font-size: clamp(30px, 5vw, 42px);
    line-height: 1;
    letter-spacing: 0.04em;
    color: var(--accent);
  }

  .auth-copy {
    max-width: 420px;
    margin: 0 auto;
    color: var(--text-dim);
    font-size: 13px;
    line-height: 1.6;
  }

  .auth-meta {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 8px;
    margin: 24px auto 22px;
    width: min(480px, 100%);
  }

  .auth-meta span {
    display: flex;
    flex-direction: column;
    gap: 3px;
    padding: 9px 10px;
    border: 1px solid var(--border);
    background: var(--panel);
    color: var(--text);
    font-family: 'Share Tech Mono', monospace;
    font-size: 12px;
    text-align: center;
  }

  .auth-meta strong {
    color: var(--text-dim);
    font-size: 8px;
    letter-spacing: 0.18em;
    font-weight: normal;
  }

  .auth-form {
    width: min(380px, 100%);
    margin-inline: auto;
  }

  .auth-toggle {
    display: grid;
    grid-template-columns: 1fr 1fr;
    margin: 0 0 18px;
    border: 1px solid var(--border);
    background: var(--panel);
    padding: 4px;
  }

  .auth-toggle button,
  .auth-submit {
    background: transparent;
    border: 1px solid var(--accent3);
    color: var(--text);
    font-family: 'Share Tech Mono', monospace;
    letter-spacing: 0.12em;
    cursor: pointer;
    transition: border-color 0.14s, color 0.14s, background 0.14s, transform 0.14s;
  }

  .auth-toggle button {
    border: 1px solid transparent;
    padding: 9px 14px;
    font-size: 11px;
    text-transform: uppercase;
  }

  .auth-toggle button.active {
    background: var(--accent);
    border-color: var(--accent);
    color: var(--bg);
  }

  .auth-submit:hover:not(:disabled) {
    border-color: var(--accent);
    color: var(--accent);
    transform: translateY(-1px);
  }

  .auth-label {
    display: block;
    margin: 14px 0 0;
    color: var(--text-dim);
    font-size: 10px;
    letter-spacing: 0.16em;
    text-transform: uppercase;
  }

  .auth-input {
    width: 100%;
    margin-top: 7px;
    background: color-mix(in srgb, var(--bg) 88%, white);
    border: 1px solid var(--border);
    color: var(--text);
    padding: 12px 13px;
    font-family: 'Share Tech Mono', monospace;
    font-size: 14px;
    outline: none;
    box-shadow: inset 0 0 0 1px var(--panel);
    transition: border-color 0.14s, box-shadow 0.14s, background 0.14s;
  }

  .auth-input:focus {
    border-color: var(--accent);
    box-shadow: inset 0 0 0 1px var(--accent3), 0 0 0 3px color-mix(in srgb, var(--accent3) 18%, transparent);
  }

  .auth-error {
    color: var(--loss);
    font-size: 12px;
    margin-top: 12px;
    line-height: 1.4;
  }

  .auth-submit {
    width: 100%;
    margin-top: 18px;
    padding: 13px 16px;
    font-size: 12px;
    text-transform: uppercase;
  }

  .auth-submit:disabled {
    opacity: 0.55;
    cursor: not-allowed;
  }

  .auth-info {
    margin-top: 16px;
    padding: 11px 12px;
    border: 1px solid var(--border);
    background: var(--panel);
    color: var(--text-dim);
    font-size: 11px;
    line-height: 1.6;
  }

  .auth-loading {
    color: var(--accent);
    font-family: 'Share Tech Mono', monospace;
    letter-spacing: 0.16em;
  }

  @media (max-width: 560px) {
    .auth-shell {
      padding: 16px;
      align-items: start;
    }

    .auth-card {
      padding: 28px 20px 24px;
    }

    .auth-meta {
      grid-template-columns: 1fr;
    }
  }
`;

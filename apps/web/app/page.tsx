import { get, type Account, type Connection, type Modes, type Order, type Strategy } from "@/lib/api";
import { fmtNum, fmtQty, fmtTime, MODE_LABEL, statusTone, type Mode } from "@/lib/format";

export const dynamic = "force-dynamic";

export default async function Overview() {
  const [modes, conns, accounts, strategies, orders] = await Promise.all([
    get<Modes>("/api/v1/system/modes"),
    get<Connection[]>("/api/v1/connections"),
    get<Account[]>("/api/v1/accounts"),
    get<Strategy[]>("/api/v1/strategies"),
    get<Order[]>("/api/v1/orders?limit=20"),
  ]);

  return (
    <main className="wrap">
      <header className="top">
        <h1>Strategy Control Hub</h1>
        <span className="muted">Phase 1 · overview</span>
      </header>

      <div className="banner" role="status">
        <strong>LIVE EXECUTION DISABLED.</strong>{" "}
        {modes.ok
          ? `Default mode: ${MODE_LABEL[modes.data.default_mode as Mode] ?? modes.data.default_mode}. `
          : "Mode information unavailable. "}
        SIM prices are synthetic and are not market data. TradingView is a manual, personal research
        surface only and has no connection to order logic.
      </div>

      <div className="grid">
        <div className="card">
          <h2>Connections</h2>
          {!conns.ok ? (
            <p className="off">API: {conns.error}</p>
          ) : (
            <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
              {conns.data.map((c) => (
                <li key={c.name} style={{ marginBottom: 10 }}>
                  <span className={`pill ${statusTone(c.status)}`}>{c.status}</span> {c.name}
                  <div className="muted">{c.detail}</div>
                  {c.last_heartbeat_utc && (
                    <div className="muted">Heartbeat {fmtTime(c.last_heartbeat_utc)}</div>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="card">
          <h2>Accounts</h2>
          {!accounts.ok ? (
            <p className="off">API: {accounts.error}</p>
          ) : accounts.data.length === 0 ? (
            <p className="muted">No accounts registered.</p>
          ) : (
            accounts.data.map((a) => (
              <div key={a.id} style={{ marginBottom: 8 }}>
                <strong>{MODE_LABEL[a.mode as Mode] ?? a.mode}</strong>
                <div className="muted">
                  {a.broker} · {a.server} · {a.login_masked} · {a.account_type} · {a.currency}
                </div>
              </div>
            ))
          )}
          <p className="muted">MT5 DEMO: NOT CONNECTED. No broker data is shown until a verified terminal is linked.</p>
        </div>
      </div>

      <section className="card">
        <h2>Recent order commands</h2>
        {!orders.ok ? (
          <p className="off">API: {orders.error}</p>
        ) : orders.data.length === 0 ? (
          <p className="muted">No order commands yet.</p>
        ) : (
          <div className="scroll">
            <table>
              <thead>
                <tr><th>Created</th><th>Mode</th><th>Symbol</th><th>Side</th><th>Vol</th>
                  <th>Est. loss at SL</th><th>State</th><th>Notes</th></tr>
              </thead>
              <tbody>
                {orders.data.map((o) => (
                  <tr key={o.id}>
                    <td>{fmtTime(o.created_utc)}</td><td>{o.mode}</td><td>{o.symbol}</td>
                    <td>{o.side}</td><td>{fmtQty(o.volume)}</td><td>{fmtNum(o.est_loss_at_stop)}</td>
                    <td>{o.state}</td><td className="muted">{o.outcome ?? o.risk_reasons.join("; ")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="card">
        <h2>Strategy catalog</h2>
        {!strategies.ok ? (
          <p className="off">API: {strategies.error}</p>
        ) : (
          <div className="scroll">
            <table>
              <thead><tr><th>Strategy</th><th>Version</th><th>Status</th></tr></thead>
              <tbody>
                {strategies.data.map((s) => (
                  <tr key={s.id}>
                    <td><strong>{s.name}</strong><div className="muted">{s.description}</div></td>
                    <td>{s.version}</td>
                    <td>{s.implemented ? "implemented" : "catalog only, not implemented"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="muted">No performance figures are shown: nothing has been backtested yet.</p>
      </section>
    </main>
  );
}

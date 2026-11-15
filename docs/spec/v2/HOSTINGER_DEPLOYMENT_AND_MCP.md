# Hostinger Ubuntu 24.04 — Deployment and MCP Integration Notes

## 1. Recommended Hostinger template

Choose **Ubuntu 24.04 with MetaTrader** (published Hostinger VPS template) where available, because it preconfigures a graphical/Wine-capable MetaTrader environment. Then install Docker Engine + Docker Compose plugin on the same VPS for the web platform. Alternative: Ubuntu 24.04 with Desktop plus official MetaTrader Linux Wine installer; install Docker. Do not assume a fresh Docker-only Ubuntu image already supports the MT5 GUI/Wine workflow.

- The Hostinger Linux VPS is not a Windows server.
- MT5 on Linux is run through Wine, not as a native Linux binary.
- Hostinger template availability changes; validate at setup. Changing OS templates may erase VPS data: back up first.
- Run MT5 in a dedicated restricted user session; verify autostart, updates, demo login and UI after reboot. Do not leave unrestricted public RDP enabled.
- Start planning VPS capacity around web/API/Postgres/Redis plus a GUI/Wine terminal. Size only after load measurements: monitoring, backtesting jobs and multi-terminal use can increase CPU/RAM. No invented minimum guarantee.

## 2. Network boundary

Public ingress: `443/tcp` for HTTPS, optional `80/tcp` for ACME challenge, SSH limited to trusted source/VPN. Caddy terminates TLS. Do not expose DB, Redis, MT5 MCP, MetaEditor MCP, diagnostics, RDP or internal API to public network. Restrict outbound services to provider endpoints as feasible.

MT5 GUI configured under **Tools -> Options -> MCP**:

- Enable internal server if integration needed.
- Use a loopback-only endpoint such as `http://127.0.0.1:22346/mcp` for **terminal**.
- Generate and protect a per-client MCP token; never put it in repo, shell history, frontend or shared logs.
- Optional `metaeditor` on localhost `http://127.0.0.1:22345/mcp` only for manual development; disable dangerous shell/file tools unless expressly required.
- Explore documented tool capabilities and configure the MT5 AI Assistant trading permissions to `no trade` or explicit confirmation. Separate app-side order approval is mandatory even if MT5 has its own confirmation mode.
- For Claude Code: MT5 can copy its MCP JSON to a `.mcp.json` file with local HTTP endpoints and Authorization bearer tokens. Create it securely in a user-managed path; exclude `.mcp.json` from Git and backups accessible to others.

**Important Docker networking fact:** inside a normal container, `127.0.0.1` refers to that container. It will not reach the host's MT5 server bound to host loopback. Use a host-side `mt5-agent` service which connects locally to MCP and communicates only with the authenticated internal application. A Unix-domain socket or locally restricted HTTP with independent auth can be used. Do not bind MT5 MCP to `0.0.0.0` as a workaround.

## 3. TradingView MCP separately

TradingView official MCP beta URL: `https://mcp.tradingview.com/mcp`.

For your own interactive Claude Code session:

```bash
claude mcp add --transport http mcp-tradingview https://mcp.tradingview.com/mcp
# In Claude Code: /mcp -> authorize via TradingView OAuth
```

**Do not configure the trading backend to harvest TradingView MCP data.** TradingView Terms §27 limit MCP to your personal, non-commercial interactive use and bar automated trading and database accumulation. A hosted personal dashboard is not automatically entitled to redistribute or repurpose the MCP results. A separate automated research feature must use permitted independent market data such as MT5 demo broker-provided historical bars, subject to broker terms.

TradingView Paper Trading is operated manually in TradingView. Do not promise API-driven account linking, order execution, balance sync or automated TradingView-to-MT5 routing.

## 4. Host process deployment split

- **Docker Compose:** frontend, backend, worker, Redis, PostgreSQL and reverse proxy. Compose binds app API on localhost/internal network; external web ingress only through TLS reverse proxy.
- **systemd on Ubuntu host:** `mt5-agent.service` connecting to terminal MCP loopback. Account service must be least privileged and separated from public containers.
- **Wine graphical session:** MT5 process. Verify session survives or restarts with required graphical facilities; check credentials persist without embedding passwords in systemd unit. MT5 agent must stop new orders during terminal relaunch.

## 5. First integration smoke-test checklist

1. SSH/management access works over restricted channel, TLS valid.
2. MT5 GUI opens on Ubuntu and connects to the selected **DEMO** broker server.
3. MT5 terminal build supports native MCP, `Enable internal server` enabled, endpoint `127.0.0.1:22346` accessible from VPS localhost only.
4. MCP token authenticates a read-only tool request; expected names and permissions confirmed by live enumeration.
5. Account number, server, demo type, equity, symbol spec and timestamp verified; user confirms.
6. One read-only broker request returns real positions/deals; dashboard reconciles with MT5 UI.
7. Firewall confirms TCP 22346/22345 not reachable from a public machine.
8. SIM and MT5 DEMO modes remain separate in DB and UI.
9. Wrong server/type and stale quote cause immediate order denial.
10. Human approval + optional single minimal demo order only on user's explicit instruction, with complete ack and reconciliation.
11. Restart OS; verify Docker, DB, web, Wine MT5 session, agent, demo connection and MCP eventually return healthy. New entries must remain disabled until health passes.

## 6. Official references

- https://www.hostinger.com/support/10420155-how-to-use-the-metatrader-vps-template-at-hostinger/
- https://www.hostinger.com/support/9571800-how-to-run-metatrader-5-on-hostinger-vps/
- https://www.hostinger.com/support/8306612-how-to-use-the-docker-vps-template-at-hostinger/
- https://www.metatrader5.com/en/terminal/help/start_advanced/install_linux
- https://www.metatrader5.com/en/terminal/help/mcp_and_ai/configuration
- https://www.metatrader5.com/en/terminal/help/mcp_and_ai/capabilities
- https://www.tradingview.com/mcp/docs
- https://www.tradingview.com/policies/

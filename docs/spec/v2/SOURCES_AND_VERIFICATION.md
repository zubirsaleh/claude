# Evidence / Sources / Verification Policy

Reviewed November 15, 2026. These are first-party source references for project capability boundaries. Re-check at implementation time.

## MT5 MCP

- MetaQuotes release notice for Build 6060, July 23, 2026, native MCP support: https://www.metaquotes.com/en/metatrader5/news/5538
- MT5 MCP help: https://www.metatrader5.com/en/terminal/help/mcp_and_ai
- MCP configuration: https://www.metatrader5.com/en/terminal/help/mcp_and_ai/configuration
- MCP tools/capabilities: https://www.metatrader5.com/en/terminal/help/mcp_and_ai/capabilities
- Linux via Wine: https://www.metatrader5.com/en/terminal/help/start_advanced/install_linux
- MQL5 WebRequest / allowed endpoints: https://www.mql5.com/en/docs/network/webrequest
- Official MetaTrader5 Python integration API: https://www.mql5.com/en/docs/python_metatrader5

**Confirmed by official docs:** MT5 native MCP provides a terminal MCP, MetaEditor MCP and market-data MCP with documented tools for read and trade operations; localhost endpoint and bearer token configuration examples; Wine-based Linux terminal install. **Not confirmed in this project:** user terminal build, Wine reliability, actual broker, actual authorized MCP tool list, MT5 demo account identity, secure host-agent network, on-host startup, and complete end-to-end order reconciliation.

## TradingView

- Official MCP docs: https://www.tradingview.com/mcp/docs
- Binding terms: https://www.tradingview.com/policies/ (Sections 3 and 27)
- TradingView Paper Trading basics: https://www.tradingview.com/support/solutions/43000516466-paper-trading-main-functionality/
- TradingView existing API scope: https://www.tradingview.com/support/solutions/43000474413-i-need-access-to-your-api-in-order-to-get-data-or-indicator-values/
- Webhook limits: https://www.tradingview.com/support/solutions/43000529348-how-to-configure-webhook-alerts/

**Confirmed:** TradingView has official personal MCP with OAuth; watchlist, market display/analysis and alert tools. Terms prohibit using MCP/data/webhooks/alerts for automated orders and certain other machine uses; no general order tool documented for TradingView Paper Trading. **Not confirmed:** user's plan eligibility, account linkage or right to any non-standard automation. Do not imply TradingView authorization to do prohibited actions just because a webhook is technically available.

## Hostinger

- MetaTrader VPS template: https://www.hostinger.com/support/10420155-how-to-use-the-metatrader-vps-template-at-hostinger/
- MT5 via Ubuntu with Desktop and Wine: https://www.hostinger.com/support/9571800-how-to-run-metatrader-5-on-hostinger-vps/
- Docker Ubuntu template: https://www.hostinger.com/support/8306612-how-to-use-the-docker-vps-template-at-hostinger/
- OS templates: https://support.hostinger.com/en/articles/1583571-what-are-the-available-operating-systems-for-vps
- Linux-only Hostinger VPS: https://www.hostinger.com/support/which-server-capabilities-are-supported-at-hostinger/

## Source video

A 150-second Phantom Control product demonstration (uploaded user file `threadsdownloader.com_b5a024 (7).mp4`) supports the *visual product modules* in `ARCHITECTURE_AND_REQUIREMENTS.md`. It does not support assertions of strategy performance, trading algorithms or the current application's functionality. All specific strategies in V2 are proposed fresh implementations.

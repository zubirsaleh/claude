# CLAUDE.md

This file provides guidance to AI assistants (Claude and others) working in this repository.

## Repository Overview

**Repo:** `zubirsaleh/claude`
**Product:** TradingView → Claude → Telegram analyst bot.

The user sends a plain-language trading query to a Telegram bot. The bot routes it to Claude (via Anthropic API), which calls TradingView tools to fetch live OHLCV data, compute technical indicators, and detect candlestick patterns, then returns a structured position analysis back to Telegram.

A standalone MCP server (`mcp_server/server.py`) exposes the same tools to Claude Code for direct use in the CLI/desktop without the Telegram layer.

## Project Structure

```
claude/
├── main.py                    # Entry point — starts Telegram bot
├── config.py                  # Env-var config
├── requirements.txt
├── .env.example               # Required env vars template
├── .claude/
│   └── settings.json          # MCP server wiring for Claude Code
├── bot/
│   ├── claude_handler.py      # Anthropic API + tool-use loop + history
│   └── telegram_bot.py        # Telegram handlers
├── mcp_server/
│   └── server.py              # FastMCP server (TradingView tools)
└── trading/
    ├── fetcher.py             # tvdatafeed OHLCV downloader
    ├── indicators.py          # pandas-ta RSI/MACD/BB/EMA/ATR/Stoch
    ├── patterns.py            # Candlestick pattern detection
    └── analysis.py            # Combined full_analysis() + TV rating
```

## Development Setup

```bash
git clone https://github.com/zubirsaleh/claude.git
cd claude
pip install -r requirements.txt
cp .env.example .env          # fill in the four required vars
python main.py                # starts the Telegram bot
```

### Prerequisites

- Python 3.10+
- A Telegram bot token (from [@BotFather](https://t.me/BotFather))
- An Anthropic API key (console.anthropic.com)
- A TradingView account (free tier works; credentials optional but unlock more data)

## Common Commands

| Task | Command |
|------|---------|
| Install deps | `pip install -r requirements.txt` |
| Start Telegram bot | `python main.py` |
| Start MCP server only | `python mcp_server/server.py` |

## Git Workflow

- **Primary branch:** `main`
- **Feature branches:** `<area>/<short-description>` (e.g. `auth/oauth-login`)
- **AI task branches:** `claude/<task-slug>` (auto-created by Claude Code on the web)
- Commit messages should be imperative, present-tense, ≤ 72 chars: `Add user authentication flow`
- Open a pull request for every change; do not push directly to `main`.

## Code Conventions

Fill this section in once the stack is decided. Typical things to document:

- **Language / framework version** in use
- **Formatting tool** (Prettier, Black, gofmt, etc.) and whether it runs automatically
- **Linter** (ESLint, Ruff, golangci-lint, etc.) and any rule overrides
- **Naming conventions** (camelCase vs snake_case, file naming, etc.)
- **Test file location and naming** (`*.test.ts` next to source, or `tests/` directory, etc.)
- **Import ordering** rules if enforced

## Testing

Describe the test strategy:

- Unit tests: `<framework>` — run with `<command>`
- Integration tests: `<framework>` — run with `<command>`
- E2E tests: `<framework>` — run with `<command>`

All new features should include tests. PRs must not reduce overall coverage.

## Environment Variables

List required environment variables and where to get them:

| Variable | Description | Required |
|----------|-------------|----------|
| `TELEGRAM_BOT_TOKEN` | Token from @BotFather | Yes |
| `TELEGRAM_ALLOWED_USERS` | Comma-separated Telegram user IDs | Yes |
| `ANTHROPIC_API_KEY` | Anthropic console API key | Yes |
| `TRADINGVIEW_USERNAME` | TradingView login email | No |
| `TRADINGVIEW_PASSWORD` | TradingView password | No |
| `MAX_HISTORY` | Conversation turns kept in memory (default 20) | No |

Never commit real secrets. Copy `.env.example` → `.env` and fill it in locally.

## AI Assistant Guidelines

Guidelines specifically for Claude Code and other AI assistants:

- **Read this file first** before making any changes.
- **Prefer editing existing files** over creating new ones.
- **No unnecessary comments** — only add a comment when the *why* is non-obvious.
- **No speculative abstractions** — implement exactly what is asked; don't design for hypothetical future requirements.
- **Security first** — never introduce SQL injection, XSS, command injection, or other OWASP Top 10 vulnerabilities.
- **No hard-coded secrets** — use environment variables at system boundaries.
- **Ask before destructive git operations** — force-push, reset --hard, branch deletion, etc.
- **Commit and push** all work to the designated feature branch; do not open a PR unless explicitly asked.
- **Run tests** after any non-trivial change and confirm they pass before reporting work as done.

## Architecture Decisions

> **2026-06-05 — Single-process bot with inline tool execution**
> The Telegram bot calls Claude's tool-use API synchronously in a thread pool (not as a separate MCP subprocess). This keeps deployment simple (one `python main.py`). The MCP server (`mcp_server/server.py`) is a separate entry point for Claude Code CLI/Desktop users who want to query TradingView directly without the bot.

> **2026-06-05 — tvdatafeed for OHLCV + tradingview-ta for TA ratings**
> `tvdatafeed` provides raw OHLCV history over TradingView's WebSocket. `tradingview-ta` scrapes TradingView's screener for the aggregated BUY/SELL/NEUTRAL rating. Both are unofficial but widely used. `pandas-ta` handles all local indicator maths so the bot works even when TV screener is unavailable.

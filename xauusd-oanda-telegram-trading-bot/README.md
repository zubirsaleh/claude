# XAU/USD OANDA Telegram Trading Bot

A production-ready, home-server trading **assistant** for **XAU/USD (gold) only**.
It uses **OANDA** as the market-data source and **Telegram** as both the input
and output channel. By default it runs in **advisory mode** — it produces
analysis and position-sizing suggestions, but **never places orders**.

> ⚠️ This is analysis only, **not financial advice**. Trading leveraged
> products like gold carries substantial risk.

---

## 1. Purpose

Send a plain-language question (or a slash command) to a Telegram bot and get a
structured XAU/USD read back: price action, technical indicators, candlestick
patterns, a LONG / SHORT / WAIT bias with a 0–100 signal score, and a risk plan
(stop loss, targets, R:R, position size). Data comes **exclusively from the
OANDA v20 REST API** — no TradingView scraping, no fabricated prices.

---

## 2. Architecture

```
Telegram User
  ↓
telegram-bot        (python-telegram-bot)
  ↓  HTTP
analysis-service    (FastAPI :8000)  ── OpenAI (optional) / rule-based engine
  ↓  HTTP
oanda-service       (FastAPI :8001)
  ↓  HTTPS
OANDA v20 REST API  (practice by default)
```

Inside `oanda-service`:

```
OANDA candles → indicator_engine → pattern_engine → JSON
```

Inside `analysis-service`:

```
market data → signal scoring → bias rules → risk_engine → formatted report
```

| Service | Folder | Port | Role |
|---|---|---|---|
| `telegram-bot` | `telegram_bot/` | — | Commands & free-text, formats replies |
| `analysis-service` | `analysis_service/` | 8000 | Orchestration, scoring, bias, risk, OpenAI |
| `oanda-service` | `oanda_service/` | 8001 | OANDA data, indicators, patterns |
| shared | `shared/` | — | Config, models, logging |

---

## 3. OANDA setup

1. Open a **free OANDA practice (demo) account** at oanda.com.
2. In the account portal go to **Manage API Access** and generate a
   **personal access token**.
3. Note your **account ID** (format like `101-001-1234567-001`).
4. Put both into `.env` as `OANDA_API_KEY` and `OANDA_ACCOUNT_ID`.
5. Keep `OANDA_ENV=practice`. XAU/USD is available as instrument code `XAU_USD`
   (TradingView shows the same market as `OANDA:XAUUSD`).

The practice endpoint `https://api-fxpractice.oanda.com` is used automatically.
The live endpoint is only ever used when **all** safety flags are relaxed (see
§9).

---

## 4. Telegram bot setup

1. Message **[@BotFather](https://t.me/BotFather)** → `/newbot` → follow prompts.
2. Copy the **bot token** into `.env` as `TELEGRAM_BOT_TOKEN`.
3. (Optional) Message **@userinfobot** to get your numeric ID for
   `TELEGRAM_CHAT_ID`.
4. Start a chat with your new bot and send `/start`.

---

## 5. `.env` configuration

Copy the template and fill it in:

```bash
cp .env.example .env
```

| Variable | Description | Required |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Token from @BotFather | Yes |
| `TELEGRAM_CHAT_ID` | Your numeric chat id | No |
| `OANDA_API_KEY` | OANDA personal access token | Yes |
| `OANDA_ACCOUNT_ID` | OANDA account id | Yes |
| `OANDA_ENV` | `practice` (default) or `live` | No |
| `OANDA_INSTRUMENT` | Fixed to `XAU_USD` | No |
| `OPENAI_API_KEY` | Enables AI commentary; falls back to rules if empty | No |
| `OPENAI_MODEL` | OpenAI model (default `gpt-4o-mini`) | No |
| `DEFAULT_TIMEFRAME` | Default analysis TF (`M15`) | No |
| `DEFAULT_CANDLE_COUNT` | Candles fetched (`150`) | No |
| `DEFAULT_RISK_PERCENT` | Risk per trade (`1.0`) | No |
| `DEFAULT_ACCOUNT_BALANCE` | Balance used for sizing (`10000`) | No |
| `ALLOW_LIVE_TRADING` | Must be `true` to ever touch live | No |
| `ADVISORY_ONLY` | Must be `false` to ever execute | No |

---

## 6. Docker installation

Install Docker Engine + Compose plugin (Linux home server):

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker "$USER"   # log out / back in afterwards
docker --version && docker compose version
```

---

## 7. Running the system

```bash
# from the project root
cp .env.example .env        # then edit .env with your keys
docker compose build
docker compose up -d        # start all three services
docker compose logs -f      # follow logs
docker compose down         # stop everything
```

Health checks:

```bash
curl http://localhost:8001/health     # oanda-service
curl http://localhost:8000/health     # analysis-service
```

### Running locally without Docker (optional, for development)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r oanda_service/requirements.txt \
            -r analysis_service/requirements.txt \
            -r telegram_bot/requirements.txt
export PYTHONPATH="$PWD"

# three terminals (or use & ):
uvicorn app:app --app-dir oanda_service --port 8001
OANDA_SERVICE_URL=http://localhost:8001 uvicorn app:app --app-dir analysis_service --port 8000
ANALYSIS_SERVICE_URL=http://localhost:8000 python telegram_bot/bot.py
```

---

## 8. Telegram commands

| Command | Behaviour |
|---|---|
| `/start` | Welcome message and usage examples |
| `/help` | List supported commands |
| `/clear` | Clear your session context |
| `/status` | Check bot, analysis & OANDA services |
| `/price` | Latest XAU/USD bid/ask |
| `/analyze [TF]` | Full analysis (default `M15`); e.g. `/analyze H1` |
| `/scalp` | M5 setup confirmed by M15 — bias LONG/SHORT/WAIT |
| `/daily` | H4 + Daily higher-timeframe bias |
| `/risk` | Sample position sizing |

**Free-text also works:** `gold now`, `xauusd m15`, `should I buy gold now`,
`scalp gold`, `xauusd h1 full read`, `long or short gold`.

Any non-gold instrument is refused with:
`This bot is configured for XAU/USD only.`

### Sample output

```
XAU/USD OANDA — M15 Analysis

Price Action
- Current Price: 2345.6
- Recent Trend: Rising
- Support: 2338.2
- Resistance: 2351.0
- Market Structure: Uptrend (higher highs, higher lows)

Technical Indicators
- RSI: 58.3
- MACD: 0.42 (hist 0.08)
- Bollinger Bands: 2333.1 / 2342.0 / 2350.9
- EMA Alignment: Bullish (9>21>50>200)
- Stochastic: K 71.2 / D 65.4
- ATR: 1.9 (0.081%)
...
Trading Bias
- Bias: LONG
- Signal Score: 82 (Strong)
- Confidence: High
...
This is analysis only, not financial advice.
```

---

## 9. Safety controls

- **Advisory mode is the default** (`ADVISORY_ONLY=true`).
- **No live trading by default** (`ALLOW_LIVE_TRADING=false`).
- **No automatic order execution** anywhere in the code.
- **Practice environment first** (`OANDA_ENV=practice`).
- Every analysis request and every generated signal is **logged**.
- OANDA/API failures are **surfaced, never hidden**, and missing market data is
  **never fabricated**.

The live OANDA endpoint is only selected when **all** of these are true:

```
ALLOW_LIVE_TRADING=true
ADVISORY_ONLY=false
OANDA_ENV=live
```

Even then, this codebase still does not place orders — see §10.

---

## 10. From advisory mode to practice execution (later)

Order execution is intentionally **not implemented**. To add **paper/practice**
execution against your OANDA **demo** account later:

1. Keep `OANDA_ENV=practice`. Confirm the account is a demo account.
2. Add an order helper to `oanda_service/oanda_client.py`, e.g.:

   ```python
   def create_market_order(units: float, stop_loss: float, take_profit: float) -> dict:
       config.validate_oanda()
       if config.ADVISORY_ONLY:
           raise OandaError("Execution blocked: ADVISORY_ONLY is true.")
       body = {
           "order": {
               "type": "MARKET",
               "instrument": config.OANDA_INSTRUMENT,
               "units": str(units),               # +long / -short
               "stopLossOnFill": {"price": f"{stop_loss:.3f}"},
               "takeProfitOnFill": {"price": f"{take_profit:.3f}"},
           }
       }
       url = f"{config.oanda_base_url()}/v3/accounts/{config.OANDA_ACCOUNT_ID}/orders"
       resp = requests.post(url, headers=_headers(), json=body, timeout=15)
       ...
   ```

3. Expose a guarded `POST /order` endpoint in `oanda_service/app.py` that
   refuses unless `ADVISORY_ONLY=false`.
4. Add a confirmation step in the Telegram bot (e.g. `/confirm`) so no order is
   sent without an explicit human approval.
5. Only after thorough demo testing, and at your own risk, consider live —
   which additionally requires the three flags in §9.

Recommended rollout: **advisory → practice execution with manual confirm →
(optional) live with manual confirm**. Never skip a stage.

---

## Project structure

```
xauusd-oanda-telegram-trading-bot/
├── docker-compose.yml
├── .env.example
├── README.md
├── telegram_bot/      Dockerfile, requirements.txt, bot.py
├── analysis_service/  Dockerfile, requirements.txt, app.py, analyst.py, risk_engine.py
├── oanda_service/     Dockerfile, requirements.txt, app.py, oanda_client.py, indicators.py, patterns.py
└── shared/            config.py, models.py, logging_config.py
```

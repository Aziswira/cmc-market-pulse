# CMC Market Pulse

> A CoinMarketCap API screener + dashboard generator: top gainers, top losers, and ±5% movers alerts from the top 100 coins — rendered as a single self-contained HTML dashboard.

Built for the **DoraHacks "Build with CMC: API Hackathon"** — **Track: Markets & Trading Tools**.
Submission deadline: 9 Dec 2026, 23:59 UTC.

CMC Market Pulse answers the question every trader asks first — *"what's moving, and how big is the whole market right now?"* — in one command, with no dependencies beyond Python itself.

## Features

- **Top 10 gainers & top 10 losers** by 24h % change among the top 100 coins by market cap
- **Movers alert** — every coin with `abs(percent_change_24h) >= 5%`, sorted by size of move
- **Global context cards** — total market cap, 24h volume, BTC dominance, ETH dominance, and Fear & Greed when the plan allows it
- **Top-20 table** with price, 1h / 24h / 7d % change, market cap, 24h volume, and a CSS bar visualisation of the 24h move
- **Three outputs per run:** an HTML dashboard, a Markdown summary, and an `evidence/` folder (see below)
- **Zero dependencies** — Python standard library only (`urllib`, `json`, `os`, `argparse`, `datetime`); nothing to `pip install`
- **Offline demo mode** (`--demo`) that runs end-to-end from a local snapshot, so anyone can try it without an API key

## CoinMarketCap API endpoints used

| # | Endpoint | Purpose | Params |
|---|----------|---------|--------|
| 1 | `GET https://pro-api.coinmarketcap.com/v1/cryptocurrency/listings/latest` | Top coins by market cap with quotes (price, % changes, volume, market cap) | `start=1, limit=100, convert=USD, sort=market_cap, cryptocurrency_type=coins` |
| 2 | `GET https://pro-api.coinmarketcap.com/v1/global-metrics/quotes/latest` | Total market cap, total 24h volume, BTC / ETH dominance | `convert=USD` |
| 3 | `GET https://pro-api.coinmarketcap.com/v3/fear-and-greed/latest` | Fear & Greed index (optional — skipped gracefully if the plan doesn't include it) | — |

All calls use the header `X-CMC_PRO_API_KEY: <your key>`. The key is read from the `CMC_API_KEY` environment variable and is **never** hard-coded or committed.

## Quickstart

### 1. Get a free API key

Sign up at <https://coinmarketcap.com/api> and copy your API key from the dashboard.

### 2. Set the key

```bash
cp .env.example .env        # optional reference — .env is git-ignored
export CMC_API_KEY=your_key_here
```

### 3. Run

```bash
# Live data from the CoinMarketCap Pro API
python3 market_pulse.py

# Offline demo — no key needed, uses the snapshot in sample_data/
python3 market_pulse.py --demo
```

Then open `output/dashboard.html` in any browser.

## Outputs

| File | What it is |
|------|------------|
| `output/dashboard.html` | Single self-contained dashboard (inline CSS, dark theme, no external assets): global-metrics cards, gainers table, losers table, movers-alert section, top-20 table with 24h % bars |
| `output/summary.md` | The same highlights in Markdown — handy for sharing or pasting into a post |
| `evidence/listings_latest_sample.json` | Trimmed API response (first 3 listings, full `status` block preserved) |
| `evidence/global_metrics.json` | Global-metrics response as received |
| `evidence/api_call_log.txt` | One entry per call: request URL (API key redacted as `***`), HTTP status, `credit_count` from the API status block, timestamp |

The terminal also prints a readable gainers / losers / movers table on every run.

## Evidence of a real API call

See the `evidence/` folder. `api_call_log.txt` records each request URL, the HTTP status, and the `credit_count` returned in the API's own `status` block; `listings_latest_sample.json` and `global_metrics.json` hold the (trimmed) response bodies the dashboard was built from.

> **About `sample_data/`:** it is a *captured-shape snapshot for offline demo* — realistic placeholder JSON in the exact CoinMarketCap response shape (`status{timestamp, error_code, error_message, credit_count}` + `data[...]`) with ~12 well-known coins and plausible Nov-2026-ish values. It is **not** live market data. When the project is run live, a real snapshot replaces it in `evidence/`.

## What the CMC API made possible

- **One call, a whole screener.** `listings/latest` returns price, 1h/24h/7d changes, volume, and market cap for 100 coins in a single response — the entire gainers/losers/movers analysis is just sorting and filtering that one payload. No scraping, no per-coin calls.
- **Instant global context.** `global-metrics/quotes/latest` gives total market cap, volume, and BTC/ETH dominance in the same shape, so the dashboard can frame individual movers against the whole market without any extra data source.
- **Trustworthy, uniform numbers.** Every coin comes back in the same `quote.USD` structure with a `status` block (timestamp, `credit_count`, error code), which made the evidence trail — request, status, credits — trivial to produce and audit.
- **Fast to prototype.** From key to a working dashboard took a single stdlib script; the free tier was enough for the full build-test loop.

## Where the API got in the way / feedback for CMC

- **The key must stay server-side — there are no scoped / read-only keys.** A single key unlocks the account's full quota, so it can never be embedded in a browser app or a public repo. Scoped keys (per-endpoint, read-only, origin-restricted) would unlock a whole class of safe client-side demos.
- **CORS limits direct browser calls.** Because the key can't ship to the client *and* the API isn't designed for direct browser use, a static frontend can't safely call it live — every web demo needs a backend proxy just to hide the key. A public, rate-limited, key-less "latest snapshot" endpoint (or CORS-enabled scoped keys) would fix this.
- **Credit counting per call makes polling dashboards expensive.** A dashboard that refreshes every minute burns credits on three endpoints continuously, even when nothing changed. Cheaper bulk/polling pricing, conditional requests, or a websocket/streaming tier would make live dashboards practical on small plans.
- **Fear & Greed lives on `v3` while listings and global metrics live on `v1` — easy to miss.** The version split is only obvious once you read each endpoint's page separately; a single "current version" map in the docs (or the same data under the current version prefix) would save builders a confusing 404.

## Screenshots

<!-- TODO: add screenshots before submission -->
- [ ] `output/dashboard.html` — full dashboard (placeholder)
- [ ] Terminal output of `python3 market_pulse.py` (placeholder)

## Project layout

```
cmc-market-pulse/
├── market_pulse.py                  # the whole tool (stdlib only)
├── sample_data/
│   ├── listings_latest.json         # demo snapshot, CMC response shape
│   └── global_metrics.json          # demo snapshot, CMC response shape
├── output/                          # generated: dashboard.html, summary.md
├── evidence/                        # generated: trimmed responses + call log
├── .env.example
├── LICENSE                          # MIT
└── README.md
```

## License

MIT — see [LICENSE](LICENSE). © Ryuma / Aziswira.

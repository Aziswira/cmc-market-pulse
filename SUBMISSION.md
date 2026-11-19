# BUIDL Submission Copy — Build with CMC: API Hackathon (DoraHacks)

> Prepared 2026-11-19. Placeholders in [BRACKETS] are filled at submission time.
> Deadline: 9 Dec 2026 23:59 UTC (10 Dec 07:00 WIB).

## Title
CMC Market Pulse — Top Movers Screener & Live Market Dashboard

## Track
Markets and Trading Tools

## Tagline
One command turns live CoinMarketCap data into a top-movers screener, a ≥5% movers alert list, and a self-contained HTML market dashboard.

## Description
Most retail traders check prices coin by coin. CMC Market Pulse answers the only questions that matter at a glance — *what is moving, how big is the move, and what is the overall market doing?* — in a single run.

CMC Market Pulse is a dependency-free Python tool (standard library only) that calls the CoinMarketCap Pro API, screens the top 100 coins by market cap, and generates:

- **Top 10 gainers & top 10 losers** by 24h % change
- **Movers alerts**: every coin with |24h change| ≥ 5%
- **Market overview**: total market cap, 24h volume, BTC/ETH dominance, Fear & Greed index
- A **self-contained HTML dashboard** (`output/dashboard.html`, no external assets) plus a markdown summary — ready to publish as a demo page
- An **evidence pack** (`evidence/`) with the real API response samples and a call log (endpoint, HTTP status, credit count, timestamp — API key always redacted)

## CoinMarketCap API endpoints used (explicit)
1. `GET https://pro-api.coinmarketcap.com/v1/cryptocurrency/listings/latest` — start=1, limit=100, convert=USD, sort=market_cap, cryptocurrency_type=coins
2. `GET https://pro-api.coinmarketcap.com/v1/global-metrics/quotes/latest` — convert=USD
3. `GET https://pro-api.coinmarketcap.com/v3/fear-and-greed/latest` — optional, skipped gracefully if the plan does not include it

Authentication: `X-CMC_PRO_API_KEY` header, key read from the `CMC_API_KEY` environment variable. No key is committed to the repository.

## Links
- GitHub (public): [GITHUB_REPO_URL]
- Live demo (GitHub Pages, dashboard generated from a live API run): [DEMO_URL]
- Evidence of a real API call: see `evidence/` in the repo (code in `market_pulse.py`, response samples + `api_call_log.txt`)

## What the API made possible
One listings call returns price, 1h/24h/7d changes, volume and market cap for the whole top 100 in a single response, so a genuinely useful screener needs no scraping, no exchange accounts and almost no code. Global metrics and Fear & Greed add market context from the same key and the same response shape (`status` block with credit_count makes usage transparent).

## Where the API got in the way (feedback for CMC)
- No scoped/read-only keys: the single key controls the whole account, so it must stay server-side; a public frontend can never call the API directly.
- CORS prevents direct browser calls, which forces a backend or a pre-generated snapshot for web demos.
- Per-call credit counting makes naive polling dashboards expensive; clearer guidance on cache-friendly polling intervals would help.
- Fear & Greed lives on v3 while listings are on v1 — easy to miss when browsing the docs by endpoint name.

## How to run
```bash
export CMC_API_KEY=your_key_here   # free at coinmarketcap.com/api
python3 market_pulse.py            # live run
python3 market_pulse.py --demo     # offline run on bundled sample snapshot
```

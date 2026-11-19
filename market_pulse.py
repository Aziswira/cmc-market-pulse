#!/usr/bin/env python3
"""CMC Market Pulse — CoinMarketCap API screener + dashboard generator.

A Markets & Trading tool built for the DoraHacks "Build with CMC: API
Hackathon". It pulls the top 100 coins and global market metrics from the
CoinMarketCap Pro API, finds the biggest 24h movers, and renders a
self-contained HTML dashboard, a Markdown summary, and evidence files.

CoinMarketCap API endpoints used
---------------------------------
1. GET https://pro-api.coinmarketcap.com/v1/cryptocurrency/listings/latest
   Params: start=1, limit=100, convert=USD, sort=market_cap,
           cryptocurrency_type=coins
2. GET https://pro-api.coinmarketcap.com/v1/global-metrics/quotes/latest
   Params: convert=USD
3. GET https://pro-api.coinmarketcap.com/v3/fear-and-greed/latest
   Optional — wrapped in try/except; skipped gracefully if the API plan
   does not allow it.

Authentication header for all calls: ``X-CMC_PRO_API_KEY: <key>``
The key is read from the ``CMC_API_KEY`` environment variable and is
never hard-coded.

Usage:
    export CMC_API_KEY=your_key_here
    python3 market_pulse.py            # live API call
    python3 market_pulse.py --demo     # offline demo from sample_data/

Only the Python standard library is used (urllib, json, os, argparse,
datetime, html, pathlib).
"""

from __future__ import annotations

import argparse
import html
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants — CoinMarketCap Pro API endpoints
# ---------------------------------------------------------------------------

BASE_URL = "https://pro-api.coinmarketcap.com"

# Endpoint 1: latest listings (top coins by market cap)
LISTINGS_ENDPOINT = "/v1/cryptocurrency/listings/latest"
LISTINGS_PARAMS = {
    "start": "1",
    "limit": "100",
    "convert": "USD",
    "sort": "market_cap",
    "cryptocurrency_type": "coins",
}

# Endpoint 2: global market metrics (total cap, volume, dominance)
GLOBAL_METRICS_ENDPOINT = "/v1/global-metrics/quotes/latest"
GLOBAL_METRICS_PARAMS = {"convert": "USD"}

# Endpoint 3 (optional): Fear & Greed index — note it lives on v3,
# while listings / global metrics live on v1.
FEAR_GREED_ENDPOINT = "/v3/fear-and-greed/latest"

ENDPOINTS_USED = [
    f"GET {BASE_URL}{LISTINGS_ENDPOINT}",
    f"GET {BASE_URL}{GLOBAL_METRICS_ENDPOINT}",
    f"GET {BASE_URL}{FEAR_GREED_ENDPOINT} (optional)",
]

ROOT = Path(__file__).resolve().parent
SAMPLE_DIR = ROOT / "sample_data"
OUTPUT_DIR = ROOT / "output"
EVIDENCE_DIR = ROOT / "evidence"

MOVERS_THRESHOLD = 5.0  # abs(percent_change_24h) >= 5% -> movers alert


# ---------------------------------------------------------------------------
# Data loading — live API or offline demo
# ---------------------------------------------------------------------------

def _api_get(endpoint: str, params: dict, api_key: str) -> tuple[dict, int]:
    """Call one CMC endpoint. Returns (parsed_json, http_status)."""
    query = urllib.parse.urlencode(params)
    url = f"{BASE_URL}{endpoint}?{query}"
    request = urllib.request.Request(
        url,
        headers={
            "Accepts": "application/json",
            "X-CMC_PRO_API_KEY": api_key,
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        body = response.read().decode("utf-8")
        return json.loads(body), response.status


def fetch_live(api_key: str) -> tuple[dict, dict, dict | None, list[dict]]:
    """Fetch listings + global metrics (+ fear & greed if available).

    Returns (listings_json, global_json, fear_greed_json_or_None, call_log).
    Each call_log entry records endpoint, url (key never included),
    http status, credit_count and timestamp for the evidence file.
    """
    call_log: list[dict] = []

    listings, status = _api_get(LISTINGS_ENDPOINT, LISTINGS_PARAMS, api_key)
    call_log.append(_log_entry(LISTINGS_ENDPOINT, LISTINGS_PARAMS, status, listings))

    global_metrics, status = _api_get(
        GLOBAL_METRICS_ENDPOINT, GLOBAL_METRICS_PARAMS, api_key
    )
    call_log.append(
        _log_entry(GLOBAL_METRICS_ENDPOINT, GLOBAL_METRICS_PARAMS, status, global_metrics)
    )

    # Optional endpoint: Fear & Greed (v3). Skip gracefully on any failure —
    # not every plan includes it, and the dashboard works without it.
    fear_greed = None
    try:
        fear_greed, status = _api_get(FEAR_GREED_ENDPOINT, {}, api_key)
        call_log.append(_log_entry(FEAR_GREED_ENDPOINT, {}, status, fear_greed))
    except (urllib.error.URLError, urllib.error.HTTPError, ValueError) as exc:
        print(f"[info] Fear & Greed endpoint skipped: {exc}", file=sys.stderr)
        call_log.append(
            {
                "endpoint": FEAR_GREED_ENDPOINT,
                "url": f"{BASE_URL}{FEAR_GREED_ENDPOINT}",
                "http_status": "skipped",
                "credit_count": 0,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "note": f"Skipped gracefully: {exc}",
            }
        )

    return listings, global_metrics, fear_greed, call_log


def _log_entry(endpoint: str, params: dict, http_status, payload: dict) -> dict:
    query = urllib.parse.urlencode(params)
    url = f"{BASE_URL}{endpoint}" + (f"?{query}" if query else "")
    status_block = payload.get("status", {}) if isinstance(payload, dict) else {}
    return {
        "endpoint": endpoint,
        "url": url,
        "http_status": http_status,
        "credit_count": status_block.get("credit_count", "n/a"),
        "timestamp": status_block.get(
            "timestamp", datetime.now(timezone.utc).isoformat()
        ),
    }


def load_demo() -> tuple[dict, dict, None, list[dict]]:
    """Load the offline sample snapshot from sample_data/ (--demo mode)."""
    with open(SAMPLE_DIR / "listings_latest.json", encoding="utf-8") as fh:
        listings = json.load(fh)
    with open(SAMPLE_DIR / "global_metrics.json", encoding="utf-8") as fh:
        global_metrics = json.load(fh)

    call_log = [
        _log_entry(LISTINGS_ENDPOINT, LISTINGS_PARAMS, 200, listings),
        _log_entry(GLOBAL_METRICS_ENDPOINT, GLOBAL_METRICS_PARAMS, 200, global_metrics),
    ]
    for entry in call_log:
        entry["note"] = "DEMO MODE: loaded from local sample_data/ snapshot, no live HTTP call."
    return listings, global_metrics, None, call_log


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

def _usd(coin: dict) -> dict:
    return coin.get("quote", {}).get("USD", {})


def _pct(coin: dict, field: str) -> float:
    value = _usd(coin).get(field)
    return float(value) if value is not None else 0.0


def analyse(listings: dict, global_metrics: dict, fear_greed: dict | None) -> dict:
    """Compute gainers, losers, movers alerts and global highlights."""
    coins = listings.get("data", [])

    by_change = sorted(coins, key=lambda c: _pct(c, "percent_change_24h"), reverse=True)
    gainers = by_change[:10]
    losers = list(reversed(by_change[-10:])) if len(by_change) >= 10 else list(reversed(by_change))
    # Losers should read most-negative first:
    losers = sorted(coins, key=lambda c: _pct(c, "percent_change_24h"))[:10]

    movers = [c for c in coins if abs(_pct(c, "percent_change_24h")) >= MOVERS_THRESHOLD]
    movers.sort(key=lambda c: abs(_pct(c, "percent_change_24h")), reverse=True)

    top20 = sorted(coins, key=lambda c: c.get("cmc_rank", 999))[:20]

    gdata = global_metrics.get("data", {})
    gusd = gdata.get("quote", {}).get("USD", {})

    fear_greed_value = None
    fear_greed_label = None
    if fear_greed:
        fg_data = fear_greed.get("data") or {}
        if isinstance(fg_data, list) and fg_data:
            fg_data = fg_data[0]
        fear_greed_value = fg_data.get("value")
        fear_greed_label = fg_data.get("value_classification")

    return {
        "coins_count": len(coins),
        "gainers": gainers,
        "losers": losers,
        "movers": movers,
        "top20": top20,
        "total_market_cap": gusd.get("total_market_cap"),
        "total_volume_24h": gusd.get("total_volume_24h"),
        "btc_dominance": gdata.get("btc_dominance"),
        "eth_dominance": gdata.get("eth_dominance"),
        "fear_greed_value": fear_greed_value,
        "fear_greed_label": fear_greed_label,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    }


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def fmt_money(value) -> str:
    if value is None:
        return "n/a"
    value = float(value)
    if abs(value) >= 1_000_000_000_000:
        return f"${value / 1_000_000_000_000:,.2f}T"
    if abs(value) >= 1_000_000_000:
        return f"${value / 1_000_000_000:,.2f}B"
    if abs(value) >= 1_000_000:
        return f"${value / 1_000_000:,.2f}M"
    return f"${value:,.2f}"


def fmt_price(value) -> str:
    if value is None:
        return "n/a"
    value = float(value)
    if value >= 1:
        return f"${value:,.2f}"
    return f"${value:,.4f}"


def fmt_pct(value) -> str:
    if value is None:
        return "n/a"
    return f"{float(value):+.2f}%"


def pct_class(value) -> str:
    if value is None:
        return ""
    return "pos" if float(value) >= 0 else "neg"


# ---------------------------------------------------------------------------
# Outputs — dashboard.html, summary.md, evidence/
# ---------------------------------------------------------------------------

def _bar_html(pct: float) -> str:
    """Simple CSS bar visualisation for a 24h % change value."""
    width = min(abs(pct) * 6, 100)  # 16.6%+ fills the bar
    cls = "bar-pos" if pct >= 0 else "bar-neg"
    return (
        f'<div class="bar-wrap"><div class="bar {cls}" '
        f'style="width:{width:.0f}%"></div></div>'
    )


def _coin_rows(coins: list[dict], with_bar: bool = False) -> str:
    rows = []
    for coin in coins:
        usd = _usd(coin)
        change = _pct(coin, "percent_change_24h")
        bar = f"<td>{_bar_html(change)}</td>" if with_bar else ""
        rows.append(
            "<tr>"
            f"<td>{coin.get('cmc_rank', '')}</td>"
            f"<td><strong>{html.escape(str(coin.get('symbol', '')))}</strong> "
            f"{html.escape(str(coin.get('name', '')))}</td>"
            f"<td>{fmt_price(usd.get('price'))}</td>"
            f'<td class="{pct_class(usd.get("percent_change_1h"))}">{fmt_pct(usd.get("percent_change_1h"))}</td>'
            f'<td class="{pct_class(change)}">{fmt_pct(change)}</td>'
            f'<td class="{pct_class(usd.get("percent_change_7d"))}">{fmt_pct(usd.get("percent_change_7d"))}</td>'
            f"<td>{fmt_money(usd.get('market_cap'))}</td>"
            f"<td>{fmt_money(usd.get('volume_24h'))}</td>"
            f"{bar}"
            "</tr>"
        )
    return "\n".join(rows)


_TABLE_HEAD = (
    "<tr><th>#</th><th>Coin</th><th>Price</th><th>1h %</th><th>24h %</th>"
    "<th>7d %</th><th>Market Cap</th><th>24h Volume</th></tr>"
)


def build_dashboard(analysis: dict, demo: bool) -> str:
    """Render the single self-contained HTML dashboard (inline CSS only)."""
    fg_card = ""
    if analysis["fear_greed_value"] is not None:
        fg_card = (
            '<div class="card"><div class="label">Fear &amp; Greed</div>'
            f'<div class="value">{analysis["fear_greed_value"]}</div>'
            f'<div class="sub">{html.escape(str(analysis["fear_greed_label"] or ""))}</div></div>'
        )

    alerts = analysis["movers"]
    if alerts:
        alert_items = "\n".join(
            f'<li><strong>{html.escape(str(c.get("symbol", "")))}</strong> '
            f'{html.escape(str(c.get("name", "")))} — '
            f'<span class="{pct_class(_pct(c, "percent_change_24h"))}">'
            f'{fmt_pct(_pct(c, "percent_change_24h"))} in 24h</span></li>'
            for c in alerts
        )
        alerts_html = f"<ul class='alerts'>{alert_items}</ul>"
    else:
        alerts_html = "<p>No coins moved ±5% or more in the last 24h.</p>"

    mode_note = (
        '<p class="demo-note">DEMO MODE — figures come from the local '
        "sample_data/ snapshot (captured CMC response shape), not a live call.</p>"
        if demo
        else ""
    )
    endpoints_footer = "<br>".join(html.escape(e) for e in ENDPOINTS_USED)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>CMC Market Pulse</title>
<style>
  :root {{ color-scheme: dark; }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
         background:#0b0e14; color:#e6e9ef; }}
  header {{ padding:28px 24px 8px; }}
  h1 {{ margin:0 0 4px; font-size:28px; }}
  h2 {{ margin:28px 0 10px; font-size:19px; }}
  main {{ padding:0 24px 32px; max-width:1100px; margin:0 auto; }}
  .muted {{ color:#8b93a7; }}
  .demo-note {{ background:#3a2f10; border:1px solid #8a6d1a; color:#f5d97a;
               padding:10px 14px; border-radius:8px; }}
  .cards {{ display:flex; flex-wrap:wrap; gap:12px; margin:18px 0 4px; }}
  .card {{ background:#141926; border:1px solid #232a3d; border-radius:10px;
          padding:14px 18px; min-width:170px; flex:1; }}
  .card .label {{ color:#8b93a7; font-size:12px; text-transform:uppercase; letter-spacing:.06em; }}
  .card .value {{ font-size:22px; font-weight:700; margin-top:4px; }}
  .card .sub {{ color:#8b93a7; font-size:13px; }}
  table {{ width:100%; border-collapse:collapse; background:#111624; border-radius:10px; overflow:hidden; }}
  th, td {{ padding:8px 10px; text-align:right; border-bottom:1px solid #1e2537; font-size:14px; }}
  th {{ color:#8b93a7; font-weight:600; }}
  td:nth-child(2), th:nth-child(2) {{ text-align:left; }}
  td:first-child, th:first-child {{ text-align:left; }}
  .pos {{ color:#2ebd85; }} .neg {{ color:#f6465d; }}
  .alerts li {{ margin:6px 0; }}
  .bar-wrap {{ background:#1e2537; border-radius:4px; width:90px; height:8px; }}
  .bar {{ height:8px; border-radius:4px; }}
  .bar-pos {{ background:#2ebd85; }} .bar-neg {{ background:#f6465d; }}
  footer {{ padding:18px 24px 28px; color:#8b93a7; font-size:13px; max-width:1100px; margin:0 auto; }}
</style>
</head>
<body>
<header>
  <h1>📈 CMC Market Pulse</h1>
  <p class="muted">Crypto market screener powered by the CoinMarketCap API — generated {analysis['generated_at']}</p>
  {mode_note}
</header>
<main>
  <section class="cards">
    <div class="card"><div class="label">Total Market Cap</div><div class="value">{fmt_money(analysis['total_market_cap'])}</div></div>
    <div class="card"><div class="label">24h Volume</div><div class="value">{fmt_money(analysis['total_volume_24h'])}</div></div>
    <div class="card"><div class="label">BTC Dominance</div><div class="value">{analysis['btc_dominance'] if analysis['btc_dominance'] is not None else 'n/a'}%</div></div>
    <div class="card"><div class="label">ETH Dominance</div><div class="value">{analysis['eth_dominance'] if analysis['eth_dominance'] is not None else 'n/a'}%</div></div>
    {fg_card}
  </section>

  <h2>🚀 Top 10 Gainers (24h)</h2>
  <table>{_TABLE_HEAD}{_coin_rows(analysis['gainers'])}</table>

  <h2>📉 Top 10 Losers (24h)</h2>
  <table>{_TABLE_HEAD}{_coin_rows(analysis['losers'])}</table>

  <h2>🔔 Movers Alert — |24h change| ≥ 5% ({len(alerts)} coins)</h2>
  {alerts_html}

  <h2>🏆 Top 20 by Market Cap</h2>
  <table>{_TABLE_HEAD}<th>24h bar</th>{_coin_rows(analysis['top20'], with_bar=True)}</table>
</main>
<footer>
  Data: CoinMarketCap API — endpoints used:<br>{endpoints_footer}<br>
  Built for the DoraHacks “Build with CMC: API Hackathon” — Markets &amp; Trading Tools track.
</footer>
</body>
</html>
"""


def build_summary(analysis: dict, demo: bool) -> str:
    """Render the Markdown summary."""
    lines = [
        "# CMC Market Pulse — Summary",
        "",
        f"_Generated {analysis['generated_at']}_"
        + (" — **DEMO MODE** (local sample_data/ snapshot, not live data)" if demo else ""),
        "",
        "## Global Market",
        "",
        f"- **Total market cap:** {fmt_money(analysis['total_market_cap'])}",
        f"- **24h volume:** {fmt_money(analysis['total_volume_24h'])}",
        f"- **BTC dominance:** {analysis['btc_dominance'] if analysis['btc_dominance'] is not None else 'n/a'}%",
        f"- **ETH dominance:** {analysis['eth_dominance'] if analysis['eth_dominance'] is not None else 'n/a'}%",
    ]
    if analysis["fear_greed_value"] is not None:
        lines.append(
            f"- **Fear & Greed:** {analysis['fear_greed_value']} ({analysis['fear_greed_label']})"
        )

    def section(title: str, coins: list[dict]) -> None:
        lines.extend(["", f"## {title}", "", "| # | Coin | Price | 24h % | Market Cap |", "|---|---|---|---|---|"])
        for c in coins:
            usd = _usd(c)
            lines.append(
                f"| {c.get('cmc_rank', '')} | {c.get('symbol', '')} {c.get('name', '')} "
                f"| {fmt_price(usd.get('price'))} | {fmt_pct(_pct(c, 'percent_change_24h'))} "
                f"| {fmt_money(usd.get('market_cap'))} |"
            )

    section("Top 10 Gainers (24h)", analysis["gainers"])
    section("Top 10 Losers (24h)", analysis["losers"])

    lines += ["", f"## Movers Alert — |24h change| ≥ 5% ({len(analysis['movers'])} coins)", ""]
    if analysis["movers"]:
        for c in analysis["movers"]:
            lines.append(
                f"- **{c.get('symbol', '')}** {c.get('name', '')} — {fmt_pct(_pct(c, 'percent_change_24h'))} in 24h"
            )
    else:
        lines.append("No coins moved ±5% or more in the last 24h.")

    lines += [
        "",
        "## Endpoints used",
        "",
        *[f"- `{e}`" for e in ENDPOINTS_USED],
        "",
        "_Data: CoinMarketCap API._",
        "",
    ]
    return "\n".join(lines)


def write_evidence(listings: dict, global_metrics: dict, call_log: list[dict], demo: bool) -> None:
    """Write trimmed responses + an API call log (key redacted) to evidence/."""
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

    trimmed = {
        "status": listings.get("status", {}),
        "data": listings.get("data", [])[:3],
        "_note": "Trimmed to the first 3 items; full response shape preserved. "
                 + ("Demo snapshot." if demo else "Live response."),
    }
    with open(EVIDENCE_DIR / "listings_latest_sample.json", "w", encoding="utf-8") as fh:
        json.dump(trimmed, fh, indent=2)

    with open(EVIDENCE_DIR / "global_metrics.json", "w", encoding="utf-8") as fh:
        json.dump(global_metrics, fh, indent=2)

    lines = [
        "CMC Market Pulse — API call log",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        f"Mode: {'DEMO (local sample_data/, no live HTTP call)' if demo else 'LIVE'}",
        "Auth header: X-CMC_PRO_API_KEY: *** (redacted)",
        "",
    ]
    for entry in call_log:
        lines.append(f"Request: GET {entry['url']}")
        lines.append("Header:  X-CMC_PRO_API_KEY: ***")
        lines.append(f"HTTP status: {entry['http_status']}")
        lines.append(f"credit_count (from API status block): {entry['credit_count']}")
        lines.append(f"Timestamp: {entry['timestamp']}")
        if entry.get("note"):
            lines.append(f"Note: {entry['note']}")
        lines.append("")
    with open(EVIDENCE_DIR / "api_call_log.txt", "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


def print_terminal(analysis: dict, demo: bool) -> None:
    """Print a readable terminal table."""
    print("=" * 72)
    print(f"CMC MARKET PULSE — {analysis['generated_at']}" + ("  [DEMO MODE]" if demo else ""))
    print("=" * 72)
    print(f"Total market cap : {fmt_money(analysis['total_market_cap'])}")
    print(f"24h volume       : {fmt_money(analysis['total_volume_24h'])}")
    print(f"BTC dominance    : {analysis['btc_dominance']}%   ETH dominance: {analysis['eth_dominance']}%")
    if analysis["fear_greed_value"] is not None:
        print(f"Fear & Greed     : {analysis['fear_greed_value']} ({analysis['fear_greed_label']})")
    print(f"Coins screened   : {analysis['coins_count']}")
    print()
    header = f"{'#':>3}  {'SYM':<6} {'PRICE':>14} {'24H %':>9} {'MARKET CAP':>14}"
    for title, coins in (("TOP GAINERS (24H)", analysis["gainers"]),
                         ("TOP LOSERS (24H)", analysis["losers"])):
        print(f"--- {title} ---")
        print(header)
        for c in coins:
            usd = _usd(c)
            print(
                f"{c.get('cmc_rank', 0):>3}  {str(c.get('symbol', '')):<6} "
                f"{fmt_price(usd.get('price')):>14} {fmt_pct(_pct(c, 'percent_change_24h')):>9} "
                f"{fmt_money(usd.get('market_cap')):>14}"
            )
        print()
    print(f"--- MOVERS ALERT (|24h| >= {MOVERS_THRESHOLD:.0f}%): {len(analysis['movers'])} coins ---")
    for c in analysis["movers"]:
        print(f"  {c.get('symbol', ''):<6} {c.get('name', ''):<14} {fmt_pct(_pct(c, 'percent_change_24h'))}")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="CMC Market Pulse — CoinMarketCap API screener + dashboard generator."
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Offline demo: load sample_data/ instead of calling the live API.",
    )
    args = parser.parse_args(argv)

    if args.demo:
        listings, global_metrics, fear_greed, call_log = load_demo()
    else:
        api_key = os.environ.get("CMC_API_KEY")
        if not api_key:
            print(
                "ERROR: CMC_API_KEY is not set.\n"
                "Get a free key at https://coinmarketcap.com/api, then:\n"
                "  cp .env.example .env   # and paste your key (never commit .env)\n"
                "  export CMC_API_KEY=your_key_here\n"
                "Or run offline with:  python3 market_pulse.py --demo",
                file=sys.stderr,
            )
            return 2
        try:
            listings, global_metrics, fear_greed, call_log = fetch_live(api_key)
        except (urllib.error.URLError, urllib.error.HTTPError, ValueError) as exc:
            print(f"ERROR: CoinMarketCap API call failed: {exc}", file=sys.stderr)
            return 1

    analysis = analyse(listings, global_metrics, fear_greed)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_DIR / "dashboard.html", "w", encoding="utf-8") as fh:
        fh.write(build_dashboard(analysis, demo=args.demo))
    with open(OUTPUT_DIR / "summary.md", "w", encoding="utf-8") as fh:
        fh.write(build_summary(analysis, demo=args.demo))
    write_evidence(listings, global_metrics, call_log, demo=args.demo)

    print_terminal(analysis, demo=args.demo)
    print(f"Wrote: {OUTPUT_DIR / 'dashboard.html'}")
    print(f"Wrote: {OUTPUT_DIR / 'summary.md'}")
    print(f"Wrote: {EVIDENCE_DIR}/ (listings_latest_sample.json, global_metrics.json, api_call_log.txt)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

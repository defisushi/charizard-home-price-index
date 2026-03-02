#!/usr/bin/env python3
"""
update_data.py
Fetches latest Charizard prices from PriceCharting and
Singapore/NYC/London/Tokyo home prices, then rewrites index.html.
Runs weekly via GitHub Actions.
"""

import re
import json
import datetime
import urllib.request
from bs4 import BeautifulSoup

def fetch(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {
        "User-Agent": "Mozilla/5.0 (compatible; HomeZardBot/1.0)"
    })
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read().decode("utf-8")

def today():
    d = datetime.date.today()
    return f"{d.year}-{d.month:02d}"

def get_fx_rate(from_currency):
    """Fetch live FX rate to USD using open.er-api.com (free, no key needed)"""
    try:
        data = fetch(f"https://open.er-api.com/v6/latest/{from_currency}")
        return json.loads(data)["rates"]["USD"]
    except Exception as e:
        print(f"  [warn] FX rate {from_currency}/USD failed: {e}")
        fallbacks = {"SGD": 0.741, "GBP": 1.262, "JPY": 0.00660, "USD": 1.0}
        return fallbacks.get(from_currency, 1.0)

# ── Charizard prices via PriceCharting ─────────────────────────────────────
# PriceCharting table columns: Ungraded | Gr7 | Gr8 | Gr9 | Gr9.5 | PSA10
# We target the "prices" table with id="full-prices"

PRICECHARTING_CARDS = {
    "base-charizard-1st-psa10": {
        "url": "https://www.pricecharting.com/game/pokemon-base-set/charizard-1st-edition-4",
        "grade_col": 5,   # PSA 10 column (0-indexed)
        "fallback": 166738
    },
    "base-charizard-1st-ungraded": {
        "url": "https://www.pricecharting.com/game/pokemon-base-set/charizard-1st-edition-4",
        "grade_col": 0,   # Ungraded column
        "fallback": 5551
    },
    "base-charizard-unlimited-psa10": {
        "url": "https://www.pricecharting.com/game/pokemon-base-set/charizard-4",
        "grade_col": 5,   # PSA 10 column
        "fallback": 16168
    },
    "base-charizard-unlimited-ungraded": {
        "url": "https://www.pricecharting.com/game/pokemon-base-set/charizard-4",
        "grade_col": 0,   # Ungraded column
        "fallback": 260
    },
}

def fetch_card_price(card_id):
    info = PRICECHARTING_CARDS[card_id]
    try:
        html = fetch(info["url"])
        soup = BeautifulSoup(html, "html.parser")
        # PriceCharting shows prices in a table — grab the header row prices
        # They appear as: $X,XXX.XX in the first table row after the header
        price_cells = soup.select("table#full-prices td.price")
        if not price_cells:
            # Fallback: grab all .price spans from the price box
            price_cells = soup.select(".price")
        if price_cells and info["grade_col"] < len(price_cells):
            raw = price_cells[info["grade_col"]].get_text(strip=True)
            raw = raw.replace("$", "").replace(",", "").strip()
            # Remove any +/- change suffix
            raw = raw.split()[0] if raw else ""
            val = float(raw)
            if val > 0:
                return val
    except Exception as e:
        print(f"  [warn] {card_id}: {e}")
    return info["fallback"]

# ── Home prices via Numbeo + live FX to USD ─────────────────────────────────

NUMBEO_CITIES = {
    "median-home-singapore": {"city": "Singapore", "currency": "SGD", "sqm": 85, "fallback": 1200000},
    "median-home-nyc":       {"city": "New-York",  "currency": "USD", "sqm": 85, "fallback": 780000},
    "median-home-london":    {"city": "London",    "currency": "GBP", "sqm": 85, "fallback": 650000},
    "median-home-tokyo":     {"city": "Tokyo",     "currency": "JPY", "sqm": 70, "fallback": 450000},
}

def fetch_home_price(asset_id):
    info = NUMBEO_CITIES[asset_id]
    try:
        url = f"https://www.numbeo.com/cost-of-living/in/{info['city']}"
        html = fetch(url)
        soup = BeautifulSoup(html, "html.parser")
        for row in soup.select("table.data_wide_table tr"):
            cells = row.find_all("td")
            if len(cells) >= 2 and "Buy" in cells[0].get_text() and "City Centre" in cells[0].get_text():
                raw = cells[1].get_text(strip=True).replace(",", "").split()[0]
                price_per_sqm = float(raw)
                local_price = price_per_sqm * info["sqm"]
                if info["currency"] != "USD":
                    fx = get_fx_rate(info["currency"])
                    usd_price = local_price * fx
                    print(f"    [{info['currency']}->USD @ {fx:.4f}] {local_price:,.0f} = ${usd_price:,.0f}")
                else:
                    usd_price = local_price
                return round(usd_price)
    except Exception as e:
        print(f"  [warn] {asset_id}: {e}")
    return info["fallback"]

# ── Update index.html ────────────────────────────────────────────────────────

def update_html(card_prices, home_prices):
    with open("index.html", "r", encoding="utf-8") as f:
        html = f.read()
    date = today()

    for card_id, price in card_prices.items():
        pattern = rf'({{[^}}]*id:\s*"{re.escape(card_id)}"[^}}]*currentPrice:\s*)([\d.]+)'
        html = re.sub(pattern, lambda m, p=price: m.group(1) + str(int(p)), html, flags=re.DOTALL)

    for asset_id, value in home_prices.items():
        pattern = rf'({{[^}}]*id:\s*"{re.escape(asset_id)}"[^}}]*currentValue:\s*)([\d.]+)'
        html = re.sub(pattern, lambda m, v=value: m.group(1) + str(int(v)), html, flags=re.DOTALL)

    for card_id, price in card_prices.items():
        needle = f'id: "{card_id}"'
        idx = html.find(needle)
        if idx == -1:
            continue
        block_end = html.find("]}", idx)
        if date not in html[idx:block_end]:
            html = html[:block_end] + f',\n    {{date:"{date}",price:{int(price)}}}' + html[block_end:]

    for asset_id, value in home_prices.items():
        needle = f'id: "{asset_id}"'
        idx = html.find(needle)
        if idx == -1:
            continue
        block_end = html.find("]}", idx)
        if date not in html[idx:block_end]:
            html = html[:block_end] + f',\n    {{date:"{date}",value:{int(value)}}}' + html[block_end:]

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"index.html updated for {date}")

# ── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Fetching Charizard prices from PriceCharting...")
    card_prices = {}
    for card_id in PRICECHARTING_CARDS:
        p = fetch_card_price(card_id)
        card_prices[card_id] = p
        print(f"  {card_id}: ${p:,.0f}")

    print("Fetching home prices (converting to USD)...")
    home_prices = {}
    for asset_id in NUMBEO_CITIES:
        v = fetch_home_price(asset_id)
        home_prices[asset_id] = v
        print(f"  {asset_id}: ${v:,.0f} USD")

    update_html(card_prices, home_prices)
    print("Done!")

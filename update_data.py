#!/usr/bin/env python3
"""
update_data.py
Fetches latest Charizard prices from PriceCharting and
Singapore/NYC/London/Tokyo home prices, then rewrites index.html.
Runs weekly via GitHub Actions.
"""

import re
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

# Charizard prices via PriceCharting
PRICECHARTING_CARDS = {
    "base-charizard-1st-psa10": {
        "url": "https://www.pricecharting.com/game/pokemon-base-set-1st-edition/charizard-4",
        "selector": "#used_price .price",
        "fallback": 420000
    },
    "base-charizard-1st-ungraded": {
        "url": "https://www.pricecharting.com/game/pokemon-base-set-1st-edition/charizard-4",
        "selector": "#complete_price .price",
        "fallback": 10000
    },
    "base-charizard-unlimited-psa10": {
        "url": "https://www.pricecharting.com/game/pokemon-base-set/charizard-4",
        "selector": "#used_price .price",
        "fallback": 7500
    },
    "base-charizard-unlimited-ungraded": {
        "url": "https://www.pricecharting.com/game/pokemon-base-set/charizard-4",
        "selector": "#complete_price .price",
        "fallback": 350
    },
}

def fetch_card_price(card_id):
    info = PRICECHARTING_CARDS[card_id]
    try:
        html = fetch(info["url"])
        soup = BeautifulSoup(html, "html.parser")
        el = soup.select_one(info["selector"])
        if el:
            raw = el.get_text(strip=True).replace("$", "").replace(",", "")
            return float(raw)
    except Exception as e:
        print(f"  [warn] {card_id}: {e}")
    return info["fallback"]

# Home prices via Numbeo
NUMBEO_CITIES = {
    "median-home-singapore": {"city": "Singapore",  "fallback": 1200000},
    "median-home-nyc":       {"city": "New-York",   "fallback": 780000},
    "median-home-london":    {"city": "London",     "fallback": 650000},
    "median-home-tokyo":     {"city": "Tokyo",      "fallback": 450000},
}

def fetch_home_price(asset_id):
    info = NUMBEO_CITIES[asset_id]
    try:
        url = f"https://www.numbeo.com/cost-of-living/in/{info['city']}"
        html = fetch(url)
        soup = BeautifulSoup(html, "html.parser")
        rows = soup.select("table.data_wide_table tr")
        for row in rows:
            cells = row.find_all("td")
            if len(cells) >= 2 and "City Centre" in cells[0].get_text():
                raw = cells[1].get_text(strip=True).replace(",", "").replace("$", "").split()[0]
                price_per_sqm = float(raw)
                return round(price_per_sqm * 85)  # assume 85 sqm median apartment
    except Exception as e:
        print(f"  [warn] {asset_id}: {e}")
    return info["fallback"]

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
            new_entry = f'{{date:"{date}",price:{int(price)}}}'
            html = html[:block_end] + f",\n    {new_entry}" + html[block_end:]

    for asset_id, value in home_prices.items():
        needle = f'id: "{asset_id}"'
        idx = html.find(needle)
        if idx == -1:
            continue
        block_end = html.find("]}", idx)
        if date not in html[idx:block_end]:
            new_entry = f'{{date:"{date}",value:{int(value)}}}'
            html = html[:block_end] + f",\n    {new_entry}" + html[block_end:]

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"index.html updated for {date}")

if __name__ == "__main__":
    print("Fetching Charizard prices...")
    card_prices = {}
    for card_id in PRICECHARTING_CARDS:
        p = fetch_card_price(card_id)
        card_prices[card_id] = p
        print(f"  {card_id}: ${p:,.0f}")

    print("Fetching home prices...")
    home_prices = {}
    for asset_id in NUMBEO_CITIES:
        v = fetch_home_price(asset_id)
        home_prices[asset_id] = v
        print(f"  {asset_id}: ${v:,.0f}")

    update_html(card_prices, home_prices)
    print("Done!")

import requests
from statistics import mean

COINGECKO_BASE = "https://api.coingecko.com/api/v3"

def fetch_market_analytics(coin_id):
    url = f"{COINGECKO_BASE}/coins/{coin_id}/market_chart?vs_currency=usd&days=1"
    try:
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            prices = res.json()["prices"]
            current_price = prices[-1][1]
            past_price = prices[-16][1] if len(prices) > 16 else prices[0][1]
            price_change_pct = ((current_price - past_price) / past_price) * 100
            return current_price, price_change_pct
        return None, None
    except Exception:
        return None, None

def fetch_instant_price(coin_id):
    url = f"{COINGECKO_BASE}/simple/price?ids={coin_id}&vs_currencies=usd&include_24hr_change=true"
    try:
        res = requests.get(url, timeout=10).json()
        if coin_id in res:
            return res[coin_id]["usd"], res[coin_id]["usd_24h_change"]
        return None, None
    except Exception:
        return None, None

def fetch_eth_gas():
    try:
        res = requests.get("https://api.etherscan.io/v2/api?chainid=1&module=gastracker&action=gasoracle", timeout=10).json()
        if res.get("status") == "1":
            result = res["result"]
            return result.get("ProposeGasPrice", "?"), result.get("FastGasPrice", "?")
        return "?", "?"
    except Exception:
        return "?", "?"

def analyze_market(coin_id):
    """Returns (direction, confidence, current_price, target_price, summary, signal_emoji)
    direction: 'bullish', 'bearish', 'neutral'
    confidence: int 0-100
    current_price: latest price
    target_price: predicted target (rise to / drop to)
    summary: short explanation
    signal_emoji: 🟢 / 🔴 / ⚪
    """
    try:
        url = f"{COINGECKO_BASE}/coins/{coin_id}/market_chart?vs_currency=usd&days=7"
        res = requests.get(url, timeout=10)
        if res.status_code != 200:
            return None, None, None, None, None, None
        prices = [p[1] for p in res.json()["prices"]]
        if len(prices) < 24:
            return None, None, None, None, None, None

        current = prices[-1]
        sma_24 = mean(prices[-24:])
        sma_7 = mean(prices[-7:])
        low_24 = min(prices[-24:])
        high_24 = max(prices[-24:])

        change_4h = ((prices[-1] - prices[-5]) / prices[-5]) * 100 if len(prices) >= 5 else 0
        change_24h = ((prices[-1] - prices[-25]) / prices[-25]) * 100 if len(prices) >= 25 else 0
        change_7d = ((prices[-1] - prices[0]) / prices[0]) * 100

        bullish = 0
        bearish = 0
        reasons = []

        if current > sma_24:
            bullish += 1
            reasons.append("Price above 24h average")
        else:
            bearish += 1
            reasons.append("Price below 24h average")

        if current > sma_7:
            bullish += 1
            reasons.append("Short-term trend up")
        else:
            bearish += 1
            reasons.append("Short-term trend down")

        if change_4h > 0.5:
            bullish += 1
        elif change_4h < -0.5:
            bearish += 1

        if change_24h > 1:
            bullish += 1
            reasons.append("Strong 24h momentum")
        elif change_24h < -1:
            bearish += 1
            reasons.append("Negative 24h momentum")
        else:
            if change_24h > 0:
                reasons.append("Slight upward drift")
            elif change_24h < 0:
                reasons.append("Slight downward drift")

        if change_4h > change_24h:
            bullish += 1
            reasons.append("Momentum building")
        else:
            bearish += 1
            reasons.append("Momentum slowing")

        range_pos = (current - low_24) / (high_24 - low_24) * 100 if high_24 != low_24 else 50
        if range_pos < 25:
            bullish += 1
            reasons.append("Near 24h low - potential bounce")
        elif range_pos > 75:
            bearish += 1
            reasons.append("Near 24h high - potential resistance")

        total = bullish + bearish
        if total == 0:
            return None, None, None, None, None, None

        move_pct = abs(change_24h) * 3
        move_pct = max(move_pct, 10.0)

        if bullish > bearish and move_pct >= 10:
            direction = "bullish"
            confidence = int((bullish / total) * 100)
            signal_emoji = "🟢"
            target_price = round(current * (1 + move_pct / 100), 2)
            summary = "; ".join(reasons[:3])
        elif bearish > bullish and move_pct >= 10:
            direction = "bearish"
            confidence = int((bearish / total) * 100)
            signal_emoji = "🔴"
            target_price = round(current * (1 - move_pct / 100), 2)
            summary = "; ".join(reasons[:3])
        else:
            return None, None, None, None, None, None

        return direction, confidence, current, target_price, summary, signal_emoji

    except Exception:
        return None, None, None, None, None, None

def fetch_trending_coins():
    """Returns list of trending/hot coin IDs from CoinGecko."""
    try:
        res = requests.get(f"{COINGECKO_BASE}/search/trending", timeout=10)
        if res.status_code != 200:
            return []
        coins = res.json().get("coins", [])
        return [c["item"]["id"] for c in coins[:10]]
    except Exception:
        return []

def fetch_volatile_coins():
    """Returns top gainers & losers by 24h change."""
    try:
        url = f"{COINGECKO_BASE}/coins/markets?vs_currency=usd&order=volume_desc&per_page=50&page=1&sparkline=false"
        res = requests.get(url, timeout=10)
        if res.status_code != 200:
            return []
        coins = res.json()
        volatile = []
        for c in coins:
            change = c.get("price_change_percentage_24h", 0)
            if change is not None and abs(change) >= 8:
                volatile.append((c["id"], change))
        volatile.sort(key=lambda x: abs(x[1]), reverse=True)
        return [v[0] for v in volatile[:10]]
    except Exception:
        return []

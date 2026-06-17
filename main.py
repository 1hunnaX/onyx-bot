import os
import time
import random
import threading
import asyncio
from http.server import HTTPServer, BaseHTTPRequestHandler
import xml.etree.ElementTree as ET
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, CallbackQueryHandler, filters
import requests

import database as db
import analytics as ana

load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")
MIN_COIN_PRICE = 1.0

DEFAULT_SETTINGS = {"risk_mode": "Safe", "alerts": "ON", "hot_discovery": "ON", "balance": 1000.0}

def get_user_settings(settings_db, user_id):
    raw = settings_db.get(user_id, {})
    merged = dict(DEFAULT_SETTINGS)
    merged.update(raw)
    return merged

async def set_bot_commands(application: Application):
    commands = [
        BotCommand("start", "Start the bot"),
        BotCommand("help", "See all commands"),
        BotCommand("watch", "Set a price alert (e.g. /watch solana 140)"),
        BotCommand("status", "View your active alerts"),
        BotCommand("price", "Check a coin's current price"),
        BotCommand("trend", "See if a coin is going up or down"),
        BotCommand("gas", "Check network fees"),
        BotCommand("news", "Latest crypto news"),
        BotCommand("portfolio", "View your balance and settings"),
        BotCommand("setbalance", "Set your trading balance"),
        BotCommand("settings", "Change risk mode or alerts"),
        BotCommand("clear", "Clear all your alerts"),
        BotCommand("predict", "Detect major pumps & dumps"),
        BotCommand("unpredict", "Stop watching a coin"),
        BotCommand("predictions", "View your prediction list"),
        BotCommand("discover", "Find hot volatile coins to track"),
        BotCommand("clear_predictions", "Remove all predictions from your watchlist")
    ]
    await application.bot.set_my_commands(commands)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    first_name = update.effective_user.first_name
    users_interacted = db.load_db(db.USER_DB_FILE)
    divider = "━" * 25

    if user_id not in users_interacted:
        welcome_text = (
            f"🤖 *Hey {first_name}! I'm onyX.*\n"
            f"{divider}\n"
            f"Your crypto wingman. I track prices, predict pumps & dumps, and alert you when it's time to buy.\n\n"
            f"👉 Type `/help` to see all commands\n"
            f"👉 Or just drop a coin name!"
        )
        users_interacted[user_id] = {"joined": time.time(), "greeted": True}
        db.save_db(users_interacted, db.USER_DB_FILE)
        user_settings = db.load_db(db.SETTINGS_DB_FILE)
        if user_id not in user_settings:
            user_settings[user_id] = dict(DEFAULT_SETTINGS)
            db.save_db(user_settings, db.SETTINGS_DB_FILE)
    else:
        welcome_text = f"👋 *Welcome back, {first_name}!* Drop a coin name or type `/help`."

    await update.message.reply_text(welcome_text, parse_mode="Markdown")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    d = "━" * 25
    help_map = (
        f"📖 *onyX Commands*\n"
        f"{d}\n"
        f"📊 *Market Data*\n"
        f"🔹 `/price [coin]` — Price & 24h change\n"
        f"🔹 `/trend [coin]` — 4h trend check\n"
        f"🔹 `/gas` — Live ETH fees\n"
        f"🔹 `/news` — Crypto headlines\n"
        f"{d}\n"
        f"🔔 *Alerts*\n"
        f"🔹 `/watch [coin] [price]` — Set buy alert\n"
        f"🔹 `/status` — View active alerts\n"
        f"🔹 `/clear` — Remove all alerts\n"
        f"{d}\n"
        f"🔮 *Predictions*\n"
        f"🔹 `/predict [coin]` — Track for pumps & dumps\n"
        f"🔹 `/unpredict [coin]` — Stop tracking\n"
        f"🔹 `/predictions` — Your prediction list\n"
        f"🔹 `/clear_predictions` — Wipe predictions\n"
        f"🔹 `/discover` — Find hot coins\n"
        f"{d}\n"
        f"💳 *Account*\n"
        f"🔹 `/setbalance [amount]` — Set wallet size\n"
        f"🔹 `/portfolio` — View balance & stats\n"
        f"🔹 `/settings` — Toggle risk/alerts\n"
        f"🔹 `/help` — Show this"
    )
    await update.message.reply_text(help_map, parse_mode="Markdown")

async def watch_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    watchlist = db.load_db(db.WATCH_DB_FILE)
    divider = "━" * 25
    try:
        coin = context.args[0].lower()
        target_price = float(context.args[1])

        if user_id not in watchlist:
            watchlist[user_id] = {}
        watchlist[user_id][coin] = target_price
        db.save_db(watchlist, db.WATCH_DB_FILE)

        await update.message.reply_text(
            f"✅ *Alert Set!*\n{divider}\n"
            f"🪙 Coin:  *{coin.upper()}*\n"
            f"🎯 Alert: *${target_price:,}*\n{divider}\n"
            f"I'll ping you when it drops to this level.",
            parse_mode="Markdown"
        )
    except (IndexError, ValueError):
        await update.message.reply_text(
            f"⚠️ *Usage:*\n{divider}\n"
            f"`/watch [coin] [price]`\n{divider}\n"
            f"📌 `/watch solana 120`",
            parse_mode="Markdown"
        )

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    watchlist = db.load_db(db.WATCH_DB_FILE)
    user_tracks = watchlist.get(str(update.effective_user.id), {})
    divider = "━" * 25
    if not user_tracks:
        await update.message.reply_text(
            f"📭 *No Alerts Set*\n{divider}\n"
            f"Use `/watch [coin] [price]` to add one.\n{divider}\n"
            f"📌 `/watch solana 120`",
            parse_mode="Markdown"
        )
        return
    summary = f"📋 *Your Alerts ({len(user_tracks)})*\n{divider}\n"
    for coin, target in user_tracks.items():
        summary += f"🔸 *{coin.upper()}*  →  *${target:,}*\n"
    summary += f"{divider}\n💡 `/clear` to remove all"
    await update.message.reply_text(summary, parse_mode="Markdown")

async def price_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        coin = context.args[0].lower()
        price, change = await asyncio.to_thread(ana.fetch_instant_price, coin)
        divider = "━" * 25
        if price is not None:
            arrow = "📈" if change >= 0 else "📉"
            sign = "+" if change >= 0 else ""
            await update.message.reply_text(
                f"💰 *{coin.upper()}*\n{divider}\n"
                f"💵 Price:  *${price:,.2f}*\n"
                f"{arrow} 24h:    *{sign}{change:.2f}%*",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(f"❌ *Not Found*\n{divider}\nCouldn't find *{coin}*. Check the name and try again.", parse_mode="Markdown")
    except (IndexError, ValueError):
        await update.message.reply_text(f"⚠️ *Usage:*\n{divider}\n`/price [coin]`\n📌 `/price bitcoin`", parse_mode="Markdown")

async def trend_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        coin = context.args[0].lower()
        await update.message.reply_text(f"⏳ Checking *{coin.upper()}*...")
        price, trend = await asyncio.to_thread(ana.fetch_market_analytics, coin)
        divider = "━" * 25
        if price is not None:
            sign = "+" if trend >= 0 else ""
            if trend > 2.0:
                status = "🔥 *PUMPING*"
            elif trend < -2.0:
                status = "❄️ *DUMPING*"
            else:
                status = "⚖️ *SIDEWAYS*"
            await update.message.reply_text(
                f"📊 *{coin.upper()} — 4h Trend*\n{divider}\n"
                f"💵 Price:   *${price:,.2f}*\n"
                f"📊 4h Chg:  *{sign}{trend:.2f}%*\n{divider}\n"
                f"{status}",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(f"❌ *Not Found*\n{divider}\nCouldn't find *{coin}*.", parse_mode="Markdown")
    except IndexError:
        await update.message.reply_text(f"⚠️ *Usage:*\n{divider}\n`/trend [coin]`\n📌 `/trend bitcoin`", parse_mode="Markdown")

async def gas_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    standard, fast = await asyncio.to_thread(ana.fetch_eth_gas)
    divider = "━" * 25
    await update.message.reply_text(
        f"⛽ *Network Fees*\n{divider}\n"
        f"🔹 *Ethereum*\n"
        f"   Standard:  *{standard} Gwei*\n"
        f"   Fast:      *{fast} Gwei*\n{divider}\n"
        f"🔹 *Solana*  ✅  ~0.00001 SOL\n{divider}\n"
        f"📡 Live from Etherscan",
        parse_mode="Markdown"
    )

async def news_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        ts = int(time.time())
        topics = ["cryptocurrency", "bitcoin OR ethereum OR solana", "altcoin rally", "crypto market crash", "defi", "meme coin"]
        topic = random.choice(topics)
        r = await asyncio.to_thread(requests.get, f"https://news.google.com/rss/search?q={topic}&hl=en-US&gl=US&ceid=US:en&t={ts}", timeout=10)
        root = ET.fromstring(r.content)
        divider = "━" * 25
        msg = f"📰 *Crypto News* — {topic.title()}\n{divider}\n"
        for item in list(root.findall('.//item'))[:3]:
            title = item.findtext('title', '')
            link = item.findtext('link', '')
            msg += f"🔹 [{title}]({link})\n\n"
        msg += f"{divider}\n📡 Google News"
        await update.message.reply_text(msg, parse_mode="Markdown", disable_web_page_preview=True)
    except Exception:
        await update.message.reply_text(f"⚠️ *News Unavailable*\n{divider}\nCouldn't fetch news. Try again later.", parse_mode="Markdown")

async def setbalance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    user_settings = db.load_db(db.SETTINGS_DB_FILE)
    divider = "━" * 25
    try:
        amount = float(context.args[0])
        if user_id not in user_settings:
            user_settings[user_id] = dict(DEFAULT_SETTINGS)
        else:
            user_settings[user_id] = get_user_settings(user_settings, user_id)
        user_settings[user_id]["balance"] = amount
        db.save_db(user_settings, db.SETTINGS_DB_FILE)
        await update.message.reply_text(
            f"💰 *Balance Updated*\n{divider}\n"
            f"Wallet: *${amount:,}*\n{divider}\n"
            f"I'll use this to suggest buy amounts in signals.",
            parse_mode="Markdown"
        )
    except (IndexError, ValueError):
        await update.message.reply_text(f"⚠️ *Usage:*\n{divider}\n`/setbalance [amount]`\n📌 `/setbalance 5000`", parse_mode="Markdown")

async def portfolio_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    user_settings = db.load_db(db.SETTINGS_DB_FILE)
    watchlist = db.load_db(db.WATCH_DB_FILE)
    predictions = db.load_db(db.PREDICT_DB_FILE)

    settings = get_user_settings(user_settings, user_id)
    user_tracks = watchlist.get(user_id, {})
    user_preds = predictions.get(user_id, {})
    divider = "━" * 25

    msg = (
        f"💳 *Your Portfolio*\n{divider}\n"
        f"💰 Wallet:    *${settings['balance']:,}*\n"
        f"🛡️ Risk Mode: *{settings['risk_mode']}*\n"
        f"🔥 Discovery: *{settings['hot_discovery']}*\n{divider}\n"
        f"📊 Alerts:     *{len(user_tracks)} active*\n"
        f"🔮 Predictions: *{len(user_preds)} watching*\n{divider}\n"
        f"💡 `/setbalance [amount]` to adjust your wallet"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    user_settings = db.load_db(db.SETTINGS_DB_FILE)
    current = get_user_settings(user_settings, user_id)
    divider = "━" * 25

    text = (
        f"⚙️ *Settings*\n{divider}\n"
        f"🛡️ Risk Mode:     *{current['risk_mode']}*\n"
        f"🔔 Alerts:        *{current['alerts']}*\n"
        f"🔥 Hot Discovery: *{current['hot_discovery']}*\n"
        f"💰 Balance:       *${current['balance']:,}*"
    )
    keyboard = [
        [InlineKeyboardButton("Toggle Risk Mode", callback_data="toggle_risk"), InlineKeyboardButton("Mute Alerts", callback_data="toggle_alerts")],
        [InlineKeyboardButton("Hot Discovery", callback_data="toggle_hot"), InlineKeyboardButton("Exit ❌", callback_data="close_settings")]
    ]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def settings_button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = str(query.from_user.id)
    user_settings = db.load_db(db.SETTINGS_DB_FILE)
    await query.answer()
    divider = "━" * 25

    current = get_user_settings(user_settings, user_id)

    if query.data == "toggle_risk":
        current["risk_mode"] = "Risky" if current["risk_mode"] == "Safe" else "Safe"
    elif query.data == "toggle_alerts":
        current["alerts"] = "OFF" if current["alerts"] == "ON" else "ON"
    elif query.data == "toggle_hot":
        current["hot_discovery"] = "OFF" if current["hot_discovery"] == "ON" else "ON"
    elif query.data == "close_settings":
        await query.edit_message_text(f"🔒 *Settings Saved*\n{divider}\nYour preferences have been updated.", parse_mode="Markdown")
        return

    user_settings[user_id] = current
    db.save_db(user_settings, db.SETTINGS_DB_FILE)

    text = (
        f"⚙️ *Settings*\n{divider}\n"
        f"🛡️ Risk Mode:     *{current['risk_mode']}*\n"
        f"🔔 Alerts:        *{current['alerts']}*\n"
        f"🔥 Hot Discovery: *{current['hot_discovery']}*\n"
        f"💰 Balance:       *${current['balance']:,}*"
    )
    keyboard = [
        [InlineKeyboardButton("Toggle Risk Mode", callback_data="toggle_risk"), InlineKeyboardButton("Mute Alerts", callback_data="toggle_alerts")],
        [InlineKeyboardButton("Hot Discovery", callback_data="toggle_hot"), InlineKeyboardButton("Exit ❌", callback_data="close_settings")]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    watchlist = db.load_db(db.WATCH_DB_FILE)
    divider = "━" * 25
    if user_id in watchlist:
        del watchlist[user_id]
        db.save_db(watchlist, db.WATCH_DB_FILE)
    await update.message.reply_text(f"🧹 *Alerts Cleared*\n{divider}\nAll price alerts have been removed.", parse_mode="Markdown")

async def clear_predictions_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    predictions = db.load_db(db.PREDICT_DB_FILE)
    divider = "━" * 25
    if user_id in predictions:
        del predictions[user_id]
        db.save_db(predictions, db.PREDICT_DB_FILE)
    await update.message.reply_text(f"🧹 *Predictions Cleared*\n{divider}\nAll prediction tracking has been removed.", parse_mode="Markdown")

async def predict_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        coin = context.args[0].lower()
        user_id = str(update.effective_user.id)
        predictions = db.load_db(db.PREDICT_DB_FILE)
        divider = "━" * 25
        if user_id not in predictions:
            predictions[user_id] = {}
        predictions[user_id][coin] = {"added": time.time(), "last_alert": None}
        db.save_db(predictions, db.PREDICT_DB_FILE)
        await update.message.reply_text(
            f"📊 *Prediction Added*\n{divider}\n"
            f"🪙 Tracking: *{coin.upper()}*\n{divider}\n"
            f"I'll alert you on high-confidence signals.",
            parse_mode="Markdown"
        )
    except IndexError:
        await update.message.reply_text(f"⚠️ *Usage:*\n{divider}\n`/predict [coin]`\n📌 `/predict bitcoin`", parse_mode="Markdown")

async def unpredict_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        coin = context.args[0].lower()
        user_id = str(update.effective_user.id)
        predictions = db.load_db(db.PREDICT_DB_FILE)
        divider = "━" * 25
        if user_id in predictions and coin in predictions[user_id]:
            del predictions[user_id][coin]
            if not predictions[user_id]:
                del predictions[user_id]
            db.save_db(predictions, db.PREDICT_DB_FILE)
            await update.message.reply_text(
                f"🔕 *Prediction Removed*\n{divider}\n"
                f"*{coin.upper()}* removed. No more signals for this coin.",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(f"⚠️ *Not Found*\n{divider}\n*{coin.upper()}* isn't on your prediction list.", parse_mode="Markdown")
    except IndexError:
        await update.message.reply_text(f"⚠️ *Usage:*\n{divider}\n`/unpredict [coin]`\n📌 `/unpredict bitcoin`", parse_mode="Markdown")

async def predictions_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    predictions = db.load_db(db.PREDICT_DB_FILE)
    user_coins = predictions.get(str(update.effective_user.id), {})
    divider = "━" * 25
    if not user_coins:
        await update.message.reply_text(
            f"📭 *No Predictions*\n{divider}\n"
            f"Use `/predict [coin]` to start tracking.\n📌 `/predict solana`",
            parse_mode="Markdown"
        )
        return
    msg = f"🔮 *Prediction Watchlist ({len(user_coins)})*\n{divider}\n"
    for coin, info in user_coins.items():
        tag = " 🤖" if isinstance(info, dict) and info.get("auto") else ""
        msg += f"🔸 *{coin.upper()}*{tag}\n"
    msg += f"{divider}\n🤖 = auto-discovered\n💡 `/clear_predictions` to wipe all"
    await update.message.reply_text(msg, parse_mode="Markdown")

async def discover_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Scanning the market for hot coins...")
    coins = await asyncio.to_thread(ana.fetch_trending_coins)
    if not coins:
        coins = await asyncio.to_thread(ana.fetch_volatile_coins)
    if not coins:
        await update.message.reply_text("⚠️ *Scan Failed*\nCouldn't scan right now. Try again later.")
        return
    divider = "━" * 25
    msg = f"🔥 *Hot Coins Found*\n{divider}\n"
    found = 0
    for coin in coins[:8]:
        result = await asyncio.to_thread(ana.analyze_market, coin)
        if result[0] is not None and result[1] >= 65:
            direction, confidence, cur, target, _, emoji = result
            if cur < MIN_COIN_PRICE:
                continue
            found += 1
            arrow = "↗" if direction == "bullish" else "↘"
            msg += f"{emoji} *{coin.upper()}*  {arrow}  *${target:,.2f}*  (conf: {confidence}%)\n"
    if found == 0:
        msg += "No strong signals right now. Check back later."
    msg += f"{divider}\n📌 `/predict [coin]` to track one"
    await update.message.reply_text(msg, parse_mode="Markdown")

async def conversational_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    divider = "━" * 25
    await update.message.reply_text(
        f"🤖 *Hey!*\n{divider}\n"
        f"Not sure what you mean.\n\n"
        f"👉 Type `/help` to see all commands\n"
        f"👉 Or try `/price bitcoin`",
        parse_mode="Markdown"
    )

async def check_prices_job(context: ContextTypes.DEFAULT_TYPE):
    watchlist = db.load_db(db.WATCH_DB_FILE)
    predictions = db.load_db(db.PREDICT_DB_FILE)
    settings_db = db.load_db(db.SETTINGS_DB_FILE)

    for user_id, coins in watchlist.items():
        user_pref = get_user_settings(settings_db, user_id)
        if user_pref["alerts"] == "OFF":
            continue
        for coin, target in list(coins.items()):
            price, trend = await asyncio.to_thread(ana.fetch_market_analytics, coin)
            if price is not None and trend is not None:
                if price <= target:
                    user_cap = user_pref["balance"]
                    if trend <= -4.0:
                        low_stake = user_cap * 0.02
                        high_stake = user_cap * 0.06
                        low_qty = low_stake / price
                        high_qty = high_stake / price
                        risk_flag = "⚠️ AGGRESSIVE" if user_pref["risk_mode"] == "Risky" else "🛡️ CONSERVATIVE"
                        prediction_msg = (
                            f"🚨 *{coin.upper()} HIT YOUR ALERT* 🚨\n"
                            f"{risk_flag} POSITIONING\n\n"
                            f"Price dropped *{trend:.2f}%* to *${price:,.2f}*\n\n"
                            f"💡 *Stake (from ${user_cap:,}):*\n"
                            f"🟢 Safe: *${low_stake:,.2f}* (~{low_qty:.1f} {coin.upper()})\n"
                            f"🔴 Aggressive: *${high_stake:,.2f}* (~{high_qty:.1f} {coin.upper()})"
                        )
                        await context.bot.send_message(chat_id=user_id, text=prediction_msg, parse_mode="Markdown")
                    else:
                        await context.bot.send_message(chat_id=user_id, text=f"🔔 *{coin.upper()}* hit your alert at *${target:,}!*\nCurrent price: *${price:,.2f}*", parse_mode="Markdown")
                    del watchlist[user_id][coin]
                    db.save_db(watchlist, db.WATCH_DB_FILE)

    for user_id, coins in predictions.items():
        user_pref = get_user_settings(settings_db, user_id)
        if user_pref["alerts"] == "OFF":
            continue
        for coin, info in list(coins.items()):
            result = await asyncio.to_thread(ana.analyze_market, coin)
            if result[0] is None:
                continue
            direction, confidence, cur_price, target_price, summary, emoji = result
            now = time.time()
            last_alert = info.get("last_alert", 0)
            move_pct = abs((target_price - cur_price) / cur_price) * 100
            if cur_price < MIN_COIN_PRICE or target_price < MIN_COIN_PRICE:
                continue
            if confidence >= 65 and move_pct >= 25 and now - last_alert > 3600:
                user_cap = user_pref["balance"]
                safe_buy = user_cap * 0.05
                risky_buy = user_cap * 0.15
                safe_qty = safe_buy / cur_price
                risky_qty = risky_buy / cur_price
                arrow = "↗" if direction == "bullish" else "↘"
                divider = "━" * 25
                msg = (
                    f"📊 *PREDICTION: {coin.upper()}*\n"
                    f"{divider}\n"
                    f"Signal: *{direction.upper()}* {emoji}  Confidence: *{confidence}%*\n"
                    f"{divider}\n"
                    f"Current: *${cur_price:,.2f}*\n"
                    f"Target:  *${target_price:,.2f}* {arrow}\n"
                    f"{divider}\n"
                    f"{summary}\n\n"
                    f"💡 *Stake (from ${user_cap:,}):*\n"
                    f"🟢 Safe: *${safe_buy:,.2f}* (~{safe_qty:.1f} {coin.upper()})\n"
                    f"🔴 Aggressive: *${risky_buy:,.2f}* (~{risky_qty:.1f} {coin.upper()})"
                )
                await context.bot.send_message(chat_id=user_id, text=msg, parse_mode="Markdown")
                predictions[user_id][coin] = {"added": info.get("added", now), "last_alert": now, "last_dir": direction}
                db.save_db(predictions, db.PREDICT_DB_FILE)

async def check_trending_job(context: ContextTypes.DEFAULT_TYPE):
    settings_db = db.load_db(db.SETTINGS_DB_FILE)
    predictions = db.load_db(db.PREDICT_DB_FILE)
    trending = await asyncio.to_thread(ana.fetch_trending_coins)
    if not trending:
        trending = await asyncio.to_thread(ana.fetch_volatile_coins)
    if not trending:
        return
    for user_id in list(settings_db.keys()):
        user_pref = get_user_settings(settings_db, user_id)
        if user_pref["alerts"] == "OFF" or user_pref["hot_discovery"] == "OFF":
            continue
        alerted = set(predictions.get(user_id, {}).keys())
        for coin in trending:
            if coin in alerted:
                continue
            result = await asyncio.to_thread(ana.analyze_market, coin)
            if result[0] is None or result[1] < 65:
                continue
            _, _, cur, tgt, _, _ = result
            if abs((tgt - cur) / cur) * 100 < 25:
                continue
            if cur < MIN_COIN_PRICE or tgt < MIN_COIN_PRICE:
                continue
            direction, confidence, cur_price, target_price, summary, emoji = result
            arrow = "↗" if direction == "bullish" else "↘"
            divider = "━" * 25
            msg = (
                f"🔥 *HOT COIN: {coin.upper()}*\n"
                f"{divider}\n"
                f"Signal: *{direction.upper()}* {emoji}  Confidence: *{confidence}%*\n"
                f"{divider}\n"
                f"Current: *${cur_price:,.2f}*\n"
                f"Target:  *${target_price:,.2f}* {arrow}\n"
                f"{divider}\n"
                f"{summary}\n\n"
                f"📌 Use `/predict {coin}` to track this coin."
            )
            await context.bot.send_message(chat_id=user_id, text=msg, parse_mode="Markdown")
            if user_id not in predictions:
                predictions[user_id] = {}
            predictions[user_id][coin] = {"added": 0, "last_alert": 0, "last_dir": direction, "auto": True}
            db.save_db(predictions, db.PREDICT_DB_FILE)

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self._ok()
    def do_HEAD(self):
        self._ok()
    def do_POST(self):
        self._ok()
    def _ok(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"ok")
    def log_message(self, *a):
        pass

def run_health_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    server.serve_forever()

def main():
    if not TOKEN:
        return
    t = threading.Thread(target=run_health_server, daemon=True)
    t.start()
    app = Application.builder().token(TOKEN).build()
    app.job_queue.run_once(lambda ctx: set_bot_commands(app), when=1)

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("watch", watch_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("price", price_command))
    app.add_handler(CommandHandler("trend", trend_command))
    app.add_handler(CommandHandler("gas", gas_command))
    app.add_handler(CommandHandler("news", news_command))
    app.add_handler(CommandHandler("portfolio", portfolio_command))
    app.add_handler(CommandHandler("setbalance", setbalance_command))
    app.add_handler(CommandHandler("settings", settings_command))
    app.add_handler(CommandHandler("clear", clear_command))
    app.add_handler(CommandHandler("clear_predictions", clear_predictions_command))
    app.add_handler(CommandHandler("predict", predict_command))
    app.add_handler(CommandHandler("unpredict", unpredict_command))
    app.add_handler(CommandHandler("predictions", predictions_command))
    app.add_handler(CommandHandler("discover", discover_command))

    app.add_handler(CallbackQueryHandler(settings_button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, conversational_handler))

    app.job_queue.scheduler.configure(timezone="UTC")
    app.job_queue.run_repeating(check_prices_job, interval=60, first=10)
    app.job_queue.run_repeating(check_trending_job, interval=7200, first=120)

    print("🚀 onyX is online!")
    app.run_polling()

if __name__ == "__main__":
    main()

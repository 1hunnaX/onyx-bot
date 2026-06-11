import os
import time
import random
import threading
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
        BotCommand("discover", "Find hot volatile coins to track")
    ]
    await application.bot.set_my_commands(commands)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    first_name = update.effective_user.first_name
    users_interacted = db.load_db(db.USER_DB_FILE)

    if user_id not in users_interacted:
        welcome_text = (
            f"👋 *Hey {first_name}! I'm onyX, your crypto bot.*\n\n"
            f"🔍 I watch coin prices and alert you when it's a good time to buy.\n\n"
            f"📌 Tap the menu button below or type `/help` to see what I can do!"
        )
        users_interacted[user_id] = {"joined": time.time(), "greeted": True}
        db.save_db(users_interacted, db.USER_DB_FILE)

        user_settings = db.load_db(db.SETTINGS_DB_FILE)
        if user_id not in user_settings:
            user_settings[user_id] = {"risk_mode": "Safe", "alerts": "ON", "hot_discovery": "ON", "balance": 1000.0}
            db.save_db(user_settings, db.SETTINGS_DB_FILE)
    else:
        welcome_text = f"👋 Welcome back, {first_name}! Use the menu or type `/help`."

    await update.message.reply_text(welcome_text, parse_mode="Markdown")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_map = (
        "📖 *onyX Commands*\n\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "📊 *Market Data*\n"
        "🔹 `/price [coin]` — Current price & 24h change\n"
        "🔹 `/trend [coin]` — 4h trend check\n"
        "🔹 `/gas` — Live ETH network fees\n"
        "🔹 `/news` — Latest crypto headlines\n"
        "━━━━━━━━━━━━━━━━━━━\n\n"
        "🔔 *Alerts*\n"
        "🔹 `/watch [coin] [price]` — Custom price alert\n"
        "🔹 `/status` — View active price alerts\n"
        "🔹 `/clear` — Remove all price alerts\n"
        "━━━━━━━━━━━━━━━━━━━\n\n"
        "🔮 *Predictions*\n"
        "🔹 `/predict [coin]` — Detects major pumps & dumps\n"
        "🔹 `/unpredict [coin]` — Stop prediction watch\n"
        "🔹 `/predictions` — View prediction watchlist\n"
        "🔹 `/discover` — Find hot volatile coins\n"
        "━━━━━━━━━━━━━━━━━━━\n\n"
        "💳 *Account*\n"
        "🔹 `/setbalance [amount]` — Set trading budget\n"
        "🔹 `/portfolio` — View balance & settings\n"
        "🔹 `/settings` — Toggle risk mode & alerts\n"
        "🔹 `/help` — Show this list"
    )
    await update.message.reply_text(help_map, parse_mode="Markdown")

async def watch_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    watchlist = db.load_db(db.WATCH_DB_FILE)
    try:
        coin = context.args[0].lower()
        target_price = float(context.args[1])

        if user_id not in watchlist:
            watchlist[user_id] = {}
        watchlist[user_id][coin] = target_price
        db.save_db(watchlist, db.WATCH_DB_FILE)

        await update.message.reply_text(f"✅ Got it! I'll alert you when *{coin.upper()}* drops to *${target_price:,}*.", parse_mode="Markdown")
    except (IndexError, ValueError):
        await update.message.reply_text("⚠️ Use: `/watch [coin] [price]` — e.g. `/watch solana 120`")

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    watchlist = db.load_db(db.WATCH_DB_FILE)
    user_tracks = watchlist.get(str(update.effective_user.id), {})
    if not user_tracks:
        await update.message.reply_text("📭 No alerts set. Use `/watch [coin] [price]` to add one.")
        return
    summary = "📋 *Your Alerts:*\n\n"
    for coin, target in user_tracks.items():
        summary += f"🔸 *{coin.upper()}* — Alert at `${target:,}`\n"
    await update.message.reply_text(summary, parse_mode="Markdown")

async def price_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        coin = context.args[0].lower()
        price, change = ana.fetch_instant_price(coin)
        if price is not None:
            emoji = "📈" if change >= 0 else "📉"
            await update.message.reply_text(f"💰 *{coin.upper()}*\nPrice: `${price:,.2f}`\n{emoji} 24h Change: `{change:.2f}%`", parse_mode="Markdown")
        else:
            await update.message.reply_text("❌ Couldn't find that coin. Check the name and try again.")
    except IndexError:
        await update.message.reply_text("⚠️ Use: `/price [coin]` — e.g. `/price bitcoin`")

async def trend_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        coin = context.args[0].lower()
        await update.message.reply_text(f"⏳ Checking *{coin.upper()}* trend...")
        price, trend = ana.fetch_market_analytics(coin)
        if price is not None:
            status = "🔥 *PUMPING*" if trend > 2.0 else ("❄️ *DUMPING*" if trend < -2.0 else "⚖️ *SIDEWAYS*")
            await update.message.reply_text(f"📊 *{coin.upper()}*\nPrice: `${price:,.2f}`\n4h Change: `{trend:.2f}%`\nSignal: {status}", parse_mode="Markdown")
        else:
            await update.message.reply_text("❌ Couldn't find that coin.")
    except IndexError:
        await update.message.reply_text("⚠️ Use: `/trend [coin]` — e.g. `/trend bitcoin`")

async def gas_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    standard, fast = ana.fetch_eth_gas()
    await update.message.reply_text(
        f"⛽ *Network Fees*\n\n"
        f"🔹 *Ethereum:* `{standard} Gwei` (standard) / `{fast} Gwei` (fast)\n"
        f"🔹 *Solana:* `~0.00001 SOL` ✅\n\n"
        "Fees are live from Etherscan.",
        parse_mode="Markdown"
    )

async def news_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        ts = int(time.time())
        topics = ["cryptocurrency", "bitcoin OR ethereum OR solana", "altcoin rally", "crypto market crash", "defi", "meme coin"]
        topic = random.choice(topics)
        r = requests.get(f"https://news.google.com/rss/search?q={topic}&hl=en-US&gl=US&ceid=US:en&t={ts}", timeout=10)
        root = ET.fromstring(r.content)
        msg = f"📰 *Crypto News — {topic.title()}*\n\n"
        for item in list(root.findall('.//item'))[:3]:
            title = item.findtext('title', '')
            link = item.findtext('link', '')
            msg += f"🔹 [{title}]({link})\n\n"
        await update.message.reply_text(msg, parse_mode="Markdown", disable_web_page_preview=True)
    except Exception:
        await update.message.reply_text("⚠️ Couldn't fetch news right now. Try again later.")

async def setbalance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    user_settings = db.load_db(db.SETTINGS_DB_FILE)
    try:
        amount = float(context.args[0])
        if user_id not in user_settings:
            user_settings[user_id] = {"risk_mode": "Safe", "alerts": "ON", "hot_discovery": "ON", "balance": 1000.0}
        user_settings[user_id]["balance"] = amount
        db.save_db(user_settings, db.SETTINGS_DB_FILE)
        await update.message.reply_text(f"💰 Staking balance set to *${amount:,}*. I'll use this to suggest buy amounts in signals.")
    except (IndexError, ValueError):
        await update.message.reply_text("⚠️ Use: `/setbalance [amount]` — e.g. `/setbalance 5000`")

async def portfolio_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    user_settings = db.load_db(db.SETTINGS_DB_FILE)
    watchlist = db.load_db(db.WATCH_DB_FILE)
    predictions = db.load_db(db.PREDICT_DB_FILE)

    settings = user_settings.get(user_id, {"risk_mode": "Safe", "alerts": "ON", "hot_discovery": "ON", "balance": 1000.0})
    user_tracks = watchlist.get(user_id, {})
    user_preds = predictions.get(user_id, {})

    msg = (
        f"💳 *Your Portfolio*\n\n"
        f"💰 Staking Balance: *${settings.get('balance', 1000.0):,}*\n"
        f"🛡️ Risk Mode: *{settings.get('risk_mode', 'Safe')}*\n"
        f"🔥 Hot Discovery: *{settings.get('hot_discovery', 'ON')}*\n"
        f"📊 Price Alerts: *{len(user_tracks)}*\n"
        f"🔮 Prediction Watch: *{len(user_preds)}*\n\n"
        f"Use `/setbalance [amount]` to adjust your staking wallet."
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    user_settings = db.load_db(db.SETTINGS_DB_FILE)
    current = user_settings.get(user_id, {"risk_mode": "Safe", "alerts": "ON", "hot_discovery": "ON", "balance": 1000.0})

    text = f"⚙️ *Settings*\n\n🛡️ Risk Mode: *{current['risk_mode']}*\n🔔 Alerts: *{current['alerts']}*\n🔥 Hot Discovery: *{current.get('hot_discovery', 'ON')}*\n💰 Balance: *${current.get('balance', 1000.0):,}*"
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

    current = user_settings.get(user_id, {"risk_mode": "Safe", "alerts": "ON", "hot_discovery": "ON", "balance": 1000.0})

    if query.data == "toggle_risk":
        current["risk_mode"] = "Risky" if current["risk_mode"] == "Safe" else "Safe"
    elif query.data == "toggle_alerts":
        current["alerts"] = "OFF" if current["alerts"] == "ON" else "ON"
    elif query.data == "toggle_hot":
        current["hot_discovery"] = "OFF" if current.get("hot_discovery", "ON") == "ON" else "ON"
    elif query.data == "close_settings":
        await query.edit_message_text("🔒 Settings saved.", parse_mode="Markdown")
        return

    user_settings[user_id] = current
    db.save_db(user_settings, db.SETTINGS_DB_FILE)

    text = f"⚙️ *Settings*\n\n🛡️ Risk Mode: *{current['risk_mode']}*\n🔔 Alerts: *{current['alerts']}*\n🔥 Hot Discovery: *{current.get('hot_discovery', 'ON')}*\n💰 Balance: *${current['balance']:,}*"
    keyboard = [
        [InlineKeyboardButton("Toggle Risk Mode", callback_data="toggle_risk"), InlineKeyboardButton("Mute Alerts", callback_data="toggle_alerts")],
        [InlineKeyboardButton("Hot Discovery", callback_data="toggle_hot"), InlineKeyboardButton("Exit ❌", callback_data="close_settings")]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    watchlist = db.load_db(db.WATCH_DB_FILE)
    if user_id in watchlist:
        del watchlist[user_id]
        db.save_db(watchlist, db.WATCH_DB_FILE)
    await update.message.reply_text("🧹 All alerts cleared.")

async def predict_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        coin = context.args[0].lower()
        user_id = str(update.effective_user.id)
        predictions = db.load_db(db.PREDICT_DB_FILE)
        if user_id not in predictions:
            predictions[user_id] = {}
        predictions[user_id][coin] = {"added": time.time(), "last_alert": None}
        db.save_db(predictions, db.PREDICT_DB_FILE)
        await update.message.reply_text(f"📊 *{coin.upper()}* added to your watchlist. You'll be notified when a high-confidence signal appears.", parse_mode="Markdown")
    except IndexError:
        await update.message.reply_text("⚠️ Use: `/predict [coin]` — e.g. `/predict bitcoin`")

async def unpredict_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        coin = context.args[0].lower()
        user_id = str(update.effective_user.id)
        predictions = db.load_db(db.PREDICT_DB_FILE)
        if user_id in predictions and coin in predictions[user_id]:
            del predictions[user_id][coin]
            if not predictions[user_id]:
                del predictions[user_id]
            db.save_db(predictions, db.PREDICT_DB_FILE)
            await update.message.reply_text(f"🔕 *{coin.upper()}* removed from your watchlist. No further signals will be sent.", parse_mode="Markdown")
        else:
            await update.message.reply_text(f"*{coin.upper()}* isn't on your prediction list.", parse_mode="Markdown")
    except IndexError:
        await update.message.reply_text("⚠️ Use: `/unpredict [coin]` — e.g. `/unpredict bitcoin`")

async def predictions_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    predictions = db.load_db(db.PREDICT_DB_FILE)
    user_coins = predictions.get(str(update.effective_user.id), {})
    if not user_coins:
        await update.message.reply_text("📭 No coins being watched for predictions. Use `/predict [coin]` to add one.")
        return
    msg = "🔮 *Prediction Watchlist:*\n\n"
    for coin in user_coins:
        msg += f"🔸 *{coin.upper()}*\n"
    await update.message.reply_text(msg, parse_mode="Markdown")

async def discover_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔍 Scanning for hot volatile coins...")
    coins = ana.fetch_trending_coins()
    if not coins:
        coins = ana.fetch_volatile_coins()
    if not coins:
        await update.message.reply_text("⚠️ Couldn't scan right now. Try again later.")
        return
    msg = "🔥 *Hot Coins Found:*\n\n"
    found = 0
    for coin in coins[:8]:
        result = ana.analyze_market(coin)
        if result[0] is not None and result[1] >= 65:
            direction, confidence, cur, target, summary, emoji = result
            found += 1
            arrow = "↗" if direction == "bullish" else "↘"
            msg += f"{emoji} *{coin.upper()}* {arrow} Target: *${target:,.2f}*  (conf: {confidence}%)\n"
    if found == 0:
        msg += "No strong signals right now. Check back later."
    msg += f"\n📌 Use `/predict [coin]` to track one of these."
    await update.message.reply_text(msg, parse_mode="Markdown")

async def conversational_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 Use the menu or type `/help` to see what I can do.", parse_mode="Markdown")

async def check_prices_job(context: ContextTypes.DEFAULT_TYPE):
    watchlist = db.load_db(db.WATCH_DB_FILE)
    predictions = db.load_db(db.PREDICT_DB_FILE)
    settings_db = db.load_db(db.SETTINGS_DB_FILE)

    for user_id, coins in watchlist.items():
        user_pref = settings_db.get(user_id, {"risk_mode": "Safe", "alerts": "ON", "hot_discovery": "ON", "balance": 1000.0})
        if user_pref["alerts"] == "OFF":
            continue
        for coin, target in list(coins.items()):
            price, trend = ana.fetch_market_analytics(coin)
            if price is not None and trend is not None:
                if price <= target:
                    user_cap = user_pref.get("balance", 1000.0)
                    if trend <= -4.0:
                        low_stake = user_cap * 0.02
                        high_stake = user_cap * 0.06
                        risk_flag = "⚠️ AGGRESSIVE RISK POSITIONING" if user_pref["risk_mode"] == "Risky" else "🛡️ CONSERVATIVE POSITIONING"
                        prediction_msg = (
                            f"🚨 *BIG DROP DETECTED* 🚨\n"
                            f"{risk_flag}\n\n"
                            f"*{coin.upper()}* hit your alert at *${price:,.2f}*.\n"
                            f"📉 Dropped *{trend:.2f}%* — might be a good buy.\n\n"
                            f"💡 *Suggested buy (from ${user_cap:,} balance):*\n"
                            f"🟢 Safe buy: *${low_stake:,.2f}*\n"
                            f"🔴 Risky buy: *${high_stake:,.2f}*"
                        )
                        await context.bot.send_message(chat_id=user_id, text=prediction_msg, parse_mode="Markdown")
                    else:
                        await context.bot.send_message(chat_id=user_id, text=f"🔔 *{coin.upper()}* hit your target of *${target:,}!*\nCurrent price: *${price:,.2f}*", parse_mode="Markdown")
                    del watchlist[user_id][coin]
                    db.save_db(watchlist, db.WATCH_DB_FILE)

    for user_id, coins in predictions.items():
        user_pref = settings_db.get(user_id, {"risk_mode": "Safe", "alerts": "ON", "hot_discovery": "ON", "balance": 1000.0})
        if user_pref["alerts"] == "OFF":
            continue
        for coin, info in list(coins.items()):
            result = ana.analyze_market(coin)
            if result[0] is None:
                continue
            direction, confidence, cur_price, target_price, summary, emoji = result
            now = time.time()
            last_alert = info.get("last_alert", 0)
            last_dir = info.get("last_dir", "")
            move_pct = abs((target_price - cur_price) / cur_price) * 100
            if confidence >= 65 and move_pct >= 25 and (direction != last_dir or now - last_alert > 86400):
                user_cap = user_pref.get("balance", 1000.0)
                safe_buy = user_cap * 0.05
                risky_buy = user_cap * 0.15
                arrow = "↗" if direction == "bullish" else "↘"
                msg = (
                    f"📊 *PREDICTION: {coin.upper()}*\n\n"
                    f"Signal: *{direction.upper()}* {emoji}  Confidence: *{confidence}%*\n"
                    f"Current: *${cur_price:,.2f}*  {arrow}  Target: *${target_price:,.2f}*\n\n"
                    f"📊 {summary}\n\n"
                    f"💡 *From your ${user_cap:,} staking balance:*\n"
                    f"🟢 Low stake: *${safe_buy:,.2f}*\n"
                    f"🔴 High stake: *${risky_buy:,.2f}*"
                )
                await context.bot.send_message(chat_id=user_id, text=msg, parse_mode="Markdown")
                predictions[user_id][coin] = {"added": info.get("added", now), "last_alert": now, "last_dir": direction}
                db.save_db(predictions, db.PREDICT_DB_FILE)

async def check_trending_job(context: ContextTypes.DEFAULT_TYPE):
    """Scans trending/volatile coins and sends predictions to all users."""
    settings_db = db.load_db(db.SETTINGS_DB_FILE)
    predictions = db.load_db(db.PREDICT_DB_FILE)
    trending = ana.fetch_trending_coins()
    if not trending:
        trending = ana.fetch_volatile_coins()
    if not trending:
        return
    for user_id in list(settings_db.keys()):
        user_pref = settings_db.get(user_id, {"alerts": "ON", "hot_discovery": "ON"})
        if user_pref.get("alerts") == "OFF" or user_pref.get("hot_discovery", "ON") == "OFF":
            continue
        alerted = set(predictions.get(user_id, {}).keys())
        for coin in trending:
            if coin in alerted:
                continue
            result = ana.analyze_market(coin)
            if result[0] is None or result[1] < 65:
                continue
            _, _, cur, tgt, _, _ = result
            if abs((tgt - cur) / cur) * 100 < 25:
                continue
            direction, confidence, cur_price, target_price, summary, emoji = result
            arrow = "↗" if direction == "bullish" else "↘"
            msg = (
                f"🔥 *HOT COIN DISCOVERED: {coin.upper()}*\n\n"
                f"Signal: *{direction.upper()}* {emoji}  Confidence: *{confidence}%*\n"
                f"Current: *${cur_price:,.2f}*  {arrow}  Target: *${target_price:,.2f}*\n\n"
                f"📊 {summary}\n\n"
                f"📌 Use `/predict {coin}` to keep tracking this coin."
            )
            await context.bot.send_message(chat_id=user_id, text=msg, parse_mode="Markdown")
            if user_id not in predictions:
                predictions[user_id] = {}
            predictions[user_id][coin] = {"added": 0, "last_alert": 0, "last_dir": direction, "auto": True}
            db.save_db(predictions, db.PREDICT_DB_FILE)

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")
    def log_message(self, *a):
        pass

def run_health_server():
    server = HTTPServer(("0.0.0.0", 10000), HealthHandler)
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

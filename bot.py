import os
import json
import logging
import requests
import asyncio
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
SUBSCRIBERS_FILE = "subscribers.json"


def load_subscribers():
    if os.path.exists(SUBSCRIBERS_FILE):
        try:
            with open(SUBSCRIBERS_FILE, "r") as f:
                return set(json.load(f))
        except:
            return set()
    return set()


def save_subscribers(subs):
    with open(SUBSCRIBERS_FILE, "w") as f:
        json.dump(list(subs), f)


def fetch_prices():
    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=solana,punch-2&vs_currencies=usd&include_24hr_change=true"
        return requests.get(url, timeout=10).json()
    except:
        return None


def build_message(data):
    now = datetime.utcnow().strftime("%H:%M UTC")

    sol = data.get("solana", {})
    punch = data.get("punch-2", {})

    def fmt(price):
        return f"${price:.4f}" if price < 1 else f"${price:,.2f}"

    def arrow(c):
        return "▲" if c >= 0 else "▼"

    return (
        f"📊 <b>Market Update</b> ({now})\n\n"
        f"◎ SOL: {fmt(sol.get('usd', 0))} {arrow(sol.get('usd_24h_change', 0))} {sol.get('usd_24h_change', 0):.2f}%\n"
        f"🥊 PUNCH: {fmt(punch.get('usd', 0))} {arrow(punch.get('usd_24h_change', 0))} {punch.get('usd_24h_change', 0):.2f}%"
    )


# ---------------- COMMANDS ----------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    subs = load_subscribers()
    subs.add(update.effective_chat.id)
    save_subscribers(subs)

    await update.message.reply_text(
        "✅ Subscribed!\n\nYou’ll get updates every 60 seconds.\n\n/price → instant\n/stop → unsubscribe"
    )


async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    subs = load_subscribers()
    subs.discard(update.effective_chat.id)
    save_subscribers(subs)

    await update.message.reply_text("❌ Unsubscribed.")


async def price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = fetch_prices()
    if data:
        await update.message.reply_text(build_message(data), parse_mode="HTML")
    else:
        await update.message.reply_text("Error fetching price.")


# ---------------- LOOP (REPLACES job_queue) ----------------

async def broadcast_loop(app):
    await asyncio.sleep(5)

    while True:
        try:
            subs = load_subscribers()
            data = fetch_prices()

            if data and subs:
                msg = build_message(data)

                for chat_id in subs:
                    try:
                        await app.bot.send_message(chat_id, msg, parse_mode="HTML")
                    except:
                        pass

        except Exception as e:
            print("Loop error:", e)

        await asyncio.sleep(60)


# ---------------- MAIN ----------------

async def main():
    if not TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN not set")

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(CommandHandler("price", price))

    # start background loop
    asyncio.create_task(broadcast_loop(app))

    print("Bot running...")
    await app.run_polling()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())

import os
import json
import logging
import requests
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
SUBSCRIBERS_FILE = "subscribers.json"


def load_subscribers() -> set:
    if os.path.exists(SUBSCRIBERS_FILE):
        try:
            with open(SUBSCRIBERS_FILE, "r") as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()


def save_subscribers(subscribers: set):
    with open(SUBSCRIBERS_FILE, "w") as f:
        json.dump(list(subscribers), f)


def fetch_prices() -> dict | None:
    url = (
        "https://api.coingecko.com/api/v3/simple/price"
        "?ids=solana,punch-2&vs_currencies=usd&include_24hr_change=true"
    )
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"Price fetch failed: {e}")
        return None


def format_price(price: float) -> str:
    if price >= 1:
        return f"${round(price):,}"
    else:
        units = round(price * 1_000_000)
        return f"{units:,} M"


def build_message(data: dict) -> str:
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    sol_price = data.get("solana", {}).get("usd", 0)
    sol_change = data.get("solana", {}).get("usd_24h_change") or 0.0
    punch_price = data.get("punch-2", {}).get("usd", 0)
    punch_change = data.get("punch-2", {}).get("usd_24h_change") or 0.0

    def arrow(c): return "▲" if c >= 0 else "▼"
    def sign(c): return "+" if c >= 0 else ""

    lines = [
        f"<b>SOL / PUNCH</b>  •  {now}\n",
        f"◎ <b>SOL</b>    {format_price(sol_price)}  {arrow(sol_change)} {sign(sol_change)}{sol_change:.2f}%",
        f"🥊 <b>PUNCH</b>  {format_price(punch_price)}  {arrow(punch_change)} {sign(punch_change)}{punch_change:.2f}%",
        "\n/stop to unsubscribe",
    ]
    return "\n".join(lines)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    subs = load_subscribers()
    if chat_id in subs:
        await update.message.reply_text(
            "Already subscribed! Use /price for instant update or /stop to unsubscribe."
        )
        return
    subs.add(chat_id)
    save_subscribers(subs)
    await update.message.reply_text(
        "Subscribed! You will get <b>SOL</b> and <b>PUNCH</b> price updates every <b>60 seconds</b>.\n\n"
        "/price — instant update\n"
        "/stop — unsubscribe",
        parse_mode="HTML",
    )


async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    subs = load_subscribers()
    if chat_id not in subs:
        await update.message.reply_text("Not subscribed. Use /start to subscribe.")
        return
    subs.discard(chat_id)
    save_subscribers(subs)
    await update.message.reply_text("Unsubscribed. Use /start anytime to resubscribe.")


async def cmd_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = fetch_prices()
    if data:
        await update.message.reply_text(build_message(data), parse_mode="HTML")
    else:
        await update.message.reply_text("Could not fetch prices right now. Try again shortly.")


async def broadcast(context: ContextTypes.DEFAULT_TYPE):
    subs = load_subscribers()
    if not subs:
        return
    data = fetch_prices()
    if not data:
        return
    msg = build_message(data)
    dead = set()
    for chat_id in subs:
        try:
            await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode="HTML")
        except Exception as e:
            logger.warning(f"Failed to message {chat_id}: {e}")
            dead.add(chat_id)
    if dead:
        subs -= dead
        save_subscribers(subs)


def main():
    if not TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("stop", cmd_stop))
    app.add_handler(CommandHandler("price", cmd_price))

    app.job_queue.run_repeating(broadcast, interval=60, first=5)

    logger.info("Bot running...")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()

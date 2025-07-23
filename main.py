import os
import logging
import asyncio
from telegram import Update, Bot
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import openai
import gspread
from datetime import datetime
from functools import wraps
from collections import defaultdict

# Logging setup
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ENV VARS
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
CHARTINK_SCAN_URL = os.getenv("CHARTINK_SCAN_URL")
SHEET_ID = os.getenv("SHEET_ID")
ADMIN_USER_IDS = os.getenv("ADMIN_USER_IDS", "").split(",")  # Optional admin controls

openai.api_key = OPENAI_API_KEY
bot = Bot(token=TELEGRAM_TOKEN)

# Google Sheet Setup
gc = gspread.service_account(filename="credentials.json")
sheet = gc.open_by_key(SHEET_ID).sheet1

# --- Simple rate limiter for /ask command ---
user_last_ask = defaultdict(lambda: 0)
ASK_INTERVAL = 30  # seconds

def rate_limited(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        now = datetime.now().timestamp()
        user_id = update.effective_user.id
        if now - user_last_ask[user_id] < ASK_INTERVAL:
            await update.message.reply_text("You're sending requests too quickly. Please wait a bit.")
            return
        user_last_ask[user_id] = now
        return await func(update, context, *args, **kwargs)
    return wrapper

# --- Helper: Split long messages ---
def split_message(text, max_len=4096):
    return [text[i:i+max_len] for i in range(0, len(text), max_len)]

# --- Bot Commands ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Welcome to OPTIONSmagicAI\n\nFrom Signal to Success—Automated.\n\nUse /ask to analyze options or /alert to get today's picks."
    )

@rate_limited
async def ask(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = ' '.join(context.args)
    if not query:
        await update.message.reply_text("Please enter a query after /ask (e.g., /ask What are good BANKNIFTY options today?)")
        return

    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[{"role": "user", "content": query}]
        )
        answer_content = response.choices[0].message.content
    except Exception as e:
        logging.error(f"OpenAI API error: {e}")
        await update.message.reply_text("Sorry, I couldn't reach OpenAI right now. Please try again later.")
        return

    for part in split_message(answer_content):
        await update.message.reply_text(part)

async def alert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        # Optionally, fetch real data here using CHARTINK_SCAN_URL (future enhancement)
        data = [
            ["PAGEIND 51000 CE", "Entry: 123.45", "SL: 112", "Target: 145", "Sector: Auto"],
            ["ASTRAL 1600 CE", "Entry: 98.70", "SL: 87", "Target: 125", "Sector: Pipes"],
            ["DIVISLAB 4500 CE", "Entry: 156.20", "SL: 140", "Target: 180", "Sector: Pharma"]
        ]
        message = "\U0001F9E0 *OPTIONSmagicAI 4PM Swing Breakout Alerts* \U0001F4A1\n\n"
        for trade in data:
            message += f"• {trade[0]} ({trade[4]})\n  {trade[1]} | {trade[2]} | {trade[3]}\n\n"
        message += "From Signal to Success—Automated."

        await update.message.reply_markdown(message)

        today = datetime.now().strftime("%Y-%m-%d")
        for row in data:
            try:
                sheet.append_row([today, row[0], row[1], row[2], row[3], row[4]])
            except Exception as e:
                logging.error(f"Failed to log to Google Sheets: {e}")

    except Exception as e:
        logging.error(f"Alert handler failed: {e}")
        await update.message.reply_text("Failed to send alerts due to an internal error. Please try again later.")

# --- Bot Init ---
def check_credentials():
    required_env = [TELEGRAM_TOKEN, OPENAI_API_KEY, SHEET_ID]
    if not all(required_env):
        raise RuntimeError("Missing one or more required environment variables. Please set TELEGRAM_TOKEN, OPENAI_API_KEY, and SHEET_ID.")

if __name__ == '__main__':
    try:
        check_credentials()
        app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("ask", ask))
        app.add_handler(CommandHandler("alert", alert))
        print("Bot is up and running.")
        app.run_polling()
    except Exception as e:
        logging.critical(f"Bot failed to start: {e}")


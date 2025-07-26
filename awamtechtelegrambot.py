"""
AwamTech Personal Assistant Bot
Requires: python-telegram-bot >= 20.x (tested on 22.2)
Run:  python awamtech_bot.py
"""

import nest_asyncio
nest_asyncio.apply()
import asyncio
import json
import os
from datetime import time, datetime, timezone
from pathlib import Path

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
)

# ────────────────────────────────────────────────────────────────────────────
# CONFIG ─ CHANGE THESE TWO LINES ONLY!
BOT_TOKEN = "8158315858:AAGC09CuoiG7vEj6y3bEKTDHrx0Mxnfk88I"
OWNER_CHAT_ID = 6988931828            # e.g. 123456789
# ────────────────────────────────────────────────────────────────────────────

DATA_FILE = Path("bot_data.json")

# ---------- Data helpers ----------------------------------------------------
def load_data() -> dict:
    if DATA_FILE.exists():
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"tasks": [], "alarms": [], "weekend_alarms": []}


def save_data(data: dict) -> None:
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


data = load_data()  # global in-memory copy

# ---------- Command functions ----------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *Welcome!*\n\n"
        "• /add <task> – add a task\n"
        "• /remove <task> – remove a task\n"
        "• /list – show current tasks\n"
        "• /addalarm HH:MM <msg> – daily alarm\n"
        "• /addweekend HH:MM <msg> – Sat & Sun alarm\n"
        "• /listalarms – list all alarms\n"
        "• /deletealarm <index> – remove an alarm\n"
        "• /id – show your chat ID",
        parse_mode=ParseMode.MARKDOWN,
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)


async def show_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"🆔 Your chat ID is: {update.effective_user.id}",
                                    parse_mode=ParseMode.MARKDOWN)


# ---------- Task list -------------------------------------------------------
async def add_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    task = " ".join(context.args)
    if not task:
        await update.message.reply_text("⚠️ Usage: /add Buy groceries")
        return
    data["tasks"].append(task)
    save_data(data)
    await update.message.reply_text(f"✅ Added: *{task}*", parse_mode=ParseMode.MARKDOWN)


async def remove_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    task = " ".join(context.args)
    if task in data["tasks"]:
        data["tasks"].remove(task)
        save_data(data)
        await update.message.reply_text(f"🗑️ Removed: *{task}*", parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text("❌ Task not found.")


async def list_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not data["tasks"]:
        await update.message.reply_text("📭 Your task list is empty.")
        return
    msg = "\n".join(f"• {t}" for t in data["tasks"])
    await update.message.reply_text(f"📝 *Current tasks:*\n{msg}", parse_mode=ParseMode.MARKDOWN)


# ---------- Alarm helpers ---------------------------------------------------
def parse_hhmm(s: str) -> time | None:
    try:
        h, m = map(int, s.split(":"))
        return time(hour=h, minute=m, tzinfo=timezone.utc)
    except Exception:
        return None


def schedule_daily(application, alarm_time: time, text: str):
    """Register a daily job and store reference in data."""
    job = application.job_queue.run_daily(
        lambda ctx: ctx.bot.send_message(chat_id=OWNER_CHAT_ID, text=f"⏰ {text}"),
        time=alarm_time,
    )
    return job
def schedule_weekend(application, alarm_time: time, text: str):
    from telegram.ext import Job
    from telegram.ext import WeekDay
    job = application.job_queue.run_daily(
        lambda ctx: ctx.bot.send_message(chat_id=OWNER_CHAT_ID, text=f"🏖️ {text}"),
        time=alarm_time,
        days=(WeekDay.SATURDAY, WeekDay.SUNDAY),
    )
    return job


def restore_jobs(application):
    """Re-create scheduled jobs from saved data."""
    for alarm in data["alarms"]:
        schedule_daily(application, parse_hhmm(alarm["time"]), alarm["text"])
    for alarm in data["weekend_alarms"]:
        schedule_weekend(application, parse_hhmm(alarm["time"]), alarm["text"])


# ---------- Alarm commands --------------------------------------------------
async def add_alarm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("⚠️ Usage: /addalarm 07:00 Morning devotion")
        return
    t = parse_hhmm(context.args[0])
    if t is None:
        await update.message.reply_text("⚠️ Time must be HH:MM, e.g., 07:30")
        return
    text = " ".join(context.args[1:])
    schedule_daily(context.application, t, text)
    data["alarms"].append({"time": context.args[0], "text": text})
    save_data(data)
    await update.message.reply_text(f"✅ Daily alarm set at *{context.args[0]}*.", parse_mode=ParseMode.MARKDOWN)


async def add_weekend_alarm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("⚠️ Usage: /addweekend 08:00 Weekend reminder")
        return
    t = parse_hhmm(context.args[0])
    if t is None:
        await update.message.reply_text("⚠️ Time must be HH:MM.")
        return
    text = " ".join(context.args[1:])
    schedule_weekend(context.application, t, text)
    data["weekend_alarms"].append({"time": context.args[0], "text": text})
    save_data(data)
    await update.message.reply_text(f"✅ Weekend alarm set at *{context.args[0]}*.", parse_mode=ParseMode.MARKDOWN)


async def list_alarms(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not (data["alarms"] or data["weekend_alarms"]):
        await update.message.reply_text("📭 No alarms set.")
        return
    lines = []
    for i, a in enumerate(data["alarms"], 1):
        lines.append(f"{i}. ⏰ {a['time']}  – {a['text']}")
    offset = len(lines)
    for j, a in enumerate(data["weekend_alarms"], 1):
        lines.append(f"{offset+j}. 🏖️ {a['time']}  – {a['text']}")
    await update.message.reply_text("*Alarms:*\n" + "\n".join(lines), parse_mode=ParseMode.MARKDOWN)


async def delete_alarm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("⚠️ Usage: /deletealarm 2")
        return
    idx = int(context.args[0]) - 1
    all_alarms = data["alarms"] + data["weekend_alarms"]
    if idx < 0 or idx >= len(all_alarms):
        await update.message.reply_text("❌ Invalid index.")
        return
    removed = all_alarms[idx]
    # remove from correct list
    if idx < len(data["alarms"]):
        data["alarms"].pop(idx)
    else:
        data["weekend_alarms"].pop(idx - len(data["alarms"]))
    save_data(data)
    await update.message.reply_text(f"🗑️ Removed alarm *{removed['time']}*.", parse_mode=ParseMode.MARKDOWN)
    # NOTE: Job removal is automatic after restart; for live removal you'd track Job objects.

# ---------- Hourly task sender ---------------------------------------------
async def hourly_sender(context: ContextTypes.DEFAULT_TYPE):
    if data["tasks"]:
        msg = "\n".join(f"• {t}" for t in data["tasks"])
    else:
        msg = "Your task list is empty."
    await context.bot.send_message(chat_id=OWNER_CHAT_ID, text=f"⏰ Hourly Task List:\n{msg}")

# ---------- Main -----------------------------------------------------------
async def main():
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    # Register commands
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_cmd))
    application.add_handler(CommandHandler("id", show_id))

    application.add_handler(CommandHandler("add", add_task))
    application.add_handler(CommandHandler("remove", remove_task))
    application.add_handler(CommandHandler("list", list_tasks))

    application.add_handler(CommandHandler("addalarm", add_alarm))
    application.add_handler(CommandHandler("addweekend", add_weekend_alarm))
    application.add_handler(CommandHandler("listalarms", list_alarms))
    application.add_handler(CommandHandler("deletealarm", delete_alarm))

    # Hourly repeating job (first run in 30 s for quick test)
    application.job_queue.run_repeating(hourly_sender, interval=3600, first=30)

    # Restore saved alarms
    restore_jobs(application)

    print("Bot is running… Press Ctrl+C to stop.")
    await application.run_polling()


if __name__ == "__main__":
    asyncio.run(main())
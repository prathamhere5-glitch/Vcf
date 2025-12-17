import os
import time
import sqlite3
from collections import defaultdict
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    BotCommand,
    BotCommandScopeChat,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# ================= CONFIG =================

BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = 6729390752

UPLOAD_DIR = "/tmp/files"
os.makedirs(UPLOAD_DIR, exist_ok=True)

START_PHOTO_URL = "https://telegram.org/img/t_logo.png"
TRIAL_DURATION = 24 * 3600

BUY_MSG = (
    "❌ <b>Access Locked</b>\n\n"
    "💳 Buy access from 👉 <b>@indiawsagent</b>"
)

USER_STATE = defaultdict(str)
USER_DATA = defaultdict(dict)

# ================= XLSX =================

try:
    from openpyxl import load_workbook
    XLSX_ENABLED = True
except Exception:
    XLSX_ENABLED = False

# ================= SQLITE =================

conn = sqlite3.connect("data.db", check_same_thread=False)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS sudo_users (
    user_id INTEGER PRIMARY KEY,
    expires_at INTEGER
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS trial_users (
    user_id INTEGER PRIMARY KEY,
    start_time INTEGER
)
""")
conn.commit()

# ================= ACCESS =================

def has_access(uid: int) -> bool:
    if uid == OWNER_ID:
        return True

    now = int(time.time())

    row = cur.execute(
        "SELECT expires_at FROM sudo_users WHERE user_id=?",
        (uid,)
    ).fetchone()
    if row and row[0] > now:
        return True

    row = cur.execute(
        "SELECT start_time FROM trial_users WHERE user_id=?",
        (uid,)
    ).fetchone()
    if row and now - row[0] <= TRIAL_DURATION:
        return True

    return False


async def ensure_trial(update: Update):
    uid = update.effective_user.id
    now = int(time.time())

    row = cur.execute(
        "SELECT start_time FROM trial_users WHERE user_id=?",
        (uid,)
    ).fetchone()

    if not row:
        cur.execute(
            "INSERT INTO trial_users VALUES (?, ?)",
            (uid, now)
        )
        conn.commit()

        await update.message.reply_text(
            "🎁 <b>24 Hours Free Trial Activated</b>",
            parse_mode="HTML"
        )


async def deny(update: Update):
    await update.message.reply_text(BUY_MSG, parse_mode="HTML")

# ================= ERROR =================

async def error_handler(update, context):
    print("ERROR:", context.error)
    if update and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "⚠️ Something went wrong. Please try again."
            )
        except Exception:
            pass

# ================= START / HELP / STATUS =================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_photo(
        photo=START_PHOTO_URL,
        caption=(
            "🤖 <b>Smart CV Bot</b>\n\n"
            "📇 TXT ⇄ VCF\n"
            "📊 XLSX ➜ VCF\n"
            "✏️ Rename Contacts (VCF)\n"
            "📝 Rename Files\n"
            "🎁 24h Free Trial\n\n"
            "👉 Use the menu below"
        ),
        parse_mode="HTML"
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/cv_txt_to_vcf\n"
        "/cv_vcf_to_txt\n"
        "/cv_xlsx_to_vcf\n"
        "/renamectc\n"
        "/renamefile\n"
        "/status"
    )


async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    now = int(time.time())

    if uid == OWNER_ID:
        await update.message.reply_text(
            "👑 <b>Owner</b>\nAccess: Unlimited",
            parse_mode="HTML"
        )
        return

    row = cur.execute(
        "SELECT expires_at FROM sudo_users WHERE user_id=?",
        (uid,)
    ).fetchone()
    if row and row[0] > now:
        rem = row[0] - now
        await update.message.reply_text(
            f"🧑‍💼 <b>Sudo Access</b>\n"
            f"⏳ {rem//3600}h {(rem%3600)//60}m left",
            parse_mode="HTML"
        )
        return

    row = cur.execute(
        "SELECT start_time FROM trial_users WHERE user_id=?",
        (uid,)
    ).fetchone()
    if row and now - row[0] <= TRIAL_DURATION:
        rem = TRIAL_DURATION - (now - row[0])
        await update.message.reply_text(
            f"🎁 <b>Free Trial</b>\n"
            f"⏳ {rem//3600}h {(rem%3600)//60}m left",
            parse_mode="HTML"
        )
        return

    await update.message.reply_text(BUY_MSG, parse_mode="HTML")

# ================= MAIN =================

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("status", status_cmd))

    app.add_handler(MessageHandler(filters.Document.ALL, file_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    app.add_error_handler(error_handler)
    app.run_polling()


if __name__ == "__main__":
    main()

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

#================ CONFIG =================

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
# ================= FILE HANDLER =================

async def file_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not update.message or not update.message.document:
        return

    doc = update.message.document
    path = os.path.join(UPLOAD_DIR, doc.file_name)
    await (await doc.get_file()).download_to_drive(path)

    st = USER_STATE.get(uid)

    if st == "RENAMECTC_FILE":
        USER_DATA[uid]["vcf"] = path
        USER_STATE[uid] = "RENAMECTC_NAME"
        await update.message.reply_text("✏️ Enter new contact name")

    elif st == "RENAMEFILE_FILE":
        USER_DATA[uid]["file"] = path
        USER_DATA[uid]["ext"] = os.path.splitext(doc.file_name)[1]
        USER_STATE[uid] = "RENAMEFILE_NAME"
        await update.message.reply_text("📝 Enter new file name")

    else:
        await update.message.reply_text("📁 File received")

# ================= TEXT HANDLER =================

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    txt = update.message.text.strip()
    st = USER_STATE.get(uid)

    if st == "RENAMECTC_NAME":
        src = USER_DATA[uid].get("vcf")
        if not src or not os.path.exists(src):
            await update.message.reply_text("❌ File missing")
            USER_STATE.pop(uid, None)
            USER_DATA.pop(uid, None)
            return

        out = src  # keep same filename
        rename_vcf_contacts(src, out, txt)

        await update.message.reply_document(
            open(out, "rb"),
            filename=os.path.basename(out)
        )

        USER_STATE.pop(uid, None)
        USER_DATA.pop(uid, None)

    elif st == "RENAMEFILE_NAME":
        src = USER_DATA[uid].get("file")
        ext = USER_DATA[uid].get("ext", "")
        if not src or not os.path.exists(src):
            await update.message.reply_text("❌ File missing")
            USER_STATE.pop(uid, None)
            USER_DATA.pop(uid, None)
            return

        new_path = os.path.join(UPLOAD_DIR, txt + ext)
        os.rename(src, new_path)

        await update.message.reply_document(
            open(new_path, "rb"),
            filename=txt + ext
        )

        USER_STATE.pop(uid, None)
        USER_DATA.pop(uid, None)

    else:
        await update.message.reply_text("❓ Unknown input")

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

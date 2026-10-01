import os
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

# ====================== SETTINGS ======================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WP_URL = "https://anontow.com/wp-json/wp/v2/posts"
WP_USERNAME = "1uieduiwi"
WP_APP_PASSWORD = "MpMVKTlDsJSjuwhdcldKxCZl"
# ======================================================

def create_wordpress_post(title, content, meta_desc="", focus_kw=""):
    data = {
        "title": title,
        "content": content,
        "status": "pending",
        "meta": {
            "_yoast_wpseo_metadesc": meta_desc,
            "_yoast_wpseo_focuskw": focus_kw
        }
    }

    response = requests.post(
        WP_URL,
        auth=(WP_USERNAME, WP_APP_PASSWORD),
        json=data,
        timeout=40
    )

    if response.status_code in [200, 201]:
        return True, response.json().get("link")
    else:
        return False, f"Error {response.status_code}\n{response.text}"


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or not message.text:
        return

    text = message.text.strip()
    parts = text.split("---")

    if len(parts) < 4:
        await message.reply_text(
            "Please send in this format:\n\n"
            "Title of the post\n"
            "---\n"
            "Meta description here\n"
            "---\n"
            "focus keyword here\n"
            "---\n"
            "<h2>Your HTML content</h2>\n"
            "<p>Paste full HTML here...</p>"
        )
        return

    title     = parts[0].strip()
    meta_desc = parts[1].strip()
    focus_kw  = parts[2].strip()
    content   = parts[3].strip()

    await message.reply_text("Creating pending post...")

    success, result = create_wordpress_post(title, content, meta_desc, focus_kw)

    if success:
        await message.reply_text(f"✅ Post created as Pending!\n\n{result}")
    else:
        await message.reply_text(f"❌ Failed:\n{result}")


if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("Bot is running...")
    app.run_polling()

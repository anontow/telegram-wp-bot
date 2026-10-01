import os
import re
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# ====================== SETTINGS ======================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WP_URL = "https://anontow.com/wp-json/wp/v2/posts"
WP_USERNAME = "1uieduiwi"
WP_APP_PASSWORD = "MpMVKTlDsJSjuwhdcldKxCZl"
# ======================================================

# Your categories (ID → Name)
CATEGORIES = {
    4: "Business",
    111: "Crypto",
    104: "Featured",
    82: "iPhone",
    5: "Lifestyle",
    74: "Marketing & SEO",
    77: "Movie",
    8: "Technology",
    1: "Uncategorized",
    203: "Wordpress",
}


def create_wordpress_post(title, content, meta_desc="", focus_kw="", slug="", category_id=None):
    data = {
        "title": title,
        "content": content,
        "status": "pending",
        "meta": {
            "_yoast_wpseo_metadesc": meta_desc,
            "_yoast_wpseo_focuskw": focus_kw,
        },
    }

    if slug:
        slug = slug.strip().strip("/")
        data["slug"] = slug

    if category_id:
        data["categories"] = [category_id]

    response = requests.post(
        WP_URL,
        auth=(WP_USERNAME, WP_APP_PASSWORD),
        json=data,
        timeout=40,
    )

    if response.status_code in [200, 201]:
        return True, response.json().get("link")
    else:
        return False, f"Error {response.status_code}\n{response.text}"


def parse_article(text: str):
    """Extract title, content, focus keyword, meta description and slug from pasted text."""
    title = ""
    content = text
    focus_kw = ""
    meta_desc = ""
    slug = ""

    # Extract title from first <h1>...</h1>
    h1_match = re.search(r"<h1[^>]*>(.*?)</h1>", text, re.IGNORECASE | re.DOTALL)
    if h1_match:
        title = re.sub(r"<[^>]+>", "", h1_match.group(1)).strip()
        # Remove the first h1 from content so it doesn't appear twice
        content = re.sub(r"<h1[^>]*>.*?</h1>", "", text, count=1, flags=re.IGNORECASE | re.DOTALL).strip()

    # Extract Focus keyword
    fk_match = re.search(r"Focus keyword:\s*(.+)", text, re.IGNORECASE)
    if fk_match:
        focus_kw = fk_match.group(1).strip()

    # Extract Meta description
    md_match = re.search(r"Meta description:\s*(.+)", text, re.IGNORECASE)
    if md_match:
        meta_desc = md_match.group(1).strip()

    # Extract Suggested slug
    slug_match = re.search(r"Suggested slug:\s*(.+)", text, re.IGNORECASE)
    if slug_match:
        slug = slug_match.group(1).strip()

    return title, content, focus_kw, meta_desc, slug


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show category buttons when /start is pressed."""
    # Clear any previous collected messages
    context.user_data.clear()

    keyboard = []
    row = []
    for cat_id, cat_name in CATEGORIES.items():
        row.append(InlineKeyboardButton(cat_name, callback_data=f"cat_{cat_id}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "👋 Welcome!\n\nPlease select a category for your post:",
        reply_markup=reply_markup,
    )


async def category_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle category button click."""
    query = update.callback_query
    await query.answer()

    cat_id = int(query.data.split("_")[1])
    cat_name = CATEGORIES.get(cat_id, "Unknown")

    # Save selected category and prepare to collect messages
    context.user_data["selected_category"] = cat_id
    context.user_data["selected_category_name"] = cat_name
    context.user_data["collected_parts"] = []  # Store all pasted pieces

    # Done button
    done_keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Done – Post Now", callback_data="done_post")]
    ])

    await query.edit_message_text(
        f"✅ Category selected: **{cat_name}**\n\n"
        f"Now paste your full article.\n"
        f"(You can paste long text – Telegram may split it into several messages)\n\n"
        f"When you finish pasting, tap the button below.",
        parse_mode="Markdown",
        reply_markup=done_keyboard,
    )


async def collect_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Collect message pieces until user taps Done."""
    message = update.message
    if not message or not message.text:
        return

    category_id = context.user_data.get("selected_category")
    if not category_id:
        await message.reply_text(
            "⚠️ Please click /start first and select a category."
        )
        return

    # Add this message to the collected parts
    if "collected_parts" not in context.user_data:
        context.user_data["collected_parts"] = []

    context.user_data["collected_parts"].append(message.text)

    # Just confirm silently (no need to reply every time to avoid spam)
    # Optional: you can uncomment the line below if you want feedback
    # await message.reply_text("📄 Part received...")


async def done_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Combine all collected parts and create the post."""
    query = update.callback_query
    await query.answer()

    category_id = context.user_data.get("selected_category")
    category_name = context.user_data.get("selected_category_name", "None")
    parts = context.user_data.get("collected_parts", [])

    if not category_id:
        await query.edit_message_text("⚠️ No category selected. Please click /start again.")
        return

    if not parts:
        await query.edit_message_text(
            "⚠️ No article received yet.\nPlease paste your article first, then tap Done."
        )
        return

    # Combine all parts into one full text
    full_text = "\n".join(parts)

    await query.edit_message_text(f"⏳ Creating pending post in **{category_name}**...", parse_mode="Markdown")

    # Parse the full article
    title, content, focus_kw, meta_desc, slug = parse_article(full_text)

    # Collect missing fields warnings
    warnings = []
    if not title:
        warnings.append("• Title (no <h1> found)")
    if not focus_kw:
        warnings.append("• Focus keyword")
    if not meta_desc:
        warnings.append("• Meta description")
    if not slug:
        warnings.append("• Suggested slug")

    if warnings:
        warning_text = "⚠️ Missing fields:\n" + "\n".join(warnings) + "\n\nStill creating the post..."
        await query.message.reply_text(warning_text)

    # Create the post
    success, result = create_wordpress_post(
        title=title or "Untitled",
        content=content,
        meta_desc=meta_desc,
        focus_kw=focus_kw,
        slug=slug,
        category_id=category_id,
    )

    if success:
        await query.message.reply_text(f"✅ Post created as Pending!\n\n{result}")
    else:
        await query.message.reply_text(f"❌ Failed:\n{result}")

    # Clear collected data after posting
    context.user_data["collected_parts"] = []


if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(category_selected, pattern=r"^cat_"))
    app.add_handler(CallbackQueryHandler(done_post, pattern=r"^done_post$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, collect_message))

    print("Bot is running...")
    app.run_polling()

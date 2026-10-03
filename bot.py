import os
import re
import requests

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    KeyboardButton,
)

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

WP_USERNAME = os.getenv("WP_USERNAME")
WP_APP_PASSWORD = os.getenv("WP_APP_PASSWORD")

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


def create_wordpress_post(
    title,
    content,
    meta_desc="",
    focus_kw="",
    slug="",
    category_id=None,
):
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

    try:
        response = requests.post(
            WP_URL,
            auth=(WP_USERNAME, WP_APP_PASSWORD),
            json=data,
            timeout=40,
        )
    except requests.RequestException as error:
        return False, f"Connection error\n{error}"

    if response.status_code in [200, 201]:
        return True, response.json().get("link")

    return False, f"Error {response.status_code}\n{response.text}"


def parse_article(text: str):
    """Extract title, content, focus keyword, meta description and slug."""

    title = ""
    content = text
    focus_kw = ""
    meta_desc = ""
    slug = ""

    # Extract title from first <h1>...</h1>
    h1_match = re.search(
        r"<h1[^>]*>(.*?)</h1>",
        text,
        re.IGNORECASE | re.DOTALL,
    )

    if h1_match:
        title = re.sub(r"<[^>]+>", "", h1_match.group(1)).strip()

        # Remove the first H1 from content
        content = re.sub(
            r"<h1[^>]*>.*?</h1>",
            "",
            text,
            count=1,
            flags=re.IGNORECASE | re.DOTALL,
        ).strip()

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


def get_main_keyboard():
    """Permanent keyboard that is always visible."""
    return ReplyKeyboardMarkup(
        [[KeyboardButton("New Post")]],
        resize_keyboard=True,
        one_time_keyboard=False,
    )


def get_article_keyboard():
    """Keyboard shown while pasting an article."""
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("Done - Post Now")],
            [KeyboardButton("Cancel")],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Paste your article here...",
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show category buttons + permanent New Post keyboard."""

    context.user_data.clear()

    # Show permanent New Post button
    await update.message.reply_text(
        "Welcome to Anontow Poster Bot!\n\n"
        "Tap **New Post** below to create a new article.",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard(),
    )


async def show_categories(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show category selection buttons."""

    context.user_data.clear()

    keyboard = []
    row = []

    for cat_id, cat_name in CATEGORIES.items():
        row.append(
            InlineKeyboardButton(
                cat_name,
                callback_data=f"cat_{cat_id}",
            )
        )

        if len(row) == 2:
            keyboard.append(row)
            row = []

    if row:
        keyboard.append(row)

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "Please select a category for your post:",
        reply_markup=reply_markup,
    )


async def category_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle category selection."""

    query = update.callback_query
    await query.answer()

    cat_id = int(query.data.split("_")[1])
    cat_name = CATEGORIES.get(cat_id, "Unknown")

    context.user_data["selected_category"] = cat_id
    context.user_data["selected_category_name"] = cat_name
    context.user_data["collected_parts"] = []

    await query.edit_message_text(f"Category selected: **{cat_name}**", parse_mode="Markdown")

    await query.message.reply_text(
        "Now paste your full article.\n\n"
        "Telegram may split a long article into several messages — that is okay.\n"
        "I will collect all parts automatically.\n\n"
        "When you finish, tap **Done - Post Now**.",
        parse_mode="Markdown",
        reply_markup=get_article_keyboard(),
    )


async def collect_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all text messages (New Post, Done, Cancel, article parts)."""

    message = update.message
    if not message or not message.text:
        return

    text = message.text.strip()

    # ---------- Permanent button: New Post ----------
    if text == "New Post":
        await show_categories(update, context)
        return

    category_id = context.user_data.get("selected_category")

    # ---------- Done ----------
    if text == "Done - Post Now":
        await done_post(update, context)
        return

    # ---------- Cancel ----------
    if text == "Cancel":
        context.user_data.clear()

        await message.reply_text(
            "Post cancelled.\n\nTap **New Post** to start again.",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard(),
        )
        return

    # ---------- Article part ----------
    if not category_id:
        await message.reply_text(
            "Please tap **New Post** first and select a category.",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard(),
        )
        return

    if "collected_parts" not in context.user_data:
        context.user_data["collected_parts"] = []

    context.user_data["collected_parts"].append(message.text)

    # No reply on every part → keeps chat clean


async def done_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Combine all parts and create the WordPress post."""

    message = update.message

    category_id = context.user_data.get("selected_category")
    category_name = context.user_data.get("selected_category_name", "None")
    parts = context.user_data.get("collected_parts", [])

    if not category_id:
        await message.reply_text(
            "No category selected.\nTap **New Post** to begin.",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard(),
        )
        return

    if not parts:
        await message.reply_text(
            "No article received yet.\nPlease paste your article first."
        )
        return

    full_text = "\n".join(parts)

    await message.reply_text(
        f"Creating pending post in **{category_name}**...",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove(),
    )

    title, content, focus_kw, meta_desc, slug = parse_article(full_text)

    warnings = []
    if not title:
        warnings.append("Title (no <h1> found)")
    if not focus_kw:
        warnings.append("Focus keyword")
    if not meta_desc:
        warnings.append("Meta description")
    if not slug:
        warnings.append("Suggested slug")

    success, result = create_wordpress_post(
        title=title or "Untitled",
        content=content,
        meta_desc=meta_desc,
        focus_kw=focus_kw,
        slug=slug,
        category_id=category_id,
    )

    if success:
        warning_text = ""
        if warnings:
            warning_text = (
                "Missing fields:\n"
                + "\n".join(f"• {w}" for w in warnings)
                + "\n\n"
            )

        await message.reply_text(
            f"Post created as Pending!\n\n{warning_text}{result}",
            reply_markup=get_main_keyboard(),
        )
    else:
        await message.reply_text(
            f"Failed to create the post.\n\n{result}",
            reply_markup=get_main_keyboard(),
        )

    # Clear session
    context.user_data.clear()


if __name__ == "__main__":

    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set.")

    if not WP_USERNAME:
        raise RuntimeError("WP_USERNAME is not set.")

    if not WP_APP_PASSWORD:
        raise RuntimeError("WP_APP_PASSWORD is not set.")

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(category_selected, pattern=r"^cat_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, collect_message))

    print("Bot is running...")
    app.run_polling()

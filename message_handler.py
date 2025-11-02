from telegram import MessageEntity, Update
from telegram.ext import CallbackContext
from primestats_adapter import format_primestats, parse_pasted_stats
from db_module import save_snapshot

def handle_pasted_stats(update: Update, context: CallbackContext) -> None:
    message = update.effective_message
    if not message:
        return
    text = message.text or message.caption
    if not text:
        return
    if message.chat and message.chat.type != "private":
        bot = context.bot
        bot_id = bot.id if bot else None
        bot_username = (bot.username or "").lower() if bot else ""
        mentioned = False
        if message.entities:
            for entity in message.entities:
                if entity.type == MessageEntity.MENTION:
                    mention = text[entity.offset:entity.offset + entity.length]
                    if mention.lstrip("@").lower() == bot_username:
                        mentioned = True
                        break
                if entity.type == MessageEntity.TEXT_MENTION and entity.user and bot_id and entity.user.id == bot_id:
                    mentioned = True
                    break
        reply_to_bot = (
            message.reply_to_message
            and message.reply_to_message.from_user
            and bot_id
            and message.reply_to_message.from_user.id == bot_id
        )
        if not mentioned and not reply_to_bot:
            return
    try:
        parsed_stats = parse_pasted_stats(text)
    except Exception:
        message.reply_text("Unable to parse stats. Please paste the raw Prime stats export text.")
        return
    if not parsed_stats:
        message.reply_text("Unable to parse stats. Please paste the raw Prime stats export text.")
        return
    for parsed_dict in parsed_stats:
        save_snapshot(parsed_dict)
        formatted_text = format_primestats(parsed_dict)
        message.reply_text(formatted_text)

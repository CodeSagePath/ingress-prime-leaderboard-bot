#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Glue Bot Module

This module integrates python-telegram-bot with the primestats parsing,
formatting, and database functionality.
"""

import logging
from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext

# Import required modules
from primestats_formatter import format_primestats
from primestats_adapter import parse_pasted_stats
from db_module import get_db_conn, save_snapshot

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot token placeholder
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"

def start(update: Update, context: CallbackContext) -> None:
    """Handle the /start command."""
    update.message.reply_text("Send me exported stat lines.")

def handle_pasted_stats(update: Update, context: CallbackContext) -> None:
    """
    Handle pasted stats from users.
    
    On DM: always parse.
    On group: parse only if bot is mentioned or message is a reply to bot.
    """
    message = update.message
    
    # Check if we should process this message
    if message.chat.type != 'private':  # Not a DM
        # Check if bot is mentioned
        bot_mentioned = False
        if message.entities:
            for entity in message.entities:
                if entity.type == 'mention' and '@' in message.text[entity.offset:entity.offset+entity.length]:
                    bot_mentioned = True
                    break
        
        # Check if message is a reply to bot
        reply_to_bot = message.reply_to_message and message.reply_to_message.from_user.is_bot
        
        # Skip if not mentioned and not a reply to bot
        if not bot_mentioned and not reply_to_bot:
            return
    
    # Parse the pasted stats
    try:
        parsed_stats = parse_pasted_stats(message.text)
        if not parsed_stats:
            message.reply_text("Could not parse any stats from your message. Please check the format.")
            return
        
        # Get database connection
        conn = get_db_conn()
        
        # Process each parsed stat
        for stat in parsed_stats:
            # Save to database
            result = save_snapshot(conn, stat)
            
            # Format the stats
            formatted_text = format_primestats(stat)
            
            # Reply with formatted text
            message.reply_text(formatted_text)
        
        # Close database connection
        conn.close()
        
    except Exception as e:
        logger.error(f"Error processing stats: {e}")
        message.reply_text("An error occurred while processing your stats. Please try again.")

def main() -> None:
    """Start the bot."""
    # Create the Updater and pass it your bot's token.
    updater = Updater(BOT_TOKEN)

    # Get the dispatcher to register handlers
    dispatcher = updater.dispatcher

    # Register the command handler
    dispatcher.add_handler(CommandHandler("start", start))
    
    # Register the message handler for pasted stats
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_pasted_stats))

    # Start the Bot
    updater.start_polling()
    
    # Run the bot until you press Ctrl-C
    updater.idle()

if __name__ == '__main__':
    main()
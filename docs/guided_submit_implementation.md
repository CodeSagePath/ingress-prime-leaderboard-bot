# Implementation Guide for Guided Submit Flow

This document provides a detailed implementation guide for adding a guided submit flow to complement the existing quick-submit functionality.

## Current Implementation Analysis

The current `/submit` command in [`bot/main.py`](bot/main.py:128-163) is a one-shot command that:
1. Parses the entire payload in one go
2. Validates all fields at once
3. Returns a single success or error message

## Proposed Guided Submit Implementation

### 1. Add New Constants

Add to the constants section in [`bot/main.py`](bot/main.py:27):

```python
CODENAME, FACTION = range(2)
AP, METRICS = range(2)  # Add these for guided submit flow
```

### 2. Create New Handler Functions

Add these functions after the existing submit function:

```python
async def guided_submit_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the guided submission flow."""
    if not update.message or not update.effective_user:
        return ConversationHandler.END
    
    session_factory = context.application.bot_data["session_factory"]
    async with session_scope(session_factory) as session:
        result = await session.execute(select(Agent).where(Agent.telegram_id == update.effective_user.id))
        agent = result.scalar_one_or_none()
    
    if not agent:
        await update.message.reply_text("Register first with /register.")
        return ConversationHandler.END
    
    await update.message.reply_text("Please enter your AP amount.")
    return AP


async def guided_submit_ap(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle AP input in guided submission."""
    if not update.message:
        return ConversationHandler.END
    
    try:
        ap = int(update.message.text.strip())
        if ap < 0:
            await update.message.reply_text("AP must be a positive number. Please enter your AP amount.")
            return AP
    except ValueError:
        await update.message.reply_text("AP must be a valid integer. Please enter your AP amount.")
        return AP
    
    context.user_data["ap"] = ap
    await update.message.reply_text(
        "Enter any additional metrics (key=value pairs, separated by semicolons), or send 'skip' to continue."
    )
    return METRICS


async def guided_submit_metrics(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle metrics input in guided submission."""
    if not update.message or not update.effective_user:
        return ConversationHandler.END
    
    text = update.message.text.strip()
    
    if text.lower() == "skip":
        # Skip metrics, proceed with just AP
        await _save_submission(update, context, {})
        return ConversationHandler.END
    
    try:
        # Parse metrics using the same logic as quick submit
        _, metrics = parse_submission(f"ap=0; {text}")
        await _save_submission(update, context, metrics)
        return ConversationHandler.END
    except ValueError as exc:
        await update.message.reply_text(
            f"Invalid format: {str(exc)}. Use key=value pairs separated by semicolons, or send 'skip' to continue."
        )
        return METRICS


async def guided_submit_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the guided submission flow."""
    if update.message:
        await update.message.reply_text("Submission cancelled.")
    context.user_data.clear()
    return ConversationHandler.END


async def _save_submission(update: Update, context: ContextTypes.DEFAULT_TYPE, metrics: dict) -> None:
    """Save the submission to the database."""
    if not update.message or not update.effective_user:
        return
    
    settings: Settings = context.application.bot_data["settings"]
    queue: Queue = context.application.bot_data["queue"]
    ap = context.user_data.get("ap", 0)
    
    session_factory = context.application.bot_data["session_factory"]
    async with session_scope(session_factory) as session:
        result = await session.execute(select(Agent).where(Agent.telegram_id == update.effective_user.id))
        agent = result.scalar_one_or_none()
        
        submission = Submission(agent_id=agent.id, ap=ap, metrics=metrics)
        session.add(submission)
    
    reply = await update.message.reply_text(f"Recorded {ap} AP for {agent.codename}.")
    
    if settings.autodelete_enabled and reply:
        schedule_message_deletion(
            queue,
            settings.telegram_token,
            reply.chat_id,
            update.message.message_id,
            reply.message_id,
            settings.autodelete_delay_seconds,
        )
    
    context.user_data.clear()
```

### 3. Modify the configure_handlers Function

Update the [`configure_handlers`](bot/main.py:179-192) function to include the guided submit handler:

```python
def configure_handlers(application: Application) -> None:
    application.add_handler(CommandHandler("start", start))
    
    # Registration handler
    register_handler = ConversationHandler(
        entry_points=[CommandHandler("register", register_start)],
        states={
            CODENAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_codename)],
            FACTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_faction)],
        },
        fallbacks=[CommandHandler("cancel", register_cancel)],
    )
    application.add_handler(register_handler)
    
    # Quick submit handler (existing)
    application.add_handler(CommandHandler("submit", submit))
    
    # Guided submit handler (new)
    guided_submit_handler = ConversationHandler(
        entry_points=[CommandHandler("submit_guided", guided_submit_start)],
        states={
            AP: [MessageHandler(filters.TEXT & ~filters.COMMAND, guided_submit_ap)],
            METRICS: [MessageHandler(filters.TEXT & ~filters.COMMAND, guided_submit_metrics)],
        },
        fallbacks=[CommandHandler("cancel", guided_submit_cancel)],
    )
    application.add_handler(guided_submit_handler)
    
    application.add_handler(CommandHandler("leaderboard", leaderboard))
```

### 4. Update Help Messages

Consider adding a help command that explains both submission methods:

```python
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    
    help_text = """
*Ingress Leaderboard Bot Commands*

/register - Register your agent codename and faction
/submit - Quick submit your stats in one message
/submit_guided - Step-by-step submission with validation
/leaderboard - View the current leaderboard
/help - Show this help message

*Quick Submit Examples:*
/submit ap=15000
/submit ap=15000; mu=500; links=100; fields=25

*Guided Submit:*
Follow the prompts to enter your AP and optional metrics step by step.
    """
    
    await update.message.reply_text(help_text, parse_mode="Markdown")
```

## Alternative: Hybrid Approach

Instead of adding a separate command, you could modify the existing `/submit` command to detect whether a payload is provided:

```python
async def submit_hybrid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle both quick submit and start guided flow."""
    if not update.message or not update.effective_user:
        return ConversationHandler.END
    
    text = update.message.text or ""
    _, _, payload = text.partition(" ")
    payload = payload.strip()
    
    if not payload:
        # No payload provided, start guided flow
        session_factory = context.application.bot_data["session_factory"]
        async with session_scope(session_factory) as session:
            result = await session.execute(select(Agent).where(Agent.telegram_id == update.effective_user.id))
            agent = result.scalar_one_or_none()
        
        if not agent:
            await update.message.reply_text("Register first with /register.")
            return ConversationHandler.END
        
        await update.message.reply_text("Please enter your AP amount.")
        return AP
    
    # Payload provided, use quick submit logic
    try:
        ap, metrics = parse_submission(payload)
    except ValueError as exc:
        await update.message.reply_text(str(exc))
        return ConversationHandler.END
    
    session_factory = context.application.bot_data["session_factory"]
    async with session_scope(session_factory) as session:
        result = await session.execute(select(Agent).where(Agent.telegram_id == update.effective_user.id))
        agent = result.scalar_one_or_none()
        if not agent:
            await update.message.reply_text("Register first with /register.")
            return ConversationHandler.END
        submission = Submission(agent_id=agent.id, ap=ap, metrics=metrics)
        session.add(submission)
    
    await update.message.reply_text(f"Recorded {ap} AP for {agent.codename}.")
    return ConversationHandler.END
```

With this approach, you'd need to restructure the handlers to use a ConversationHandler for the submit command as well.

## Testing Considerations

1. **Unit Tests**: Create tests for each new handler function
2. **Integration Tests**: Test the complete conversation flow
3. **Edge Cases**: Test with various invalid inputs
4. **Database Tests**: Verify submissions are saved correctly

## User Experience Considerations

1. **Clear Instructions**: Provide examples and format requirements
2. **Error Recovery**: Allow users to correct individual fields without restarting
3. **Progress Indicators**: Consider showing users their progress in multi-step flows
4. **Timeout Handling**: Implement reasonable timeouts for conversation states
5. **Confirmation**: Consider adding a confirmation step before final submission

## Migration Strategy

1. **Phase 1**: Implement the guided submit as a separate command (`/submit_guided`)
2. **Phase 2**: Gather user feedback and refine the flow
3. **Phase 3**: Consider implementing the hybrid approach or replacing the current flow
4. **Phase 4**: Update documentation and help messages
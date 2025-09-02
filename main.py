# main.py
"""
The main entry point for the Telegram Promotion Bot.

This script initializes the database, sets up the bot application,
registers all command and message handlers, schedules periodic jobs,
and starts the bot's polling loop.
"""
import logging
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ConversationHandler,
)

import config
import database as db
import handlers
import jobs

# --- Pre-run setup ---
# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


async def post_init(application: Application):
    """
    Post-initialization function.
    This is called by the Application builder after everything is set up.
    We use it to initialize our database.
    """
    logger.info("Initializing database...")
    await db.initialize_database()
    logger.info("Database initialized.")


def main() -> None:
    """
    Run the bot.
    This function builds the application, registers handlers,
    sets up jobs, and starts the bot.
    """
    # Create the Application and pass it your bot's token.
    builder = Application.builder().token(config.BOT_TOKEN).post_init(post_init)
    application = builder.build()

    # --- Setup Conversation Handlers for multi-step interactions ---
    
    # User-facing conversations
    normal_link_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(handlers.promote_normal_link_start, pattern='^set_normal_link$')],
        states={
            handlers.LINK_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.get_link_text)],
            handlers.LINK_URL: [MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.get_link_url)],
        },
        fallbacks=[CommandHandler('cancel', handlers.cancel_conversation)],
    )

    force_channel_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(handlers.set_force_channel_start, pattern='^set_force_channel$')],
        states={
            handlers.CHANNEL_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.get_channel_id)],
        },
        fallbacks=[CommandHandler('cancel', handlers.cancel_conversation)],
    )

    create_promotion_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(handlers.create_promotion_start, pattern='^create_promotion$')],
        states={
            handlers.AWAIT_PROMO_TYPE_FOR_CREATION: [CallbackQueryHandler(handlers.get_promotion_type_for_creation, pattern='^create_promo_')],
            handlers.AWAIT_BUDGET: [MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.get_promotion_budget)],
        },
        fallbacks=[CommandHandler('cancel', handlers.cancel_conversation)],
    )

    premium_broadcast_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(handlers.premium_broadcast_start, pattern='^premium_broadcast$')],
        states={
            handlers.AWAIT_IMAGE_FOR_BROADCAST: [MessageHandler(filters.PHOTO, handlers.get_image_for_broadcast)],
            handlers.AWAIT_BROADCAST_COUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.get_broadcast_count)],
        },
        fallbacks=[CommandHandler('cancel', handlers.cancel_conversation)],
    )

    # Admin conversations
    broadcast_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(handlers.admin_broadcast_start, pattern='^admin_broadcast$')],
        states={
            handlers.BROADCAST_MESSAGE: [MessageHandler(filters.ALL & ~filters.COMMAND, handlers.get_broadcast_message)],
        },
        fallbacks=[CommandHandler('cancel', handlers.cancel_conversation)],
    )
    
    add_premium_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(handlers.admin_add_premium_start, pattern='^admin_add_premium$')],
        states={
            handlers.AWAIT_USER_ID_FOR_PREMIUM: [MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.get_user_id_for_premium)],
            handlers.AWAIT_PREMIUM_DAYS: [MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.get_premium_days)],
        },
        fallbacks=[CommandHandler('cancel', handlers.cancel_conversation)],
    )
    
    remove_premium_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(handlers.admin_remove_premium_start, pattern='^admin_remove_premium$')],
        states={handlers.AWAIT_USER_ID_FOR_REMOVE_PREMIUM: [MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.get_user_id_for_remove_premium)]},
        fallbacks=[CommandHandler('cancel', handlers.cancel_conversation)],
    )

    ban_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(handlers.admin_ban_user_start, pattern='^admin_ban_user$')],
        states={handlers.AWAIT_USER_ID_FOR_BAN: [MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.get_user_id_for_ban)]},
        fallbacks=[CommandHandler('cancel', handlers.cancel_conversation)],
    )

    unban_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(handlers.admin_unban_user_start, pattern='^admin_unban_user$')],
        states={handlers.AWAIT_USER_ID_FOR_UNBAN: [MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.get_user_id_for_unban)]},
        fallbacks=[CommandHandler('cancel', handlers.cancel_conversation)],
    )

    stats_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(handlers.admin_get_stats_start, pattern='^admin_stats$')],
        states={handlers.AWAIT_USER_ID_FOR_STATS: [MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.get_user_id_for_stats)]},
        fallbacks=[CommandHandler('cancel', handlers.cancel_conversation)],
    )

    # --- Register handlers ---
    application.add_handler(normal_link_handler)
    application.add_handler(force_channel_handler)
    application.add_handler(create_promotion_handler)
    application.add_handler(premium_broadcast_handler)
    application.add_handler(broadcast_handler)
    application.add_handler(add_premium_handler)
    application.add_handler(remove_premium_handler)
    application.add_handler(ban_handler)
    application.add_handler(unban_handler)
    application.add_handler(stats_handler)

    # Register other handlers
    application.add_handler(CommandHandler("start", handlers.start))
    application.add_handler(CommandHandler("referral", handlers.referral))
    application.add_handler(CommandHandler("leaderboard", handlers.leaderboard))
    application.add_handler(CommandHandler("tasks", handlers.tasks))
    application.add_handler(CommandHandler("help", handlers.start)) # Alias for start
    application.add_handler(CommandHandler("cancel", handlers.cancel_conversation))

    # This general button handler processes all callbacks that are NOT entry points for conversations
    application.add_handler(CallbackQueryHandler(handlers.button_handler))
    
    # Specific message handlers
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, handlers.new_group_member))
    application.add_handler(MessageHandler(filters.FORWARDED & filters.ChatType.PRIVATE, handlers.handle_report_forward))


    # --- Schedule Jobs ---
    job_queue = application.job_queue
    job_queue.run_daily(jobs.daily_credit_reset, time=jobs.time(0, 0), name="daily_reset")
    job_queue.run_daily(jobs.weekly_leaderboard_reset, time=jobs.time(0, 0), days=(0,), name="weekly_reset")
    job_queue.run_daily(jobs.reset_image_broadcasts, time=jobs.time(0, 0), name="daily_image_broadcast_reset")


    # --- Start the Bot ---
    logger.info("Starting bot polling...")
    application.run_polling()


if __name__ == "__main__":
    main()


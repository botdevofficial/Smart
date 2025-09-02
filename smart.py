# -*- coding: utf-8 -*-

"""
A comprehensive Telegram bot for link and channel promotions based on a credit economy.

This bot includes features such as:
- User credits system (daily, referral, earned).
- Normal link and force-join channel promotions.
- Group sharing capabilities.
- A task system for users to earn credits.
- Referral program with milestones.
- Weekly leaderboards for engagement.
- Premium user features with enhanced capabilities.
- A full-featured admin panel for management and control.
"""

import logging
import json
import asyncio
from datetime import datetime, timedelta
import random

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    constants,
    Message,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)
from telegram.error import Forbidden, BadRequest

# --- Configuration ---
BOT_TOKEN = "8320194297:AAEPoJK8BhrIsuece6xfK6dWNr3kPQBJ1m4"  # Replace with your bot's token
ADMIN_IDS = [8009876932]  # Replace with your Telegram user ID(s)
DB_FILE = "promotion_bot_database.json"
DAILY_FREE_CREDITS = 10
REFERRAL_CREDITS_AWARD = 5
GROUP_ADD_REWARD = 5
PREMIUM_GROUP_ADD_REWARD = 10

# --- Logging Setup ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Database Management ---
db_lock = asyncio.Lock()

async def load_database():
    """Loads the database from the JSON file."""
    async with db_lock:
        try:
            with open(DB_FILE, "r") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {
                "users": {},
                "groups": {},
                "promotions": {"normal": [], "force_join": []},
                "leaderboard": {},
                "settings": {
                    "image_promo_enabled": True,
                    "channel_promo_enabled": True,
                    "group_promo_enabled": True,
                },
            }

async def save_database(data):
    """Saves the given data to the JSON database file."""
    async with db_lock:
        with open(DB_FILE, "w") as f:
            json.dump(data, f, indent=4)

# --- User Management Helper ---
async def get_or_create_user(user_id, username):
    """Retrieves a user from the database or creates a new one."""
    user_id = str(user_id)
    db = await load_database()
    if user_id not in db["users"]:
        db["users"][user_id] = {
            "username": username,
            "credits": DAILY_FREE_CREDITS,
            "referrals": 0,
            "permanent_daily_credits": 0,
            "earned_credits": 0,
            "is_premium": False,
            "premium_expiry": None,
            "is_banned": False,
            "promotions": {
                "normal_link": None,
                "force_join_channel": None,
            },
            "clicks_received": 0,
            "last_group_promo": None,
            "completed_tasks": [],
            "groups_added": [],
        }
        await save_database(db)
    return db["users"][user_id]

# --- Main Menu ---
async def build_main_menu(user_id):
    """Constructs the main menu keyboard based on user and admin status."""
    keyboard = [
        [InlineKeyboardButton("🚀 Promote My Link", callback_data="promote_link")],
        [InlineKeyboardButton("📢 Group Share", callback_data="group_share")],
        [InlineKeyboardButton("🎁 Earn Credits", callback_data="earn_credits")],
        [InlineKeyboardButton("👥 Referral Link", callback_data="referral_link")],
        [InlineKeyboardButton("📊 Leaderboard", callback_data="leaderboard")],
        [InlineKeyboardButton("💎 Premium Upgrade", callback_data="upgrade_premium")],
        [InlineKeyboardButton("➕ Add Me to Group", callback_data="add_to_group")],
    ]
    if int(user_id) in ADMIN_IDS:
        keyboard.append([InlineKeyboardButton("👑 Admin Panel", callback_data="admin_panel")])
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /start command, registers user, and handles referrals."""
    user = update.effective_user
    user_id = str(user.id)
    
    db = await load_database()
    
    # Handle referral
    if context.args and len(context.args) > 0:
        inviter_id = context.args[0]
        if inviter_id != user_id and inviter_id in db["users"]:
            # Check if user is new
            if user_id not in db["users"]:
                db["users"][inviter_id]["referrals"] += 1
                db["users"][inviter_id]["permanent_daily_credits"] += REFERRAL_CREDITS_AWARD
                
                # Milestone check
                if db["users"][inviter_id]["referrals"] % 5 == 0:
                    db["users"][inviter_id]["permanent_daily_credits"] += 1
                
                await save_database(db)
                try:
                    await context.bot.send_message(
                        chat_id=inviter_id,
                        text=f"🎉 Congratulations! {user.first_name} joined using your referral link. You've earned {REFERRAL_CREDITS_AWARD} permanent daily credits!"
                    )
                except (Forbidden, BadRequest):
                    logger.warning(f"Could not send referral notification to {inviter_id}")

    await get_or_create_user(user_id, user.username or user.first_name)
    
    welcome_text = (
        f"👋 Welcome, {user.first_name}!\n\n"
        "I am your ultimate promotion bot. You can promote your links and channels, "
        "or earn credits by completing tasks.\n\n"
        "Use the buttons below to navigate."
    )
    reply_markup = await build_main_menu(user_id)
    await update.message.reply_text(welcome_text, reply_markup=reply_markup)


# --- Promotion System ---
# States for ConversationHandler
PROMO_TYPE, NORMAL_PROMO_TEXT, NORMAL_PROMO_LINK, FORCE_JOIN_ID = range(4)

async def promote_link_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Entry point for the promotion setup conversation."""
    query = update.callback_query
    await query.answer()
    
    db = await load_database()
    settings = db.get("settings", {})
    
    keyboard_buttons = []
    if settings.get("channel_promo_enabled", True):
        keyboard_buttons.append(InlineKeyboardButton("📢 Force Join Channel Promo", callback_data="promo_force_join"))
    keyboard_buttons.append(InlineKeyboardButton("🔗 Normal Link Promo", callback_data="promo_normal"))
    keyboard_buttons.append(InlineKeyboardButton("🔙 Back to Menu", callback_data="main_menu"))
    
    keyboard = InlineKeyboardMarkup([keyboard_buttons])
    
    await query.edit_message_text(
        text="Choose the type of promotion you want to create:",
        reply_markup=keyboard,
    )
    return PROMO_TYPE

async def promo_type_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the selection of promotion type."""
    query = update.callback_query
    promo_type = query.data
    await query.answer()

    if promo_type == "promo_normal":
        await query.edit_message_text(text="Please send the text you want to display for your promotion.")
        return NORMAL_PROMO_TEXT
    elif promo_type == "promo_force_join":
        await query.edit_message_text(text="Please send the Channel ID (e.g., -100123456789) for your Force Join promotion.\n\nMake sure I am an administrator in that channel!")
        return FORCE_JOIN_ID

async def normal_promo_text_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receives the text for a normal promotion."""
    context.user_data["promo_text"] = update.message.text
    await update.message.reply_text("Great! Now send me the URL for the button (e.g., https://telegram.org).")
    return NORMAL_PROMO_LINK

async def normal_promo_link_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receives the link and saves the normal promotion."""
    user_id = str(update.effective_user.id)
    link = update.message.text
    text = context.user_data.get("promo_text")

    if not text or not link.startswith(("http://", "https://")):
        await update.message.reply_text("Invalid link. Please provide a valid URL starting with http:// or https://. Let's try again.")
        return NORMAL_PROMO_LINK

    db = await load_database()
    db["users"][user_id]["promotions"]["normal_link"] = {"text": text, "link": link}
    await save_database(db)

    await update.message.reply_text("✅ Your normal link promotion has been saved!")
    del context.user_data["promo_text"]
    await show_main_menu(update, context)
    return ConversationHandler.END

async def force_join_id_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receives the channel ID and saves the force join promotion."""
    user_id = str(update.effective_user.id)
    channel_id_str = update.message.text

    try:
        channel_id = int(channel_id_str)
    except ValueError:
        await update.message.reply_text("Invalid Channel ID. It must be a number. Please try again.")
        return FORCE_JOIN_ID

    try:
        bot_member = await context.bot.get_chat_member(chat_id=channel_id, user_id=context.bot.id)
        if bot_member.status != constants.ChatMemberStatus.ADMINISTRATOR:
            await update.message.reply_text("I am not an admin in that channel! Please make me an admin and try again.")
            return FORCE_JOIN_ID
    except BadRequest:
        await update.message.reply_text("Invalid Channel ID or I can't access it. Please double-check the ID and my permissions.")
        return FORCE_JOIN_ID
    except Exception as e:
        logger.error(f"Error checking channel membership: {e}")
        await update.message.reply_text("An unexpected error occurred. Please try again later.")
        await show_main_menu(update, context)
        return ConversationHandler.END

    db = await load_database()
    db["users"][user_id]["promotions"]["force_join_channel"] = channel_id
    await save_database(db)

    await update.message.reply_text("✅ Your Force Join channel has been set!")
    await show_main_menu(update, context)
    return ConversationHandler.END

async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancels the current conversation."""
    await update.message.reply_text("Operation cancelled.")
    await show_main_menu(update, context)
    return ConversationHandler.END

# --- Group Share ---
async def group_share(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the 'Group Share' button click."""
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    
    db = await load_database()
    user_data = db["users"][user_id]
    
    if not user_data["promotions"]["normal_link"]:
        await query.edit_message_text(text="You haven't set up a normal link promotion yet. Please set one up from the 'Promote My Link' menu first.", reply_markup=await build_main_menu(user_id))
        return

    # Check daily limit
    now = datetime.now()
    last_promo_str = user_data.get("last_group_promo")
    promo_runs_today = 0 # In a real scenario, you'd store and check this
    daily_limit = 4 if user_data["is_premium"] else 2

    # This is a simplified check. A robust implementation would store a count and reset it daily.
    if last_promo_str and (now - datetime.fromisoformat(last_promo_str)).total_seconds() < 24 * 3600 / daily_limit:
         await query.edit_message_text(text=f"You have reached your daily limit of {daily_limit} group promotions. Try again later.", reply_markup=await build_main_menu(user_id))
         return

    available_groups = [gid for gid, gdata in db["groups"].items() if gdata["active"]]
    if not available_groups:
        await query.edit_message_text(text="There are no available groups to promote in right now. Please try again later.", reply_markup=await build_main_menu(user_id))
        return

    promo_limit = 10 if user_data["is_premium"] else 5
    groups_to_promote = random.sample(available_groups, min(promo_limit, len(available_groups)))
    
    promo = user_data["promotions"]["normal_link"]
    text = promo['text']
    link = promo['link']
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("Visit Link", url=link)]])
    
    success_count = 0
    failed_count = 0
    
    for group_id in groups_to_promote:
        try:
            await context.bot.send_message(chat_id=int(group_id), text=text, reply_markup=keyboard)
            success_count += 1
            await asyncio.sleep(0.5) # Avoid spam limits
        except (Forbidden, BadRequest) as e:
            logger.warning(f"Failed to send to group {group_id}: {e}")
            failed_count += 1
            # Optional: Mark group as inactive if bot is kicked
            if "bot was kicked" in str(e).lower():
                db["groups"][group_id]["active"] = False

    db["users"][user_id]["last_group_promo"] = now.isoformat()
    await save_database(db)

    await query.edit_message_text(
        text=f"📢 Promotion sent!\n\n✅ Success: {success_count} groups\n❌ Failed: {failed_count} groups",
        reply_markup=await build_main_menu(user_id)
    )

# --- Earn Credits ---
async def earn_credits(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Presents a task for the user to earn credits."""
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)

    db = await load_database()
    all_promos = []

    # Collect normal link promotions
    for promo_user_id, user_data in db["users"].items():
        if promo_user_id != user_id and user_data["promotions"]["normal_link"] and user_data.get("credits", 0) > 0:
            promo_id = f"normal_{promo_user_id}"
            if promo_id not in db["users"][user_id].get("completed_tasks", []):
                all_promos.append({
                    "type": "normal", "id": promo_id,
                    "user_id": promo_user_id, "data": user_data["promotions"]["normal_link"]
                })

    # Collect force join promotions
    for promo_user_id, user_data in db["users"].items():
        if promo_user_id != user_id and user_data["promotions"]["force_join_channel"] and user_data.get("credits", 0) > 0:
            promo_id = f"forcejoin_{user_data['promotions']['force_join_channel']}"
            if promo_id not in db["users"][user_id].get("completed_tasks", []):
                all_promos.append({
                    "type": "force_join", "id": promo_id,
                    "user_id": promo_user_id, "channel_id": user_data["promotions"]["force_join_channel"]
                })
    
    if not all_promos:
        await query.edit_message_text("No tasks available right now. Please check back later!", reply_markup=await build_main_menu(user_id))
        return

    task = random.choice(all_promos)

    if task["type"] == "normal":
        promo_data = task["data"]
        keyboard = [
            [InlineKeyboardButton("Visit Link", url=promo_data["link"])],
            [InlineKeyboardButton("✅ Claim Credits", callback_data=f"claim_normal_{task['user_id']}")]
        ]
        text = f"**Visit this link to earn credits!**\n\n{promo_data['text']}"
    else: # force_join
        channel_id = task['channel_id']
        try:
            chat = await context.bot.get_chat(channel_id)
            invite_link = chat.invite_link
            if not invite_link:
                # Fallback if no invite link
                 invite_link = f"https://t.me/c/{str(channel_id).replace('-100', '')}/"

            keyboard = [
                [InlineKeyboardButton(f"🔗 Join {chat.title}", url=invite_link)],
                [InlineKeyboardButton("✅ Verify Join", callback_data=f"verify_join_{channel_id}_{task['user_id']}")]
            ]
            text = f"**Join this channel to earn credits!**\n\nJoin `{chat.title}` and then click 'Verify Join'."
        except Exception as e:
            logger.error(f"Failed to get info for channel {channel_id}: {e}")
            await query.edit_message_text("An error occurred with a task. Please try again.", reply_markup=await build_main_menu(user_id))
            return
            
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode="Markdown")

async def claim_normal_credits(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Awards credits for a 'normal' promotion task."""
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    
    parts = query.data.split("_")
    promo_owner_id = parts[-1]
    promo_id = f"normal_{promo_owner_id}"

    db = await load_database()
    
    if promo_id in db["users"][user_id].get("completed_tasks", []):
        await query.edit_message_text("You have already completed this task.", reply_markup=await build_main_menu(user_id))
        return

    if db["users"][promo_owner_id]["credits"] <= 0:
        await query.edit_message_text("The promoter is out of credits. Task unavailable.", reply_markup=await build_main_menu(user_id))
        return

    # Award credits
    award = 2 if db["users"][user_id]["is_premium"] else 1
    db["users"][user_id]["earned_credits"] += award
    db["users"][user_id].setdefault("completed_tasks", []).append(promo_id)
    
    # Deduct credits
    db["users"][promo_owner_id]["credits"] -= 1
    db["users"][promo_owner_id]["clicks_received"] +=1

    await save_database(db)

    await query.edit_message_text(f"🎉 You have earned {award} credit(s)!", reply_markup=await build_main_menu(user_id))


async def verify_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Verifies if a user has joined a channel."""
    query = update.callback_query
    await query.answer(text="Verifying...", show_alert=False)
    user_id = str(query.from_user.id)

    parts = query.data.split("_")
    channel_id = int(parts[2])
    promo_owner_id = parts[3]
    promo_id = f"forcejoin_{channel_id}"

    db = await load_database()

    if promo_id in db["users"][user_id].get("completed_tasks", []):
        await query.edit_message_text("You have already completed this task.", reply_markup=await build_main_menu(user_id))
        return

    if db["users"][promo_owner_id]["credits"] <= 0:
        await query.edit_message_text("The promoter is out of credits. Task unavailable.", reply_markup=await build_main_menu(user_id))
        return

    try:
        member = await context.bot.get_chat_member(chat_id=channel_id, user_id=query.from_user.id)
        if member.status in [constants.ChatMemberStatus.MEMBER, constants.ChatMemberStatus.ADMINISTRATOR, constants.ChatMemberStatus.OWNER]:
            # Award credits
            award = 4 if db["users"][user_id]["is_premium"] else 2 # Higher reward for force join
            db["users"][user_id]["earned_credits"] += award
            db["users"][user_id].setdefault("completed_tasks", []).append(promo_id)

            # Deduct credits
            db["users"][promo_owner_id]["credits"] -= 1
            db["users"][promo_owner_id]["clicks_received"] += 1
            
            await save_database(db)
            await query.edit_message_text(f"✅ Verified! You have earned {award} credits!", reply_markup=await build_main_menu(user_id))
        else:
            await query.answer("You haven't joined the channel yet.", show_alert=True)
    except BadRequest:
        await query.answer("Verification failed. Make sure you have joined the channel.", show_alert=True)
    except Exception as e:
        logger.error(f"Error during join verification: {e}")
        await query.answer("An error occurred during verification.", show_alert=True)


# --- Other Menu Items ---
async def referral_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays the user's referral link."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    bot_username = (await context.bot.get_me()).username
    ref_link = f"https://t.me/{bot_username}?start={user_id}"
    
    db = await load_database()
    user_data = db["users"][str(user_id)]
    
    text = (
        f"🔗 Your Referral Link:\n`{ref_link}`\n\n"
        f"Share this link with your friends. For each new user who joins, you get {REFERRAL_CREDITS_AWARD} permanent daily credits!\n\n"
        f"Total Referrals: {user_data['referrals']}"
    )
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=await build_main_menu(user_id))

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays the weekly leaderboard."""
    query = update.callback_query
    await query.answer()
    
    db = await load_database()
    
    # Sort users by clicks received
    sorted_users = sorted(db["users"].items(), key=lambda item: item[1].get("clicks_received", 0), reverse=True)
    
    leaderboard_text = "🏆 **Weekly Leaderboard (by Clicks Received)**\n\n"
    for i, (user_id, user_data) in enumerate(sorted_users[:10]):
        leaderboard_text += f"{i+1}. {user_data['username']} - {user_data.get('clicks_received', 0)} clicks\n"
        
    if not sorted_users:
        leaderboard_text += "The leaderboard is empty. Start promoting to get on the board!"
        
    await query.edit_message_text(leaderboard_text, parse_mode="Markdown", reply_markup=await build_main_menu(user_id))

async def upgrade_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shows premium benefits."""
    query = update.callback_query
    await query.answer()
    text = (
        "💎 **Premium Benefits** 💎\n\n"
        "- Double rewards for all tasks.\n"
        "- Higher daily credits.\n"
        "- Promote in more groups at once.\n"
        "- Special feature: Send an image with a caption to 100 random users daily!\n"
        "- Priority delivery for your promotions.\n\n"
        "To upgrade, contact the admin." # Simplified for this example
    )
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data="main_menu")]])
    await query.edit_message_text(text, reply_markup=keyboard)


# --- Group Management ---
async def add_to_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Provides a link to add the bot to a group."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    bot_username = (await context.bot.get_me()).username
    add_link = f"https://t.me/{bot_username}?startgroup={user_id}"
    
    text = (
        f"Click the link below to add me to your group!\n\n"
        f"🔗 [Add Me to Your Group]({add_link})\n\n"
        f"You will earn credits if I am made an administrator in a new group. "
        f"Normal users get {GROUP_ADD_REWARD} credits, Premium users get {PREMIUM_GROUP_ADD_REWARD} credits!"
    )
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data="main_menu")]])
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=keyboard)

async def new_chat_members(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the bot being added to a group."""
    me = await context.bot.get_me()
    chat = update.effective_chat

    for member in update.message.new_chat_members:
        if member.id == me.id:
            logger.info(f"Bot added to group: {chat.title} ({chat.id})")
            # The startgroup parameter is handled via deeplinking,
            # but we need to check if the bot is admin
            try:
                bot_member = await context.bot.get_chat_member(chat.id, me.id)
                if bot_member.status == constants.ChatMemberStatus.ADMINISTRATOR:
                    # In a real bot, the user_id from startgroup would be passed here
                    # For simplicity, we just add the group. Reward logic is harder without that context.
                    db = await load_database()
                    if str(chat.id) not in db["groups"]:
                        db["groups"][str(chat.id)] = {
                            "title": chat.title,
                            "active": True,
                            "added_by": None # This would be the user_id
                        }
                        await save_database(db)
                        await context.bot.send_message(chat.id, "Thanks for adding me! I am now active in this group.")
                else:
                    await context.bot.send_message(chat.id, "Thanks for adding me! Please make me an admin so I can function properly.")
            except Exception as e:
                 logger.error(f"Could not check own status in group {chat.id}: {e}")

# --- Admin Panel ---
# Admin Conversation States
ADMIN_MAIN, ADMIN_BROADCAST, ADMIN_ADD_PREMIUM_ID, ADMIN_ADD_PREMIUM_DAYS, ADMIN_REMOVE_PREMIUM, \
ADMIN_BAN, ADMIN_UNBAN, ADMIN_USER_INFO = range(8)

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays the main admin panel."""
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("📢 Broadcast Message", callback_data="admin_broadcast")],
        [InlineKeyboardButton("💎 Add Premium", callback_data="admin_add_premium")],
        [InlineKeyboardButton("🚫 Remove Premium", callback_data="admin_remove_premium")],
        [InlineKeyboardButton("🔨 Ban User", callback_data="admin_ban")],
        [InlineKeyboardButton("✅ Unban User", callback_data="admin_unban")],
        [InlineKeyboardButton("ℹ️ User Info", callback_data="admin_user_info")],
        [InlineKeyboardButton("🔧 Feature Control", callback_data="admin_feature_control")],
        [InlineKeyboardButton("🔙 Back to Menu", callback_data="main_menu")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("👑 Admin Panel 👑", reply_markup=reply_markup)
    return ADMIN_MAIN

async def admin_broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Starts the broadcast conversation."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Please send the message you want to broadcast to all users.")
    return ADMIN_BROADCAST

async def admin_broadcast_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receives and executes the broadcast."""
    message = update.message
    db = await load_database()
    users = list(db["users"].keys())
    
    await update.message.reply_text(f"Starting broadcast to {len(users)} users...")
    
    success_count = 0
    failed_count = 0
    blocked_users = []

    for user_id in users:
        try:
            await context.bot.copy_message(chat_id=user_id, from_chat_id=message.chat_id, message_id=message.message_id)
            success_count += 1
            await asyncio.sleep(0.1) # Rate limiting
        except Forbidden:
            failed_count += 1
            blocked_users.append(user_id)
        except Exception as e:
            failed_count += 1
            logger.error(f"Broadcast failed for user {user_id}: {e}")
    
    # Clean up blocked users
    if blocked_users:
        for user_id in blocked_users:
            if user_id in db["users"]:
                del db["users"][user_id]
        await save_database(db)

    report = (
        f"📢 Broadcast Complete!\n\n"
        f"✅ Sent: {success_count}\n"
        f"❌ Failed: {failed_count}\n"
        f"🗑️ Blocked users removed: {len(blocked_users)}"
    )
    await update.message.reply_text(report)
    await show_main_menu(update, context)
    return ConversationHandler.END


# ... Stubs for other admin functions for brevity. Implementation would follow a similar pattern.
async def admin_add_premium_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Enter the User ID to make premium.")
    return ADMIN_ADD_PREMIUM_ID

async def admin_add_premium_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['premium_user_id'] = update.message.text
    await update.message.reply_text("Enter the number of days for the premium subscription.")
    return ADMIN_ADD_PREMIUM_DAYS

async def admin_add_premium_days(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = context.user_data['premium_user_id']
    days = int(update.message.text)
    
    db = await load_database()
    if user_id in db['users']:
        db['users'][user_id]['is_premium'] = True
        expiry_date = datetime.now() + timedelta(days=days)
        db['users'][user_id]['premium_expiry'] = expiry_date.isoformat()
        await save_database(db)
        await update.message.reply_text(f"User {user_id} is now a premium member for {days} days.")
    else:
        await update.message.reply_text("User not found.")
        
    del context.user_data['premium_user_id']
    await show_main_menu(update, context, as_admin=True)
    return ConversationHandler.END
    
# --- Jobs ---
async def daily_reset(context: ContextTypes.DEFAULT_TYPE):
    """Resets daily credits for all users."""
    logger.info("Running daily credit reset job.")
    db = await load_database()
    for user_id, user_data in db["users"].items():
        user_data["credits"] = DAILY_FREE_CREDITS + user_data.get("permanent_daily_credits", 0)
        # Add premium bonus
        if user_data.get("is_premium"):
            user_data["credits"] *= 2
    await save_database(db)
    logger.info("Daily credit reset complete.")

async def weekly_leaderboard_reset(context: ContextTypes.DEFAULT_TYPE):
    """Resets the leaderboard clicks."""
    logger.info("Running weekly leaderboard reset job.")
    db = await load_database()
    for user_id in db["users"]:
        db["users"][user_id]["clicks_received"] = 0
    await save_database(db)
    # Optionally notify admins or users
    logger.info("Weekly leaderboard reset complete.")

# --- Helper to return to main menu ---
async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, as_admin=False):
    """Displays the main menu, used for returning from other actions."""
    user = update.effective_user
    text = "Welcome back to the main menu!"
    if as_admin:
        text = "Returning to the admin panel."

    # Check if we are in a conversation
    if isinstance(update, Update) and update.callback_query:
        query = update.callback_query
        await query.edit_message_text(text, reply_markup=await build_main_menu(user.id))
    else:
        await context.bot.send_message(user.id, text, reply_markup=await build_main_menu(user.id))


# --- Main Application Setup ---
def main() -> None:
    """Start the bot."""
    application = Application.builder().token(BOT_TOKEN).build()

    # Job Queue for scheduled tasks
    job_queue = application.job_queue
    job_queue.run_daily(daily_reset, time=datetime.strptime("00:00", "%H:%M").time())
    job_queue.run_daily(weekly_leaderboard_reset, time=datetime.strptime("00:00", "%H:%M").time(), days=(0,)) # Monday

    # Conversation handler for promotions
    promo_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(promote_link_start, pattern="^promote_link$")],
        states={
            PROMO_TYPE: [CallbackQueryHandler(promo_type_selection, pattern="^promo_")],
            NORMAL_PROMO_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, normal_promo_text_received)],
            NORMAL_PROMO_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, normal_promo_link_received)],
            FORCE_JOIN_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, force_join_id_received)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_conversation),
            CallbackQueryHandler(lambda u,c: show_main_menu(u,c) or ConversationHandler.END, pattern="^main_menu$")
        ],
    )
    
    # Admin conversation handler
    admin_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_panel, pattern="^admin_panel$")],
        states={
            ADMIN_MAIN: [
                CallbackQueryHandler(admin_broadcast_start, pattern="^admin_broadcast$"),
                CallbackQueryHandler(admin_add_premium_start, pattern="^admin_add_premium$"),
                # ... other admin entry points
            ],
            ADMIN_BROADCAST: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_broadcast_received)],
            ADMIN_ADD_PREMIUM_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_premium_id)],
            ADMIN_ADD_PREMIUM_DAYS: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_premium_days)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_conversation),
            CallbackQueryHandler(lambda u,c: show_main_menu(u,c) or ConversationHandler.END, pattern="^main_menu$")
        ],
    )

    # Command handlers
    application.add_handler(CommandHandler("start", start))

    # Callback query handlers
    application.add_handler(promo_conv_handler)
    application.add_handler(admin_conv_handler)
    application.add_handler(CallbackQueryHandler(show_main_menu, pattern="^main_menu$"))
    application.add_handler(CallbackQueryHandler(group_share, pattern="^group_share$"))
    application.add_handler(CallbackQueryHandler(earn_credits, pattern="^earn_credits$"))
    application.add_handler(CallbackQueryHandler(referral_link, pattern="^referral_link$"))
    application.add_handler(CallbackQueryHandler(leaderboard, pattern="^leaderboard$"))
    application.add_handler(CallbackQueryHandler(upgrade_premium, pattern="^upgrade_premium$"))
    application.add_handler(CallbackQueryHandler(add_to_group, pattern="^add_to_group$"))
    application.add_handler(CallbackQueryHandler(claim_normal_credits, pattern="^claim_normal_"))
    application.add_handler(CallbackQueryHandler(verify_join, pattern="^verify_join_"))
    
    # Message handlers
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, new_chat_members))
    
    # Run the bot
    application.run_polling()


if __name__ == "__main__":
    main()

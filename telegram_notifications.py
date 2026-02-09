"""
Telegram Bot Notification System for UGC Reports
Apple Guideline 1.2 Compliance - 24-hour Alert System
"""

import os
import httpx
from datetime import datetime
from typing import Optional

# --- Configuration (from environment variables) ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# Telegram API base URL
TELEGRAM_API_BASE = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"


async def send_telegram_message(message: str) -> dict:
    """
    Send a message to the configured Telegram chat.
    
    Args:
        message: The message text to send (supports Telegram markdown)
    
    Returns:
        dict with success status and any error details
    """
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Telegram credentials not configured. Skipping notification.")
        return {
            "success": False,
            "error": "Telegram credentials not configured"
        }
    
    url = f"{TELEGRAM_API_BASE}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json=payload)
            
            if response.status_code == 200:
                print("✅ Telegram notification sent successfully")
                return {"success": True}
            else:
                error_msg = response.text
                print(f"❌ Telegram API error: {response.status_code} - {error_msg}")
                return {"success": False, "error": error_msg}
                
    except Exception as e:
        print(f"❌ Telegram delivery failed: {e}")
        return {"success": False, "error": str(e)}


async def send_message_with_buttons(
    message: str,
    buttons: list[list[dict]]
) -> dict:
    """
    Send a message with inline keyboard buttons to the configured Telegram chat.
    
    Args:
        message: The message text (supports Telegram markdown)
        buttons: 2D array of button objects. Each button dict can have:
                 - {"text": "...", "url": "..."} for URL buttons
                 - {"text": "...", "callback_data": "..."} for callback buttons
    
    Returns:
        dict with success status and message_id if successful
    """
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Telegram credentials not configured. Skipping notification.")
        return {
            "success": False,
            "error": "Telegram credentials not configured"
        }
    
    url = f"{TELEGRAM_API_BASE}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown",
        "reply_markup": {
            "inline_keyboard": buttons
        }
    }
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json=payload)
            
            if response.status_code == 200:
                result = response.json()
                message_id = result.get("result", {}).get("message_id")
                print(f"✅ Telegram notification with buttons sent (msg_id: {message_id})")
                return {"success": True, "message_id": message_id}
            else:
                error_msg = response.text
                print(f"❌ Telegram API error: {response.status_code} - {error_msg}")
                return {"success": False, "error": error_msg}
                
    except Exception as e:
        print(f"❌ Telegram delivery failed: {e}")
        return {"success": False, "error": str(e)}


async def send_ugc_report_notification(
    reporter_id: str,
    reported_user_id: str,
    content_type: str,
    reason: str,
    report_id: Optional[str] = None,
    task_id: Optional[str] = None,  # ✅ Task-level reporting
    task_title: Optional[str] = None  # ✅ Task-level reporting
) -> dict:
    """
    Send a formatted UGC report notification with action buttons.
    
    Apple Guideline 1.2 requires 24-hour response to UGC reports.
    This notification ensures immediate developer awareness with one-tap actions.
    
    Buttons:
      - "👤 View Profile": Opens deep link to user's profile in the app
      - "🚫 Ban User": Triggers callback to instantly ban the user
    
    Args:
        reporter_id: User ID of the person making the report
        reported_user_id: User ID of the reported user
        content_type: Type of content being reported (bio, name, post, task)
        reason: Reason for the report (harassment, spam, inappropriate)
        report_id: Optional report document ID for reference
        task_id: Optional task ID if reporting task content
        task_title: Optional task title for context
    
    Returns:
        dict with success status and message_id if successful
    """
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    
    # Build formatted message
    message = f"""🚨 *YENİ UGC RAPORU* 🚨

📋 *Rapor Detayları:*
• Rapor Eden: `{reporter_id}`
• Rapor Edilen: `{reported_user_id}`
• İçerik Türü: `{content_type}`
• Sebep: `{reason}`
• Zaman: `{timestamp}`

⚠️ *Lütfen 24 saat içinde inceleyip aksiyon alın.*

_Apple Guideline 1.2 Uyumluluğu_"""

    if task_id and task_title:
        message += f"\n\n📝 *Task Detayları:*\n• Task ID: `{task_id}`\n• Başlık: _{task_title}_"
    
    if report_id:
        message += f"\n📎 Rapor ID: `{report_id}`"
    
    # ✅ Inline Keyboard Buttons for instant moderation
    # NOTE: Telegram requires HTTPS URLs - iOS intercepts via Universal Links
    buttons = [[
        {
            "text": "👤 View Profile",
            "url": f"https://greenhabit-backend.onrender.com/user/{reported_user_id}"
        },
        {
            "text": "🚫 Ban User",
            "callback_data": f"ban_{reported_user_id}"
        }
    ]]
    
    return await send_message_with_buttons(message, buttons)


async def edit_message_text(
    chat_id: str,
    message_id: int,
    new_text: str
) -> dict:
    """
    Edit an existing Telegram message text.
    Used to update UGC report messages after moderation action.
    
    Args:
        chat_id: The chat ID where the message exists
        message_id: The message ID to edit
        new_text: The new text content
    
    Returns:
        dict with success status
    """
    if not TELEGRAM_TOKEN:
        return {"success": False, "error": "Telegram token not configured"}
    
    url = f"{TELEGRAM_API_BASE}/editMessageText"
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": new_text,
        "parse_mode": "Markdown"
    }
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json=payload)
            
            if response.status_code == 200:
                print(f"✅ Message {message_id} edited successfully")
                return {"success": True}
            else:
                error_msg = response.text
                print(f"❌ Failed to edit message: {response.status_code} - {error_msg}")
                return {"success": False, "error": error_msg}
                
    except Exception as e:
        print(f"❌ Edit message failed: {e}")
        return {"success": False, "error": str(e)}


async def answer_callback_query(
    callback_query_id: str,
    text: Optional[str] = None,
    show_alert: bool = False
) -> dict:
    """
    Acknowledge a Telegram callback query (button press).
    Must be called within 30 seconds of receiving the callback.
    
    Args:
        callback_query_id: The callback query ID from Telegram
        text: Optional notification text to show the user
        show_alert: If True, shows an alert instead of a toast
    
    Returns:
        dict with success status
    """
    if not TELEGRAM_TOKEN:
        return {"success": False, "error": "Telegram token not configured"}
    
    url = f"{TELEGRAM_API_BASE}/answerCallbackQuery"
    payload = {
        "callback_query_id": callback_query_id
    }
    
    if text:
        payload["text"] = text
        payload["show_alert"] = show_alert
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json=payload)
            
            if response.status_code == 200:
                return {"success": True}
            else:
                return {"success": False, "error": response.text}
                
    except Exception as e:
        return {"success": False, "error": str(e)}


async def send_test_notification() -> dict:
    """
    Send a test notification to verify Telegram integration.
    """
    message = """🧪 *TEST BİLDİRİMİ*

✅ Telegram entegrasyonu başarıyla çalışıyor!

_GreenHabit UGC Raporlama Sistemi_"""
    
    return await send_telegram_message(message)

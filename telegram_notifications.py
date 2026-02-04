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


async def send_ugc_report_notification(
    reporter_id: str,
    reported_user_id: str,
    content_type: str,
    reason: str,
    report_id: Optional[str] = None
) -> dict:
    """
    Send a formatted UGC report notification to the developer.
    
    Apple Guideline 1.2 requires 24-hour response to UGC reports.
    This notification ensures immediate developer awareness.
    
    Args:
        reporter_id: User ID of the person making the report
        reported_user_id: User ID of the reported user
        content_type: Type of content being reported (bio, name, post, etc.)
        reason: Reason for the report (harassment, spam, inappropriate)
        report_id: Optional report document ID for reference
    
    Returns:
        dict with success status
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

    if report_id:
        message += f"\n📎 Rapor ID: `{report_id}`"
    
    return await send_telegram_message(message)


async def send_test_notification() -> dict:
    """
    Send a test notification to verify Telegram integration.
    """
    message = """🧪 *TEST BİLDİRİMİ*

✅ Telegram entegrasyonu başarıyla çalışıyor!

_GreenHabit UGC Raporlama Sistemi_"""
    
    return await send_telegram_message(message)

"""Telegram notification handler."""

import aiohttp
import structlog

from .base import BaseNotifier, AlertPayload

log = structlog.get_logger()


class TelegramNotifier(BaseNotifier):
    """Send alerts via Telegram Bot API."""
    
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.api_url = f"https://api.telegram.org/bot{bot_token}"
    
    async def send(self, payload: AlertPayload) -> bool:
        """Send alert to Telegram."""
        message = payload.format_telegram_message()
        
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.api_url}/sendMessage"
                data = {
                    "chat_id": self.chat_id,
                    "text": message,
                    "parse_mode": "Markdown",
                    "disable_web_page_preview": True,
                }
                
                async with session.post(url, json=data, timeout=10) as resp:
                    if resp.status == 200:
                        log.info("Telegram notification sent")
                        return True
                    else:
                        error = await resp.text()
                        log.error(
                            "Telegram send failed",
                            status=resp.status,
                            error=error[:200]
                        )
                        return False
                        
        except aiohttp.ClientError as e:
            log.error("Telegram connection error", error=str(e))
            return False
        except Exception as e:
            log.error("Telegram notification error", error=str(e))
            return False
    
    async def health_check(self) -> bool:
        """Check if Telegram bot is configured correctly."""
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.api_url}/getMe"
                async with session.get(url, timeout=5) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("ok"):
                            log.info(
                                "Telegram bot connected",
                                username=data.get("result", {}).get("username")
                            )
                            return True
                    return False
        except Exception as e:
            log.error("Telegram health check failed", error=str(e))
            return False

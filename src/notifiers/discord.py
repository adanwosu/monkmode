"""Discord notification handler using webhooks."""

import aiohttp
import structlog

from .base import BaseNotifier, AlertPayload

log = structlog.get_logger()


class DiscordNotifier(BaseNotifier):
    """Send alerts via Discord webhook."""
    
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url
    
    async def send(self, payload: AlertPayload) -> bool:
        """Send alert to Discord."""
        embed = payload.format_discord_embed()
        
        try:
            async with aiohttp.ClientSession() as session:
                data = {
                    "username": "Monk Mode",
                    "avatar_url": "https://em-content.zobj.net/source/apple/391/person-in-lotus-position_1f9d8.png",
                    "embeds": [embed],
                }
                
                async with session.post(
                    self.webhook_url,
                    json=data,
                    timeout=10
                ) as resp:
                    # Discord returns 204 No Content on success
                    if resp.status in [200, 204]:
                        log.info("Discord notification sent")
                        return True
                    else:
                        error = await resp.text()
                        log.error(
                            "Discord send failed",
                            status=resp.status,
                            error=error[:200]
                        )
                        return False
                        
        except aiohttp.ClientError as e:
            log.error("Discord connection error", error=str(e))
            return False
        except Exception as e:
            log.error("Discord notification error", error=str(e))
            return False
    
    async def health_check(self) -> bool:
        """Check if Discord webhook is valid."""
        try:
            # Extract webhook ID/token and check via GET
            # Discord webhooks support GET to retrieve info
            async with aiohttp.ClientSession() as session:
                async with session.get(self.webhook_url, timeout=5) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        log.info(
                            "Discord webhook connected",
                            name=data.get("name"),
                            channel=data.get("channel_id")
                        )
                        return True
                    return False
        except Exception as e:
            log.error("Discord health check failed", error=str(e))
            return False

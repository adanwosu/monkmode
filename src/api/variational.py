"""Variational API client - Platform-specific prices for alerts."""

from datetime import datetime
from typing import Optional

import aiohttp
import structlog

from .base import PriceData

log = structlog.get_logger()


class VariationalAPI:
    """
    Fetch prices from Variational Omni for alert context.
    
    API Docs: https://docs.variational.io/technical-documentation/api
    """
    
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
    
    async def get_prices(self) -> dict[str, PriceData]:
        """
        Fetch BTC and ETH prices from Variational.
        
        Returns:
            Dict mapping symbol ("BTC", "ETH") to PriceData
        """
        prices = {}
        
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.base_url}/metadata/stats"
                
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status != 200:
                        log.warning("Variational API error", status=resp.status)
                        return prices
                    
                    data = await resp.json()
                    
                    for listing in data.get("listings", []):
                        ticker = listing.get("ticker", "").upper()
                        
                        if ticker not in ["BTC", "ETH"]:
                            continue
                        
                        try:
                            quotes = listing.get("quotes", {})
                            size_1k = quotes.get("size_1k", {})
                            
                            # Parse timestamp
                            updated_at = quotes.get("updated_at")
                            if updated_at:
                                # Handle ISO format with Z suffix
                                timestamp = datetime.fromisoformat(
                                    updated_at.replace("Z", "+00:00")
                                )
                            else:
                                timestamp = datetime.utcnow()
                            
                            # Parse funding rate (given as decimal, convert to %)
                            funding_rate = listing.get("funding_rate")
                            if funding_rate:
                                funding_rate = float(funding_rate) * 100
                            
                            prices[ticker] = PriceData(
                                symbol=ticker,
                                price=float(listing["mark_price"]),
                                change_24h_pct=0.0,  # Not provided by Variational
                                timestamp=timestamp,
                                platform="variational",
                                bid=float(size_1k["bid"]) if size_1k.get("bid") else None,
                                ask=float(size_1k["ask"]) if size_1k.get("ask") else None,
                                volume_24h=float(listing.get("volume_24h", 0)),
                                funding_rate=funding_rate,
                            )
                            
                        except (KeyError, ValueError, TypeError) as e:
                            log.warning(
                                "Failed to parse Variational listing",
                                ticker=ticker,
                                error=str(e)
                            )
                            continue
                            
        except aiohttp.ClientError as e:
            log.error("Variational API connection error", error=str(e))
        except Exception as e:
            log.error("Failed to fetch Variational prices", error=str(e))
        
        return prices
    
    async def health_check(self) -> bool:
        """Check if Variational API is reachable."""
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.base_url}/metadata/stats"
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    return resp.status == 200
        except Exception:
            return False

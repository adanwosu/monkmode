"""Extended Exchange API client - Platform-specific prices for alerts."""

from datetime import datetime
from typing import Optional

import aiohttp
import structlog

from .base import PriceData

log = structlog.get_logger()


class ExtendedAPI:
    """
    Fetch prices from Extended Exchange for alert context.
    
    API Docs: https://api.docs.extended.exchange/
    """
    
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
    
    async def get_prices(self) -> dict[str, PriceData]:
        """
        Fetch BTC and ETH prices from Extended (Starknet instance).
        
        Returns:
            Dict mapping symbol ("BTC", "ETH") to PriceData
        """
        prices = {}
        
        try:
            async with aiohttp.ClientSession() as session:
                # Starknet API endpoint - get both markets in one call
                url = f"{self.base_url}/info/markets?market=BTC-USD&market=ETH-USD"
                
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status != 200:
                        log.warning("Extended API error", status=resp.status)
                        return prices
                    
                    response = await resp.json()
                    
                    # Starknet API format: {"status": "OK", "data": [...]}
                    if response.get("status") != "OK":
                        log.warning("Extended API returned error", response=response)
                        return prices
                    
                    markets = response.get("data", [])
                    
                    for market in markets:
                        try:
                            # Market name format: "BTC-USD", "ETH-USD"
                            name = market.get("name", "")
                            
                            if name == "BTC-USD":
                                ticker = "BTC"
                            elif name == "ETH-USD":
                                ticker = "ETH"
                            else:
                                continue
                            
                            stats = market.get("marketStats", {})
                            
                            price = stats.get("lastPrice")
                            if not price:
                                continue
                            
                            change_24h = stats.get("dailyPriceChangePercentage", 0)
                            bid = stats.get("bidPrice")
                            ask = stats.get("askPrice")
                            volume = stats.get("dailyVolume", 0)
                            funding = stats.get("fundingRate")
                            
                            if funding:
                                funding = float(funding) * 100  # Convert to %
                            
                            prices[ticker] = PriceData(
                                symbol=ticker,
                                price=float(price),
                                change_24h_pct=float(change_24h),
                                timestamp=datetime.utcnow(),
                                platform="extended",
                                bid=float(bid) if bid else None,
                                ask=float(ask) if ask else None,
                                volume_24h=float(volume),
                                funding_rate=funding,
                            )
                            
                        except (KeyError, ValueError, TypeError) as e:
                            log.warning(
                                "Failed to parse Extended market",
                                name=market.get("name"),
                                error=str(e)
                            )
                            continue
                            
        except aiohttp.ClientError as e:
            log.error("Extended API connection error", error=str(e))
        except Exception as e:
            log.error("Failed to fetch Extended prices", error=str(e))
        
        return prices
    
    async def health_check(self) -> bool:
        """Check if Extended API is reachable."""
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.base_url}/info/markets?market=BTC-USD"
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("status") == "OK"
                    return False
        except Exception:
            return False

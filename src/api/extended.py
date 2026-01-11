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
        Fetch BTC and ETH prices from Extended.
        
        Returns:
            Dict mapping symbol ("BTC", "ETH") to PriceData
        """
        prices = {}
        
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.base_url}/markets"
                
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status != 200:
                        log.warning("Extended API error", status=resp.status)
                        return prices
                    
                    data = await resp.json()
                    
                    # Handle both list and dict response formats
                    markets = data if isinstance(data, list) else data.get("markets", [])
                    
                    for market in markets:
                        try:
                            symbol = market.get("symbol", "")
                            
                            # Match BTC-PERP, BTCUSDT, etc.
                            if "BTC" in symbol.upper():
                                ticker = "BTC"
                            elif "ETH" in symbol.upper():
                                ticker = "ETH"
                            else:
                                continue
                            
                            # Skip if we already have this ticker (take first match)
                            if ticker in prices:
                                continue
                            
                            # Try various field names for price
                            price = (
                                market.get("markPrice") or 
                                market.get("mark_price") or
                                market.get("lastPrice") or
                                market.get("last_price") or
                                market.get("price")
                            )
                            
                            if not price:
                                continue
                            
                            # Try various field names for 24h change
                            change_24h = (
                                market.get("priceChangePercent24h") or
                                market.get("price_change_percent_24h") or
                                market.get("change24h") or
                                0.0
                            )
                            
                            # Try various field names for bid/ask
                            bid = market.get("bestBid") or market.get("best_bid") or market.get("bid")
                            ask = market.get("bestAsk") or market.get("best_ask") or market.get("ask")
                            
                            # Try various field names for volume
                            volume = (
                                market.get("volume24h") or
                                market.get("volume_24h") or
                                market.get("quoteVolume24h") or
                                0.0
                            )
                            
                            # Try various field names for funding rate
                            funding = market.get("fundingRate") or market.get("funding_rate")
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
                                symbol=market.get("symbol"),
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
                url = f"{self.base_url}/markets"
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    return resp.status == 200
        except Exception:
            return False

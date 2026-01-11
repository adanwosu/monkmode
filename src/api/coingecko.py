"""CoinGecko API client - Alternative data source when Binance is unavailable."""

import asyncio
from datetime import datetime, timedelta
from typing import Callable, Optional, Awaitable

import aiohttp
import structlog

from .base import PriceData, SpreadSignal

log = structlog.get_logger()


class CoinGeckoAPI:
    """
    Alternative data source using CoinGecko REST API.
    
    Free tier: 10-30 calls/minute (we poll every 30 seconds = 2/min)
    """
    
    BASE_URL = "https://api.coingecko.com/api/v3"
    
    COIN_IDS = {
        "BTC": "bitcoin",
        "ETH": "ethereum",
    }
    
    def __init__(self, polling_interval: int = 30, debug_mode: bool = False, spread_threshold: float = 2.0):
        self.polling_interval = polling_interval
        self.debug_mode = debug_mode
        self.spread_threshold = spread_threshold
        self._prices: dict[str, PriceData] = {}
        self._running = False
        
        # Rate limit tracking
        self._rate_limited = False
        self._rate_limit_until: Optional[datetime] = None
        self._last_successful_fetch: Optional[datetime] = None
        self._fetch_count = 0
        self._rate_limit_count = 0
        self._last_heartbeat: Optional[datetime] = None
        self._heartbeat_interval = 60  # Show heartbeat every 60 seconds
    
    async def start_polling(
        self, 
        on_update: Callable[[SpreadSignal], Awaitable[None]],
    ) -> None:
        """
        Start polling for price updates.
        
        Args:
            on_update: Async callback receiving SpreadSignal on each update
        """
        self._running = True
        
        log.info(
            "Starting CoinGecko polling",
            interval=f"{self.polling_interval}s"
        )
        
        while self._running:
            try:
                # Check if we're still in rate limit cooldown
                if self._rate_limited and self._rate_limit_until:
                    remaining = (self._rate_limit_until - datetime.utcnow()).total_seconds()
                    if remaining > 0:
                        log.warning(
                            "⏳ Rate limited - waiting",
                            seconds_remaining=f"{remaining:.0f}s",
                            resume_at=self._rate_limit_until.strftime("%H:%M:%S UTC")
                        )
                        await asyncio.sleep(min(remaining, self.polling_interval))
                        continue
                    else:
                        self._rate_limited = False
                        self._rate_limit_until = None
                        log.info("✅ Rate limit cleared, resuming...")
                
                signal = await self.get_current_prices()
                if signal:
                    await on_update(signal)
                    
            except Exception as e:
                log.error("CoinGecko polling error", error=str(e))
            
            await asyncio.sleep(self.polling_interval)
    
    async def get_current_prices(self) -> Optional[SpreadSignal]:
        """Fetch current prices from CoinGecko."""
        self._fetch_count += 1
        
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.BASE_URL}/simple/price"
                params = {
                    "ids": ",".join(self.COIN_IDS.values()),
                    "vs_currencies": "usd",
                    "include_24hr_change": "true",
                    "include_24hr_vol": "true",
                }
                
                async with session.get(url, params=params, timeout=10) as resp:
                    if resp.status == 429:
                        self._rate_limited = True
                        self._rate_limit_count += 1
                        self._rate_limit_until = datetime.utcnow() + timedelta(seconds=60)
                        
                        log.error(
                            "🚫 RATE LIMITED by CoinGecko!",
                            cooldown="60s",
                            total_rate_limits=self._rate_limit_count,
                            total_fetches=self._fetch_count,
                            tip="Consider increasing polling_interval_sec in config.yaml"
                        )
                        return None
                    
                    if resp.status != 200:
                        log.warning("CoinGecko API error", status=resp.status)
                        return None
                    
                    data = await resp.json()
                    now = datetime.utcnow()
                    
                    prices = {}
                    for symbol, coin_id in self.COIN_IDS.items():
                        coin_data = data.get(coin_id, {})
                        
                        if "usd" not in coin_data:
                            continue
                        
                        prices[symbol] = PriceData(
                            symbol=symbol,
                            price=float(coin_data["usd"]),
                            change_24h_pct=float(coin_data.get("usd_24h_change", 0)),
                            timestamp=now,
                            platform="coingecko",
                            volume_24h=float(coin_data.get("usd_24h_vol", 0)) if coin_data.get("usd_24h_vol") else None,
                        )
                    
                    self._prices = prices
                    
                    # Calculate time since last update
                    time_since_last = ""
                    if self._last_successful_fetch:
                        delta = (now - self._last_successful_fetch).total_seconds()
                        time_since_last = f"{delta:.0f}s ago"
                    
                    self._last_successful_fetch = now
                    
                    if "BTC" in prices and "ETH" in prices:
                        spread = prices["ETH"].change_24h_pct - prices["BTC"].change_24h_pct
                        threshold = self.spread_threshold
                        
                        # SIGNAL ZONE - Always log loudly
                        if spread >= threshold:
                            log.warning(
                                "🟢🟢🟢 STRATEGY 1 SIGNAL! 🟢🟢🟢",
                                spread=f"{spread:+.2f}%",
                                threshold=f"±{threshold}%",
                                action="Long BTC / Short ETH",
                                btc=f"${prices['BTC'].price:,.2f} ({prices['BTC'].change_24h_pct:+.2f}%)",
                                eth=f"${prices['ETH'].price:,.2f} ({prices['ETH'].change_24h_pct:+.2f}%)",
                            )
                        elif spread <= -threshold:
                            log.warning(
                                "🔴🔴🔴 STRATEGY 2 SIGNAL! 🔴🔴🔴",
                                spread=f"{spread:+.2f}%",
                                threshold=f"±{threshold}%",
                                action="Short BTC / Long ETH",
                                btc=f"${prices['BTC'].price:,.2f} ({prices['BTC'].change_24h_pct:+.2f}%)",
                                eth=f"${prices['ETH'].price:,.2f} ({prices['ETH'].change_24h_pct:+.2f}%)",
                            )
                        elif self.debug_mode:
                            # Debug mode: show all updates
                            if abs(spread) >= (threshold * 0.75):
                                status = "🟡 Approaching threshold"
                            else:
                                status = "⚪ Normal range"
                            
                            log.info(
                                f"📊 Price Update #{self._fetch_count}",
                                time=now.strftime("%H:%M:%S UTC"),
                                btc=f"${prices['BTC'].price:,.2f} ({prices['BTC'].change_24h_pct:+.2f}%)",
                                eth=f"${prices['ETH'].price:,.2f} ({prices['ETH'].change_24h_pct:+.2f}%)",
                                spread=f"{spread:+.2f}%",
                                status=status,
                                next_refresh=f"{self.polling_interval}s",
                            )
                        else:
                            # Quiet mode: just show heartbeat periodically
                            show_heartbeat = (
                                self._last_heartbeat is None or
                                (now - self._last_heartbeat).total_seconds() >= self._heartbeat_interval
                            )
                            
                            if show_heartbeat:
                                self._last_heartbeat = now
                                log.info(
                                    f"💓 Heartbeat",
                                    spread=f"{spread:+.2f}%",
                                    signal_at=f"±{threshold}%",
                                    btc=f"${prices['BTC'].price:,.0f}",
                                    eth=f"${prices['ETH'].price:,.0f}",
                                    updates=self._fetch_count,
                                )
                        
                        return SpreadSignal(
                            btc=prices["BTC"],
                            eth=prices["ETH"],
                            spread_pct=spread
                        )
                    
        except aiohttp.ClientError as e:
            log.error("CoinGecko connection error", error=str(e))
        except Exception as e:
            log.error("Failed to fetch CoinGecko prices", error=str(e))
        
        return None
    
    def get_cached_signal(self) -> Optional[SpreadSignal]:
        """Get signal from cached prices (no network call)."""
        if "BTC" in self._prices and "ETH" in self._prices:
            btc = self._prices["BTC"]
            eth = self._prices["ETH"]
            spread = eth.change_24h_pct - btc.change_24h_pct
            return SpreadSignal(btc=btc, eth=eth, spread_pct=spread)
        return None
    
    def stop(self) -> None:
        """Stop the polling loop."""
        self._running = False
        log.info("CoinGecko polling stopped")
    
    async def health_check(self) -> bool:
        """Check if CoinGecko API is reachable."""
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.BASE_URL}/ping"
                async with session.get(url, timeout=5) as resp:
                    return resp.status == 200
        except Exception:
            return False

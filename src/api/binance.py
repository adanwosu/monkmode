"""Binance API client - Primary data source using WebSocket."""

import asyncio
import json
from datetime import datetime
from typing import Callable, Optional, Awaitable

import aiohttp
import websockets
import structlog

from .base import PriceData, SpreadSignal

log = structlog.get_logger()


class BinanceAPI:
    """
    Primary data source using Binance WebSocket for real-time prices.
    
    Uses the combined ticker stream for BTC and ETH to get synchronized
    price updates with minimal latency.
    """
    
    SYMBOLS = {
        "BTC": "BTCUSDT",
        "ETH": "ETHUSDT",
    }
    
    def __init__(self, ws_url: str, rest_url: str):
        self.ws_url = ws_url
        self.rest_url = rest_url
        self._prices: dict[str, PriceData] = {}
        self._running = False
        self._ws = None
        self._reconnect_delay = 5
        self._max_reconnect_delay = 60
    
    async def start_stream(
        self, 
        on_update: Callable[[SpreadSignal], Awaitable[None]],
    ) -> None:
        """
        Start WebSocket stream and call on_update with every price update.
        
        Args:
            on_update: Async callback receiving SpreadSignal on each tick
        """
        self._running = True
        reconnect_delay = self._reconnect_delay
        
        subscribe_msg = {
            "method": "SUBSCRIBE",
            "params": [f"{s.lower()}@ticker" for s in self.SYMBOLS.values()],
            "id": 1
        }
        
        while self._running:
            try:
                async with websockets.connect(
                    self.ws_url,
                    ping_interval=20,
                    ping_timeout=10,
                    close_timeout=5,
                ) as ws:
                    self._ws = ws
                    await ws.send(json.dumps(subscribe_msg))
                    log.info("Connected to Binance WebSocket", url=self.ws_url)
                    reconnect_delay = self._reconnect_delay  # Reset on successful connect
                    
                    async for message in ws:
                        if not self._running:
                            break
                        
                        try:
                            data = json.loads(message)
                            
                            # Skip subscription confirmation
                            if "result" in data or "id" in data:
                                continue
                            
                            signal = await self._handle_ticker(data)
                            if signal:
                                await on_update(signal)
                                
                        except json.JSONDecodeError as e:
                            log.warning("Invalid JSON from WebSocket", error=str(e))
                            
            except websockets.exceptions.ConnectionClosed as e:
                log.warning("WebSocket connection closed", code=e.code, reason=e.reason)
            except Exception as e:
                log.error("WebSocket error", error=str(e), error_type=type(e).__name__)
            
            if self._running:
                log.info("Reconnecting in {delay}s...", delay=reconnect_delay)
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, self._max_reconnect_delay)
    
    async def _handle_ticker(self, data: dict) -> Optional[SpreadSignal]:
        """Process ticker update and return SpreadSignal if both prices available."""
        symbol_map = {v: k for k, v in self.SYMBOLS.items()}
        binance_symbol = data.get("s")
        
        if binance_symbol not in symbol_map:
            return None
        
        symbol = symbol_map[binance_symbol]
        
        try:
            self._prices[symbol] = PriceData(
                symbol=symbol,
                price=float(data["c"]),           # Last price
                change_24h_pct=float(data["P"]),  # 24h change %
                timestamp=datetime.utcnow(),
                platform="binance",
                bid=float(data["b"]),             # Best bid
                ask=float(data["a"]),             # Best ask
                volume_24h=float(data["q"]),      # Quote volume
            )
        except (KeyError, ValueError) as e:
            log.warning("Failed to parse ticker", symbol=symbol, error=str(e))
            return None
        
        # Return signal only if we have both prices
        if "BTC" in self._prices and "ETH" in self._prices:
            btc = self._prices["BTC"]
            eth = self._prices["ETH"]
            
            # Calculate spread: how much ETH outperformed/underperformed BTC
            spread = eth.change_24h_pct - btc.change_24h_pct
            
            return SpreadSignal(btc=btc, eth=eth, spread_pct=spread)
        
        return None
    
    async def get_current_prices(self) -> Optional[SpreadSignal]:
        """Get current prices via REST API (fallback/initial fetch)."""
        async with aiohttp.ClientSession() as session:
            prices = {}
            
            for symbol, binance_symbol in self.SYMBOLS.items():
                try:
                    url = f"{self.rest_url}/ticker/24hr"
                    params = {"symbol": binance_symbol}
                    
                    async with session.get(url, params=params, timeout=10) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            prices[symbol] = PriceData(
                                symbol=symbol,
                                price=float(data["lastPrice"]),
                                change_24h_pct=float(data["priceChangePercent"]),
                                timestamp=datetime.utcnow(),
                                platform="binance",
                                bid=float(data["bidPrice"]),
                                ask=float(data["askPrice"]),
                                volume_24h=float(data["quoteVolume"]),
                            )
                        else:
                            log.warning("Binance REST error", status=resp.status, symbol=symbol)
                            
                except Exception as e:
                    log.error("Failed to fetch price via REST", symbol=symbol, error=str(e))
                    return None
            
            if "BTC" in prices and "ETH" in prices:
                spread = prices["ETH"].change_24h_pct - prices["BTC"].change_24h_pct
                return SpreadSignal(btc=prices["BTC"], eth=prices["ETH"], spread_pct=spread)
        
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
        """Stop the WebSocket stream."""
        self._running = False
        if self._ws:
            asyncio.create_task(self._ws.close())
            log.info("Binance WebSocket stopped")

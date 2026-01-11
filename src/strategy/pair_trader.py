"""
Monk Mode Pair Trading Strategy

Monitors BTC/ETH spread and sends alerts when:
- Strategy 1: ETH outperforms BTC by >= threshold (Long BTC / Short ETH)
- Strategy 2: ETH underperforms BTC by >= threshold (Short BTC / Long ETH)
- Close: Spread normalizes and estimated PnL is positive
"""

import asyncio
from datetime import datetime, timedelta
from typing import Optional

import structlog

from src.api.base import SpreadSignal, SignalType, Position
from src.api.binance import BinanceAPI
from src.api.coingecko import CoinGeckoAPI
from src.api.variational import VariationalAPI
from src.api.extended import ExtendedAPI
from src.config import Config
from src.notifiers.base import AlertPayload, AlertType, BaseNotifier
from src.notifiers.telegram import TelegramNotifier
from src.notifiers.discord import DiscordNotifier

log = structlog.get_logger()


class MonkPairTrader:
    """
    Hybrid pair trading strategy bot.
    
    Uses Binance WebSocket for fast signal detection, then enriches
    alerts with platform-specific prices from Variational and Extended.
    """
    
    def __init__(self, config: Config):
        self.config = config
        
        # Initialize APIs - try Binance first, fallback to CoinGecko
        self.binance = BinanceAPI(
            ws_url=config.binance_ws_url,
            rest_url=config.binance_rest_url,
        )
        self.coingecko = CoinGeckoAPI(
            polling_interval=config.strategy.polling_interval_sec,
            debug_mode=config.strategy.debug_mode,
            spread_threshold=config.strategy.spread_threshold,
        )
        self.variational = VariationalAPI(config.variational_url)
        self.extended = ExtendedAPI(config.extended_url)
        
        # Track which data source we're using
        self._use_coingecko = False
        self._debug_mode = config.strategy.debug_mode
        
        # Initialize notifiers
        self.notifiers: list[BaseNotifier] = []
        
        if config.notifications.telegram_enabled and config.telegram_bot_token:
            self.notifiers.append(
                TelegramNotifier(config.telegram_bot_token, config.telegram_chat_id)
            )
            log.info("Telegram notifier enabled")
        
        if config.notifications.discord_enabled and config.discord_webhook_url:
            self.notifiers.append(
                DiscordNotifier(
                    webhook_url=config.discord_webhook_url,
                    role_id=config.notifications.discord_role_id,
                )
            )
            role_info = f" (tagging role {config.notifications.discord_role_id})" if config.notifications.discord_role_id else ""
            log.info(f"Discord notifier enabled{role_info}")
        
        # State tracking
        self._last_signal_time: dict[str, datetime] = {}
        self._current_position: Optional[Position] = None
        self._running = False
        self._last_spread: Optional[float] = None
    
    async def _check_health(self) -> None:
        """Check health of all connected services."""
        log.info("Checking service health...")
        
        # Check notifiers
        for notifier in self.notifiers:
            healthy = await notifier.health_check()
            notifier_name = type(notifier).__name__
            if healthy:
                log.info(f"{notifier_name} is healthy")
            else:
                log.warning(f"{notifier_name} health check failed")
        
        # Check platform APIs
        if "variational" in self.config.notifications.include_platforms:
            healthy = await self.variational.health_check()
            log.info("Variational API", healthy=healthy)
        
        if "extended" in self.config.notifications.include_platforms:
            healthy = await self.extended.health_check()
            log.info("Extended API", healthy=healthy)
    
    async def _on_price_update(self, signal: SpreadSignal) -> None:
        """Handle incoming price update from Binance."""
        self._last_spread = signal.spread_pct
        
        # Check for close signal first
        if self._current_position:
            await self._check_close_signal(signal)
            return
        
        # Check for new signal
        await self._check_entry_signal(signal)
    
    async def _check_entry_signal(self, signal: SpreadSignal) -> None:
        """Check if we should send an entry signal."""
        threshold = self.config.strategy.spread_threshold
        max_spread = self.config.strategy.spread_max
        
        # Check if spread is within valid range
        if abs(signal.spread_pct) < threshold:
            return
        
        if abs(signal.spread_pct) > max_spread:
            log.warning(
                "Spread exceeds max threshold, possible anomaly",
                spread=signal.spread_pct,
                max=max_spread
            )
            return
        
        # Determine signal type
        if signal.spread_pct >= threshold:
            signal_type = SignalType.STRATEGY1
        elif signal.spread_pct <= -threshold:
            signal_type = SignalType.STRATEGY2
        else:
            return
        
        signal.signal_type = signal_type
        
        # Check cooldown
        cooldown = timedelta(seconds=self.config.strategy.cooldown_sec)
        last_time = self._last_signal_time.get(signal_type.value)
        
        if last_time and (datetime.utcnow() - last_time) < cooldown:
            return
        
        log.info(
            "Entry signal detected!",
            signal_type=signal_type.value,
            spread=f"{signal.spread_pct:+.2f}%",
            btc_change=f"{signal.btc.change_24h_pct:+.2f}%",
            eth_change=f"{signal.eth.change_24h_pct:+.2f}%",
        )
        
        # Create position for tracking
        self._current_position = Position(
            signal_type=signal_type,
            entry_spread=signal.spread_pct,
            entry_btc_price=signal.btc.price,
            entry_eth_price=signal.eth.price,
            entry_time=datetime.utcnow(),
            position_size_usd=self.config.strategy.position_size_usd,
        )
        
        # Send alert
        await self._send_alert(signal, AlertType.SIGNAL)
        
        # Update cooldown
        self._last_signal_time[signal_type.value] = datetime.utcnow()
    
    async def _check_close_signal(self, signal: SpreadSignal) -> None:
        """Check if we should send a close signal."""
        position = self._current_position
        if not position:
            return
        
        close_threshold = self.config.strategy.spread_close_threshold
        take_profit = self.config.strategy.take_profit_usd
        
        # Check if spread has normalized
        spread_normalized = abs(signal.spread_pct) <= close_threshold
        
        # Calculate estimated PnL
        estimated_pnl = position.estimate_pnl(signal.btc.price, signal.eth.price)
        
        # Close if spread normalized AND profitable
        if spread_normalized and estimated_pnl >= take_profit:
            log.info(
                "Close signal detected!",
                current_spread=f"{signal.spread_pct:+.2f}%",
                entry_spread=f"{position.entry_spread:+.2f}%",
                estimated_pnl=f"${estimated_pnl:+.2f}",
                duration=position.duration_str,
            )
            
            signal.signal_type = SignalType.CLOSE
            
            await self._send_alert(
                signal,
                AlertType.CLOSE,
                position=position,
                estimated_pnl=estimated_pnl
            )
            
            # Clear position
            self._current_position = None
    
    async def _send_alert(
        self,
        signal: SpreadSignal,
        alert_type: AlertType,
        position: Optional[Position] = None,
        estimated_pnl: Optional[float] = None,
    ) -> None:
        """Fetch platform prices and send alert to all notifiers."""
        # Fetch platform-specific prices in parallel
        platform_prices = {}
        
        fetch_tasks = []
        platforms = self.config.notifications.include_platforms
        
        if "variational" in platforms:
            fetch_tasks.append(("variational", self.variational.get_prices()))
        if "extended" in platforms:
            fetch_tasks.append(("extended", self.extended.get_prices()))
        
        if fetch_tasks:
            results = await asyncio.gather(
                *[task for _, task in fetch_tasks],
                return_exceptions=True
            )
            
            for (platform, _), result in zip(fetch_tasks, results):
                if isinstance(result, Exception):
                    log.warning(f"Failed to fetch {platform} prices", error=str(result))
                else:
                    platform_prices[platform] = result
        
        # Create alert payload
        payload = AlertPayload(
            signal=signal,
            platform_prices=platform_prices,
            alert_type=alert_type,
            position=position,
            estimated_pnl=estimated_pnl,
        )
        
        # Send to all notifiers in parallel
        if self.notifiers:
            tasks = [notifier.send(payload) for notifier in self.notifiers]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for notifier, result in zip(self.notifiers, results):
                if isinstance(result, Exception):
                    log.error(
                        "Notifier failed",
                        notifier=type(notifier).__name__,
                        error=str(result)
                    )
    
    async def run(self) -> None:
        """Start the pair trader bot."""
        self._running = True
        
        mode = "🔍 DEBUG MODE" if self._debug_mode else "🔇 QUIET MODE (alerts only)"
        log.info(
            "🧘 Starting Monk Mode Pair Trader",
            mode=mode,
            spread_threshold=f"±{self.config.strategy.spread_threshold}%",
            close_threshold=f"{self.config.strategy.spread_close_threshold}%",
            polling=f"{self.config.strategy.polling_interval_sec}s",
            notifiers=[type(n).__name__ for n in self.notifiers] or ["None (logs only)"],
        )
        
        # Health check
        await self._check_health()
        
        # Try Binance first, fallback to CoinGecko
        initial_signal = await self.binance.get_current_prices()
        
        if initial_signal:
            log.info(
                "Initial prices fetched from Binance",
                btc=f"${initial_signal.btc.price:,.2f}",
                eth=f"${initial_signal.eth.price:,.2f}",
                spread=f"{initial_signal.spread_pct:+.2f}%",
            )
            log.info("Starting Binance WebSocket stream...")
            await self.binance.start_stream(on_update=self._on_price_update)
        else:
            # Binance unavailable, use CoinGecko
            log.warning("Binance unavailable, falling back to CoinGecko")
            self._use_coingecko = True
            
            initial_signal = await self.coingecko.get_current_prices()
            if initial_signal:
                log.info(
                    "Initial prices fetched from CoinGecko",
                    btc=f"${initial_signal.btc.price:,.2f}",
                    eth=f"${initial_signal.eth.price:,.2f}",
                    spread=f"{initial_signal.spread_pct:+.2f}%",
                )
            
            log.info("Starting CoinGecko polling...")
            await self.coingecko.start_polling(on_update=self._on_price_update)
    
    def stop(self) -> None:
        """Stop the bot gracefully."""
        self._running = False
        if self._use_coingecko:
            self.coingecko.stop()
        else:
            self.binance.stop()
        log.info("🧘 Monk Mode Pair Trader stopped")
    
    @property
    def status(self) -> dict:
        """Get current bot status."""
        return {
            "running": self._running,
            "last_spread": self._last_spread,
            "has_position": self._current_position is not None,
            "position": {
                "type": self._current_position.signal_type.value,
                "entry_spread": self._current_position.entry_spread,
                "duration": self._current_position.duration_str,
            } if self._current_position else None,
            "notifiers": [type(n).__name__ for n in self.notifiers],
        }

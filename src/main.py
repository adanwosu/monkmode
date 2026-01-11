"""
Monk Mode - BTC/ETH Pair Trading Bot

Entry point for the bot. Handles configuration loading,
signal handling, and graceful shutdown.
"""

import asyncio
import signal
import sys

import structlog

from src.config import Config
from src.strategy.pair_trader import MonkPairTrader

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.dev.ConsoleRenderer(colors=True),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(20),  # INFO level
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
)

log = structlog.get_logger()


def create_shutdown_handler(trader: MonkPairTrader, loop: asyncio.AbstractEventLoop):
    """Create a shutdown handler that stops the trader gracefully."""
    def handler(signum, frame):
        signame = signal.Signals(signum).name
        log.info(f"Received {signame}, shutting down...")
        trader.stop()
        
        # Give tasks time to complete
        loop.call_soon_threadsafe(loop.stop)
    
    return handler


async def main():
    """Main entry point."""
    log.info("=" * 50)
    log.info("🧘 MONK MODE - BTC/ETH Pair Trading Bot")
    log.info("=" * 50)
    
    # Load configuration
    try:
        config = Config.load()
    except Exception as e:
        log.error("Failed to load configuration", error=str(e))
        sys.exit(1)
    
    # Validate configuration
    errors = config.validate()
    if errors:
        for error in errors:
            log.error(f"Configuration error: {error}")
        log.error(
            "Please set the required environment variables. "
            "See README.md for setup instructions."
        )
        sys.exit(1)
    
    log.info(
        "Configuration loaded",
        spread_threshold=f"{config.strategy.spread_threshold}%",
        telegram_enabled=config.notifications.telegram_enabled,
        discord_enabled=config.notifications.discord_enabled,
    )
    
    # Create trader instance
    trader = MonkPairTrader(config)
    
    # Setup signal handlers for graceful shutdown
    loop = asyncio.get_running_loop()
    
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(
                sig,
                lambda s=sig: asyncio.create_task(shutdown(trader, s))
            )
        except NotImplementedError:
            # Windows doesn't support add_signal_handler
            signal.signal(sig, create_shutdown_handler(trader, loop))
    
    # Run the bot
    try:
        await trader.run()
    except asyncio.CancelledError:
        log.info("Bot task cancelled")
    except Exception as e:
        log.error("Fatal error", error=str(e), error_type=type(e).__name__)
        trader.stop()
        raise


async def shutdown(trader: MonkPairTrader, sig: signal.Signals):
    """Handle graceful shutdown."""
    log.info(f"Received {sig.name}, initiating shutdown...")
    trader.stop()
    
    # Cancel all running tasks except current
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    for task in tasks:
        task.cancel()
    
    await asyncio.gather(*tasks, return_exceptions=True)
    asyncio.get_running_loop().stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Interrupted by user")
    except Exception as e:
        log.error("Unexpected error", error=str(e))
        sys.exit(1)

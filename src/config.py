"""Configuration loader for Monk Mode bot."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml
from dotenv import load_dotenv

load_dotenv()


@dataclass
class StrategyConfig:
    """Strategy parameters."""
    debug_mode: bool = False  # True = verbose logging, False = only alerts
    spread_threshold: float = 2.0
    spread_max: float = 8.0
    spread_close_threshold: float = 1.0
    position_size_usd: float = 1000
    take_profit_usd: float = 25
    cooldown_sec: int = 300
    polling_interval_sec: int = 30


@dataclass
class NotificationConfig:
    """Notification settings."""
    telegram_enabled: bool = True
    discord_enabled: bool = True
    discord_role_id: str = ""  # Discord role ID to tag on alerts
    include_platforms: list[str] = field(default_factory=lambda: ["variational", "extended"])


@dataclass
class Config:
    """Main configuration."""
    strategy: StrategyConfig
    notifications: NotificationConfig
    
    # Secrets from environment
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    discord_webhook_url: Optional[str] = None
    
    # API URLs (defaults, can be overridden)
    binance_ws_url: str = "wss://stream.binance.com:9443/ws"
    binance_rest_url: str = "https://api.binance.com/api/v3"
    variational_url: str = "https://omni-client-api.prod.ap-northeast-1.variational.io"
    extended_url: str = "https://api.extended.exchange/api/v1"
    
    @classmethod
    def load(cls, config_path: str = "config.yaml") -> "Config":
        """Load configuration from YAML file and environment variables."""
        config_file = Path(config_path)
        
        if config_file.exists():
            with open(config_file) as f:
                data = yaml.safe_load(f) or {}
        else:
            data = {}
        
        strategy_data = data.get("strategy", {})
        notif_data = data.get("notifications", {})
        platforms = data.get("platforms", {})
        
        return cls(
            strategy=StrategyConfig(
                debug_mode=strategy_data.get("debug_mode", False),
                spread_threshold=strategy_data.get("spread_threshold", 2.0),
                spread_max=strategy_data.get("spread_max", 8.0),
                spread_close_threshold=strategy_data.get("spread_close_threshold", 1.0),
                position_size_usd=strategy_data.get("position_size_usd", 1000),
                take_profit_usd=strategy_data.get("take_profit_usd", 25),
                cooldown_sec=strategy_data.get("cooldown_sec", 300),
                polling_interval_sec=strategy_data.get("polling_interval_sec", 30),
            ),
            notifications=NotificationConfig(
                telegram_enabled=notif_data.get("telegram", {}).get("enabled", True),
                discord_enabled=notif_data.get("discord", {}).get("enabled", True),
                discord_role_id=notif_data.get("discord", {}).get("role_id", ""),
                include_platforms=notif_data.get("include_platforms", ["variational", "extended"]),
            ),
            # Environment variables (Railway sets these)
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN"),
            telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID"),
            discord_webhook_url=os.getenv("DISCORD_WEBHOOK_URL"),
            # API URLs (env overrides config file)
            binance_ws_url=os.getenv(
                "BINANCE_WS_URL",
                platforms.get("binance", {}).get("ws_url", cls.binance_ws_url)
            ),
            binance_rest_url=os.getenv(
                "BINANCE_REST_URL",
                platforms.get("binance", {}).get("rest_url", cls.binance_rest_url)
            ),
            variational_url=os.getenv(
                "VARIATIONAL_URL",
                platforms.get("variational", {}).get("rest_url", cls.variational_url)
            ),
            extended_url=os.getenv(
                "EXTENDED_URL",
                platforms.get("extended", {}).get("rest_url", cls.extended_url)
            ),
        )
    
    def validate(self) -> list[str]:
        """Validate configuration and return list of errors."""
        errors = []
        
        if self.notifications.telegram_enabled:
            if not self.telegram_bot_token:
                errors.append("TELEGRAM_BOT_TOKEN is required when Telegram is enabled")
            if not self.telegram_chat_id:
                errors.append("TELEGRAM_CHAT_ID is required when Telegram is enabled")
        
        if self.notifications.discord_enabled:
            if not self.discord_webhook_url:
                errors.append("DISCORD_WEBHOOK_URL is required when Discord is enabled")
        
        if self.strategy.spread_threshold <= 0:
            errors.append("spread_threshold must be positive")
        
        if self.strategy.spread_threshold >= self.strategy.spread_max:
            errors.append("spread_threshold must be less than spread_max")
        
        return errors

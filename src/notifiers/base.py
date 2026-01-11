"""Base notifier classes and alert formatting."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional

from src.api.base import SpreadSignal, SignalType, PriceData, Position


class AlertType(str, Enum):
    """Type of alert to send."""
    SIGNAL = "signal"      # New trading signal
    CLOSE = "close"        # Close position signal
    STATUS = "status"      # Bot status update


@dataclass
class AlertPayload:
    """Data for an alert notification."""
    signal: SpreadSignal
    platform_prices: dict[str, dict[str, PriceData]]  # platform -> symbol -> price
    alert_type: AlertType = AlertType.SIGNAL
    position: Optional[Position] = None  # For close alerts
    estimated_pnl: Optional[float] = None  # For close alerts
    
    def format_telegram_message(self) -> str:
        """Format the alert for Telegram (Markdown)."""
        signal = self.signal
        
        if self.alert_type == AlertType.CLOSE:
            return self._format_close_telegram()
        
        # Determine strategy
        if signal.signal_type == SignalType.STRATEGY1:
            emoji = "📈"
            strategy_name = "STRATEGY 1"
        else:
            emoji = "📉"
            strategy_name = "STRATEGY 2"
        
        lines = [
            "🧘 *MONK MODE ALERT*",
            "",
            "━━━━━━━━━━━━━━━━━━━━━",
            f"{emoji} *{strategy_name} SIGNAL*",
            "━━━━━━━━━━━━━━━━━━━━━",
            "",
            f"*Action:* {signal.action_text}",
            f"*Reason:* {signal.reason_text}",
            "",
            "📊 *Binance (Signal Source)*",
            f"├─ BTC: ${signal.btc.price:,.2f} ({signal.btc.change_24h_pct:+.2f}%)",
            f"├─ ETH: ${signal.eth.price:,.2f} ({signal.eth.change_24h_pct:+.2f}%)",
            f"└─ Spread: {signal.spread_pct:+.2f}%",
        ]
        
        # Add platform-specific prices
        for platform, prices in self.platform_prices.items():
            if not prices:
                continue
            
            platform_name = platform.upper()
            lines.append("")
            lines.append(f"💹 *{platform_name}*")
            
            if "BTC" in prices:
                btc = prices["BTC"]
                parts = [f"├─ BTC: ${btc.price:,.2f}"]
                if btc.bid and btc.ask:
                    parts.append(f" (B/A: ${btc.bid:,.2f}/${btc.ask:,.2f})")
                if btc.funding_rate is not None:
                    parts.append(f" | FR: {btc.funding_rate:.4f}%")
                lines.append("".join(parts))
            
            if "ETH" in prices:
                eth = prices["ETH"]
                parts = [f"└─ ETH: ${eth.price:,.2f}"]
                if eth.bid and eth.ask:
                    parts.append(f" (B/A: ${eth.bid:,.2f}/${eth.ask:,.2f})")
                if eth.funding_rate is not None:
                    parts.append(f" | FR: {eth.funding_rate:.4f}%")
                lines.append("".join(parts))
        
        lines.extend([
            "",
            f"⏰ {signal.timestamp.strftime('%Y-%m-%d %H:%M:%S')} UTC",
            "",
            "_NFA. DYOR 🙏_",
        ])
        
        return "\n".join(lines)
    
    def _format_close_telegram(self) -> str:
        """Format close alert for Telegram."""
        signal = self.signal
        position = self.position
        
        lines = [
            "🧘 *MONK MODE ALERT*",
            "",
            "━━━━━━━━━━━━━━━━━━━━━",
            "💰 *CLOSE POSITION SIGNAL*",
            "━━━━━━━━━━━━━━━━━━━━━",
            "",
            "*Action:* Close All Positions",
            f"*Reason:* Spread normalized to {signal.spread_pct:+.2f}%",
            "",
        ]
        
        if position:
            pnl_emoji = "🟢" if self.estimated_pnl and self.estimated_pnl > 0 else "🔴"
            pnl_str = f"${self.estimated_pnl:+,.2f}" if self.estimated_pnl else "N/A"
            
            lines.extend([
                "📊 *Position Summary*",
                f"├─ Entry Spread: {position.entry_spread:+.2f}%",
                f"├─ Current Spread: {signal.spread_pct:+.2f}%",
                f"├─ Duration: {position.duration_str}",
                f"└─ Est. PnL: {pnl_emoji} {pnl_str}",
                "",
            ])
        
        lines.extend([
            "📊 *Current Prices*",
            f"├─ BTC: ${signal.btc.price:,.2f}",
            f"└─ ETH: ${signal.eth.price:,.2f}",
            "",
            f"⏰ {signal.timestamp.strftime('%Y-%m-%d %H:%M:%S')} UTC",
            "",
            "_NFA. DYOR 🙏_",
        ])
        
        return "\n".join(lines)
    
    def format_discord_embed(self) -> dict:
        """Format the alert as a Discord embed."""
        signal = self.signal
        
        if self.alert_type == AlertType.CLOSE:
            return self._format_close_discord()
        
        # Determine style based on strategy
        if signal.signal_type == SignalType.STRATEGY1:
            color = 0x00FF88  # Green
            title = "📈 Strategy 1 Signal"
        else:
            color = 0xFF3366  # Red
            title = "📉 Strategy 2 Signal"
        
        fields = [
            {
                "name": "🟠 BTC",
                "value": f"${signal.btc.price:,.2f}\n{signal.btc.change_24h_pct:+.2f}% (24h)",
                "inline": True,
            },
            {
                "name": "🔷 ETH",
                "value": f"${signal.eth.price:,.2f}\n{signal.eth.change_24h_pct:+.2f}% (24h)",
                "inline": True,
            },
            {
                "name": "📊 Spread",
                "value": f"{signal.spread_pct:+.2f}%",
                "inline": True,
            },
        ]
        
        # Add platform-specific fields
        for platform, prices in self.platform_prices.items():
            if not prices:
                continue
            
            platform_name = platform.capitalize()
            value_parts = []
            
            if "BTC" in prices:
                btc = prices["BTC"]
                line = f"BTC: ${btc.price:,.2f}"
                if btc.funding_rate is not None:
                    line += f" (FR: {btc.funding_rate:.3f}%)"
                value_parts.append(line)
            
            if "ETH" in prices:
                eth = prices["ETH"]
                line = f"ETH: ${eth.price:,.2f}"
                if eth.funding_rate is not None:
                    line += f" (FR: {eth.funding_rate:.3f}%)"
                value_parts.append(line)
            
            if value_parts:
                fields.append({
                    "name": f"💹 {platform_name}",
                    "value": "\n".join(value_parts),
                    "inline": True,
                })
        
        return {
            "title": title,
            "description": f"**{signal.action_text}**\n{signal.reason_text}",
            "color": color,
            "fields": fields,
            "footer": {"text": "Monk Mode Bot • NFA DYOR"},
            "timestamp": signal.timestamp.isoformat(),
        }
    
    def _format_close_discord(self) -> dict:
        """Format close alert as Discord embed."""
        signal = self.signal
        position = self.position
        
        pnl_str = f"${self.estimated_pnl:+,.2f}" if self.estimated_pnl else "N/A"
        pnl_positive = self.estimated_pnl and self.estimated_pnl > 0
        
        fields = [
            {
                "name": "📊 Current Spread",
                "value": f"{signal.spread_pct:+.2f}%",
                "inline": True,
            },
            {
                "name": "📈 Entry Spread",
                "value": f"{position.entry_spread:+.2f}%" if position else "N/A",
                "inline": True,
            },
            {
                "name": "💵 Est. PnL",
                "value": pnl_str,
                "inline": True,
            },
        ]
        
        if position:
            fields.append({
                "name": "📝 Position Summary",
                "value": (
                    f"Entry: {position.signal_type.value.replace('strategy', 'Strategy ')}\n"
                    f"BTC @ ${position.entry_btc_price:,.2f} / ETH @ ${position.entry_eth_price:,.2f}\n"
                    f"Duration: {position.duration_str} • Size: ${position.position_size_usd:,.0f}/leg"
                ),
                "inline": False,
            })
        
        return {
            "title": "💰 Close Position Signal",
            "description": f"**Spread Normalized - Take Profit**\nSpread returned to: **{signal.spread_pct:+.2f}%**",
            "color": 0xF7931A,  # Gold
            "fields": fields,
            "footer": {"text": "Monk Mode Bot • NFA DYOR"},
            "timestamp": signal.timestamp.isoformat(),
        }


class BaseNotifier(ABC):
    """Abstract base class for notification handlers."""
    
    @abstractmethod
    async def send(self, payload: AlertPayload) -> bool:
        """
        Send notification.
        
        Args:
            payload: The alert data to send
            
        Returns:
            True if notification was sent successfully
        """
        pass
    
    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the notification service is reachable."""
        pass

"""Base data models for the Monk Mode bot."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class SignalType(str, Enum):
    """Type of trading signal."""
    STRATEGY1 = "strategy1"  # Long BTC / Short ETH (ETH outperforming)
    STRATEGY2 = "strategy2"  # Short BTC / Long ETH (ETH underperforming)
    CLOSE = "close"          # Close position (spread normalized)


@dataclass
class PriceData:
    """Price information for an asset."""
    symbol: str
    price: float
    change_24h_pct: float
    timestamp: datetime
    platform: str
    bid: Optional[float] = None
    ask: Optional[float] = None
    volume_24h: Optional[float] = None
    funding_rate: Optional[float] = None
    
    @property
    def spread_bps(self) -> Optional[float]:
        """Calculate bid-ask spread in basis points."""
        if self.bid and self.ask and self.price > 0:
            return ((self.ask - self.bid) / self.price) * 10000
        return None
    
    def __repr__(self) -> str:
        return f"PriceData({self.symbol}@{self.platform}: ${self.price:,.2f} [{self.change_24h_pct:+.2f}%])"


@dataclass 
class SpreadSignal:
    """A trading signal based on BTC/ETH spread."""
    btc: PriceData
    eth: PriceData
    spread_pct: float  # ETH change - BTC change (positive = ETH outperforming)
    signal_type: Optional[SignalType] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    def __post_init__(self):
        """Determine signal type based on spread."""
        if self.signal_type is None:
            if self.spread_pct >= 2.0:
                self.signal_type = SignalType.STRATEGY1
            elif self.spread_pct <= -2.0:
                self.signal_type = SignalType.STRATEGY2
    
    @property
    def action_text(self) -> str:
        """Human-readable action text."""
        if self.signal_type == SignalType.STRATEGY1:
            return "Long BTC / Short ETH"
        elif self.signal_type == SignalType.STRATEGY2:
            return "Short BTC / Long ETH"
        elif self.signal_type == SignalType.CLOSE:
            return "Close Positions"
        return "No Action"
    
    @property
    def reason_text(self) -> str:
        """Human-readable reason text."""
        if self.signal_type == SignalType.STRATEGY1:
            return f"ETH outperforming BTC by {abs(self.spread_pct):.2f}%"
        elif self.signal_type == SignalType.STRATEGY2:
            return f"ETH underperforming BTC by {abs(self.spread_pct):.2f}%"
        elif self.signal_type == SignalType.CLOSE:
            return f"Spread normalized to {self.spread_pct:+.2f}%"
        return "Spread within normal range"


@dataclass
class Position:
    """Tracks an open position for close signal detection."""
    signal_type: SignalType
    entry_spread: float
    entry_btc_price: float
    entry_eth_price: float
    entry_time: datetime
    position_size_usd: float
    
    def estimate_pnl(self, current_btc: float, current_eth: float) -> float:
        """
        Estimate PnL based on current prices.
        
        For Strategy 1 (Long BTC / Short ETH):
        - BTC leg: (current - entry) / entry * size
        - ETH leg: (entry - current) / entry * size (short)
        
        For Strategy 2 (Short BTC / Long ETH):
        - BTC leg: (entry - current) / entry * size (short)
        - ETH leg: (current - entry) / entry * size
        """
        btc_pct_change = (current_btc - self.entry_btc_price) / self.entry_btc_price
        eth_pct_change = (current_eth - self.entry_eth_price) / self.entry_eth_price
        
        if self.signal_type == SignalType.STRATEGY1:
            # Long BTC, Short ETH
            btc_pnl = btc_pct_change * self.position_size_usd
            eth_pnl = -eth_pct_change * self.position_size_usd
        else:
            # Short BTC, Long ETH
            btc_pnl = -btc_pct_change * self.position_size_usd
            eth_pnl = eth_pct_change * self.position_size_usd
        
        return btc_pnl + eth_pnl
    
    @property
    def duration_str(self) -> str:
        """Human-readable position duration."""
        delta = datetime.utcnow() - self.entry_time
        hours, remainder = divmod(int(delta.total_seconds()), 3600)
        minutes, _ = divmod(remainder, 60)
        
        if hours > 0:
            return f"{hours}h {minutes}m"
        return f"{minutes}m"

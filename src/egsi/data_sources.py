"""
EGSI Data Sources

Pluggable data source interfaces for external market data.
Currently provides mock implementations with structure for future
real data integrations (TTF prices, AGSI+ storage data).
"""
import logging
from datetime import date, datetime, timedelta
from typing import Optional, Protocol, List
from abc import ABC, abstractmethod
import os

from src.egsi.types import MarketDataSnapshot

logger = logging.getLogger(__name__)

EGSI_S_DATA_SOURCE = os.environ.get("EGSI_S_DATA_SOURCE", "mock")


class MarketDataProvider(ABC):
    """Abstract base class for market data providers."""
    
    @abstractmethod
    def get_snapshot(self, target_date: date) -> Optional[MarketDataSnapshot]:
        """Fetch market data snapshot for a specific date."""
        pass
    
    @abstractmethod
    def get_history(self, days: int = 7) -> List[MarketDataSnapshot]:
        """Fetch historical market data."""
        pass
    
    @property
    @abstractmethod
    def source_name(self) -> str:
        """Return the name of this data source."""
        pass


class MockMarketDataProvider(MarketDataProvider):
    """
    Mock market data provider for development/testing.
    
    Provides synthetic data based on seasonal patterns.
    Replace with real implementations when data sources are available.
    """
    
    @property
    def source_name(self) -> str:
        return "mock"
    
    def get_snapshot(self, target_date: date) -> Optional[MarketDataSnapshot]:
        """Generate mock market data with seasonal variation."""
        month = target_date.month
        
        if month in [12, 1, 2]:
            base_storage = 0.55
            base_price = 45.0
            season = 'winter'
        elif month in [3, 4, 5]:
            base_storage = 0.35
            base_price = 32.0
            season = 'spring'
        elif month in [6, 7, 8]:
            base_storage = 0.60
            base_price = 28.0
            season = 'summer'
        else:
            base_storage = 0.80
            base_price = 38.0
            season = 'autumn'
        
        day_variation = (target_date.day % 10) / 100.0
        storage_pct = min(1.0, base_storage + day_variation)
        ttf_price = base_price + (target_date.day % 15) - 7
        
        volatility = abs(target_date.day % 7 - 3) * 2.5
        
        if month in [4, 5, 6, 7, 8, 9]:
            injection_rate = 0.5 + (target_date.day % 10) / 20.0
        else:
            injection_rate = -0.3 - (target_date.day % 5) / 10.0
        
        return MarketDataSnapshot(
            data_date=target_date,
            ttf_price=ttf_price,
            ttf_price_ma7=base_price,
            ttf_volatility=volatility,
            storage_level_pct=storage_pct,
            storage_capacity_twh=1100.0,
            storage_level_twh=storage_pct * 1100.0,
            injection_rate_twh=injection_rate,
            source="mock",
            fetched_at=datetime.utcnow(),
        )
    
    def get_history(self, days: int = 7) -> List[MarketDataSnapshot]:
        """Generate mock historical data."""
        today = date.today()
        return [
            self.get_snapshot(today - timedelta(days=i))
            for i in range(days)
        ]


class AGSIPlusProvider(MarketDataProvider):
    """
    AGSI+ (Aggregated Gas Storage Inventory) data provider.
    
    AGSI+ provides EU-wide gas storage data.
    Website: https://agsi.gie.eu/
    
    NOTE: This is a placeholder for future implementation.
    Requires AGSI_API_KEY environment variable.
    """
    
    def __init__(self):
        self.api_key = os.environ.get("AGSI_API_KEY")
        self.base_url = "https://agsi.gie.eu/api"
    
    @property
    def source_name(self) -> str:
        return "agsi_plus"
    
    def get_snapshot(self, target_date: date) -> Optional[MarketDataSnapshot]:
        """
        Fetch storage data from AGSI+.
        
        TODO: Implement actual API call when credentials are available.
        """
        if not self.api_key:
            logger.warning("AGSI+ API key not configured, falling back to mock data")
            return None
        
        logger.info(f"AGSI+ API call would be made for {target_date}")
        return None
    
    def get_history(self, days: int = 7) -> List[MarketDataSnapshot]:
        """Fetch historical storage data."""
        if not self.api_key:
            return []
        return []


class TTFPriceProvider(MarketDataProvider):
    """
    TTF (Title Transfer Facility) gas price provider.
    
    TTF is the main European gas benchmark.
    Data sources: ICE, EEX, or third-party APIs.
    
    NOTE: This is a placeholder for future implementation.
    """
    
    def __init__(self):
        self.api_key = os.environ.get("TTF_PRICE_API_KEY")
    
    @property
    def source_name(self) -> str:
        return "ttf_price"
    
    def get_snapshot(self, target_date: date) -> Optional[MarketDataSnapshot]:
        """
        Fetch TTF price data.
        
        TODO: Implement actual API call when credentials are available.
        """
        if not self.api_key:
            logger.warning("TTF Price API key not configured, falling back to mock data")
            return None
        
        logger.info(f"TTF Price API call would be made for {target_date}")
        return None
    
    def get_history(self, days: int = 7) -> List[MarketDataSnapshot]:
        """Fetch historical price data."""
        if not self.api_key:
            return []
        return []


class CompositeMarketDataProvider(MarketDataProvider):
    """
    Combines multiple data providers with fallback logic.
    
    Priority order:
    1. Try real data providers (AGSI+, TTF)
    2. Fall back to mock data if real data unavailable
    """
    
    def __init__(self):
        self.providers = []
        
        if os.environ.get("AGSI_API_KEY"):
            self.providers.append(AGSIPlusProvider())
        if os.environ.get("TTF_PRICE_API_KEY"):
            self.providers.append(TTFPriceProvider())
        
        self.mock_provider = MockMarketDataProvider()
    
    @property
    def source_name(self) -> str:
        if self.providers:
            return "+".join(p.source_name for p in self.providers)
        return "mock"
    
    def get_snapshot(self, target_date: date) -> Optional[MarketDataSnapshot]:
        """
        Fetch from real providers, merge results, fall back to mock.
        """
        storage_data = None
        price_data = None
        
        for provider in self.providers:
            try:
                snapshot = provider.get_snapshot(target_date)
                if snapshot:
                    if snapshot.has_storage_data and not storage_data:
                        storage_data = snapshot
                    if snapshot.has_price_data and not price_data:
                        price_data = snapshot
            except Exception as e:
                logger.error(f"Error fetching from {provider.source_name}: {e}")
        
        if storage_data and price_data:
            return MarketDataSnapshot(
                data_date=target_date,
                ttf_price=price_data.ttf_price,
                ttf_price_ma7=price_data.ttf_price_ma7,
                ttf_volatility=price_data.ttf_volatility,
                storage_level_pct=storage_data.storage_level_pct,
                storage_capacity_twh=storage_data.storage_capacity_twh,
                storage_level_twh=storage_data.storage_level_twh,
                injection_rate_twh=storage_data.injection_rate_twh,
                source=f"{storage_data.source}+{price_data.source}",
                fetched_at=datetime.utcnow(),
            )
        
        if storage_data:
            mock = self.mock_provider.get_snapshot(target_date)
            if mock:
                storage_data.ttf_price = mock.ttf_price
                storage_data.ttf_price_ma7 = mock.ttf_price_ma7
                storage_data.ttf_volatility = mock.ttf_volatility
                storage_data.source = f"{storage_data.source}+mock_prices"
            return storage_data
        
        if price_data:
            mock = self.mock_provider.get_snapshot(target_date)
            if mock:
                price_data.storage_level_pct = mock.storage_level_pct
                price_data.storage_capacity_twh = mock.storage_capacity_twh
                price_data.storage_level_twh = mock.storage_level_twh
                price_data.injection_rate_twh = mock.injection_rate_twh
                price_data.source = f"{price_data.source}+mock_storage"
            return price_data
        
        return self.mock_provider.get_snapshot(target_date)
    
    def get_history(self, days: int = 7) -> List[MarketDataSnapshot]:
        """Fetch historical data."""
        return [
            self.get_snapshot(date.today() - timedelta(days=i))
            for i in range(days)
        ]


def get_market_data_provider() -> MarketDataProvider:
    """
    Factory function to get the appropriate market data provider.
    
    Set EGSI_S_DATA_SOURCE environment variable to control:
    - "mock": Use synthetic data (default)
    - "agsi": Try AGSI+ first, fall back to mock
    - "ttf": Try TTF price API first, fall back to mock
    - "composite": Try all available real sources, merge results
    """
    source = EGSI_S_DATA_SOURCE.lower()
    
    if source == "agsi":
        provider = AGSIPlusProvider()
        if provider.api_key:
            return provider
        logger.warning("AGSI+ requested but no API key, using mock")
        return MockMarketDataProvider()
    
    if source == "ttf":
        provider = TTFPriceProvider()
        if provider.api_key:
            return provider
        logger.warning("TTF requested but no API key, using mock")
        return MockMarketDataProvider()
    
    if source == "composite":
        return CompositeMarketDataProvider()
    
    return MockMarketDataProvider()

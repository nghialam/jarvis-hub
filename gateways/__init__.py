"""
gateways/__init__.py - Gateway layer initialization for Jarvis Hub 3.0
"""
from gateways.market_gateway import MarketGateway
from gateways.news_gateway import NewsGateway

__all__ = ["MarketGateway", "NewsGateway"]

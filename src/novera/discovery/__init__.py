"""Source discovery adapters. Discovery is URL-first, not internet-wide search."""
from .engine import Asset, DiscoveryError, classify_asset, discover_url, guess_architecture, recommended_method

__all__ = ["Asset", "DiscoveryError", "discover_url", "guess_architecture", "classify_asset", "recommended_method"]

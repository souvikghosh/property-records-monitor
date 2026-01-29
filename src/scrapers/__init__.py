from .base import BaseScraper, PropertyResult
from .miami_dade import MiamiDadeScraper
from .redfin import RedfinScraper
from .realtor import RealtorScraper
from .zillow import ZillowScraper

# Registry of available scrapers
# Key is the CLI name, value is (class, default_kwargs)
SCRAPERS = {
    "zillow_miami": (ZillowScraper, {"location": "miami-fl"}),
    "zillow_la": (ZillowScraper, {"location": "los-angeles-ca"}),
    "zillow_chicago": (ZillowScraper, {"location": "chicago-il"}),
    "zillow_phoenix": (ZillowScraper, {"location": "phoenix-az"}),
    "miami_dade": (MiamiDadeScraper, {}),
    "redfin_miami": (RedfinScraper, {"location": "Miami, FL"}),
    "redfin_la": (RedfinScraper, {"location": "Los Angeles, CA"}),
    "realtor_miami": (RealtorScraper, {"location": "Miami_FL"}),
}


def get_scraper(name: str) -> BaseScraper:
    """Get a scraper instance by name."""
    if name not in SCRAPERS:
        raise ValueError(f"Unknown scraper: {name}. Available: {list(SCRAPERS.keys())}")

    scraper_class, kwargs = SCRAPERS[name]
    return scraper_class(**kwargs)


__all__ = [
    "BaseScraper",
    "PropertyResult",
    "MiamiDadeScraper",
    "RedfinScraper",
    "RealtorScraper",
    "ZillowScraper",
    "SCRAPERS",
    "get_scraper",
]

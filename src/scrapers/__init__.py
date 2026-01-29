from .base import BaseScraper, PropertyResult
from .miami_dade import MiamiDadeScraper
from .redfin import RedfinScraper
from .realtor import RealtorScraper

# Registry of available scrapers
# Key is the CLI name, value is (class, default_kwargs)
SCRAPERS = {
    "miami_dade": (MiamiDadeScraper, {}),
    "redfin_miami": (RedfinScraper, {"location": "Miami, FL"}),
    "redfin_la": (RedfinScraper, {"location": "Los Angeles, CA"}),
    "redfin_chicago": (RedfinScraper, {"location": "Chicago, IL"}),
    "redfin_phoenix": (RedfinScraper, {"location": "Phoenix, AZ"}),
    "realtor_miami": (RealtorScraper, {"location": "Miami_FL"}),
    "realtor_la": (RealtorScraper, {"location": "Los-Angeles_CA"}),
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
    "SCRAPERS",
    "get_scraper",
]

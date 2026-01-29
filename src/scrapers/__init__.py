from .base import BaseScraper, PropertyResult
from .miami_dade import MiamiDadeScraper
from .redfin import RedfinScraper
from .realtor import RealtorScraper
from .zillow import ZillowScraper
from .san_diego import SanDiegoCountyScraper

# Registry of available scrapers
# Key is the CLI name, value is (class, default_kwargs)
SCRAPERS = {
    # County assessor sites (more accessible)
    "san_diego": (SanDiegoCountyScraper, {}),
    "miami_dade": (MiamiDadeScraper, {}),
    # Aggregators (have bot protection)
    "zillow_san_diego": (ZillowScraper, {"location": "san-diego-ca"}),
    "zillow_miami": (ZillowScraper, {"location": "miami-fl"}),
    "zillow_la": (ZillowScraper, {"location": "los-angeles-ca"}),
    "redfin_san_diego": (RedfinScraper, {"location": "San Diego, CA"}),
    "redfin_miami": (RedfinScraper, {"location": "Miami, FL"}),
    "realtor_san_diego": (RealtorScraper, {"location": "San-Diego_CA"}),
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
    "SanDiegoCountyScraper",
    "SCRAPERS",
    "get_scraper",
]

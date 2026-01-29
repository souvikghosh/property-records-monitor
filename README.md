# Property Records Monitor

Monitor county property records for sales, transfers, liens, and foreclosures.

## Features

- Track property sales and transfers across multiple counties
- Filter by price range, property type, zip codes
- Detect foreclosures and liens
- SQLite database for history tracking
- Discord/email/webhook notifications
- Screenshot capture of new listings

## Supported Counties

| County | State | Data Available |
|--------|-------|----------------|
| Miami-Dade | FL | Sales, foreclosures, liens |
| Cook County | IL | Sales, transfers |
| Maricopa | AZ | Sales, assessments |
| Los Angeles | CA | Sales, transfers |

## Quick Start

```bash
# Setup
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
playwright install chromium

# Configure
cp .env.example .env
# Edit .env with your filters and notification settings

# Run
python main.py --dry-run    # Test run
python main.py              # Full run with notifications
```

## Configuration

```bash
# Counties to monitor
COUNTIES=miami_dade,cook_county

# Price filters
MIN_PRICE=200000
MAX_PRICE=750000

# Property types
PROPERTY_TYPES=residential,foreclosure

# Specific zip codes
ZIP_CODES=33139,33140

# Discord notifications
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
```

## Usage

```bash
python main.py                          # All configured counties
python main.py --county miami_dade      # Specific county
python main.py --type foreclosure       # Only foreclosures
python main.py --dry-run                # No notifications
python main.py --list-counties          # Show available counties
```

## License

MIT

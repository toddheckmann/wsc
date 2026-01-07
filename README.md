# Milan Laser Intelligence - Layer 1 Collector

Production-grade competitive intelligence collector for Milan Laser Hair Removal. This system collects raw digital artifacts daily and stores them with strong evidence and change detection.

## Overview

**Layer 1** focuses on raw data collection only - no summarization or analysis. The system:

1. Fetches and archives raw HTML/JSON for each source
2. Takes screenshots for web sources (homepage/offers/careers)
3. Parses key structured fields (jobs, offers, ads metadata, email headers/body)
4. Computes stable hashes for change detection
5. Stores everything in a local SQLite database + artifacts folder
6. Provides deterministic outputs with resilience (retries, timeouts, logging)

## Features

### Data Sources

- **Web Pages**: Change detection + full-page screenshots
  - Homepage, careers, locations, specials pages
  - Normalized HTML hashing for change detection
  - Playwright-based dynamic content capture

- **Job Listings**: Automated career page parsing
  - Extracts all job detail pages
  - Structured fields: title, location, department, type, description
  - Stable job keys using requisition IDs

- **Ads**: Multi-platform ad creative collection
  - Google Ads Transparency Center
  - Meta Ad Library
  - Pluggable backends (manual export + API stub)

- **Email**: IMAP-based seed inbox monitoring
  - RFC822 storage + HTML extraction
  - Configurable filters (sender domains, keywords)
  - Link and preheader extraction

### Technical Features

- **Change Detection**: SHA-256 hashing with normalization
- **Idempotency**: Deduplication within runs
- **Rate Limiting**: Configurable delays between requests
- **Retry Logic**: Exponential backoff with configurable attempts
- **Screenshots**: Full-page PNG captures via Playwright
- **Structured Logging**: Console + file logging with rotation
- **Evidence Trail**: All artifacts timestamped and organized

## Installation

### Prerequisites

- Python 3.11+
- pip

### Setup Steps

1. **Clone or extract the repository**

```bash
cd /path/to/wsc
```

2. **Install Python dependencies**

```bash
pip install -e .
```

3. **Install Playwright browsers**

```bash
playwright install chromium
```

4. **Configure the system**

```bash
cp config.example.yaml config.yaml
# Edit config.yaml to customize settings
```

5. **Initialize the database**

```bash
python -m milanintel init-db --config config.yaml
```

## Configuration

Edit `config.yaml` to configure collectors and settings.

### Web Collector

```yaml
collectors:
  web:
    enabled: true
    urls:
      - url: "https://milanlaser.com/"
        slug: "homepage"
      - url: "https://milanlaser.com/careers"
        slug: "careers"
    rate_limit_seconds: 2.0
```

### Jobs Collector

```yaml
collectors:
  jobs:
    enabled: true
    careers_url: "https://milanlaser.com/careers"
    rate_limit_seconds: 2.0
    max_job_pages: 100
```

### Ads Collector

The ads collector supports two providers:

1. **manual_export** (recommended): Import manually exported data
2. **api_stub**: Placeholder for future API integration

#### Using Manual Export

1. Export ad data from platforms:
   - Google: [Ads Transparency Center](https://adstransparency.google.com/)
   - Meta: [Ad Library](https://www.facebook.com/ads/library/)

2. Save exports as JSON files:
   - Google: `imports/google_ads/export_2024-01-15.json`
   - Meta: `imports/meta_ads/export_2024-01-15.json`

3. Run the collector - it will automatically ingest the files

```yaml
collectors:
  ads:
    enabled: true
    platforms:
      google:
        enabled: true
        provider: "manual_export"
        import_path: "imports/google_ads/"
      meta:
        enabled: true
        provider: "manual_export"
        import_path: "imports/meta_ads/"
```

### Email Collector

**Important**: Only use with email accounts you own and have authorization to access.

Set environment variables for IMAP credentials:

```bash
export MILANINTEL_EMAIL_HOST="imap.gmail.com"
export MILANINTEL_EMAIL_PORT="993"
export MILANINTEL_EMAIL_USERNAME="your-seed-account@gmail.com"
export MILANINTEL_EMAIL_PASSWORD="your-app-password"
export MILANINTEL_EMAIL_FOLDER="INBOX"
```

Enable in config:

```yaml
collectors:
  email:
    enabled: true
    accounts:
      - name: "seed_account_1"
        use_ssl: true
        filters:
          from_domains:
            - "milanlaser.com"
          subject_keywords:
            - "milan"
            - "laser"
            - "offer"
```

## Usage

### Run All Enabled Collectors

```bash
python -m milanintel run --config config.yaml
```

### Run Specific Collectors

```bash
python -m milanintel run --config config.yaml --collectors web,jobs
```

### Check Collection Status

```bash
python -m milanintel status --config config.yaml
```

### View Recent Runs

```bash
python -m milanintel status --config config.yaml --limit 20
```

## Output Structure

### Database

SQLite database at `data/milanintel.db`:

- **runs**: Collection run metadata
- **observations**: Individual entity observations with hashes

### Artifacts Directory

```
artifacts/
├── web/
│   └── 2024-01-15/
│       ├── homepage/
│       │   ├── page.html
│       │   ├── screenshot.png
│       │   └── parsed.json
│       └── careers/
│           ├── page.html
│           ├── screenshot.png
│           └── parsed.json
├── jobs/
│   └── 2024-01-15/
│       ├── laser-technician/
│       │   ├── detail.html
│       │   ├── screenshot.png
│       │   └── parsed.json
│       └── regional-manager/
│           ├── detail.html
│           ├── screenshot.png
│           └── parsed.json
├── ads/
│   └── 2024-01-15/
│       ├── google/
│       │   ├── abc123.json
│       │   └── def456.json
│       └── meta/
│           ├── 987654321.json
│           └── 123456789.json
└── email/
    └── 2024-01-15/
        └── seedaccount/
            ├── special_offer_123.eml
            ├── special_offer_123_body.html
            └── special_offer_123_parsed.json
```

### Logs

Logs are written to:
- Console (STDOUT)
- `logs/run_YYYY-MM-DD.log`

## Data Models

### Observation

Each observation includes:
- `entity_key`: Stable identifier for the entity
- `content_hash`: SHA-256 hash for change detection
- `observed_at_utc`: Timestamp in UTC
- `raw_path`: Path to raw artifact
- `screenshot_path`: Path to screenshot (if applicable)
- `parsed_json`: Structured data as JSON

### Change Detection

The system detects changes by:
1. Normalizing content (removing dynamic elements)
2. Computing SHA-256 hash
3. Comparing with previous observation
4. Logging when changes occur

## Scheduling

For daily collection, use cron:

```bash
# Run daily at 6 AM
0 6 * * * cd /path/to/wsc && /usr/bin/python -m milanintel run --config config.yaml
```

Or use systemd timers, Task Scheduler (Windows), or your preferred scheduler.

## Security & Ethics

### Authentication
- Never hardcode passwords in config files
- Use environment variables for credentials
- Store sensitive configs outside version control

### Robots.txt Compliance
The system logs warnings if robots.txt disallows access. Review and respect these restrictions.

### Rate Limiting
Default 2-second delays between requests to avoid overwhelming target servers. Adjust `rate_limit_seconds` as needed.

### Email Access
Only monitor email accounts you own or have explicit authorization to access. This tool is designed for seed/test accounts that receive marketing emails.

## Troubleshooting

### Playwright Installation Issues

If Playwright fails to install:

```bash
# Install system dependencies (Ubuntu/Debian)
sudo apt-get install -y libgbm1 libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 \
    libxrandr2 libgbm1 libpango-1.0-0 libcairo2 libasound2

# Then retry
playwright install chromium
```

### SSL Certificate Errors (IMAP)

If you encounter SSL errors with Gmail:

```bash
# Use app-specific password instead of account password
# Generate at: https://myaccount.google.com/apppasswords
```

### Database Locked Errors

SQLite may lock if multiple processes access simultaneously. Ensure only one collection runs at a time.

## Development

### Project Structure

```
milanintel/
├── __init__.py
├── __main__.py          # Entry point
├── cli.py               # Click-based CLI
├── config.py            # Configuration management
├── storage.py           # SQLite storage layer
├── models.py            # Data models
├── utils.py             # Utilities (hashing, normalization)
└── collectors/
    ├── __init__.py
    ├── base.py          # Base collector class
    ├── web.py           # Web page collector
    ├── jobs.py          # Jobs collector
    ├── ads.py           # Ads collector
    └── email.py         # Email collector
```

### Running Tests

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest
```

### Code Formatting

```bash
black milanintel/
```

## Architecture Decisions

### Why SQLite?
- Single-file database, easy backups
- No server required
- Sufficient for Layer 1 collection volumes
- Can migrate to PostgreSQL if needed

### Why Playwright vs Requests?
- Many modern sites require JavaScript rendering
- Playwright provides consistent screenshots
- Better handling of SPAs and dynamic content

### Why Manual Export for Ads?
- Ad platform APIs require approval and keys
- Manual export is immediately functional
- API integration can be added later via pluggable backend

### Why IMAP vs API for Email?
- IMAP is universally supported
- No API keys or OAuth flows required
- Direct access to seed account inboxes

## Roadmap

Future enhancements (Layer 2+):
- Automated change alerts
- Trend analysis
- Competitive comparison reports
- API integration for ad platforms
- Multi-competitor support
- Dashboard for visualization

## License

Internal use only. Not for distribution.

## Support

For issues or questions, contact the development team or file an issue in the project repository.

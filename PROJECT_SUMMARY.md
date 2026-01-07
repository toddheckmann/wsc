# Milan Laser Intelligence - Layer 1 Collector
## Complete Project Summary

## Repository Structure

```
wsc/
├── README.md                          # Complete documentation
├── QUICKSTART.md                      # Quick start guide
├── PROJECT_SUMMARY.md                 # This file
├── setup.sh                           # Automated setup script
├── .gitignore                         # Git ignore rules
│
├── pyproject.toml                     # Python project config
├── requirements.txt                   # Alternative pip requirements
├── config.example.yaml                # Example configuration
│
├── milanintel/                        # Main package
│   ├── __init__.py                    # Package initialization
│   ├── __main__.py                    # CLI entry point
│   ├── cli.py                         # Click-based CLI commands
│   ├── config.py                      # Configuration loader
│   ├── storage.py                     # SQLite storage layer
│   ├── models.py                      # Data models
│   ├── utils.py                       # Utilities (hashing, normalization)
│   │
│   └── collectors/                    # Data collectors
│       ├── __init__.py
│       ├── base.py                    # Base collector class
│       ├── web.py                     # Web page collector (Playwright)
│       ├── jobs.py                    # Jobs collector
│       ├── ads.py                     # Ads collector (Google + Meta)
│       └── email.py                   # Email collector (IMAP)
│
├── data/                              # SQLite database (created on init)
│   └── .gitkeep
│
├── artifacts/                         # Collected artifacts (created on run)
│   └── .gitkeep
│
├── logs/                              # Log files (created on run)
│   └── .gitkeep
│
└── imports/                           # Manual import directory
    ├── google_ads/
    │   ├── .gitkeep
    │   └── example_export.json        # Example Google Ads export
    └── meta_ads/
        ├── .gitkeep
        └── example_export.json        # Example Meta Ads export
```

## Components Overview

### Core Modules

1. **cli.py** (407 lines)
   - Click-based command-line interface
   - Commands: `init-db`, `run`, `status`
   - Logging setup and orchestration

2. **storage.py** (296 lines)
   - SQLite database management
   - Tables: `runs`, `observations`
   - Change detection and deduplication

3. **models.py** (130 lines)
   - Data classes: Run, Observation, WebPage, Job, AdCreative, Email
   - Enums: RunStatus, SourceType

4. **config.py** (91 lines)
   - YAML configuration loader
   - Environment variable support
   - Dot-notation access

5. **utils.py** (287 lines)
   - HTML normalization
   - SHA-256 hashing
   - URL cleaning
   - Retry logic with exponential backoff

### Collectors

1. **web.py** (272 lines)
   - Playwright-based web scraping
   - Full-page screenshots
   - HTML normalization and hashing
   - Redirect detection

2. **jobs.py** (341 lines)
   - Career page parsing
   - Job detail extraction
   - Flexible CSS selectors
   - Stable job key generation

3. **ads.py** (357 lines)
   - Pluggable provider architecture
   - ManualExportProvider: JSON imports
   - APIStubProvider: Future API integration
   - Platform-specific parsers (Google, Meta)

4. **email.py** (402 lines)
   - IMAP connection
   - RFC822 storage
   - HTML body extraction
   - Preheader and link extraction
   - Configurable filters

## Key Features

### 1. Change Detection
- Normalized HTML hashing (removes dynamic content)
- SHA-256 for content integrity
- Tracks content changes over time
- Idempotent within runs

### 2. Evidence Trail
- Raw HTML/JSON storage
- Full-page screenshots
- Parsed structured data
- UTC timestamps
- Organized by date and entity

### 3. Resilience
- Exponential backoff retries
- Configurable timeouts
- Error capture in observations
- Partial run support
- Comprehensive logging

### 4. Security
- Environment variables for credentials
- No hardcoded passwords
- robots.txt awareness
- Rate limiting

### 5. Extensibility
- Pluggable ad providers
- Configurable CSS selectors
- Multiple email accounts
- Easy to add new collectors

## Database Schema

### runs Table
```sql
CREATE TABLE runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at_utc TEXT NOT NULL,
    finished_at_utc TEXT,
    status TEXT NOT NULL,
    notes TEXT
);
```

### observations Table
```sql
CREATE TABLE observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    source TEXT NOT NULL,
    entity_key TEXT NOT NULL,
    url TEXT,
    observed_at_utc TEXT NOT NULL,
    content_hash TEXT,
    raw_path TEXT,
    screenshot_path TEXT,
    parsed_json TEXT,
    status TEXT DEFAULT 'success',
    error_message TEXT,
    FOREIGN KEY (run_id) REFERENCES runs (id)
);
```

### Indices
- `idx_observations_run_id`
- `idx_observations_entity_key`
- `idx_observations_content_hash`
- `idx_observations_source`
- `idx_observations_dedup` (UNIQUE on entity_key + content_hash + run_id)

## Installation & Usage

### Quick Setup

```bash
# 1. Install dependencies
pip install -e .
playwright install chromium

# 2. Create configuration
cp config.example.yaml config.yaml

# 3. Initialize database
python -m milanintel init-db

# 4. Run collection
python -m milanintel run
```

### Automated Setup

```bash
chmod +x setup.sh
./setup.sh
```

### CLI Commands

```bash
# Initialize database
python -m milanintel init-db --config config.yaml

# Run all enabled collectors
python -m milanintel run --config config.yaml

# Run specific collectors
python -m milanintel run --collectors web,jobs

# Check status
python -m milanintel status --limit 10
```

## Configuration Examples

### Minimal Configuration

```yaml
competitor:
  name: "Milan Laser Hair Removal"
  primary_domain: "milanlaser.com"

collectors:
  web:
    enabled: true
    urls:
      - url: "https://milanlaser.com/"
        slug: "homepage"

  jobs:
    enabled: true
    careers_url: "https://milanlaser.com/careers"

storage:
  database_path: "data/milanintel.db"
  artifacts_path: "artifacts/"

logging:
  level: "INFO"
```

### Full Configuration

See `config.example.yaml` for all available options.

## Output Structure

### After First Run

```
data/
└── milanintel.db                      # SQLite database

artifacts/
├── web/
│   └── 2024-01-15/
│       ├── homepage/
│       │   ├── page.html              # Raw HTML
│       │   ├── screenshot.png         # Full-page screenshot
│       │   └── parsed.json            # Structured data
│       └── careers/
│           ├── page.html
│           ├── screenshot.png
│           └── parsed.json
│
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
│
├── ads/
│   └── 2024-01-15/
│       ├── google/
│       │   ├── ABC123456789.json
│       │   └── DEF987654321.json
│       └── meta/
│           ├── 123456789012345.json
│           └── 987654321098765.json
│
└── email/
    └── 2024-01-15/
        └── seedaccount/
            ├── special_offer_123.eml  # Raw RFC822
            ├── special_offer_123_body.html
            └── special_offer_123_parsed.json

logs/
└── run_2024-01-15.log                 # Daily log file
```

## Example Queries

### SQLite Queries

```bash
# Count observations by source
sqlite3 data/milanintel.db \
  "SELECT source, COUNT(*) as count FROM observations GROUP BY source;"

# Find changed content
sqlite3 data/milanintel.db \
  "SELECT entity_key, COUNT(DISTINCT content_hash) as versions
   FROM observations
   GROUP BY entity_key
   HAVING versions > 1;"

# Recent runs
sqlite3 data/milanintel.db \
  "SELECT * FROM runs ORDER BY started_at_utc DESC LIMIT 5;"

# Latest observations
sqlite3 data/milanintel.db \
  "SELECT source, entity_key, observed_at_utc, status
   FROM observations
   ORDER BY observed_at_utc DESC
   LIMIT 20;"
```

## Production Deployment

### Scheduling

**Linux/Mac (cron):**
```bash
# Edit crontab
crontab -e

# Add daily collection at 6 AM
0 6 * * * cd /path/to/wsc && /usr/bin/python -m milanintel run --config config.yaml
```

**Windows (Task Scheduler):**
1. Create Basic Task
2. Trigger: Daily at 6:00 AM
3. Action: Start a program
   - Program: `C:\Python311\python.exe`
   - Arguments: `-m milanintel run --config config.yaml`
   - Start in: `C:\path\to\wsc`

### Monitoring

```bash
# Check last run status
python -m milanintel status --limit 1

# Monitor log file
tail -f logs/run_$(date +%Y-%m-%d).log

# Database size
ls -lh data/milanintel.db

# Artifacts size
du -sh artifacts/
```

### Backup

```bash
# Backup database
cp data/milanintel.db backups/milanintel_$(date +%Y%m%d).db

# Backup artifacts (compress)
tar -czf backups/artifacts_$(date +%Y%m%d).tar.gz artifacts/

# Automated backup script
#!/bin/bash
DATE=$(date +%Y%m%d)
mkdir -p backups
cp data/milanintel.db backups/milanintel_$DATE.db
tar -czf backups/artifacts_$DATE.tar.gz artifacts/
find backups/ -mtime +30 -delete  # Keep 30 days
```

## Development

### Running Tests

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests (when implemented)
pytest tests/

# Code formatting
black milanintel/

# Type checking
mypy milanintel/
```

### Adding New Collectors

1. Create collector in `milanintel/collectors/new_collector.py`
2. Extend `BaseCollector`
3. Implement `collect()` method
4. Add to `collectors/__init__.py`
5. Add configuration section to `config.example.yaml`
6. Update CLI to include new collector

## Troubleshooting

### Common Issues

**1. Playwright installation fails**
```bash
# Install system dependencies (Ubuntu/Debian)
sudo apt-get install -y libgbm1 libnss3 libnspr4 libatk1.0-0

# Then retry
playwright install chromium
```

**2. IMAP SSL errors**
```bash
# Use app-specific password for Gmail
# Generate at: https://myaccount.google.com/apppasswords
```

**3. Database locked**
- Ensure only one collection runs at a time
- Check for zombie processes

**4. Rate limiting / IP blocking**
- Increase `rate_limit_seconds` in config
- Use proxy or VPN
- Reduce collection frequency

## Performance

### Expected Collection Times

- **Web (4 pages)**: ~15-30 seconds
- **Jobs (10-50 listings)**: 30-120 seconds
- **Ads (manual import)**: <5 seconds
- **Email (100 messages)**: 10-30 seconds

Total: ~2-5 minutes for typical daily run

### Resource Usage

- **CPU**: Low (mostly waiting for network)
- **Memory**: ~100-200 MB
- **Disk**: ~50-100 MB per day (depends on content)
- **Network**: ~10-50 MB per run

### Optimization Tips

1. Reduce `viewport_width/height` for smaller screenshots
2. Disable screenshots if not needed
3. Adjust `max_job_pages` limit
4. Archive old artifacts periodically
5. Use SQLite VACUUM to compact database

## Security Considerations

### Credentials Management

```bash
# Use environment variables
export MILANINTEL_EMAIL_PASSWORD="..."

# Or use .env file (add to .gitignore)
echo "MILANINTEL_EMAIL_PASSWORD=..." > .env
source .env

# Or use system keychain
# macOS: security add-generic-password -s milanintel -a email -w
# Linux: use gnome-keyring or secret-tool
```

### Network Security

- Collections go over HTTPS
- IMAP uses SSL/TLS by default
- No authentication bypass or exploitation
- Respects robots.txt warnings

### Data Privacy

- Store database and artifacts securely
- Encrypt backups
- Limit access to config files
- Audit log files regularly

## License & Compliance

- Internal use only
- Respect target site terms of service
- Comply with data protection laws
- Only access owned email accounts
- Rate limit to avoid service disruption

## Roadmap

Future enhancements (not in scope for Layer 1):

### Layer 2: Analysis
- Change detection alerts
- Diff visualization
- Trend analysis
- Anomaly detection

### Layer 3: Reporting
- Executive summaries
- Competitive dashboards
- Weekly digests
- Slack/email notifications

### Infrastructure
- PostgreSQL backend
- Docker deployment
- API endpoints
- Web UI

## Support & Contact

For questions or issues:
- Review README.md
- Check logs in `logs/`
- Query database for debugging
- Contact development team

---

**Version**: 1.0.0
**Last Updated**: 2024-01-15
**Python**: 3.11+
**License**: Internal Use Only

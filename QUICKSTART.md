# Quick Start Guide

Get Milan Intel running in 5 minutes.

## Prerequisites

- Python 3.11 or higher
- pip
- Internet connection

## Installation

### 1. Install Dependencies

```bash
# Install Python packages
pip install -e .

# Install Playwright browsers
playwright install chromium
```

### 2. Create Configuration

```bash
# Copy example config
cp config.example.yaml config.yaml

# Edit if needed (defaults work for basic testing)
# nano config.yaml
```

### 3. Initialize Database

```bash
python -m milanintel init-db
```

## First Run

### Minimal Test (Web + Jobs only)

```bash
# Run with default config
python -m milanintel run
```

This will:
- Collect 4 web pages from milanlaser.com
- Find and collect all job listings
- Save everything to `data/` and `artifacts/`
- Log to console and `logs/`

### View Results

```bash
# Check run status
python -m milanintel status

# Browse artifacts
ls -R artifacts/

# Query database
sqlite3 data/milanintel.db "SELECT * FROM runs;"
sqlite3 data/milanintel.db "SELECT source, COUNT(*) FROM observations GROUP BY source;"
```

## Adding More Collectors

### Enable Ads Collection

1. Get ad exports from:
   - [Google Ads Transparency](https://adstransparency.google.com/)
   - [Meta Ad Library](https://www.facebook.com/ads/library/)

2. Save as JSON:
   ```bash
   # Place exports here
   imports/google_ads/my_export.json
   imports/meta_ads/my_export.json
   ```

3. Run again:
   ```bash
   python -m milanintel run
   ```

### Enable Email Collection

1. Set environment variables:
   ```bash
   export MILANINTEL_EMAIL_HOST="imap.gmail.com"
   export MILANINTEL_EMAIL_USERNAME="your-seed@gmail.com"
   export MILANINTEL_EMAIL_PASSWORD="your-app-password"
   ```

2. Enable in config.yaml:
   ```yaml
   collectors:
     email:
       enabled: true  # Change from false to true
   ```

3. Run:
   ```bash
   python -m milanintel run
   ```

## Scheduling

### Daily Collection (Linux/Mac)

```bash
# Add to crontab
crontab -e

# Run daily at 6 AM
0 6 * * * cd /path/to/wsc && /usr/bin/python -m milanintel run --config config.yaml >> /var/log/milanintel.log 2>&1
```

### Daily Collection (Windows)

Use Task Scheduler:
1. Open Task Scheduler
2. Create Basic Task
3. Trigger: Daily at 6:00 AM
4. Action: Start a program
   - Program: `python`
   - Arguments: `-m milanintel run --config config.yaml`
   - Start in: `C:\path\to\wsc`

## Common Issues

### "Playwright not installed"

```bash
playwright install chromium
```

### "Config file not found"

```bash
cp config.example.yaml config.yaml
```

### "Permission denied" (Linux)

```bash
chmod +x setup.sh
```

### Import errors

```bash
# Reinstall
pip install -e . --force-reinstall
```

## Next Steps

- Read [README.md](README.md) for full documentation
- Customize `config.yaml` for your needs
- Set up scheduling for daily runs
- Review artifacts in `artifacts/` directory
- Query database for insights

## Support

For issues, check:
1. Logs in `logs/` directory
2. Database with `python -m milanintel status`
3. README.md troubleshooting section

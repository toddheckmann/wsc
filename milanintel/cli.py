"""
Command-line interface for Milan Intelligence collector.
"""

import sys
import logging
import click
from datetime import datetime
from pathlib import Path

from .config import Config
from .storage import Storage
from .models import RunStatus
from .collectors import WebCollector, JobsCollector, AdsCollector, EmailCollector


def setup_logging(config: Config):
    """
    Setup logging configuration.

    Args:
        config: Configuration object
    """
    log_level = config.get('logging.level', 'INFO')
    log_path = Path(config.get('logging.log_path', 'logs/'))
    log_to_console = config.get('logging.console', True)
    log_to_file = config.get('logging.file', True)

    # Create logs directory
    log_path.mkdir(parents=True, exist_ok=True)

    # Configure root logger
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, log_level))

    # Clear existing handlers
    logger.handlers.clear()

    # Formatter
    formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Console handler
    if log_to_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(getattr(logging, log_level))
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    # File handler
    if log_to_file:
        date_str = datetime.utcnow().strftime('%Y-%m-%d')
        file_handler = logging.FileHandler(
            log_path / f'run_{date_str}.log',
            encoding='utf-8'
        )
        file_handler.setLevel(getattr(logging, log_level))
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)


@click.group()
def cli():
    """Milan Laser Intelligence - Layer 1 Competitive Intelligence Collector"""
    pass


@cli.command()
@click.option(
    '--config',
    default='config.yaml',
    help='Path to configuration file',
    type=click.Path(exists=True)
)
def init_db(config):
    """Initialize the database schema."""
    click.echo("Initializing Milan Intelligence database...")

    try:
        cfg = Config(config)
        storage = Storage(cfg.get('storage.database_path', 'data/milanintel.db'))
        storage.init_db()

        click.echo("✓ Database initialized successfully")
        click.echo(f"  Location: {storage.db_path}")

    except Exception as e:
        click.echo(f"✗ Error initializing database: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option(
    '--config',
    default='config.yaml',
    help='Path to configuration file',
    type=click.Path(exists=True)
)
@click.option(
    '--collectors',
    help='Comma-separated list of collectors to run (web,jobs,ads,email)',
    default=None
)
def run(config, collectors):
    """Run the intelligence collection process."""
    click.echo("=" * 70)
    click.echo("Milan Laser Intelligence - Layer 1 Collection")
    click.echo("=" * 70)
    click.echo()

    try:
        # Load configuration
        cfg = Config(config)
        setup_logging(cfg)

        logger = logging.getLogger(__name__)
        logger.info("Starting collection run")

        # Initialize storage
        storage = Storage(cfg.get('storage.database_path', 'data/milanintel.db'))

        # Create run
        run_obj = storage.create_run(notes=f"CLI run with config: {config}")
        click.echo(f"Run ID: {run_obj.id}")
        click.echo(f"Started: {run_obj.started_at_utc.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        click.echo()

        # Determine which collectors to run
        if collectors:
            enabled_collectors = [c.strip() for c in collectors.split(',')]
        else:
            enabled_collectors = []
            if cfg.is_collector_enabled('web'):
                enabled_collectors.append('web')
            if cfg.is_collector_enabled('jobs'):
                enabled_collectors.append('jobs')
            if cfg.is_collector_enabled('ads'):
                enabled_collectors.append('ads')
            if cfg.is_collector_enabled('email'):
                enabled_collectors.append('email')

        if not enabled_collectors:
            click.echo("⚠ No collectors enabled. Check your configuration.")
            run_obj.status = RunStatus.COMPLETED
            run_obj.finished_at_utc = datetime.utcnow()
            run_obj.notes += " | No collectors enabled"
            storage.update_run(run_obj)
            return

        click.echo(f"Enabled collectors: {', '.join(enabled_collectors)}")
        click.echo()

        total_observations = 0
        total_errors = 0
        collector_results = {}

        # Run web collector
        if 'web' in enabled_collectors:
            click.echo("─" * 70)
            click.echo("WEB COLLECTOR")
            click.echo("─" * 70)
            try:
                collector = WebCollector(cfg, storage, run_obj)
                results = collector.collect()
                collector_results['web'] = results
                total_observations += results.get('observations', 0)
                total_errors += results.get('errors', 0)
                click.echo(f"✓ Web: {results.get('observations', 0)} pages collected")
            except Exception as e:
                logger.error(f"Web collector failed: {e}", exc_info=True)
                click.echo(f"✗ Web collector error: {e}", err=True)
                total_errors += 1
            click.echo()

        # Run jobs collector
        if 'jobs' in enabled_collectors:
            click.echo("─" * 70)
            click.echo("JOBS COLLECTOR")
            click.echo("─" * 70)
            try:
                collector = JobsCollector(cfg, storage, run_obj)
                results = collector.collect()
                collector_results['jobs'] = results
                total_observations += results.get('observations', 0)
                total_errors += results.get('errors', 0)
                click.echo(f"✓ Jobs: {results.get('observations', 0)} listings collected")
            except Exception as e:
                logger.error(f"Jobs collector failed: {e}", exc_info=True)
                click.echo(f"✗ Jobs collector error: {e}", err=True)
                total_errors += 1
            click.echo()

        # Run ads collector
        if 'ads' in enabled_collectors:
            click.echo("─" * 70)
            click.echo("ADS COLLECTOR")
            click.echo("─" * 70)
            try:
                collector = AdsCollector(cfg, storage, run_obj)
                results = collector.collect()
                collector_results['ads'] = results
                total_observations += results.get('observations', 0)
                click.echo(f"✓ Ads: {results.get('observations', 0)} creatives collected")
            except Exception as e:
                logger.error(f"Ads collector failed: {e}", exc_info=True)
                click.echo(f"✗ Ads collector error: {e}", err=True)
                total_errors += 1
            click.echo()

        # Run email collector
        if 'email' in enabled_collectors:
            click.echo("─" * 70)
            click.echo("EMAIL COLLECTOR")
            click.echo("─" * 70)
            try:
                collector = EmailCollector(cfg, storage, run_obj)
                results = collector.collect()
                collector_results['email'] = results
                total_observations += results.get('observations', 0)
                click.echo(f"✓ Email: {results.get('observations', 0)} messages collected")
            except Exception as e:
                logger.error(f"Email collector failed: {e}", exc_info=True)
                click.echo(f"✗ Email collector error: {e}", err=True)
                total_errors += 1
            click.echo()

        # Update run status
        run_obj.finished_at_utc = datetime.utcnow()
        if total_errors > 0:
            run_obj.status = RunStatus.PARTIAL if total_observations > 0 else RunStatus.FAILED
        else:
            run_obj.status = RunStatus.COMPLETED

        storage.update_run(run_obj)

        # Print summary
        click.echo("=" * 70)
        click.echo("COLLECTION SUMMARY")
        click.echo("=" * 70)
        click.echo(f"Total observations: {total_observations}")
        click.echo(f"Errors: {total_errors}")
        click.echo(f"Status: {run_obj.status.value}")
        click.echo(f"Duration: {(run_obj.finished_at_utc - run_obj.started_at_utc).total_seconds():.1f}s")
        click.echo()

        # Get stats from database
        stats = storage.get_run_stats(run_obj.id)
        click.echo("Database stats:")
        click.echo(f"  Successful observations: {stats['successful']}")
        click.echo(f"  Errors: {stats['errors']}")
        click.echo(f"  Sources: {stats['sources']}")
        click.echo()

        logger.info(f"Collection run {run_obj.id} completed with status {run_obj.status.value}")

    except Exception as e:
        logger.error(f"Fatal error during collection: {e}", exc_info=True)
        click.echo(f"✗ Fatal error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option(
    '--config',
    default='config.yaml',
    help='Path to configuration file',
    type=click.Path(exists=True)
)
@click.option(
    '--limit',
    default=10,
    help='Number of recent runs to show',
    type=int
)
def status(config, limit):
    """Show recent collection runs and stats."""
    try:
        cfg = Config(config)
        storage = Storage(cfg.get('storage.database_path', 'data/milanintel.db'))

        with storage.get_connection() as conn:
            cursor = conn.cursor()

            # Get recent runs
            cursor.execute("""
                SELECT id, started_at_utc, finished_at_utc, status, notes
                FROM runs
                ORDER BY started_at_utc DESC
                LIMIT ?
            """, (limit,))

            runs = cursor.fetchall()

            if not runs:
                click.echo("No runs found.")
                return

            click.echo(f"Recent {len(runs)} runs:")
            click.echo()

            for run in runs:
                run_id = run['id']
                started = run['started_at_utc']
                finished = run['finished_at_utc']
                status_val = run['status']

                # Get run stats
                stats = storage.get_run_stats(run_id)

                click.echo(f"Run #{run_id} - {status_val.upper()}")
                click.echo(f"  Started: {started}")
                click.echo(f"  Finished: {finished or 'In progress'}")
                click.echo(f"  Observations: {stats['total_observations']} "
                          f"({stats['successful']} successful, {stats['errors']} errors)")
                click.echo()

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


if __name__ == '__main__':
    cli()

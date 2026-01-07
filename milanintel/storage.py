"""
SQLite storage layer for observations and runs.
"""

import sqlite3
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from contextlib import contextmanager

from .models import Run, Observation, RunStatus, SourceType

logger = logging.getLogger(__name__)


class Storage:
    """SQLite storage manager for intelligence data."""

    def __init__(self, db_path: str):
        """
        Initialize storage.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def get_connection(self):
        """Get a database connection context manager."""
        conn = sqlite3.connect(
            self.db_path,
            detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES
        )
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            conn.close()

    def init_db(self):
        """Initialize database schema."""
        logger.info(f"Initializing database at {self.db_path}")

        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Create runs table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    started_at_utc TEXT NOT NULL,
                    finished_at_utc TEXT,
                    status TEXT NOT NULL,
                    notes TEXT
                )
            """)

            # Create observations table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS observations (
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
                )
            """)

            # Create indices for performance
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_observations_run_id
                ON observations (run_id)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_observations_entity_key
                ON observations (entity_key)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_observations_content_hash
                ON observations (content_hash)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_observations_source
                ON observations (source)
            """)

            cursor.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_observations_dedup
                ON observations (entity_key, content_hash, run_id)
            """)

            conn.commit()
            logger.info("Database schema initialized successfully")

    def create_run(self, notes: Optional[str] = None) -> Run:
        """
        Create a new collection run.

        Args:
            notes: Optional notes about the run

        Returns:
            Run object with ID populated
        """
        run = Run(
            started_at_utc=datetime.utcnow(),
            status=RunStatus.STARTED,
            notes=notes
        )

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO runs (started_at_utc, status, notes)
                VALUES (?, ?, ?)
            """, (
                run.started_at_utc.isoformat(),
                run.status.value,
                run.notes
            ))
            run.id = cursor.lastrowid

        logger.info(f"Created run {run.id}")
        return run

    def update_run(self, run: Run):
        """
        Update an existing run.

        Args:
            run: Run object to update
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE runs
                SET finished_at_utc = ?,
                    status = ?,
                    notes = ?
                WHERE id = ?
            """, (
                run.finished_at_utc.isoformat() if run.finished_at_utc else None,
                run.status.value,
                run.notes,
                run.id
            ))

        logger.info(f"Updated run {run.id} with status {run.status.value}")

    def create_observation(self, observation: Observation) -> Observation:
        """
        Create a new observation.

        Args:
            observation: Observation object to create

        Returns:
            Observation with ID populated
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()

            try:
                cursor.execute("""
                    INSERT INTO observations (
                        run_id, source, entity_key, url, observed_at_utc,
                        content_hash, raw_path, screenshot_path, parsed_json,
                        status, error_message
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    observation.run_id,
                    observation.source.value if observation.source else None,
                    observation.entity_key,
                    observation.url,
                    observation.observed_at_utc.isoformat() if observation.observed_at_utc else None,
                    observation.content_hash,
                    observation.raw_path,
                    observation.screenshot_path,
                    observation.parsed_json,
                    observation.status,
                    observation.error_message
                ))
                observation.id = cursor.lastrowid
            except sqlite3.IntegrityError as e:
                # Duplicate observation (same entity_key + content_hash in same run)
                logger.debug(f"Duplicate observation skipped: {observation.entity_key}")
                # Fetch existing observation
                cursor.execute("""
                    SELECT id FROM observations
                    WHERE entity_key = ? AND content_hash = ? AND run_id = ?
                """, (observation.entity_key, observation.content_hash, observation.run_id))
                row = cursor.fetchone()
                if row:
                    observation.id = row['id']

        return observation

    def get_last_observation(
        self,
        entity_key: str,
        source: Optional[SourceType] = None
    ) -> Optional[Observation]:
        """
        Get the most recent observation for an entity.

        Args:
            entity_key: Entity key to lookup
            source: Optional source type filter

        Returns:
            Observation or None
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()

            if source:
                cursor.execute("""
                    SELECT * FROM observations
                    WHERE entity_key = ? AND source = ?
                    ORDER BY observed_at_utc DESC
                    LIMIT 1
                """, (entity_key, source.value))
            else:
                cursor.execute("""
                    SELECT * FROM observations
                    WHERE entity_key = ?
                    ORDER BY observed_at_utc DESC
                    LIMIT 1
                """, (entity_key,))

            row = cursor.fetchone()
            if not row:
                return None

            return self._row_to_observation(row)

    def get_run_observations(self, run_id: int) -> List[Observation]:
        """
        Get all observations for a run.

        Args:
            run_id: Run ID

        Returns:
            List of observations
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM observations
                WHERE run_id = ?
                ORDER BY observed_at_utc
            """, (run_id,))

            return [self._row_to_observation(row) for row in cursor.fetchall()]

    def get_run_stats(self, run_id: int) -> Dict[str, Any]:
        """
        Get statistics for a run.

        Args:
            run_id: Run ID

        Returns:
            Dictionary with stats
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT
                    COUNT(*) as total,
                    COUNT(CASE WHEN status = 'success' THEN 1 END) as success,
                    COUNT(CASE WHEN status = 'error' THEN 1 END) as errors,
                    COUNT(DISTINCT source) as sources
                FROM observations
                WHERE run_id = ?
            """, (run_id,))

            row = cursor.fetchone()

            return {
                'total_observations': row['total'],
                'successful': row['success'],
                'errors': row['errors'],
                'sources': row['sources']
            }

    def _row_to_observation(self, row: sqlite3.Row) -> Observation:
        """Convert database row to Observation object."""
        return Observation(
            id=row['id'],
            run_id=row['run_id'],
            source=SourceType(row['source']) if row['source'] else None,
            entity_key=row['entity_key'],
            url=row['url'],
            observed_at_utc=datetime.fromisoformat(row['observed_at_utc']) if row['observed_at_utc'] else None,
            content_hash=row['content_hash'],
            raw_path=row['raw_path'],
            screenshot_path=row['screenshot_path'],
            parsed_json=row['parsed_json'],
            status=row['status'],
            error_message=row['error_message']
        )

    def check_for_changes(self, entity_key: str, current_hash: str) -> bool:
        """
        Check if content has changed since last observation.

        Args:
            entity_key: Entity key
            current_hash: Current content hash

        Returns:
            True if changed (or no previous observation), False if unchanged
        """
        last_obs = self.get_last_observation(entity_key)
        if not last_obs:
            return True

        return last_obs.content_hash != current_hash

"""Checkpoint storage and management."""

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class CheckpointStorage:
    """Storage for workflow checkpoints."""

    def __init__(self, database_url: str):
        self.database_url = database_url
        self.is_sqlite = "sqlite" in database_url.lower()

        if self.is_sqlite:
            self.db_path = Path(database_url.replace("sqlite:///", ""))
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

    async def save_checkpoint(self, job_id: str, state_dict: dict[str, Any]) -> None:
        """Save a workflow checkpoint."""
        state_json = json.dumps(state_dict, default=str)

        if self.is_sqlite:
            await self._save_sqlite(job_id, state_json, state_dict)
        else:
            await self._save_postgres(job_id, state_json, state_dict)

    async def load_checkpoint(self, job_id: str) -> dict[str, Any] | None:
        """Load a workflow checkpoint."""
        if self.is_sqlite:
            return await self._load_sqlite(job_id)
        else:
            return await self._load_postgres(job_id)

    async def _save_sqlite(self, job_id: str, state_json: str, state_dict: dict[str, Any]) -> None:
        """Save to SQLite."""
        import aiosqlite

        async with aiosqlite.connect(str(self.db_path)) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS checkpoints (
                    job_id TEXT PRIMARY KEY,
                    state_json TEXT NOT NULL,
                    step TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """)

            await db.execute(
                """
                INSERT OR REPLACE INTO checkpoints (job_id, state_json, step, updated_at)
                VALUES (?, ?, ?, datetime('now'))
                """,
                (
                    job_id,
                    state_json,
                    state_dict.get("current_step", "unknown"),
                ),
            )
            await db.commit()

        logger.info(f"Saved checkpoint for job {job_id}")

    async def _load_sqlite(self, job_id: str) -> dict[str, Any] | None:
        """Load from SQLite."""
        import aiosqlite

        if not self.db_path.exists():
            return None

        async with aiosqlite.connect(str(self.db_path)) as db:
            cursor = await db.execute(
                "SELECT state_json FROM checkpoints WHERE job_id = ?",
                (job_id,),
            )
            row = await cursor.fetchone()

            if row:
                logger.info(f"Loaded checkpoint for job {job_id}")
                return json.loads(row[0])  # type: ignore[no-any-return]

        return None

    async def _save_postgres(
        self, job_id: str, state_json: str, state_dict: dict[str, Any]
    ) -> None:
        """Save to Postgres."""
        import asyncpg

        conn = await asyncpg.connect(self.database_url)

        try:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS checkpoints (
                    job_id TEXT PRIMARY KEY,
                    state_json JSONB NOT NULL,
                    step TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT NOW()
                )
                """)

            await conn.execute(
                """
                INSERT INTO checkpoints (job_id, state_json, step, updated_at)
                VALUES ($1, $2, $3, NOW())
                ON CONFLICT (job_id) DO UPDATE
                SET state_json = EXCLUDED.state_json,
                    step = EXCLUDED.step,
                    updated_at = NOW()
                """,
                job_id,
                state_json,
                state_dict.get("current_step", "unknown"),
            )

            logger.info(f"Saved checkpoint for job {job_id}")

        finally:
            await conn.close()

    async def _load_postgres(self, job_id: str) -> dict[str, Any] | None:
        """Load from Postgres."""
        import asyncpg

        conn = await asyncpg.connect(self.database_url)

        try:
            row = await conn.fetchrow(
                "SELECT state_json FROM checkpoints WHERE job_id = $1",
                job_id,
            )

            if row:
                logger.info(f"Loaded checkpoint for job {job_id}")
                return json.loads(row["state_json"])  # type: ignore[no-any-return]

            return None

        finally:
            await conn.close()

#!/usr/bin/env python3
"""Initialize database tables."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config.logging import configure_logging, get_logger
from app.storage.postgres import init_db

configure_logging()
logger = get_logger(__name__)


async def main() -> None:
    """Initialize database."""
    logger.info("Initializing database tables...")
    await init_db()
    logger.info("Database initialization complete!")


if __name__ == "__main__":
    asyncio.run(main())

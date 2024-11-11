# app/tasks/__init__.py
from app.core.logger import setup_logger

logger = setup_logger(__name__)
logger.info("Tasks Module Initialized")

from app.tasks.queue_tasks import process_queue1, process_queue2

__all__ = ['process_queue1', 'process_queue2']
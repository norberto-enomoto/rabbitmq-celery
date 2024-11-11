# app/workers/__init__.py
import logging

logger = logging.getLogger(__name__)
logger.info("Workers Module Initialized")

from .worker_manager import WorkerManager
from .worker_scaler import WorkerScaler

__all__ = ['WorkerManager', 'WorkerScaler']
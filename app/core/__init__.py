# app/core/__init__.py
from app.core.logger import setup_logger
from app.core.celery_app import app as celery_app

logger = setup_logger(__name__)
logger.info("Core Module Initialized")

# Isso garante que o Celery encontre a app
__all__ = ('celery_app',)
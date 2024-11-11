# app/api/__init__.py
from app.core.logger import setup_logger

logger = setup_logger(__name__)
logger.info("API Module Initialized")

from app.api.routes import app as api_app

__all__ = ['api_app']
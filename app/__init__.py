# app/__init__.py
from app.core.logger import setup_logger

logger = setup_logger(__name__)
logger.info("Queue Processor Application Starting")

# Versão da aplicação
__version__ = '1.0.0'

# Exporta as principais funcionalidades para facilitar importações
from app.core.celery_app import app as celery_app
from app.workers.worker_manager import WorkerManager

__all__ = ['celery_app', 'WorkerManager', '__version__']
# app/tasks/queue_tasks.py
from app.core.celery_app import app, QUEUE_1_NAME, QUEUE_2_NAME
from app.core.logger import setup_logger
import json
from datetime import datetime

logger = setup_logger(__name__)

@app.task(name='app.tasks.queue_tasks.process_queue1')
def process_queue1(message):
    """Processa mensagens da fila 1 (pedidos)"""
    try:
        logger.info(f'Processing order: {json.dumps(message)}')
        return True
    except Exception as e:
        logger.error(f'Error processing order: {str(e)}')
        raise

@app.task(name='app.tasks.queue_tasks.process_queue2')
def process_queue2(message):
    """Processa mensagens da fila 2 (pagamentos)"""
    try:
        logger.info(f'Processing payment: {json.dumps(message)}')
        return True
    except Exception as e:
        logger.error(f'Error processing payment: {str(e)}')
        raise
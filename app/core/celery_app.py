# app/core/celery_app.py

import os
from celery import Celery
from kombu import Exchange, Queue
import logging

logger = logging.getLogger(__name__)

# RabbitMQ Configuration
RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'localhost')
RABBITMQ_PORT = os.getenv('RABBITMQ_PORT', '5672')
RABBITMQ_USER = os.getenv('RABBITMQ_USER', 'admin')
RABBITMQ_PASS = os.getenv('RABBITMQ_PASS', 'admin123')
RABBITMQ_VHOST = os.getenv('RABBITMQ_VHOST', '/')

RABBITMQ_URL = f"amqp://{RABBITMQ_USER}:{RABBITMQ_PASS}@{RABBITMQ_HOST}:{RABBITMQ_PORT}/{RABBITMQ_VHOST}"

# Redis Configuration
REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT = os.getenv('REDIS_PORT', '6379')
REDIS_URL = f"redis://{REDIS_HOST}:{REDIS_PORT}/0"

# Exchange and Queue Configuration
BUSINESS_EXCHANGE = 'business_exchange'
QUEUE_1_NAME = 'business_queue_1'
QUEUE_2_NAME = 'business_queue_2'
ROUTING_KEY_1 = 'business.queue1'
ROUTING_KEY_2 = 'business.queue2'

# Create Celery application
app = Celery('queue_processor',
             broker=RABBITMQ_URL,
             backend=REDIS_URL,
             include=['app.tasks.queue_tasks'])

# Configure Celery
app.conf.update(
    # Broker settings
    broker_connection_retry=True,
    broker_connection_retry_on_startup=True,
    broker_connection_max_retries=10,
    broker_connection_timeout=30,
    
    # Task settings
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    
    # Worker settings
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=100,
    worker_max_memory_per_child=512000,  # 512MB
    worker_timer_precision=1,
    worker_enable_remote_control=True,
    
    # Task execution settings
    task_time_limit=3600,  # 1 hora
    task_soft_time_limit=3300,  # 55 minutos
    
    # Logging
    worker_redirect_stdouts=False,
    worker_redirect_stdouts_level='INFO',
    
    # Performance
    task_default_rate_limit='1000/s',
    
    # Error handling
    task_reject_on_worker_lost=True,
    task_acks_late=True
)

# Define exchanges
business_exchange = Exchange(BUSINESS_EXCHANGE, type='direct')

# Define queues
app.conf.task_queues = (
    Queue(QUEUE_1_NAME, business_exchange, routing_key=ROUTING_KEY_1),
    Queue(QUEUE_2_NAME, business_exchange, routing_key=ROUTING_KEY_2),
)

logger.info(f"Celery application configured successfully with RABBITMQ_URL: {RABBITMQ_URL}")
# app/core/config.py
import os

# app/core/config.py
import os

# RabbitMQ Configuration
RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'localhost')
RABBITMQ_PORT = int(os.getenv('RABBITMQ_PORT', 5672))
RABBITMQ_USER = os.getenv('RABBITMQ_USER', 'admin')
RABBITMQ_PASS = os.getenv('RABBITMQ_PASS', 'admin123')
RABBITMQ_VHOST = os.getenv('RABBITMQ_VHOST', '/')  # Importante: note a barra

# Construindo a URL do RabbitMQ corretamente
RABBITMQ_URL = f'amqp://{RABBITMQ_USER}:{RABBITMQ_PASS}@{RABBITMQ_HOST}:{RABBITMQ_PORT}/{RABBITMQ_VHOST}'

# Exchange Configuration
BUSINESS_EXCHANGE = 'business_exchange'
EXCHANGE_TYPE = 'direct'

# Queue names
QUEUE_1_NAME = 'business_queue_1'
QUEUE_2_NAME = 'business_queue_2'

# Routing keys
ROUTING_KEY_1 = 'business.queue1'
ROUTING_KEY_2 = 'business.queue2'

# Redis Configuration
REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))
REDIS_URL = f'redis://{REDIS_HOST}:{REDIS_PORT}/0'

# Worker Configuration
MIN_WORKERS = int(os.getenv('MIN_WORKERS', 1))
MAX_WORKERS = int(os.getenv('MAX_WORKERS', 10))
SCALE_UP_THRESHOLD = int(os.getenv('SCALE_UP_THRESHOLD', 1000))
SCALE_DOWN_THRESHOLD = int(os.getenv('SCALE_DOWN_THRESHOLD', 100))
MESSAGES_PER_WORKER = int(os.getenv('MESSAGES_PER_WORKER', 200))

# API Configuration
API_HOST = os.getenv('API_HOST', '0.0.0.0')
API_PORT = int(os.getenv('API_PORT', 5000))
# app/workers/worker_manager.py
import pika
import redis
import json
import time
import os
from datetime import datetime
from app.core.logger import setup_logger
from app.core.celery_app import (
    RABBITMQ_URL, REDIS_URL, BUSINESS_EXCHANGE,
    QUEUE_1_NAME, QUEUE_2_NAME, ROUTING_KEY_1, ROUTING_KEY_2
)

# Worker Configuration
MIN_WORKERS = int(os.getenv('MIN_WORKERS', 1))
MAX_WORKERS = int(os.getenv('MAX_WORKERS', 10))
SCALE_UP_THRESHOLD = int(os.getenv('SCALE_UP_THRESHOLD', 1000))
SCALE_DOWN_THRESHOLD = int(os.getenv('SCALE_DOWN_THRESHOLD', 100))
MESSAGES_PER_WORKER = int(os.getenv('MESSAGES_PER_WORKER', 200))

logger = setup_logger(__name__)

class WorkerManager:
    def __init__(self):
        """Inicializa o Worker Manager"""
        self.redis_client = redis.from_url(REDIS_URL)
        self.monitoring = True
        self.connection = None
        self.channel = None
        self.worker_processes = {
            QUEUE_1_NAME: [],
            QUEUE_2_NAME: []
        }
        self._initialize_queue_weights()
        logger.info("Worker Manager initialized with RABBITMQ_URL: %s", RABBITMQ_URL)
        
    def _initialize_queue_weights(self):
        """Inicializa os pesos das filas no Redis se não existirem"""
        try:
            if not self.redis_client.exists('queue_weights'):
                default_weights = {
                    QUEUE_1_NAME: 0.4,
                    QUEUE_2_NAME: 0.6
                }
                self.redis_client.set('queue_weights', json.dumps(default_weights))
                logger.info("Initialized default queue weights: %s", default_weights)
        except Exception as e:
            logger.error("Error initializing queue weights: %s", str(e), exc_info=True)

    def _get_rabbitmq_connection(self):
        """Estabelece conexão com o RabbitMQ"""
        try:
            if self.connection is None or self.connection.is_closed:
                credentials = pika.PlainCredentials(
                    username=os.getenv('RABBITMQ_USER', 'admin'),
                    password=os.getenv('RABBITMQ_PASS', 'admin123')
                )
                
                parameters = pika.ConnectionParameters(
                    host=os.getenv('RABBITMQ_HOST', 'localhost'),
                    port=int(os.getenv('RABBITMQ_PORT', 5672)),
                    virtual_host=os.getenv('RABBITMQ_VHOST', '/'),
                    credentials=credentials,
                    heartbeat=600,
                    blocked_connection_timeout=300
                )
                
                logger.info("Connecting to RabbitMQ with parameters: host=%s, port=%s, vhost=%s, user=%s",
                           parameters.host, parameters.port, parameters.virtual_host, 
                           parameters.credentials.username)
                
                self.connection = pika.BlockingConnection(parameters)
                self.channel = self.connection.channel()
                logger.info("Successfully connected to RabbitMQ")
            
            return self.connection, self.channel
            
        except Exception as e:
            logger.error("Failed to connect to RabbitMQ: %s", str(e), exc_info=True)
            self.connection = None
            self.channel = None
            raise

    def _ensure_connection(self):
        """Garante que a conexão está ativa e reconecta se necessário"""
        try:
            if self.connection is None or self.connection.is_closed:
                connection, channel = self._get_rabbitmq_connection()
                self.connection = connection
                self.channel = channel
            elif self.channel is None or self.channel.is_closed:
                self.channel = self.connection.channel()
                
            # Verifica se o canal está realmente utilizável
            try:
                self.channel.basic_qos(prefetch_count=1)
                return True
            except (pika.exceptions.AMQPConnectionError, pika.exceptions.AMQPChannelError):
                self.connection = None
                self.channel = None
                return False
                
        except Exception as e:
            logger.error("Error ensuring connection: %s", str(e))
            self.connection = None
            self.channel = None
            return False
    
    def _initialize_rabbitmq(self):
        """Inicializa a estrutura do RabbitMQ (exchange e filas)"""
        try:
            self._ensure_connection()

            # Declara o exchange
            self.channel.exchange_declare(
                exchange=BUSINESS_EXCHANGE,
                exchange_type='direct',
                durable=True
            )
            logger.info(f"Declared exchange: {BUSINESS_EXCHANGE}")

            # Declara as filas
            self.channel.queue_declare(queue=QUEUE_1_NAME, durable=True)
            self.channel.queue_declare(queue=QUEUE_2_NAME, durable=True)
            
            # Bind das filas ao exchange
            self.channel.queue_bind(
                queue=QUEUE_1_NAME,
                exchange=BUSINESS_EXCHANGE,
                routing_key=ROUTING_KEY_1
            )
            self.channel.queue_bind(
                queue=QUEUE_2_NAME,
                exchange=BUSINESS_EXCHANGE,
                routing_key=ROUTING_KEY_2
            )
            
            logger.info(f"Queues {QUEUE_1_NAME} and {QUEUE_2_NAME} bound to exchange {BUSINESS_EXCHANGE}")
            
        except Exception as e:
            logger.error(f"Error initializing RabbitMQ structure: {str(e)}", exc_info=True)
            raise

    def _get_queue_stats(self, queue_name):
        """Obtém estatísticas de uma fila específica"""
        try:
            if not self._ensure_connection():
                return 0
                
            # Ensure queue exists
            self.channel.queue_declare(queue=queue_name, durable=True)
            # Get queue stats
            stats = self.channel.queue_declare(queue=queue_name, passive=True)
            return stats.method.message_count
        except Exception as e:
            logger.error("Error getting stats for queue %s: %s", queue_name, str(e))
            return 0
    
    def _monitor_queues(self):
        """Monitora as filas e ajusta os workers conforme necessário"""
        while self.monitoring:
            try:
                # Garante que temos uma conexão válida
                if not self._ensure_connection():
                    logger.warning("Failed to ensure connection. Retrying in 5 seconds...")
                    time.sleep(5)
                    continue
                    
                # Monitoramento das filas
                queue_metrics = {
                    QUEUE_1_NAME: self._get_queue_stats(QUEUE_1_NAME),
                    QUEUE_2_NAME: self._get_queue_stats(QUEUE_2_NAME)
                }
                
                # Log das métricas
                logger.info("Queue metrics: %s", json.dumps(queue_metrics))
                
                # Ajuste de workers para cada fila
                for queue_name, message_count in queue_metrics.items():
                    self._adjust_workers(queue_name, message_count)
                    
                # Atualiza métricas no Redis
                self._update_metrics(queue_metrics)
                
                time.sleep(10)  # Intervalo de monitoramento
                
            except pika.exceptions.AMQPConnectionError as e:
                logger.error("AMQP Connection error: %s. Reconnecting...", str(e))
                self.connection = None
                self.channel = None
                time.sleep(5)
            except pika.exceptions.AMQPChannelError as e:
                logger.error("AMQP Channel error: %s. Recreating channel...", str(e))
                self.channel = None
                time.sleep(5)
            except Exception as e:
                logger.error("Error in monitoring loop: %s", str(e), exc_info=True)
                time.sleep(5)
        

    def _update_metrics(self, metrics):
        """Atualiza métricas no Redis"""
        try:
            metrics['timestamp'] = datetime.utcnow().isoformat()
            self.redis_client.set('queue_metrics', json.dumps(metrics))
            logger.debug("Updated metrics in Redis: %s", json.dumps(metrics))
        except Exception as e:
            logger.error("Error updating metrics: %s", str(e))

    def _adjust_workers(self, queue_name, message_count):
        """Ajusta o número de workers baseado na quantidade de mensagens"""
        try:
            # Obtém os pesos atuais das filas
            weights = json.loads(self.redis_client.get('queue_weights') or '{}')
            queue_weight = weights.get(queue_name, 0.5)
            
            # Calcula o número de workers necessários considerando o peso da fila
            weighted_message_count = int(message_count * queue_weight)
            
            # Aplica thresholds e limites
            if weighted_message_count > SCALE_UP_THRESHOLD:
                needed_workers = min(
                    MAX_WORKERS,
                    weighted_message_count // MESSAGES_PER_WORKER + 1
                )
            elif weighted_message_count < SCALE_DOWN_THRESHOLD:
                needed_workers = max(
                    MIN_WORKERS,
                    weighted_message_count // MESSAGES_PER_WORKER + 1
                )
            else:
                needed_workers = weighted_message_count // MESSAGES_PER_WORKER + 1
            
            current_workers = int(self.redis_client.get(f'{queue_name}_workers') or 0)
            
            if needed_workers != current_workers:
                logger.info(
                    "Adjusting %s workers: current=%d, needed=%d (messages=%d, weight=%.2f)",
                    queue_name, current_workers, needed_workers, message_count, queue_weight
                )
                
                self.redis_client.set(f'{queue_name}_workers', needed_workers)
                
                # Log da alteração
                self._log_scaling_event(queue_name, current_workers, needed_workers, message_count)
                
                # Atualiza configuração do Celery worker
                self._update_worker_concurrency(queue_name, needed_workers)
                
        except Exception as e:
            logger.error("Error adjusting workers for %s: %s", queue_name, str(e), exc_info=True)

    def _update_worker_concurrency(self, queue_name, num_workers):
        """Atualiza a concorrência dos workers do Celery"""
        try:
            # Atualiza a configuração no Redis para que os workers possam ler
            config = {
                'concurrency': num_workers,
                'prefetch_multiplier': max(1, MESSAGES_PER_WORKER // num_workers),
                'updated_at': datetime.utcnow().isoformat()
            }
            self.redis_client.set(
                f'{queue_name}_worker_config',
                json.dumps(config)
            )
            logger.info("Updated worker configuration for %s: %s", queue_name, json.dumps(config))
        except Exception as e:
            logger.error("Error updating worker configuration: %s", str(e))

    def _log_scaling_event(self, queue_name, current_workers, new_workers, message_count):
        """Registra eventos de scaling no Redis"""
        try:
            event = {
                'timestamp': datetime.utcnow().isoformat(),
                'queue': queue_name,
                'current_workers': current_workers,
                'new_workers': new_workers,
                'message_count': message_count,
                'reason': self._get_scaling_reason(current_workers, new_workers, message_count)
            }
            
            # Adiciona o evento à lista de eventos
            self.redis_client.rpush('scaling_events', json.dumps(event))
            
            # Mantém apenas os últimos 100 eventos
            self.redis_client.ltrim('scaling_events', -100, -1)
            
            # Log do evento
            logger.info("Scaling event recorded: %s", json.dumps(event))
            
        except Exception as e:
            logger.error("Error logging scaling event: %s", str(e))

    def _get_scaling_reason(self, current_workers, new_workers, message_count):
        """Determina a razão do scaling"""
        if new_workers > current_workers:
            return f"Scale up due to high message count ({message_count})"
        elif new_workers < current_workers:
            return f"Scale down due to low message count ({message_count})"
        else:
            return "No scaling needed"

    def _check_worker_health(self):
        """Verifica a saúde dos workers"""
        try:
            for queue_name in [QUEUE_1_NAME, QUEUE_2_NAME]:
                # Verifica último heartbeat dos workers
                worker_heartbeats = self.redis_client.hgetall(f'{queue_name}_worker_heartbeats')
                
                current_time = datetime.utcnow()
                for worker_id, last_heartbeat in worker_heartbeats.items():
                    last_heartbeat_time = datetime.fromisoformat(last_heartbeat.decode('utf-8'))
                    
                    # Se o worker não reportou nos últimos 60 segundos, considera morto
                    if (current_time - last_heartbeat_time).total_seconds() > 60:
                        logger.warning("Worker %s appears to be dead. Last heartbeat: %s",
                                     worker_id, last_heartbeat_time)
                        
                        # Remove o worker morto
                        self.redis_client.hdel(f'{queue_name}_worker_heartbeats', worker_id)
                        
        except Exception as e:
            logger.error("Error checking worker health: %s", str(e))

    def start(self):
        """Inicia o Worker Manager"""
        try:
            logger.info("Starting Worker Manager")
            self._initialize_rabbitmq()
            
            # Inicia o loop de monitoramento
            while self.monitoring:
                try:
                    self._monitor_queues()
                    self._check_worker_health()
                    time.sleep(10)  # Intervalo entre verificações
                except Exception as e:
                    logger.error("Error in main loop: %s", str(e))
                    time.sleep(5)  # Espera antes de tentar novamente
                    
        except Exception as e:
            logger.error("Fatal error in Worker Manager: %s", str(e), exc_info=True)
            raise
        finally:
            if self.connection and not self.connection.is_closed:
                self.connection.close()
            logger.info("Worker Manager stopped")
    
    def stop(self):
        """Para o Worker Manager"""
        logger.info("Stopping Worker Manager")
        self.monitoring = False
        if self.connection and not self.connection.is_closed:
            try:
                self.connection.close()
            except Exception as e:
                logger.error("Error closing connection: %s", str(e))

def main():
    """Função principal"""
    try:
        manager = WorkerManager()
        manager.start()
    except KeyboardInterrupt:
        logger.info("Worker Manager stopped by user")
        manager.stop()
    except Exception as e:
        logger.error("Fatal error in main: %s", str(e), exc_info=True)
        raise

if __name__ == '__main__':
    main()
# app/workers/worker_scaler.py

import os
import json
import signal
import psutil
import subprocess
import threading
import time
from datetime import datetime
import redis
from app.core.logger import setup_logger
from app.core.celery_app import (
    REDIS_URL, QUEUE_1_NAME, QUEUE_2_NAME,
    RABBITMQ_HOST, RABBITMQ_PORT, RABBITMQ_USER,
    RABBITMQ_PASS, RABBITMQ_VHOST
)

def parse_memory_value(memory_str):
    """Converte string de memória (ex: '512M', '1G') para KB"""
    if isinstance(memory_str, (int, float)):
        return int(memory_str)
        
    memory_str = str(memory_str).upper()
    multipliers = {
        'K': 1,
        'M': 1024,
        'G': 1024 * 1024,
        'T': 1024 * 1024 * 1024
    }
    
    if memory_str.isdigit():
        return int(memory_str)
        
    unit = memory_str[-1]
    if unit in multipliers:
        try:
            value = float(memory_str[:-1])
            return int(value * multipliers[unit])
        except ValueError:
            return 512000  # valor padrão (512MB em KB)
    
    return 512000  # valor padrão se não conseguir converter

# Configurações
MIN_WORKERS = int(os.getenv('MIN_WORKERS', 1))
MAX_WORKERS = int(os.getenv('MAX_WORKERS', 10))
SCALE_UP_THRESHOLD = int(os.getenv('SCALE_UP_THRESHOLD', 1000))
SCALE_DOWN_THRESHOLD = int(os.getenv('SCALE_DOWN_THRESHOLD', 100))
MESSAGES_PER_WORKER = int(os.getenv('MESSAGES_PER_WORKER', 200))
HEALTHCHECK_INTERVAL = int(os.getenv('HEALTHCHECK_INTERVAL', 10))
MAX_MEMORY_PER_WORKER = parse_memory_value(os.getenv('MAX_MEMORY_PER_WORKER', '512M'))
CPU_THRESHOLD = float(os.getenv('CPU_THRESHOLD', 80.0))

logger = setup_logger(__name__)

class WorkerScaler:
    def __init__(self):
        """Inicializa o Worker Scaler"""
        self.redis_client = redis.from_url(REDIS_URL)
        self.running = True
        self.worker_processes = {
            QUEUE_1_NAME: {},  # {process_id: process_info}
            QUEUE_2_NAME: {}
        }
        self.lock = threading.Lock()
        
    def _get_worker_config(self, queue_name):
        """Obtém a configuração do worker do Redis"""
        try:
            config_str = self.redis_client.get(f'{queue_name}_worker_config')
            if config_str:
                return json.loads(config_str)
            return {
                'concurrency': 1,
                'prefetch_multiplier': MESSAGES_PER_WORKER,
            }
        except Exception as e:
            logger.error(f"Error getting worker config for {queue_name}: {str(e)}")
            return None

    def _start_worker(self, queue_name, worker_id):
        """Inicia um novo processo worker do Celery"""
        try:
            # Obtém configuração atual
            config = self._get_worker_config(queue_name)
            if not config:
                logger.error(f"No configuration found for queue {queue_name}")
                return None

            # Configura comando do worker
            worker_cmd = [
                'celery',
                '-A', 'app.core.celery_app',
                'worker',
                '--loglevel=INFO',
                f'--concurrency={config["concurrency"]}',
                f'--prefetch-multiplier={config["prefetch_multiplier"]}',
                '-Q', queue_name,
                '-n', f'worker_{queue_name}_{worker_id}@%h',
                '--max-tasks-per-child=100',
                f'--max-memory-per-child={MAX_MEMORY_PER_WORKER}',
                '--time-limit=3600',
                '--soft-time-limit=3300'
            ]

            # Configura variáveis de ambiente
            env = os.environ.copy()
            env.update({
                'QUEUE_NAME': queue_name,
                'WORKER_ID': str(worker_id),
                'PYTHONPATH': '/app',
                'C_FORCE_ROOT': 'true',
                'RABBITMQ_HOST': RABBITMQ_HOST,
                'RABBITMQ_PORT': str(RABBITMQ_PORT),
                'RABBITMQ_USER': RABBITMQ_USER,
                'RABBITMQ_PASS': RABBITMQ_PASS,
                'RABBITMQ_VHOST': RABBITMQ_VHOST
            })

            # Inicia processo do worker com captura de saída
            process = subprocess.Popen(
                worker_cmd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                bufsize=1
            )

            # Inicia threads de monitoramento de saída
            def monitor_output(pipe, is_error):
                prefix = 'ERROR' if is_error else 'INFO'
                try:
                    for line in pipe:
                        logger.info(f"Worker {queue_name}_{worker_id} {prefix}: {line.strip()}")
                except Exception as e:
                    logger.error(f"Error monitoring worker output: {str(e)}")

            threading.Thread(target=monitor_output, args=(process.stdout, False), daemon=True).start()
            threading.Thread(target=monitor_output, args=(process.stderr, True), daemon=True).start()

            logger.info(f"Started worker for {queue_name} with PID {process.pid}")

            with self.lock:
                # Armazena informações do processo
                self.worker_processes[queue_name][process.pid] = {
                    'process': process,
                    'started_at': datetime.utcnow().isoformat(),
                    'worker_id': worker_id,
                    'config': config,
                    'last_heartbeat': datetime.utcnow()
                }

            # Registra heartbeat do worker
            self._register_worker_heartbeat(queue_name, worker_id)

            return process.pid

        except Exception as e:
            logger.error(f"Error starting worker for {queue_name}: {str(e)}", exc_info=True)
            return None

    def _stop_worker(self, queue_name, pid):
        """Para um processo worker específico"""
        try:
            with self.lock:
                if queue_name in self.worker_processes and pid in self.worker_processes[queue_name]:
                    process_info = self.worker_processes[queue_name][pid]
                    
                    # Remove do dicionário primeiro para evitar problemas de iteração
                    worker_id = process_info['worker_id']
                    del self.worker_processes[queue_name][pid]
                    
                    # Tenta parar o processo
                    try:
                        # Envia sinal SIGTERM
                        process_info['process'].terminate()
                        
                        # Aguarda processo terminar (max 10 segundos)
                        try:
                            process_info['process'].wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            # Se não terminar, força kill
                            process_info['process'].kill()
                            try:
                                process_info['process'].wait(timeout=5)
                            except subprocess.TimeoutExpired:
                                logger.error(f"Failed to kill worker {pid} for {queue_name}")
                    except Exception as e:
                        logger.error(f"Error stopping process {pid} for {queue_name}: {str(e)}")

                    # Remove heartbeat
                    try:
                        self.redis_client.hdel(f'{queue_name}_worker_heartbeats', worker_id)
                    except Exception as e:
                        logger.error(f"Error removing heartbeat for worker {worker_id}: {str(e)}")

                    logger.info(f"Stopped worker {pid} for queue {queue_name}")

        except Exception as e:
            logger.error(f"Error in _stop_worker for {pid} in {queue_name}: {str(e)}")

    def _register_worker_heartbeat(self, queue_name, worker_id):
        """Registra heartbeat do worker no Redis"""
        try:
            self.redis_client.hset(
                f'{queue_name}_worker_heartbeats',
                worker_id,
                datetime.utcnow().isoformat()
            )
        except Exception as e:
            logger.error(f"Error registering heartbeat: {str(e)}")

    def _check_worker_health(self):
        """Verifica a saúde dos workers"""
        try:
            current_time = datetime.utcnow()
            
            for queue_name in [QUEUE_1_NAME, QUEUE_2_NAME]:
                # Cria uma cópia da lista de PIDs para iteração segura
                with self.lock:
                    pids = list(self.worker_processes[queue_name].keys())
                
                for pid in pids:
                    try:
                        with self.lock:
                            process_info = self.worker_processes[queue_name].get(pid)
                            if not process_info:
                                continue
                            
                            process = process_info['process']
                            last_heartbeat = process_info.get('last_heartbeat', datetime.utcnow())
                            
                            # Verifica se processo ainda está rodando
                            if process.poll() is not None:
                                returncode = process.poll()
                                stderr_output = process.stderr.read() if process.stderr else "No error output"
                                logger.warning(f"Worker {pid} for {queue_name} died unexpectedly")
                                logger.error(f"Worker exit code: {returncode}, Error: {stderr_output}")
                                
                                # Remove worker morto e inicia um novo
                                self._stop_worker(queue_name, pid)
                                new_worker_id = f"{datetime.utcnow().timestamp()}"
                                self._start_worker(queue_name, new_worker_id)
                                continue
                            
                            # Verifica tempo desde último heartbeat
                            heartbeat_age = (current_time - last_heartbeat).total_seconds()
                            if heartbeat_age > 30:
                                logger.warning(f"Worker {pid} hasn't sent heartbeat in {heartbeat_age} seconds")
                                
                    except Exception as e:
                        logger.error(f"Error checking worker {pid}: {str(e)}")
                        
        except Exception as e:
            logger.error(f"Error in health check: {str(e)}")

    def _monitor_system_resources(self):
        """Monitora recursos do sistema e ajusta workers se necessário"""
        try:
            # Obtém métricas do sistema
            cpu_percent = psutil.cpu_percent(interval=1)
            memory_percent = psutil.virtual_memory().percent
            
            # Registra métricas
            logger.info(f"System metrics - CPU: {cpu_percent}%, Memory: {memory_percent}%")
            
            # Armazena métricas no Redis
            metrics = {
                'cpu_percent': cpu_percent,
                'memory_percent': memory_percent,
                'timestamp': datetime.utcnow().isoformat()
            }
            self.redis_client.set('system_metrics', json.dumps(metrics))
            
            # Se sistema está sobrecarregado, reduz workers
            if cpu_percent > CPU_THRESHOLD or memory_percent > 90:
                logger.warning("System overload detected, scaling down workers")
                for queue_name in [QUEUE_1_NAME, QUEUE_2_NAME]:
                    with self.lock:
                        current_workers = len(self.worker_processes[queue_name])
                        if current_workers > MIN_WORKERS:
                            # Remove o worker mais antigo
                            oldest_pid = min(
                                self.worker_processes[queue_name].keys(),
                                key=lambda p: self.worker_processes[queue_name][p]['started_at']
                            )
                            self._stop_worker(queue_name, oldest_pid)
                            
        except Exception as e:
            logger.error(f"Error monitoring system resources: {str(e)}")

    def _adjust_workers(self):
        """Ajusta número de workers com base nas configurações do Redis"""
        for queue_name in [QUEUE_1_NAME, QUEUE_2_NAME]:
            try:
                with self.lock:
                    current_workers = len(self.worker_processes[queue_name])
                    target_workers = int(self.redis_client.get(f'{queue_name}_workers') or MIN_WORKERS)
                    target_workers = min(max(target_workers, MIN_WORKERS), MAX_WORKERS)

                    if current_workers < target_workers:
                        # Scale up
                        for _ in range(target_workers - current_workers):
                            worker_id = f"{datetime.utcnow().timestamp()}"
                            self._start_worker(queue_name, worker_id)
                    elif current_workers > target_workers:
                        # Scale down
                        pids_to_stop = sorted(
                            self.worker_processes[queue_name].keys(),
                            key=lambda p: self.worker_processes[queue_name][p]['started_at']
                        )[:current_workers - target_workers]
                        
                        for pid in pids_to_stop:
                            self._stop_worker(queue_name, pid)

                    logger.info(f"Adjusted workers for {queue_name}: current={len(self.worker_processes[queue_name])}, target={target_workers}")

            except Exception as e:
                logger.error(f"Error adjusting workers for {queue_name}: {str(e)}")

    def start(self):
        """Inicia o Worker Scaler"""
        logger.info("Starting Worker Scaler")
        
        try:
            # Inicia workers iniciais
            for queue_name in [QUEUE_1_NAME, QUEUE_2_NAME]:
                for _ in range(MIN_WORKERS):
                    worker_id = f"{datetime.utcnow().timestamp()}"
                    self._start_worker(queue_name, worker_id)
            
            # Loop principal
            while self.running:
                try:
                    self._check_worker_health()
                    self._monitor_system_resources()
                    self._adjust_workers()
                    time.sleep(HEALTHCHECK_INTERVAL)
                except Exception as e:
                    logger.error(f"Error in main loop: {str(e)}")
                    time.sleep(5)
                    
        except KeyboardInterrupt:
            logger.info("Received shutdown signal")
            self.stop()
        except Exception as e:
            logger.error(f"Fatal error in Worker Scaler: {str(e)}")
            self.stop()
            raise

    def stop(self):
        """Para o Worker Scaler e todos os workers gerenciados"""
        logger.info("Stopping Worker Scaler")
        self.running = False
        
        # Para todos os workers
        for queue_name in [QUEUE_1_NAME, QUEUE_2_NAME]:
            with self.lock:
                for pid in list(self.worker_processes[queue_name].keys()):
                    self._stop_worker(queue_name, pid)

def main():
    """Função principal"""
    try:
        scaler = WorkerScaler()
        scaler.start()
    except KeyboardInterrupt:
        logger.info("Worker Scaler stopped by user")
    except Exception as e:
        logger.error(f"Fatal error in main: {str(e)}")
        raise

if __name__ == '__main__':
    main()
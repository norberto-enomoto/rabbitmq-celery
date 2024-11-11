# Arquitetura Celery e RabbitMQ
```mermaid
flowchart TB
    subgraph External ["Sistema Externo"]
        API["API de Controle\nde Vazão"]
        Redis["Redis\n(Configurações e\nMétricas)"]
        API -->|"Atualiza configs"| Redis
    end
    
    subgraph RMQ ["RabbitMQ"]
        Q1["Fila 1"]
        Q2["Fila 2"]
    end
    
    subgraph Kubernetes ["Cluster Kubernetes"]
        subgraph Management ["Gerenciamento"]
            WorkerManager["Worker Manager\n(Controle de Vazão)"]
            WorkerScaler["Worker Scaler\n(Escalonamento)"]
        end
        
        subgraph CeleryWorkers ["Celery Workers Pool"]
            W1["Workers Fila 1\n(Auto-scaling)"]
            W2["Workers Fila 2\n(Auto-scaling)"]
        end
        
        subgraph Monitor ["Monitoring"]
            Prometheus["Prometheus\n(Métricas)"]
        end
    end
    
    WorkerManager -->|"Grava métricas\ne configs"| Redis
    Redis -->|"Lê métricas\ne configs"| WorkerScaler
    
    WorkerScaler -->|"Escala e\ndistribui tasks\n(40%)"| W1
    WorkerScaler -->|"Escala e\ndistribui tasks\n(60%)"| W2
    
    W1 -->|"Processa"| Q1
    W2 -->|"Processa"| Q2
    
    Prometheus -->|"Monitora\nfilas"| RMQ
    Prometheus -->|"Monitora"| CeleryWorkers
    
    WorkerManager -->|"Monitora"| RMQ
```    

# Visão Geral do Sistema

## Funcionamento do Sistema

O sistema funciona da seguinte forma:

### 1. Worker Manager

* Monitora as filas no RabbitMQ
* Calcula a quantidade necessária de workers baseado no volume
* Atualiza as métricas e configurações no Redis
* Gerencia os pesos de distribuição entre as filas (40%/60%)

### 2. Worker Scaler

* Lê as configurações do Redis
* Gerencia o ciclo de vida dos workers (inicia/para)
* Monitora saúde dos workers via heartbeats
* Ajusta workers baseado em:
  * Métricas do sistema (CPU/Memória)
  * Volume de mensagens
  * Configurações mínimas/máximas

### 3. Workers

* Processam mensagens das filas específicas
* Enviam heartbeats para o Redis
* Auto-escalam baseado nas configurações

### 4. Redis

* Armazena configurações
* Mantém métricas do sistema
* Registra heartbeats dos workers
* Guarda eventos de scaling

### 5. RabbitMQ

* Mantém as filas de mensagens
* Gerencia o roteamento entre filas
* Fornece métricas de volume

## Mecanismos de Resiliência

O sistema possui os seguintes mecanismos de resiliência:

* Monitoramento constante de saúde dos workers
* Reconexão automática em caso de falhas
* Limites de memória e CPU por worker
* Escalonamento automático baseado em demanda
* Distribuição balanceada de carga


# Tasks (Tarefas)

* São funções/trabalhos que precisam ser executados de forma assíncrona
* São definidas no código usando o decorador @app.task
* Representam a unidade de trabalho a ser realizada
* Podem ser enfileiradas múltiplas vezes com parâmetros diferentes

# Workers

* São processos que executam as tasks
* Ficam escutando as filas do message broker
* Podem executar múltiplas tasks sequencialmente
* Podem ser escalados horizontalmente (múltiplas instâncias)
* Gerenciam recursos como conexões com banco de dados
* Possuem configurações como concorrência, timeouts, etc

# Exemplo:

## Worker 1:              
* processar_pedido(1)  
* Executa                      
                      
## Worker 2:
* processar_pedido(2)
* Executa
* processar_pedido(3)
* Executa 

```bash
docker compose build --no-cache
```

```bash
docker compose up
```

```bash
python3 populate.py 
```

```bash
docker logs -f docker logs -f worker_manager
```

```bash
docker logs -f worker_scaler
```

## Flower
http://localhost:5555
admin
admin123

# Comandos de Monitoramento do Celery

## 1. Monitoramento dos Workers por Fila

```bash
# Monitorar workers da fila de negócios (business_queue_1)
celery -A app.core.celery_app inspect -Q business_queue_1 active

# Monitorar workers da fila de negócios (business_queue_2)
celery -A app.core.celery_app inspect -Q business_queue_2 active
```

## 2. Monitoramento das Tasks

```bash
# Ver tasks ativas de processamento de pedidos
celery -A app.core.celery_app inspect query_task app.tasks.queue_tasks.process_queue1

# Ver tasks ativas de processamento de pagamentos
celery -A app.core.celery_app inspect query_task app.tasks.queue_tasks.process_queue2
```

## 3. Status do Sistema

```bash
# Ver estatísticas gerais
celery -A app.core.celery_app inspect stats

# Ver filas ativas e suas configurações
celery -A app.core.celery_app inspect active_queues

# Ver todas as tasks registradas
celery -A app.core.celery_app inspect registered
```

## 4. Monitoramento via Flower

```bash
# Iniciar Flower com autenticação e métricas detalhadas
celery -A app.core.celery_app flower \
    --port=5555 \
    --broker_api='http://admin:admin123@localhost:15672/api/' \
    --broker=amqp://admin:admin123@localhost:5672// \
    --persistent=True \
    --db=/path/to/flower.db \
    --max_tasks=10000
```

## 5. Monitoramento de Eventos

```bash
# Habilitar eventos
celery -A app.core.celery_app control enable_events

# Monitorar eventos em tempo real
celery -A app.core.celery_app events --dump
```

## 6. Controle de Workers

```bash
# Ver status dos workers
celery -A app.core.celery_app status

# Ver tasks ativas
celery -A app.core.celery_app inspect active

# Ver configurações dos workers
celery -A app.core.celery_app inspect conf
```

## 7. Gerenciamento de Recursos

```bash
# Ver uso de memória
celery -A app.core.celery_app inspect memdump

# Ver uso de pool
celery -A app.core.celery_app inspect pool

# Ver limites de taxa
celery -A app.core.celery_app inspect ping
```

## 8. Limpeza e Manutenção

```bash
# Limpar fila de pedidos
celery -A app.core.celery_app purge -Q business_queue_1

# Limpar fila de pagamentos
celery -A app.core.celery_app purge -Q business_queue_2

# Revogar todas as tasks
celery -A app.core.celery_app purge
```

## 9. Debug e Troubleshooting

```bash
# Iniciar worker em modo debug
celery -A app.core.celery_app worker \
    --loglevel=DEBUG \
    -Q business_queue_1,business_queue_2 \
    --logfile=/var/log/celery/worker.log

# Ver tasks reservadas
celery -A app.core.celery_app inspect reserved

# Ver tasks agendadas
celery -A app.core.celery_app inspect scheduled
```

## 10. Monitoramento Específico do Worker Manager

```bash
# Ver métricas específicas de escalabilidade
celery -A app.core.celery_app inspect stats --destination=worker_manager@%h

# Ver configurações de pool
celery -A app.core.celery_app inspect pool --destination=worker_scaler@%h
```

## 11. Verificação de Saúde

```bash
# Ping em todos os workers
celery -A app.core.celery_app inspect ping

# Ver heartbeats
celery -A app.core.celery_app inspect heartbeat
```

## 12. Monitoramento de Rate Limits

```bash
# Ver rate limits ativos
celery -A app.core.celery_app inspect active_queues

# Ver configurações de rate limit
celery -A app.core.celery_app inspect conf
```

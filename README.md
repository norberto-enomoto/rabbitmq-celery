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
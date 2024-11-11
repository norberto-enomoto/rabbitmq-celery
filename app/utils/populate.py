# app/utils/populate.py
import os
import sys

# Adiciona o diretório raiz do projeto ao PYTHONPATH
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, project_root)

from app.core.celery_app import app, QUEUE_1_NAME, QUEUE_2_NAME, ROUTING_KEY_1, ROUTING_KEY_2
from app.tasks.queue_tasks import process_queue1, process_queue2
from datetime import datetime, timedelta
import random
import logging
import uuid
from typing import Dict, Any

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class CeleryQueuePopulator:
    """Populator class for sending messages through Celery tasks"""
    
    def generate_order_data(self) -> Dict[str, Any]:
        """Gera dados simulados de pedido"""
        products = [
            {"name": "Laptop", "price_range": (800, 2000)},
            {"name": "Smartphone", "price_range": (400, 1200)},
            {"name": "Headphones", "price_range": (50, 300)},
            {"name": "Monitor", "price_range": (200, 800)},
            {"name": "Keyboard", "price_range": (30, 150)},
            {"name": "Mouse", "price_range": (20, 100)},
            {"name": "Tablet", "price_range": (200, 1000)},
            {"name": "Printer", "price_range": (150, 500)}
        ]
        
        product = random.choice(products)
        quantity = random.randint(1, 5)
        price = round(random.uniform(*product["price_range"]), 2)
        
        return {
            "id": f"ORD-{random.randint(10000, 99999)}",
            "type": "order",
            "timestamp": (datetime.utcnow() - timedelta(days=random.randint(0, 30))).isoformat(),
            "data": {
                "customer": {
                    "id": f"CUST-{random.randint(1000, 9999)}",
                    "name": f"Customer {random.randint(1, 1000)}",
                    "email": f"customer{random.randint(1, 1000)}@example.com",
                    "address": {
                        "street": f"{random.randint(100, 999)} Main St",
                        "city": random.choice(["New York", "Los Angeles", "Chicago", "Houston", "Phoenix"]),
                        "state": random.choice(["NY", "CA", "IL", "TX", "AZ"]),
                        "zip": f"{random.randint(10000, 99999)}"
                    }
                },
                "product": {
                    "name": product["name"],
                    "quantity": quantity,
                    "unit_price": price,
                    "total": round(quantity * price, 2)
                },
                "status": random.choice(["pending", "processing", "shipped", "delivered"]),
                "shipping_method": random.choice(["standard", "express", "overnight"]),
                "notes": random.choice(["", "Fragile", "Handle with care", "Gift wrap"])
            }
        }
    
    def generate_payment_data(self, order_id: str) -> Dict[str, Any]:
        """Gera dados simulados de pagamento"""
        payment_methods = ["credit_card", "debit_card", "bank_transfer", "paypal", "crypto"]
        statuses = ["pending", "processing", "approved", "declined"]
        
        return {
            "id": f"PAY-{random.randint(10000, 99999)}",
            "type": "payment",
            "timestamp": datetime.utcnow().isoformat(),
            "data": {
                "order_id": order_id,
                "amount": round(random.uniform(10, 2000), 2),
                "payment_method": random.choice(payment_methods),
                "status": random.choice(statuses),
                "transaction_id": f"TRX-{random.randint(100000, 999999)}",
                "payment_details": {
                    "processor": random.choice(["stripe", "paypal", "square", "adyen"]),
                    "currency": random.choice(["USD", "EUR", "GBP", "BRL"]),
                    "installments": random.randint(1, 12) if random.random() > 0.7 else 1,
                    "card_type": random.choice(["visa", "mastercard", "amex", ""]),
                    "card_last_four": f"{random.randint(1000, 9999)}" if random.random() > 0.3 else ""
                }
            }
        }

    def publish_order(self) -> str:
        """
        Publica uma mensagem de pedido usando Celery task
        
        Returns:
            str: Task ID
        """
        try:
            order_data = self.generate_order_data()
            task_id = str(uuid.uuid4())
            
            # Envia usando a interface do Celery
            result = process_queue1.apply_async(
                args=[order_data],
                task_id=task_id,
                queue=QUEUE_1_NAME,
                routing_key=ROUTING_KEY_1
            )
            
            logger.info(f"Order published successfully - Task ID: {result.id}")
            return order_data["id"]
            
        except Exception as e:
            logger.error(f"Error publishing order: {e}")
            raise

    def publish_payment(self, order_id: str):
        """
        Publica uma mensagem de pagamento usando Celery task
        
        Args:
            order_id: ID do pedido relacionado
        """
        try:
            payment_data = self.generate_payment_data(order_id)
            task_id = str(uuid.uuid4())
            
            # Envia usando a interface do Celery
            result = process_queue2.apply_async(
                args=[payment_data],
                task_id=task_id,
                queue=QUEUE_2_NAME,
                routing_key=ROUTING_KEY_2
            )
            
            logger.info(f"Payment published successfully - Task ID: {result.id}")
            
        except Exception as e:
            logger.error(f"Error publishing payment: {e}")
            raise

    def populate_queues(self, message_count: int = 500):
        """
        Popula as filas com mensagens usando tasks do Celery
        
        Args:
            message_count: Número de mensagens a serem geradas para cada fila
        """
        try:
            logger.info(f"Starting queue population with {message_count} messages each")
            
            for i in range(message_count):
                # Publica pedido e seu pagamento relacionado
                order_id = self.publish_order()
                self.publish_payment(order_id)
                
                if (i + 1) % 100 == 0:
                    logger.info(f"Published {i + 1} messages in each queue")
                    
            logger.info("Queue population completed successfully")
            
        except Exception as e:
            logger.error(f"Error during queue population: {e}")
            raise

def main():
    """Main execution function"""
    populator = CeleryQueuePopulator()
    
    try:
        populator.populate_queues(50000)
        logger.info("Process completed successfully!")
        
    except Exception as e:
        logger.error(f"Error during execution: {e}")
        raise

if __name__ == "__main__":
    main()
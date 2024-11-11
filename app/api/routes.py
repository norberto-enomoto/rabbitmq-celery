# app/api/routes.py
from flask import Flask, request, jsonify
from app.core.logger import setup_logger
import redis
from app.core.config import REDIS_URL

app = Flask(__name__)
logger = setup_logger(__name__)
redis_client = redis.from_url(REDIS_URL)

@app.route('/api/queue-weights', methods=['GET'])
def get_queue_weights():
    try:
        weights = redis_client.get('queue_weights')
        return jsonify(weights or {"queue1": 0.4, "queue2": 0.6})
    except Exception as e:
        logger.error(f"Error getting queue weights: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500

@app.route('/api/queue-weights', methods=['POST'])
def update_queue_weights():
    try:
        weights = request.json
        
        if sum(weights.values()) != 1.0:
            return jsonify({"error": "Weights must sum to 1.0"}), 400
            
        redis_client.set('queue_weights', weights)
        logger.info(f"Queue weights updated: {weights}")
        return jsonify({"status": "success"})
        
    except Exception as e:
        logger.error(f"Error updating queue weights: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
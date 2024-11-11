# app/api/routes.py
from flask import Flask, request, jsonify
from app.core.logger import setup_logger
import redis
import json
from app.core.config import REDIS_URL

app = Flask(__name__)
logger = setup_logger(__name__)
redis_client = redis.from_url(REDIS_URL)

@app.route('/api/queue-weights', methods=['GET'])
def get_queue_weights():
    try:
        weights = redis_client.get('queue_weights')
        if weights is None:
            return jsonify({"queue1": 0.4, "queue2": 0.6})
        
        # Decode bytes to string and parse JSON
        weights_dict = json.loads(weights.decode('utf-8'))
        return jsonify(weights_dict)
    except Exception as e:
        logger.error(f"Error getting queue weights: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500

@app.route('/api/queue-weights', methods=['POST'])
def update_queue_weights():
    try:
        weights = request.json
        
        if not weights or sum(weights.values()) != 1.0:
            return jsonify({"error": "Weights must sum to 1.0"}), 400
            
        # Store as JSON string in Redis
        redis_client.set('queue_weights', json.dumps(weights))
        logger.info(f"Queue weights updated: {weights}")
        return jsonify({"status": "success"})
        
    except Exception as e:
        logger.error(f"Error updating queue weights: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
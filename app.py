from flask import Flask, json, jsonify, request, render_template
import mysql.connector
import boto3
import os
import time
import threading
from datetime import datetime, date as date_cls, timezone
from decimal import Decimal
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

def get_db_connection():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT", 3306)),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASS"),
        database=os.getenv("DB_NAME")
    )

# Localstack DynamoDB client
dynamodb = boto3.resource(
    "dynamodb",
    endpoint_url=os.getenv("LOCALSTACK_ENDPOINT", "http://localhost:4566"),
    region_name="us-east-1",
    aws_access_key_id="test",
    aws_secret_access_key="test"
)
DYNAMO_TABLE = os.getenv("DYNAMODB_TABLE_NAME", "multicloud-lab-instance")

# AWS S3 client
# Added in
s3_endpoint_override = os.getenv("AWS_S3_ENDPOINT_OVERRIDE")
s3 = boto3.client(
    "s3",
    region_name=os.getenv("AWS_REGION", "ap-southeast-1"),
    endpoint_url=s3_endpoint_override if s3_endpoint_override else None
)
S3_BUCKET = os.getenv("AWS_S3_BUCKET_NAME")

event_stats = {"dynamodb_success": 0, "dynamodb_failed": 0}
event_stats_lock = threading.Lock()

def log_event_to_dynamodb(event_type, expense, max_retries=3):
    """Write an activity/audit record to LocalStack with retry/backoff. Never breaks the main flow, failures are tracked, not raised"""
    table = dynamodb.Table(DYNAMO_TABLE)
    delay = 0.5  # initial delay in seconds
    for attempt in range(1, max_retries + 1):
        try:
            table = dynamodb.Table(DYNAMO_TABLE)
            table.put_item(Item={
                "id": f"{expense['id']}-{event_type}",
                "event_type": event_type,
                "expense_id": expense['id'],
                "title": expense['title'],
                "amount": Decimal(str(expense['amount'])),
                "category": expense['category'],
                "date": str(expense['date']),
                "logged_at": datetime.now(timezone.utc).isoformat()
            })
            with event_stats_lock:
                event_stats["dynamodb_success"] += 1
            return True
        except Exception as e:
            # LocalStack being down shouuldn't take the app down with it
            app.logger.warning(f"DynamoDB event log failed: {e}")
            if attempt < max_retries:
               time.sleep(delay)
               delay *= 2
    with event_stats_lock:
        event_stats["dynamodb_failed"] += 1
    return False

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/health")
def health():
    return jsonify({"status": "healthy"}), 200

@app.route("/ready")
def ready():
    try:
        db = get_db_connection()
        db.close()
        return jsonify({"status": "ready"}), 200
    except Exception as e:
        return jsonify({"status": "not ready", "error": str(e)}), 503

@app.route("/expenses", methods=["GET"])
def get_expenses():
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM expense ORDER BY date DESC")
    results = cursor.fetchall()
    cursor.close()
    db.close()
    return jsonify(results)

@app.route("/expenses", methods=["POST"])
def add_expense():
    data = request.get_json()
    title = data.get("title")
    amount = data.get("amount")
    category = data.get("category")
    date = data.get("date")

    if not all([title, amount, category, date]):
        return jsonify({"error": "Missing required fields"}), 400

    db = get_db_connection()
    cursor = db.cursor()
    cursor.execute(
        "INSERT INTO expense (title, amount, category, date) VALUES (%s, %s, %s, %s)",
        (title, amount, category, date)
    )
    db.commit()
    new_id = cursor.lastrowid
    cursor.close()
    db.close()

    result = {"id": new_id, "title": title, "amount": amount, "category": category, "date": date}

    # Write to the "second cloud" (LocalStack DynamoDB)
    log_event_to_dynamodb("expense_created", result)

    return jsonify(result), 201

# export/backup route
@app.route("/expenses/export", methods=["POST"])
def export_expenses():
    if not S3_BUCKET:
        return jsonify({"error": "AWS_S3_BUCKET_NAME not configured"}), 500
    
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM expense ORDER BY date DESC")
    results = cursor.fetchall()
    cursor.close()
    db.close()

    for row in results:
        if isinstance(row['date'], date_cls):
            row['date'] = row['date'].isoformat()
        if isinstance(row['amount'], Decimal):
            row['amount'] = float(row['amount'])
    
    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    key = f"exports/expenses-{timestamp}.json"

    try:
        s3.put_object(
            Bucket=S3_BUCKET,
            Key=key,
            Body=json.dumps(results, indent=2),
            ContentType="application/json"
        )
    except Exception as e:
        return jsonify({"error": f"S3 export failed: {str(e)}"}), 502
    
    return jsonify({
        "exported_records": len(results),
        "s3_bucket": S3_BUCKET,
        "s3_key": key,
    }), 200

@app.route("/status/multicloud", methods=["GET"])
def multicloud_status():
    status = {"aws": {}, "localstack": {}, "event_stats": {}}

    # Check real AWS reachability
    try:
        start = time.time()
        s3.head_bucket(Bucket=S3_BUCKET)
        status["aws"] = {"reachable": True, "latency_ms": round((time.time() - start) * 1000, 1)}
    except Exception as e:
        status["aws"] = {"reachable": False, "error": str(e)}

    # Check LocalStack reachability
    try:
        start = time.time()
        dynamodb.meta.client.describe_table(TableName=DYNAMO_TABLE)
        status["localstack"] = {"reachable": True, "latency_ms": round((time.time() - start) * 1000, 1)}
    except Exception as e:
        status["localstack"] = {"reachable": False, "error": str(e)}

    with event_stats_lock:
        status["event_stats"] = dict(event_stats)

    return jsonify(status), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

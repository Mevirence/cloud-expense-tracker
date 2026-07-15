from flask import Flask, jsonify, request, render_template
import mysql.connector
import boto3
import os
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
s3 = boto3.client(
    "s3",
    region_name=os.getenv("AWS_REGION", "ap-southeast-1")
)
S3_BUCKET = os.getenv("AWS_S3_BUCKET_NAME")

def log_event_to_dynamodb(event_type, expense):
    """Write an activity/audit record to LocalStack. Never breaks the main flow"""
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
    except Exception as e:
        # LocalStack being down shouuldn't take the app down with it
        app.logger.warning(f"DynamoDB event log failed: {e}")

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
@app.route("/expense/export", methods=["POST"])
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
    key = f"exports/expenses={timestamp}.json"

    try:
        s3.put_object(
            Bucket=S3_BUCKET,
            Key=key,
            Body=jsonify(results, indent=2),
            ContentType="application/json"
        )
    except Exception as e:
        return jsonify({"error": f"S3 export failed: {str(e)}"}), 502
    
    return jsonify({
        "exported_records": len(results),
        "s3_bucket": S3_BUCKET,
        "s3_key": key,
    }), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

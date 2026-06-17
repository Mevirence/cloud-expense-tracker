from flask import Flask, jsonify, request, render_template
import mysql.connector
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

def get_db_connection():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASS"),
        database=os.getenv("DB_NAME")
    )

@app.route("/")
def home():
    return render_template("index.html")

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

    return jsonify({"id": new_id, "title": title, "amount": amount, "category": category, "date": date}), 201

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

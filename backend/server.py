from flask import Flask, jsonify
from flask_cors import CORS

from database import init_db, add_test_entry, get_all_test_entries

app = Flask(__name__)
CORS(app)

# Initialize database tables on startup
init_db()

temp = get_all_test_entries()

print("DATABASE ENTRIES")

for row in temp:
    print(row.id, row.field1)

@app.route("/", methods=["GET"])
def get_data():
    return jsonify({"message": "Hello from Flask backend!"})


@app.route("/add", methods=["POST"])
def add_entry():
    entry = add_test_entry("Hello")
    return jsonify({"id": entry.id, "field1": entry.field1})


@app.route("/all", methods=["GET"])
def get_all():
    entries = get_all_test_entries()
    return jsonify(
        [{"id": e.id, "field1": e.field1} for e in entries]
    )


if __name__ == "__main__":
    app.run(debug=True)

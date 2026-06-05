"""Flask website: type plain English, get SQL + results from multiple databases."""
from __future__ import annotations

import os
from pathlib import Path
from werkzeug.utils import secure_filename

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

from core.db import get_schema, init_db, run_query, set_db_path, DB_PATH
from core.db_manager import DatabaseManager, convert_csv_to_sqlite, convert_excel_to_sqlite
from core.nl2sql import SQLGenerationError, english_to_sql

load_dotenv()

app = Flask(__name__)
UPLOAD_FOLDER = Path(__file__).parent / "data" / "uploads"
UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
app.config["UPLOAD_FOLDER"] = str(UPLOAD_FOLDER)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50MB max

# Initialize database manager
db_manager = DatabaseManager()

# Add sample database if no databases exist
if not db_manager.databases:
    init_db()
    db_manager.add_database("Sample Database", DB_PATH, "sqlite")
else:
    # Load the active database
    active = db_manager.get_active()
    if active:
        set_db_path(active["path"])


@app.route("/")
def index():
    return render_template("index.html", schema=get_schema())


@app.post("/api/query")
def api_query():
    """Accept an English question, return generated SQL and result rows as JSON."""
    data = request.get_json(silent=True) or {}
    question = (data.get("question") or "").strip()

    try:
        sql = english_to_sql(question, get_schema())
    except SQLGenerationError as exc:
        return jsonify(error=str(exc)), 400

    try:
        columns, rows = run_query(sql)
    except Exception as exc:  # surface SQL execution errors to the user
        return jsonify(error=f"SQL failed to run: {exc}", sql=sql), 400

    return jsonify(sql=sql, columns=columns, rows=rows)


@app.get("/api/databases")
def api_get_databases():
    """Get list of all available databases."""
    return jsonify(databases=db_manager.get_all())


@app.post("/api/databases/switch")
def api_switch_database():
    """Switch to a different database."""
    data = request.get_json(silent=True) or {}
    db_name = (data.get("name") or "").strip()
    
    if not db_name:
        return jsonify(error="Database name required"), 400
    
    if not db_manager.set_active(db_name):
        return jsonify(error="Database not found"), 404
    
    # Update the active connection
    active = db_manager.get_active()
    set_db_path(active["path"])
    
    return jsonify(success=True, schema=get_schema())


@app.post("/api/upload-db")
def api_upload_db():
    """Upload a database file (SQLite, CSV, or Excel)."""
    if "file" not in request.files:
        return jsonify(error="No file provided"), 400
    
    file = request.files["file"]
    if file.filename == "":
        return jsonify(error="No file selected"), 400
    
    filename = secure_filename(file.filename)
    file_ext = Path(filename).suffix.lower()
    
    # Validate file type
    if file_ext not in (".db", ".sqlite", ".sqlite3", ".csv", ".xlsx", ".xls"):
        return jsonify(error="Only .db, .sqlite, .csv, .xlsx, or .xls files are allowed"), 400
    
    try:
        # Save uploaded file
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file.save(filepath)
        
        db_type = "sqlite"
        
        # Convert CSV or Excel to SQLite
        if file_ext == ".csv":
            table_name = Path(filename).stem.replace("-", "_").replace(" ", "_")[:30]
            db_filename = f"{table_name}.db"
            db_path = os.path.join(app.config["UPLOAD_FOLDER"], db_filename)
            
            if not convert_csv_to_sqlite(filepath, db_path, table_name):
                os.remove(filepath)
                return jsonify(error="Failed to convert CSV to SQLite"), 400
            
            # Remove original CSV
            os.remove(filepath)
            filepath = db_path
            db_type = "csv"
        
        elif file_ext in (".xlsx", ".xls"):
            db_filename = f"{Path(filename).stem}.db"
            db_path = os.path.join(app.config["UPLOAD_FOLDER"], db_filename)
            
            if not convert_excel_to_sqlite(filepath, db_path):
                os.remove(filepath)
                return jsonify(error="Failed to convert Excel to SQLite"), 400
            
            # Remove original Excel
            os.remove(filepath)
            filepath = db_path
            db_type = "excel"
        
        # Verify it's a valid SQLite database by reading schema
        set_db_path(filepath)
        schema = get_schema()
        if not schema:
            os.remove(filepath)
            return jsonify(error="Invalid or empty database file"), 400
        
        # Add to database manager
        db_display_name = Path(filename).stem
        db_manager.add_database(db_display_name, filepath, db_type)
        
        # Switch to the new database
        db_manager.set_active(db_display_name)
        
        return jsonify(
            success=True,
            filename=db_display_name,
            schema=schema,
            databases=db_manager.get_all()
        )
    
    except Exception as exc:
        return jsonify(error=f"Upload failed: {str(exc)}"), 500


@app.delete("/api/databases/<db_name>")
def api_delete_database(db_name: str):
    """Delete a database."""
    if db_name == "Sample Database":
        return jsonify(error="Cannot delete sample database"), 403
    
    if not db_manager.remove_database(db_name):
        return jsonify(error="Database not found"), 404
    
    # Switch to an active database
    active = db_manager.get_active()
    if active:
        set_db_path(active["path"])
    
    return jsonify(success=True, databases=db_manager.get_all())


if __name__ == "__main__":
    app.run(debug=True)

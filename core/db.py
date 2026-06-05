"""SQLite helpers: build a sample database, read its schema, and run read-only queries."""
from __future__ import annotations

import os
import sqlite3

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "shop.db")
DB_PATH = os.path.abspath(DB_PATH)

# Global variable to track current database path (can be changed at runtime)
_current_db_path = DB_PATH


def set_db_path(path: str) -> None:
    """Change the active database path (for custom uploads)."""
    global _current_db_path
    _current_db_path = os.path.abspath(path)


def get_current_db_path() -> str:
    """Get the current active database path."""
    return _current_db_path


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(get_current_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create sample tables and seed data if the database does not exist."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    fresh = not os.path.exists(DB_PATH)
    conn = get_connection()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS customers (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                city TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY,
                customer_id INTEGER NOT NULL,
                product TEXT NOT NULL,
                amount REAL NOT NULL,
                order_date TEXT NOT NULL,
                FOREIGN KEY (customer_id) REFERENCES customers(id)
            );
            """
        )
        if fresh:
            conn.executemany(
                "INSERT INTO customers (id, name, city) VALUES (?, ?, ?)",
                [
                    (1, "Aarav Sharma", "Mumbai"),
                    (2, "Bina Patel", "Ahmedabad"),
                    (3, "Chen Wei", "Singapore"),
                    (4, "Diana Costa", "Lisbon"),
                    (5, "Ethan Brown", "London"),
                    (6, "Fatima Noor", "Dubai"),
                ],
            )
            conn.executemany(
                "INSERT INTO orders (id, customer_id, product, amount, order_date) VALUES (?, ?, ?, ?, ?)",
                [
                    (1, 1, "Laptop", 1200.0, "2026-01-05"),
                    (2, 1, "Mouse", 25.0, "2026-01-06"),
                    (3, 2, "Monitor", 300.0, "2026-02-11"),
                    (4, 3, "Laptop", 1500.0, "2026-02-15"),
                    (5, 3, "Keyboard", 80.0, "2026-03-01"),
                    (6, 4, "Phone", 900.0, "2026-03-09"),
                    (7, 5, "Tablet", 600.0, "2026-03-20"),
                    (8, 6, "Laptop", 1100.0, "2026-04-02"),
                    (9, 2, "Headphones", 150.0, "2026-04-10"),
                    (10, 3, "Monitor", 320.0, "2026-04-18"),
                ],
            )
        conn.commit()
    finally:
        conn.close()


def get_schema() -> str:
    """Return a compact text description of all tables and columns for the LLM prompt."""
    conn = get_connection()
    try:
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        lines = []
        for (table,) in ((t["name"],) for t in tables):
            cols = conn.execute(f"PRAGMA table_info({table})").fetchall()
            col_desc = ", ".join(f"{c['name']} {c['type']}" for c in cols)
            lines.append(f"{table}({col_desc})")
        return "\n".join(lines)
    finally:
        conn.close()


def run_query(sql: str):
    """Run a read-only query and return (columns, rows)."""
    conn = get_connection()
    try:
        cursor = conn.execute(sql)
        rows = cursor.fetchall()
        columns = [d[0] for d in cursor.description] if cursor.description else []
        return columns, [list(r) for r in rows]
    finally:
        conn.close()

"""Multi-database manager: track and switch between multiple databases (SQLite, CSV, Excel)."""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

# Store metadata about uploaded databases
DB_MANAGER_FILE = Path(__file__).parent.parent / "data" / "db_manager.json"


class DatabaseManager:
    """Manage multiple uploaded databases."""
    
    def __init__(self):
        self.databases: dict[str, dict] = {}
        self.active_db: str | None = None
        self.load()
    
    def load(self) -> None:
        """Load database metadata from disk."""
        if DB_MANAGER_FILE.exists():
            try:
                with open(DB_MANAGER_FILE, "r") as f:
                    data = json.load(f)
                    self.databases = data.get("databases", {})
                    self.active_db = data.get("active_db")
            except Exception as e:
                print(f"Error loading DB manager: {e}")
    
    def save(self) -> None:
        """Save database metadata to disk."""
        DB_MANAGER_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(DB_MANAGER_FILE, "w") as f:
            json.dump({
                "databases": self.databases,
                "active_db": self.active_db
            }, f, indent=2)
    
    def add_database(self, name: str, filepath: str, file_type: str) -> bool:
        """Add a database to the manager."""
        if not os.path.exists(filepath):
            return False
        
        self.databases[name] = {
            "path": filepath,
            "type": file_type,  # sqlite, csv, excel
            "created": str(Path(filepath).stat().st_ctime)
        }
        
        if self.active_db is None:
            self.active_db = name
        
        self.save()
        return True
    
    def remove_database(self, name: str) -> bool:
        """Remove a database from the manager."""
        if name not in self.databases:
            return False
        
        db_info = self.databases[name]
        filepath = db_info["path"]
        
        # Try to delete the file
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
        except Exception as e:
            print(f"Error deleting file {filepath}: {e}")
        
        del self.databases[name]
        
        if self.active_db == name:
            self.active_db = list(self.databases.keys())[0] if self.databases else None
        
        self.save()
        return True
    
    def set_active(self, name: str) -> bool:
        """Set the active database."""
        if name not in self.databases:
            return False
        self.active_db = name
        self.save()
        return True
    
    def get_active(self) -> dict | None:
        """Get the active database info."""
        if not self.active_db or self.active_db not in self.databases:
            return None
        return {
            "name": self.active_db,
            **self.databases[self.active_db]
        }
    
    def get_all(self) -> list[dict]:
        """Get all databases as a list."""
        return [
            {
                "name": name,
                "active": name == self.active_db,
                **info
            }
            for name, info in self.databases.items()
        ]


def convert_csv_to_sqlite(csv_path: str, db_path: str, table_name: str) -> bool:
    """Convert a CSV file to SQLite database."""
    try:
        import pandas as pd
        
        df = pd.read_csv(csv_path)
        conn = sqlite3.connect(db_path)
        df.to_sql(table_name, conn, if_exists="replace", index=False)
        conn.close()
        return True
    except ImportError:
        print("pandas not installed; trying csv module")
        import csv
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            
            if not rows:
                conn.close()
                return False
            
            # Create table from header
            cols = rows[0].keys()
            col_def = ", ".join([f'"{col}" TEXT' for col in cols])
            cursor.execute(f'CREATE TABLE IF NOT EXISTS "{table_name}" ({col_def})')
            
            # Insert data
            placeholders = ", ".join(["?" for _ in cols])
            col_names = ", ".join([f'"{c}"' for c in cols])
            for row in rows:
                values = [row.get(col, "") for col in cols]
                cursor.execute(
                    f'INSERT INTO "{table_name}" ({col_names}) VALUES ({placeholders})',
                    values
                )
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Error converting CSV to SQLite: {e}")
        return False


def convert_excel_to_sqlite(excel_path: str, db_path: str, sheet_name: str = None) -> bool:
    """Convert an Excel file to SQLite database."""
    try:
        import pandas as pd
        
        xls = pd.ExcelFile(excel_path)
        sheets = xls.sheet_names
        
        conn = sqlite3.connect(db_path)
        
        for sheet in sheets:
            df = pd.read_excel(excel_path, sheet_name=sheet)
            table_name = sheet.replace(" ", "_").replace("-", "_")[:30]
            df.to_sql(table_name, conn, if_exists="replace", index=False)
        
        conn.close()
        return True
    except ImportError:
        print("pandas and openpyxl not installed for Excel support")
        return False
    except Exception as e:
        print(f"Error converting Excel to SQLite: {e}")
        return False

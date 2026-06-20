"""
Database initialization module for setting up the database schema.
"""
import sqlite3
from .database_utils import hash_password


def initialize_database(db_file='DB_FILE'):
    """
    Initialize the database with required tables and views.
    
    Args:
        db_file (str): The database file path.
    """
    try:
        # Connect to SQLite database
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()

        # Create users table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_name TEXT NOT NULL,
            face_encoding BLOB,
            type TEXT DEFAULT 'User',
            school TEXT DEFAULT '',
            place TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        )
        """)
        # Migration: add columns if they don't exist yet (existing DBs)
        for col in ("school TEXT DEFAULT ''", "place TEXT DEFAULT ''", "created_at TEXT DEFAULT (datetime('now', 'localtime'))"):
            try:
                cursor.execute(f"ALTER TABLE users ADD COLUMN {col}")
            except sqlite3.OperationalError:
                pass

        # Set default created_at date for legacy users that were updated
        try:
            cursor.execute("UPDATE users SET created_at = datetime('now', 'localtime') WHERE created_at IS NULL")
        except sqlite3.OperationalError:
            pass

        # Create face_encodings table for multiple patterns per user
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS face_encodings (
            encoding_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            face_encoding BLOB NOT NULL,
            face_image BLOB,
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
        )
        """)
        # Migration: add face_image column if it doesn't exist yet
        try:
            cursor.execute("ALTER TABLE face_encodings ADD COLUMN face_image BLOB")
        except sqlite3.OperationalError:
            pass

        # Create product_history table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS product_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id TEXT NOT NULL,
            product_name TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            user_name TEXT NOT NULL,
            check_out_time TEXT NOT NULL,
            check_in_time TEXT
        )
        """)

        # Create items table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_name TEXT NOT NULL
        )
        """)

        # Create the formatted_items view
        cursor.execute("""
        CREATE VIEW IF NOT EXISTS formatted_items AS 
        SELECT 'slof_' || id AS product_id, product_name
        FROM items;
        """)

        # Create logusers table for authentication
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS logusers (
            username TEXT PRIMARY KEY,
            password TEXT
        )
        """)

        # Insert default admin user if not exists
        cursor.execute("""
        INSERT OR IGNORE INTO logusers (username, password)
        VALUES ('admin', ?)
        """, (hash_password('admin'),))

        # Commit changes to the database
        conn.commit()
        conn.close()
        
    except Exception as e:
        print(f"Database initialization error: {e}")

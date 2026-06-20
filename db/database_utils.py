"""
Database utilities module for handling database operations.
"""
import sqlite3
import hashlib


def execute_query(query, params=(), fetch=False, db_file='DB_FILE'):
    """
    Execute database queries with optional fetch.
    
    Args:
        query (str): The SQL query to execute.
        params (tuple): Parameters to bind to the query.
        fetch (bool): Whether to fetch results.
        db_file (str): The database file path.
        
    Returns:
        list or None: Fetched results if fetch=True, otherwise None.
    """
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    cursor.execute(query, params)
    result = cursor.fetchall() if fetch else None
    conn.commit()
    conn.close()
    return result


def fetch_user_data(db_file='DB_FILE'):
    """
    Fetch all user data from the database.
    
    Args:
        db_file (str): The database file path.
        
    Returns:
        list: List of user records (user_id, user_name, type).
    """
    return execute_query("SELECT user_id, user_name, type FROM users", fetch=True, db_file=db_file)


def update_user_type(user_id, new_type, db_file='DB_FILE'):
    """
    Update user type in the database.
    
    Args:
        user_id (int): The user ID.
        new_type (str): The new user type.
        db_file (str): The database file path.
    """
    execute_query("UPDATE users SET type = ? WHERE user_id = ?", (new_type, user_id), db_file=db_file)


def remove_user(user_id, db_file='DB_FILE'):
    """
    Remove a user from the database.
    
    Args:
        user_id (int): The user ID to remove.
        db_file (str): The database file path.
    """
    execute_query("DELETE FROM face_encodings WHERE user_id = ?", (user_id,), db_file=db_file)
    execute_query("DELETE FROM users WHERE user_id = ?", (user_id,), db_file=db_file)


def hash_password(password):
    """
    Hash a password using SHA256.
    
    Args:
        password (str): The password to hash.
        
    Returns:
        str: The hashed password.
    """
    return hashlib.sha256(password.encode()).hexdigest()

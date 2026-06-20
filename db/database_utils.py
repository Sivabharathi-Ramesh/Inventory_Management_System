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


def is_created_at_update_required(created_at):
    """
    Check if a registration date string requires an annual profile/photo update.
    Returns True if more than one year has passed since registration, otherwise False.
    """
    if not created_at:
        return False
    from datetime import datetime
    try:
        if " " in created_at:
            reg_date = datetime.strptime(created_at.split()[0], "%Y-%m-%d").date()
        else:
            reg_date = datetime.strptime(created_at, "%Y-%m-%d").date()
            
        try:
            anniversary = reg_date.replace(year=reg_date.year + 1)
        except ValueError:
            anniversary = reg_date.replace(year=reg_date.year + 1, day=28)
            
        return datetime.now().date() >= anniversary
    except Exception:
        return False


def is_user_update_required(user_id, db_file='DB_FILE'):
    """
    Check if a user requires an annual profile/photo update.
    Returns True if more than one year has passed since registration, otherwise False.
    """
    result = execute_query("SELECT created_at FROM users WHERE user_id = ?", (user_id,), fetch=True, db_file=db_file)
    if not result or not result[0][0]:
        return False
    return is_created_at_update_required(result[0][0])

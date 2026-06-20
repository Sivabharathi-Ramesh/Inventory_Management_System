"""
Product management utilities module for product history and checking.
"""
import sqlite3
import tkinter as tk
from datetime import datetime
import threading
from utils import scan_qr_code, recognize_user, text_to_speech


def search_product(entry_search, tree, db_file='DB_FILE'):
    """
    Search products based on the user's input.
    
    Args:
        entry_search (tk.Entry): The search entry widget.
        tree (ttk.Treeview): The treeview to display results.
        db_file (str): The database file path.
    """
    search_term = entry_search.get().strip()

    try:
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()
        
        cursor.execute(""" 
            SELECT product_id, product_name, check_out_time, check_in_time, user_id, user_name 
            FROM product_history 
            WHERE product_id LIKE ? OR product_name LIKE ? OR user_id LIKE ? OR user_name LIKE ?
        """, (f'%{search_term}%', f'%{search_term}%', f'%{search_term}%', f'%{search_term}%'))

        items = cursor.fetchall()
        conn.close()

        # Update the Treeview with fetched items
        update_treeview(tree, items)

    finally:
        # Clear the entry field after searching
        entry_search.delete(0, tk.END)


def format_date_str(date_str):
    if not date_str:
        return date_str
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
        return dt.strftime("%d-%m-%Y %I:%M:%S %p")
    except ValueError:
        return date_str


def update_treeview(tree, items):
    """
    Helper function to update the Treeview.
    
    Args:
        tree (ttk.Treeview): The treeview to update.
        items (list): List of items to display.
    """
    # Clear previous items in the Treeview
    for item in tree.get_children():
        tree.delete(item)

    # Insert fetched items into the Treeview
    for item in items:
        # item is a tuple, we need to format the date fields if they match the datetime format
        formatted_item = []
        for val in item:
            if isinstance(val, str) and "-" in val and ":" in val:
                formatted_item.append(format_date_str(val))
            else:
                formatted_item.append(val)
        tree.insert("", "end", values=tuple(formatted_item))


def show_items_admin(tree, db_file='DB_FILE'):
    """
    Show all items for the admin.
    
    Args:
        tree (ttk.Treeview): The treeview to display items.
        db_file (str): The database file path.
    """
    try:
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT ph.product_id, ph.product_name, ph.check_out_time, ph.check_in_time,
                   ph.user_id, COALESCE(u.user_name, ph.user_name) AS user_name
            FROM product_history ph
            LEFT JOIN users u ON ph.user_id = u.user_id
            ORDER BY ph.check_out_time DESC
        """)
        items = cursor.fetchall()
        conn.close()

        # Update the Treeview with fetched items
        update_treeview(tree, items)

    except:
        pass


def show_items(tree, db_file='DB_FILE'):
    """
    Show today's items in the Treeview.
    
    Args:
        tree (ttk.Treeview): The treeview to display items.
        db_file (str): The database file path.
    """
    # Get today's date in the format YYYY-MM-DD
    today_date = datetime.today().strftime('%Y-%m-%d')

    try:
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()

        # SQL query to filter data by today's date
        query = """
        SELECT ph.product_id, ph.product_name, ph.user_id,
               COALESCE(u.user_name, ph.user_name) AS user_name,
               ph.check_out_time, ph.check_in_time
        FROM product_history ph
        LEFT JOIN users u ON ph.user_id = u.user_id
        WHERE DATE(ph.check_out_time) = ?
        ORDER BY ph.check_out_time DESC
        """

        cursor.execute(query, (today_date,))
        items = cursor.fetchall()
        conn.close()

        # Clear existing items in the Treeview
        tree.delete(*tree.get_children())

        # Insert rows into TreeView
        for row in items:
            tag = 'checked_in' if row[5] else 'checked_out'
            formatted_row = []
            for val in row:
                if isinstance(val, str) and "-" in val and ":" in val:
                    formatted_row.append(format_date_str(val))
                else:
                    formatted_row.append(val)
            tree.insert("", "end", values=tuple(formatted_row), tags=(tag,))

    except:
        pass


def check_product(tree, db_file='DB_FILE'):
    """
    Check product function to handle QR scanning and product check-in/check-out.
    
    Args:
        tree (ttk.Treeview): The treeview to update with product info.
        db_file (str): The database file path.
    """
    # Launch QR scanner with Tk preview (keeps UI responsive while scanning).
    parent = tree.winfo_toplevel()
    try:
        from utils.qr_utils import scan_qr_code_with_tk_preview
        product_id = scan_qr_code_with_tk_preview(parent, timeout=30)
    except Exception:
        # Fallback to headless scanner
        product_id = scan_qr_code()

    if product_id is None:
        return

    product_id = product_id.strip()

    try:
        with sqlite3.connect(db_file) as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT product_id, product_name FROM formatted_items WHERE product_id = ?", (product_id,))
            result = cursor.fetchone()

            if result:
                product_name = result[1]
                current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                cursor.execute("SELECT * FROM product_history WHERE product_id = ? AND check_in_time IS NULL", (product_id,))
                checked_out_record = cursor.fetchone()

                if checked_out_record:
                    check_out_time = checked_out_record[5]
                    user_id = checked_out_record[3]
                    user_name = checked_out_record[4]

                    cursor.execute("""UPDATE product_history 
                                    SET check_in_time = ? 
                                    WHERE product_id = ? AND check_in_time IS NULL""",
                                (current_time, product_id))
                    conn.commit()

                    # Update TreeView: refresh items
                    tree.delete(*tree.get_children())
                    show_items(tree, db_file=db_file)

                    text = f"Checked in successfully: {product_id}"
                    text_to_speech(text)

                else:
                    user_id, user_name = recognize_user(db_file=db_file)

                    if user_id == 0:
                        text = "Unknown user, please contact the administrator."
                        text_to_speech(text)
                        return
                    elif user_id is None:
                        text = "Operation cancelled."
                        text_to_speech(text)
                        return
                    else:
                        cursor.execute("""INSERT INTO product_history (product_id, product_name, user_id, user_name, check_out_time, check_in_time)
                                    VALUES (?, ?, ?, ?, ?, NULL)""", (product_id, product_name, user_id, user_name, current_time))
                        conn.commit()

                        # Update TreeView after check-out
                        tree.delete(*tree.get_children())
                        show_items(tree, db_file=db_file)

                        text = f"Checked out successfully: {product_id}"
                        text_to_speech(text)

            else:
                text = "Invalid QR code"
                text_to_speech(text)

    except sqlite3.Error as e:
        text = f"Database error: {e}"
        text_to_speech(text)



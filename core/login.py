"""
Login and authentication module.
"""
import sqlite3
import tkinter as tk
from tkinter import messagebox
import time
from db import hash_password


def open_login_page(window, open_admin_window_callback):
    """
    Open the login page as a modal dialog.
    
    Args:
        window (tk.Tk): The parent window.
        open_admin_window_callback (callable): Callback function to open admin window after login.
    """
    # Ensure parent isn't forced on top so modal can appear above it
    try:
        window.attributes('-topmost', False)
    except Exception:
        pass

    # write a tiny debug log so we can confirm the function was invoked
    try:
        with open('/tmp/login_debug.log', 'a') as f:
            f.write(f"open_login_page called at {time.time()}\n")
    except Exception:
        pass

    print("DEBUG: open_login_page called")
    login_page = tk.Toplevel(window)
    print("DEBUG: login_page Toplevel created")
    login_page.title("Login")
    # Configure size and ensure it appears above the parent.
    width, height = 360, 220
    login_page.resizable(False, False)
    login_page.transient(window)

    # Force geometry calculations and compute a safe centered position
    try:
        window.update_idletasks()
        screen_w = window.winfo_screenwidth()
        screen_h = window.winfo_screenheight()
        x = max(0, (screen_w - width) // 2)
        y = max(0, (screen_h - height) // 2)
        login_page.geometry(f"{width}x{height}+{x}+{y}")
    except Exception:
        # Fallback: let the window manager decide
        pass

    login_page.lift()
    try:
        # Make it topmost temporarily so it is visible above fullscreen parents
        login_page.attributes('-topmost', True)
    except Exception:
        pass

    tk.Label(login_page, text="User name:").pack(pady=5)
    username_entry = tk.Entry(login_page)
    username_entry.pack(pady=5)

    tk.Label(login_page, text="Password:").pack(pady=5)
    password_entry = tk.Entry(login_page, show="*")
    password_entry.pack(pady=5)

    tk.Button(login_page, text="Login", 
              command=lambda: verify_login(username_entry, password_entry, login_page, open_admin_window_callback)).pack(pady=10)
    
    login_page.bind("<Return>", lambda event: verify_login(username_entry, password_entry, login_page, open_admin_window_callback))

    try:
        login_page.wait_visibility()
        login_page.grab_set()
    except tk.TclError:
        pass
    login_page.focus_force()
    # Ensure the dialog stays above the parent while open
    try:
        login_page.attributes('-topmost', True)
    except Exception:
        pass

    window.wait_window(login_page)

    # Restore parent topmost attribute if needed
    try:
        window.attributes('-topmost', False)
    except Exception:
        pass


def verify_login(username_entry, password_entry, login_page, open_admin_window_callback, db_file='DB_FILE'):
    """
    Verify login credentials against the database.
    
    Args:
        username_entry (tk.Entry): The username entry widget.
        password_entry (tk.Entry): The password entry widget.
        login_page (tk.Toplevel): The login window.
        open_admin_window_callback (callable): Callback to open admin window.
        db_file (str): The database file path.
    """
    username = username_entry.get().strip()
    password = password_entry.get()

    if not username or not password:
        messagebox.showerror("Login Failed", "Please enter both username and password")
        return

    # Hash the entered password
    hashed_password = hash_password(password)

    try:
        # Connect to the database
        with sqlite3.connect(db_file) as conn:
            cursor = conn.cursor()
            # Retrieve the stored hashed password for the entered username
            cursor.execute("SELECT password FROM logusers WHERE username = ?", (username,))
            result = cursor.fetchone()

        # Check if the username exists and the hashed password matches
        if result and result[0] == hashed_password:
            login_page.destroy()
            open_admin_window_callback()
        else:
            messagebox.showerror("Login Failed", "Invalid username or password")

    except Exception as e:
        messagebox.showerror("Error", f"Database error: {e}")

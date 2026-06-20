"""
Admin window module for managing admin interface.
"""
import sqlite3
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
from utils import setup_placeholder, resource_path
from core import search_product, show_items_admin
from .user_management_ui import setup_tab2
from .product_manager_ui import setup_tab3


def open_admin_window(window, db_file='DB_FILE'):
    """
    Open the administrator window with tabs for History, User Management, and Product Manager.
    
    Args:
        window (tk.Tk): The parent window.
        db_file (str): The database file path.
    """
    admin_window = tk.Toplevel(window)
    admin_window.title("Administrator")
    admin_window.transient(window)
    admin_window.geometry(f"{window.winfo_screenwidth()}x{window.winfo_screenheight()}")

    # Dictionary to store images to prevent garbage collection
    image_references = {}

    # Create a notebook (tabs container)
    notebook = ttk.Notebook(admin_window)
    notebook.pack(expand=True, fill='both')

    # Tab 1: History
    tab1 = ttk.Frame(notebook)
    notebook.add(tab1, text="History")

    # Title label at the center
    title_label = tk.Label(tab1, text="HISTORY", font=("Arial", 15, "bold"))
    title_label.place(relx=0.5, rely=0.02, anchor="center")

    # Search frame
    search_frame = tk.Frame(tab1)
    search_frame.place(relx=0.95, rely=0.02, anchor="ne")

    # Create and layout widgets in the search frame
    entry_search = tk.Entry(search_frame, width=20)
    entry_search.grid(row=0, column=0, padx=5, pady=5)
    entry_search.placeholder = "Search"
    entry_search.bind("<Return>", lambda event: search_product(entry_search, tree, db_file=db_file))
    setup_placeholder(entry_search)

    # Load images and create buttons
    refresh_image = Image.open(resource_path("icons/reload.ico")).resize((15, 15))
    search_image = Image.open(resource_path("icons/search_icon.ico")).resize((15, 15))

    refresh_icon = ImageTk.PhotoImage(refresh_image)
    search_icon = ImageTk.PhotoImage(search_image)

    image_references["refresh_icon"] = refresh_icon
    image_references["search_icon"] = search_icon

    search_button = tk.Button(search_frame, image=search_icon, command=lambda: search_product(entry_search, tree, db_file=db_file))
    search_button.grid(row=0, column=2, padx=5, pady=5)

    refresh_history_button = tk.Button(search_frame, image=refresh_icon, command=lambda: show_items_admin(tree, db_file=db_file))
    refresh_history_button.grid(row=0, column=3, padx=5, pady=5)

    admin_window.bind("<F5>", lambda event: show_items_admin(tree, db_file=db_file))

    # Tree view frame
    tree_frame = tk.Frame(tab1)
    tree_frame.place(relx=0.5, rely=0.1, anchor="n", relwidth=1.0, relheight=0.85)

    columns = ("Product ID", "Product Name", "Check Out Time", "Check In Time", "User ID", "User Name")
    tree = ttk.Treeview(tree_frame, columns=columns, show='headings')

    column_widths = [80, 150, 120, 120, 80, 150]
    for col, width in zip(columns, column_widths):
        tree.heading(col, text=col)
        tree.column(col, anchor=tk.CENTER, width=width)

    scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=scrollbar.set)
    tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    # Prevent garbage collection by attaching the dictionary to the window
    admin_window.image_references = image_references

    def on_tab_selected(event):
        """Handle tab selection to load content."""
        selected_tab = event.widget.select()
        tab_index = notebook.index(selected_tab)

        if tab_index == 0:  # Only call for tab1 (History)
            show_items_admin(tree, db_file=db_file)

    notebook.bind("<<NotebookTabChanged>>", on_tab_selected)

    # Tab 2: User Management
    tab2 = ttk.Frame(notebook)
    notebook.add(tab2, text="User Management")
    setup_tab2(tab2, db_file=db_file)

    # Tab 3: Product Manager
    tab3 = ttk.Frame(notebook)
    notebook.add(tab3, text="Product Manager")
    setup_tab3(tab3, db_file=db_file)

    # Do not start a new mainloop for Toplevel windows; the application's
    # main `window.mainloop()` should drive the event loop. Starting a
    # nested mainloop can freeze or prevent other windows from showing.
    admin_window.focus_force()
    try:
        admin_window.attributes('-topmost', True)
    except Exception:
        pass

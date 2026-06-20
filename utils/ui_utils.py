"""
UI utilities module for handling common UI operations.
"""
import tkinter as tk
import sys
import os


def on_focus_in(entry):
    """
    Clear the placeholder text when the entry box gets focus.
    
    Args:
        entry (tk.Entry): The entry widget.
    """
    if entry.get() == entry.placeholder:
        entry.delete(0, tk.END)
        entry.config(fg='black')


def on_focus_out(entry):
    """
    Restore the placeholder text when the entry box loses focus.
    
    Args:
        entry (tk.Entry): The entry widget.
    """
    if entry.get() == "":
        entry.insert(0, entry.placeholder)
        entry.config(fg='gray')


def setup_placeholder(entry):
    """
    Setup placeholder functionality on an entry widget.
    
    Args:
        entry (tk.Entry): The entry widget to add placeholder functionality to.
    """
    entry.bind("<FocusIn>", lambda event: on_focus_in(entry))
    entry.bind("<FocusOut>", lambda event: on_focus_out(entry))


def resource_path(relative_path):
    """
    Get the absolute path to a resource, works for dev and PyInstaller.
    
    Args:
        relative_path (str): The relative path to the resource.
        
    Returns:
        str: The absolute path to the resource.
    """
    base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base_path, relative_path)

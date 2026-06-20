"""UI module package."""
from .admin_window import open_admin_window
from .user_management_ui import setup_tab2
from .product_manager_ui import setup_tab3

__all__ = [
    'open_admin_window',
    'setup_tab2',
    'setup_tab3'
]

"""
Entry point — launches the single-frame inventory management application.
"""
import os
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)
os.environ["QT_QPA_PLATFORM"] = "xcb"

from ui.app import InventoryApp

if __name__ == "__main__":
    app = InventoryApp()
    app.mainloop()

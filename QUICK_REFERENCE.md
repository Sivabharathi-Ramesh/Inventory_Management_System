# Quick Reference Guide - Module Organization

## 🎯 Quick Navigation

### I want to change **___**... where do I go?

| Task | Location | File |
|------|----------|------|
| Change **database schema** | `db/` | `database_init.py` |
| Add **new database query** | `db/` | `database_utils.py` |
| **Text-to-speech** output | `utils/` | `text_utils.py` |
| **QR code** scanning | `utils/` | `qr_utils.py` |
| **Face recognition** logic | `utils/` | `face_recognition_utils.py` |
| **Product check-in/out** logic | `core/` | `product_management.py` |
| **Login** system | `core/` | `login.py` |
| **Admin window** | `ui/` | `admin_window.py` |
| **User management** tab | `ui/` | `user_management_ui.py` |
| **Product manager** tab | `ui/` | `product_manager_ui.py` |
| **UI helpers** (placeholders, etc) | `utils/` | `ui_utils.py` |

---

## 📂 Folder Contents at a Glance

### **`db/` - Database Layer**
```
db/
├── __init__.py              # Exports: execute_query, fetch_user_data, ...
├── database_utils.py        # All DB operations (queries, user mgmt, hashing)
└── database_init.py         # Schema & table creation
```
👉 **Use when:** Working with data persistence, queries, schemas

---

### **`utils/` - Utility Functions**
```
utils/
├── __init__.py              # Exports: all utilities
├── ui_utils.py              # Placeholder, resource paths
├── text_utils.py            # Text-to-speech
├── qr_utils.py              # QR scanning & zoom
└── face_recognition_utils.py # Face detection & matching
```
👉 **Use when:** Need reusable functions (no business logic)

---

### **`core/` - Business Logic**
```
core/
├── __init__.py              # Exports: check_product, open_login_page, ...
├── product_management.py    # Check-in/out workflow, history
└── login.py                 # Authentication
```
👉 **Use when:** Implementing application workflows

---

### **`ui/` - User Interface**
```
ui/
├── __init__.py              # Exports: open_admin_window, setup_tab2, ...
├── admin_window.py          # Main window with tabs
├── user_management_ui.py    # User management tab
└── product_manager_ui.py    # Product manager tab
```
👉 **Use when:** Building or modifying GUI components

---

## 🔗 Import Patterns

### **From main.py:**
```python
from db import initialize_database
from utils import resource_path, text_to_speech
from core import check_product, show_items, open_login_page
from ui import open_admin_window
```

### **From core/product_management.py:**
```python
from ..utils import scan_qr_code, recognize_user, text_to_speech
from ..db import execute_query
# Note: `..` goes up one level to the project root
```

### **From ui/admin_window.py:**
```python
from ..utils import setup_placeholder, resource_path
from ..core import search_product, show_items_admin
from .user_management_ui import setup_tab2
from .product_manager_ui import setup_tab3
# Note: `..` goes to root, `.` stays in same folder
```

---

## 🧪 Testing Individual Modules

### Test QR scanning:
```python
from utils import scan_qr_code
result = scan_qr_code()
print(f"QR Data: {result}")
```

### Test face recognition:
```python
from utils import recognize_user, load_known_encodings
faces = load_known_encodings()
user = recognize_user()
```

### Test database:
```python
from db import execute_query, fetch_user_data
users = fetch_user_data()
print(users)
```

### Test product check:
```python
from core import check_product
check_product(tree_widget)
```

---

## 📋 Module Function Reference

### **`db/database_utils.py`**
- `execute_query(query, params, fetch, db_file)` - Generic query executor
- `fetch_user_data(db_file)` - Get all users
- `update_user_type(user_id, new_type, db_file)` - Change user level
- `remove_user(user_id, db_file)` - Delete user
- `hash_password(password)` - Hash a password

### **`db/database_init.py`**
- `initialize_database(db_file)` - Setup schema & tables

### **`utils/ui_utils.py`**
- `setup_placeholder(entry)` - Add placeholder to entry widget
- `resource_path(relative_path)` - Get PyInstaller-compatible path
- `on_focus_in(entry)` - Clear placeholder on focus
- `on_focus_out(entry)` - Restore placeholder on blur

### **`utils/text_utils.py`**
- `text_to_speech(text)` - Play audio feedback

### **`utils/qr_utils.py`**
- `scan_qr_code()` - Scan & decode QR (30s timeout)
- `zoom_in_on_qr_code(frame, points, zoom_factor)` - Zoom for small QR codes

### **`utils/face_recognition_utils.py`**
- `load_known_encodings(db_file)` - Load all face encodings
- `find_matching_face(known_encodings, test_encoding, tolerance)` - Match face
- `recognize_user(timeout, db_file)` - Recognize from webcam

### **`core/product_management.py`**
- `check_product(tree, db_file)` - Main check-in/out workflow
- `show_items(tree, db_file)` - Show today's history
- `show_items_admin(tree, db_file)` - Show all history
- `search_product(entry, tree, db_file)` - Search history
- `update_treeview(tree, items)` - Update tree display

### **`core/login.py`**
- `open_login_page(window, callback)` - Show login dialog
- `verify_login(username_entry, password_entry, login_page, callback, db_file)` - Verify creds

### **`ui/admin_window.py`**
- `open_admin_window(window, db_file)` - Main admin window

### **`ui/user_management_ui.py`**
- `setup_tab2(parent_window, db_file)` - Setup user management tab

### **`ui/product_manager_ui.py`**
- `setup_tab3(tab3, db_file)` - Setup product manager tab

---

## 🚀 Running the App

```bash
cd /path/to/inventory_management_stemland
python3 main.py
```

---

## 🔧 Troubleshooting

### **ImportError: No module named 'db'**
→ Make sure you're in the project root directory when running

### **ImportError: No module named 'PIL'**
→ Install: `pip3 install pillow opencv-python face-recognition numpy qrcode`

### **ModuleNotFoundError for relative imports**
→ Ensure all folders have `__init__.py` files ✓

---

## 📊 Layer Responsibilities

| Layer | Imports From | Responsibility |
|-------|--------------|-----------------|
| **UI** | Core, Utils | Display & user interaction |
| **Core** | Utils, DB | Business logic & workflows |
| **Utils** | External libs | Reusable functions only |
| **DB** | External libs | Data storage & retrieval |

**Golden Rule:** Dependencies flow DOWN only. Never UP. ✅

---

## ✨ Benefits Summary

- ✅ **Clear organization** - Know where to find anything
- ✅ **Easy maintenance** - Isolated modules are easier to fix
- ✅ **Testable** - Each module can be tested independently
- ✅ **Reusable** - Utils can be used in other projects
- ✅ **Scalable** - Add features without touching old code
- ✅ **Professional** - Industry-standard architecture

---

For detailed information, see **`STRUCTURE.md`** 📚

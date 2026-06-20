# Modular Project Structure - Organized by Category

The application has been reorganized into **4 main folder categories** for better organization and maintainability.

## 📁 Project Structure

```
inventory_management_stemland/
├── main.py                          # 🎯 Application entry point
│
├── db/                              # 💾 Database Layer
│   ├── __init__.py                 # Package exports
│   ├── database_utils.py           # Database operations (CRUD)
│   └── database_init.py            # Database schema initialization
│
├── utils/                           # 🛠️ Utility Functions
│   ├── __init__.py                 # Package exports
│   ├── ui_utils.py                 # UI helpers (placeholders, resource paths)
│   ├── text_utils.py               # Text-to-speech functionality
│   ├── qr_utils.py                 # QR code scanning & processing
│   └── face_recognition_utils.py   # Face detection & matching
│
├── core/                            # 🧠 Business Logic
│   ├── __init__.py                 # Package exports
│   ├── product_management.py       # Check-in/check-out workflow
│   └── login.py                    # Authentication system
│
├── ui/                              # 🖥️ User Interface
│   ├── __init__.py                 # Package exports
│   ├── admin_window.py             # Main admin window (tabs container)
│   ├── user_management_ui.py       # User management tab (Tab 2)
│   └── product_manager_ui.py       # Product manager tab (Tab 3)
│
├── icons/                           # 🎨 Images & Icons
│   ├── admin_icon.ico
│   ├── reload.ico
│   └── search_icon.ico
│
├── DB_FILE                          # 📊 SQLite Database
├── haarcascade_*.xml                # Face detection cascades
├── README.md                        # Original documentation
├── MODULES.md                       # Old modular structure doc
├── STRUCTURE.md                     # This file
└── check_out_check_in_2_2.py        # Original monolithic version (backup)
```

---

## 📋 Module Categories

### **1. 💾 Database Layer (`db/`)**

Handles all database operations. Isolated from UI and business logic.

| File | Purpose |
|------|---------|
| `database_utils.py` | CRUD operations, queries, password hashing |
| `database_init.py` | Schema setup, table/view creation |

**Key Functions:**
- `execute_query()` - Generic query executor
- `fetch_user_data()`, `update_user_type()`, `remove_user()` - User operations
- `hash_password()` - Password encryption
- `initialize_database()` - Schema initialization

---

### **2. 🛠️ Utilities Layer (`utils/`)**

Reusable utility functions used across the application. **Zero business logic.**

| File | Purpose |
|------|---------|
| `ui_utils.py` | Placeholder handling, resource paths (PyInstaller compatible) |
| `text_utils.py` | Text-to-speech audio output |
| `qr_utils.py` | QR code scanning with zoom capability |
| `face_recognition_utils.py` | Face encoding, matching, user recognition |

**Key Functions:**
- `setup_placeholder()` - UI placeholder management
- `text_to_speech()` - Audio feedback
- `scan_qr_code()` - QR detection & decoding
- `recognize_user()`, `find_matching_face()` - Face recognition

---

### **3. 🧠 Business Logic Layer (`core/`)**

Application workflow and business rules. Uses utilities and database layers.

| File | Purpose |
|------|---------|
| `product_management.py` | Check-in/check-out workflow, product history |
| `login.py` | Authentication & credential verification |

**Key Functions:**
- `check_product()` - Main workflow: scan QR → recognize user → check-in/out
- `show_items()`, `show_items_admin()` - Product history display
- `search_product()` - History search functionality
- `open_login_page()`, `verify_login()` - Authentication

---

### **4. 🖥️ User Interface Layer (`ui/`)**

GUI components. Uses business logic and utilities. **No direct database access.**

| File | Purpose |
|------|---------|
| `admin_window.py` | Main admin window controller, tabs setup |
| `user_management_ui.py` | User management tab (add/remove/promote) |
| `product_manager_ui.py` | Product manager tab (add/modify/QR codes) |

**Components:**
- `admin_window.py` creates 3 tabs:
  - **Tab 1: History** - View all product movements
  - **Tab 2: User Management** - Manage system users
  - **Tab 3: Product Manager** - Manage inventory & QR codes

---

## 🔄 Dependency Flow (Unidirectional)

```
┌─────────────────────────────────────────────┐
│  UI Layer (User Interfaces)                 │
│  admin_window.py                            │
│  user_management_ui.py                      │
│  product_manager_ui.py                      │
└──────────────────┬──────────────────────────┘
                   │ imports from
┌──────────────────▼──────────────────────────┐
│  Core Layer (Business Logic)                │
│  product_management.py                      │
│  login.py                                   │
└──────────────────┬──────────────────────────┘
                   │ imports from
┌──────────────────┼──────────────────────────┐
│  ├─ Utils Layer (Reusable Functions)        │
│  │  ├─ ui_utils.py                          │
│  │  ├─ text_utils.py                        │
│  │  ├─ qr_utils.py                          │
│  │  └─ face_recognition_utils.py            │
│  │                                          │
│  └─ DB Layer (Data Access)                  │
│     ├─ database_utils.py                    │
│     └─ database_init.py                     │
└─────────────────────────────────────────────┘
        External Libraries (CV2, Face, etc.)
```

**✅ Rule:** Imports only flow downward. No circular dependencies.

---

## 🚀 Running the Application

```bash
# From the project root directory
python3 main.py
```

**main.py** orchestrates everything:
1. ✅ Imports from organized modules
2. ✅ Initializes database
3. ✅ Sets up main GUI window
4. ✅ Binds keyboard shortcuts

---

## 🔧 Using the Modules

### **Example 1: Use QR Scanner**
```python
from utils import scan_qr_code
qr_data = scan_qr_code()
print(f"Scanned: {qr_data}")
```

### **Example 2: Use Face Recognition**
```python
from utils import recognize_user, load_known_encodings
known_faces = load_known_encodings()
user_id, user_name = recognize_user()
```

### **Example 3: Use Database**
```python
from db import execute_query, fetch_user_data
users = fetch_user_data()
execute_query("UPDATE users SET type = ? WHERE user_id = ?", ("Admin", 1))
```

### **Example 4: Check Product**
```python
from core import check_product
check_product(tree_widget)  # Handles full workflow
```

---

## 📊 Module Statistics

| Category | Modules | Files | Purpose |
|----------|---------|-------|---------|
| DB | Database Operations | 2 | Data persistence & queries |
| Utils | Utilities | 4 | Reusable functions |
| Core | Business Logic | 2 | Application workflows |
| UI | User Interfaces | 3 | GUI components |
| **Total** | - | **11** | Complete application |

---

## ✨ Benefits of This Structure

| Benefit | Why It Matters |
|---------|----------------|
| **Clear Separation** | Each layer has one job, easy to understand |
| **Reusability** | Utils can be used in other projects |
| **Testability** | Each module can be tested independently |
| **Maintainability** | Bug fixes are localized, easier to debug |
| **Scalability** | Adding features doesn't require rewriting |
| **Collaboration** | Team members can work on different modules |

---

## 🔗 Import Examples from Each Layer

### **From main.py (Entry Point):**
```python
from db import initialize_database
from utils import resource_path, text_to_speech
from core import check_product, show_items, open_login_page
from ui import open_admin_window
```

### **From core modules:**
```python
# product_management.py imports from:
from ..utils import scan_qr_code, recognize_user, text_to_speech
from ..db import execute_query

# login.py imports from:
from ..db import hash_password
```

### **From ui modules:**
```python
# admin_window.py imports from:
from ..utils import setup_placeholder, resource_path
from ..core import search_product, show_items_admin
from .user_management_ui import setup_tab2
from .product_manager_ui import setup_tab3
```

---

## 📝 Adding New Features

### **Add a new recognition method?**
→ Create `new_recognition.py` in `utils/`

### **Add a new tab to admin?**
→ Create `new_tab_ui.py` in `ui/` and import in `admin_window.py`

### **Add a new database table?**
→ Update `db/database_init.py` and add utility functions in `db/database_utils.py`

---

## 🎯 Summary

The modular structure organizes code by **responsibility and category**:

- **`db/`** → How to get/store data
- **`utils/`** → Reusable tools
- **`core/`** → What the app does
- **`ui/`** → How users interact with it

This makes the codebase **maintainable, scalable, and professional**. 🚀

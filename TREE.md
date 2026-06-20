# Project Structure Visualization

## 📂 Complete Directory Tree

```
inventory_management_stemland/
│
├── 🎯 main.py                          ← Application entry point
│
├── 📁 db/                              ← Database Layer (💾 Data Access)
│   ├── __init__.py
│   ├── database_utils.py               • CRUD operations
│   └── database_init.py                • Schema setup
│
├── 📁 utils/                           ← Utilities Layer (🛠️ Reusable Functions)
│   ├── __init__.py
│   ├── ui_utils.py                     • Placeholder handling
│   ├── text_utils.py                   • Text-to-speech
│   ├── qr_utils.py                     • QR scanning
│   └── face_recognition_utils.py       • Face detection
│
├── 📁 core/                            ← Business Logic Layer (🧠 Workflows)
│   ├── __init__.py
│   ├── product_management.py           • Check-in/out logic
│   └── login.py                        • Authentication
│
├── 📁 ui/                              ← UI Layer (🖥️ User Interfaces)
│   ├── __init__.py
│   ├── admin_window.py                 • Main admin window
│   ├── user_management_ui.py           • User management tab
│   └── product_manager_ui.py           • Product manager tab
│
├── 📁 icons/                           ← Images & Assets
│   ├── admin_icon.ico
│   ├── reload.ico
│   └── search_icon.ico
│
├── 📊 DB_FILE                          ← SQLite Database
│
├── 📚 Documentation Files:
│   ├── README.md                       • Original project docs
│   ├── STRUCTURE.md                    • Detailed structure guide
│   ├── QUICK_REFERENCE.md              • Quick navigation guide
│   ├── MODULES.md                      • Old module documentation
│   └── TREE.md                         ← This file
│
├── 🔧 Configuration:
│   ├── Makefile
│   ├── haarcascade_eye.xml
│   ├── haarcascade_frontalface_default.xml
│   └── .gitignore
│
├── 🗂️ Legacy Files (Original):
│   └── check_out_check_in_2_2.py       • Original monolithic file (backup)
│
└── 📁 .git/ & .vscode/                 ← Git & VS Code config
```

---

## 🔗 Layer Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                  main.py (Entry Point)                      │
│                   Orchestrator Layer                        │
└────────────────────┬────────────────────────────────────────┘
                     │
         ┌───────────┼───────────┐
         │           │           │
         ▼           ▼           ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│ 🖥️ UI Layer  │  │🧠Core Layer  │  │💾 DB Layer   │
│   (ui/)      │  │  (core/)     │  │   (db/)      │
└──────────────┘  └──────────────┘  └──────────────┘
         │               │                  │
         └───────────────┼──────────────────┘
                         │
                         ▼
         ┌──────────────────────────────┐
         │  🛠️ Utils Layer (utils/)      │
         │  • ui_utils.py               │
         │  • text_utils.py             │
         │  • qr_utils.py               │
         │  • face_recognition_utils.py │
         └──────────────────────────────┘
                         │
                         ▼
         ┌──────────────────────────────┐
         │  External Libraries          │
         │  • OpenCV (cv2)              │
         │  • face_recognition          │
         │  • numpy, qrcode, PIL        │
         └──────────────────────────────┘
```

---

## 📊 File Organization Summary

| Layer | Folder | Files | Lines | Purpose |
|-------|--------|-------|-------|---------|
| **Entry** | - | main.py | ~70 | Orchestrates entire app |
| **DB** | `db/` | 2 files | ~150 | Data persistence |
| **Utils** | `utils/` | 4 files | ~400 | Reusable functions |
| **Core** | `core/` | 2 files | ~200 | Business logic |
| **UI** | `ui/` | 3 files | ~500 | User interfaces |
| **Total** | - | **12 files** | **~1,320** | Complete app |

---

## 🔄 Import Flow Diagram

```
┌──────────────────────────────────────────────────────┐
│ main.py                                              │
│ ↓ imports                                            │
│ • from db import initialize_database                 │
│ • from utils import resource_path, text_to_speech    │
│ • from core import check_product, show_items         │
│ • from ui import open_admin_window                   │
└──────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────┐
│ core/product_management.py                           │
│ ↓ imports                                            │
│ • from utils import scan_qr_code, recognize_user    │
└──────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────┐
│ ui/admin_window.py                                   │
│ ↓ imports                                            │
│ • from utils import setup_placeholder, resource_path│
│ • from core import search_product, show_items_admin  │
│ • from .user_management_ui import setup_tab2         │
│ • from .product_manager_ui import setup_tab3         │
└──────────────────────────────────────────────────────┘

✓ Rule: Dependencies flow DOWNWARD ONLY
✓ No circular dependencies
✓ Clear separation of concerns
```

---

## 📦 Package Exports (__init__.py Files)

### **db/__init__.py**
```python
Exports:
- execute_query
- fetch_user_data
- update_user_type
- remove_user
- hash_password
- initialize_database
```

### **utils/__init__.py**
```python
Exports:
- setup_placeholder
- resource_path
- text_to_speech
- scan_qr_code
- zoom_in_on_qr_code
- load_known_encodings
- find_matching_face
- recognize_user
```

### **core/__init__.py**
```python
Exports:
- search_product
- update_treeview
- show_items_admin
- show_items
- check_product
- open_login_page
- verify_login
```

### **ui/__init__.py**
```python
Exports:
- open_admin_window
- setup_tab2
- setup_tab3
```

---

## 🚀 Running the Application

```bash
# From project root
python3 main.py

# Logs
# → Initializes database
# → Creates main window
# → Ready for QR scanning
```

---

## 🎯 Module Dependencies (What imports What)

```
main.py
├─ db.initialize_database
├─ utils.resource_path
├─ utils.text_to_speech
├─ core.check_product
├─ core.show_items
├─ core.open_login_page
└─ ui.open_admin_window

core/product_management.py
├─ utils.scan_qr_code
├─ utils.recognize_user
└─ utils.text_to_speech

core/login.py
└─ db.hash_password

ui/admin_window.py
├─ utils.setup_placeholder
├─ utils.resource_path
├─ core.search_product
├─ core.show_items_admin
├─ ui.user_management_ui
└─ ui.product_manager_ui

ui/user_management_ui.py
├─ db.execute_query
├─ db.fetch_user_data
├─ db.update_user_type
├─ db.remove_user
├─ utils.setup_placeholder
├─ utils.text_to_speech
├─ utils.load_known_encodings
└─ utils.find_matching_face

ui/product_manager_ui.py
└─ (Standard libraries only)

db/database_init.py
└─ db.hash_password
```

---

## ✨ Key Features of This Structure

| Feature | Benefit | Example |
|---------|---------|---------|
| **Layered** | Clear responsibility | UI doesn't access DB directly |
| **Modular** | Easy to maintain | Change QR logic in one file |
| **Testable** | Unit tests possible | Import & test each module |
| **Reusable** | Functions available elsewhere | Use utils in new project |
| **Scalable** | Easy to add features | New tab = new file in ui/ |
| **Professional** | Industry standard | Used by major projects |

---

## 📚 Documentation Hierarchy

1. **This file (TREE.md)** ← Visual structure overview
2. **STRUCTURE.md** ← Detailed structure guide & examples
3. **QUICK_REFERENCE.md** ← Quick lookup for file locations
4. **MODULES.md** ← Original modular architecture docs

---

## 🔍 Finding Things

| Looking for... | Go to... |
|---|---|
| Entry point | `main.py` |
| Database operations | `db/` folder |
| QR scanning | `utils/qr_utils.py` |
| Face recognition | `utils/face_recognition_utils.py` |
| Check-in/out logic | `core/product_management.py` |
| Admin window | `ui/admin_window.py` |
| User management | `ui/user_management_ui.py` |
| Product manager | `ui/product_manager_ui.py` |

---

**Generated:** 28 April 2026  
**Status:** ✅ Complete & Functional  
**Version:** 2.0 (Modular)

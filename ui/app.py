"""
Single-frame inventory management application.
All navigation happens inside the same window — no Toplevel popups.
"""
import os
import pickle
import sqlite3
import threading
import time
from datetime import datetime
import warnings
import tkinter as tk
from tkinter import ttk, messagebox

import cv2
import numpy as np
from PIL import Image, ImageTk
from utils.face_recognition_utils import (
    detect_faces, faces_to_locations, get_face_embedding,
    VERIFY_THRESHOLD, ENROLL_THRESHOLD, check_liveness,
)

from db import initialize_database, execute_query, fetch_user_data, update_user_type, remove_user, hash_password
from utils import resource_path, text_to_speech, setup_placeholder
from utils import load_known_encodings as get_known_encodings
from utils import find_matching_face
from core import show_items, show_items_admin, search_product

warnings.filterwarnings("ignore")

DB_FILE = "DB_FILE"
CAMERA_INDEX = 1          # default: prefer USB webcam (index 1)
PREVIEW_W, PREVIEW_H = 640, 480   # inline camera preview size

# On Windows use DirectShow backend (faster open, avoids MSMF hangs)
_CAM_BACKEND = cv2.CAP_DSHOW if os.name == "nt" else cv2.CAP_ANY

# Runtime-selected camera index (changed via admin camera selector)
_active_camera_index = CAMERA_INDEX


def _open_camera(index):
    """Open camera with platform-appropriate backend, fall back to index 0."""
    cap = cv2.VideoCapture(index, _CAM_BACKEND)
    if not cap.isOpened() and index != 0:
        cap = cv2.VideoCapture(0, _CAM_BACKEND)
    return cap


def _detect_cameras(max_test=10):
    """
    Return list of (index, label) for all cameras found.
    Filters out phantom/metadata nodes by checking Linux sysfs, 
    and reads the actual device name for the dropdown.
    """
    found = []
    for i in range(max_test):
        sys_name = ""
        # On Linux, skip metadata nodes (index > 0) to prevent duplicate/phantom cameras
        if os.name == "posix":
            index_file = f"/sys/class/video4linux/video{i}/index"
            name_file = f"/sys/class/video4linux/video{i}/name"
            if os.path.exists(index_file):
                try:
                    with open(index_file, "r") as f:
                        if f.read().strip() != "0":
                            continue  # Skip metadata/IR nodes
                except Exception:
                    pass
            if os.path.exists(name_file):
                try:
                    with open(name_file, "r") as f:
                        sys_name = f.read().strip()
                except Exception:
                    pass

        cap = cv2.VideoCapture(i, _CAM_BACKEND)
        if cap.isOpened():
            # Test if it can actually read a frame
            ret, frame = cap.read()
            if ret and frame is not None:
                found.append((i, sys_name))
            cap.release()

    if not found:
        return [(0, "Camera 0 (default)")]

    labels = []
    for i, sys_name in found:
        if sys_name:
            label = f"Camera {i} ({sys_name})"
        elif i == 0:
            label = f"Camera {i} (Built-in)"
        else:
            label = f"Camera {i} (USB Webcam)"
        labels.append((i, label))

    # Put USB cameras first (higher index = likely USB)
    labels.sort(key=lambda x: -x[0])
    return labels

# ─── Themes ──────────────────────────────────────────────────────────────────

THEMES = {
    "AIAT": {                          # aiat.edu.in brand colours
        "sidebar_bg":     "#021e5a",   # dark navy
        "sidebar_fg":     "#ffffff",
        "sidebar_active": "#ea5532",   # orange-red accent
        "sidebar_hover":  "#ea5532",
        "sidebar_sub_bg": "#05164d",   # deeper navy for admin sub-items
        "logo_fg":        "#a4d65e",   # lime green
        "logo_sub_fg":    "#ffbc23",   # golden yellow
        "content_bg":     "#f9f9f9",
        "header_fg":      "#021e5a",
        "btn_primary":    "#ea5532",
        "btn_primary_fg": "#ffffff",
        "btn_secondary":  "#021e5a",
        "btn_secondary_fg":"#ffffff",
        "btn_danger":     "#c0392b",
        "btn_warning":    "#ffbc23",
        "btn_warning_fg": "#021e5a",
        "status_ok":      "#568c11",
        "status_err":     "#ea5532",
        "status_info":    "#021e5a",
        "cam_bg":         "#05164d",
    },
    "Dark": {
        "sidebar_bg":     "#0f172a",
        "sidebar_fg":     "#f8fafc",
        "sidebar_active": "#3b82f6",
        "sidebar_hover":  "#3b82f6",
        "sidebar_sub_bg": "#1e293b",
        "logo_fg":        "#38bdf8",
        "logo_sub_fg":    "#94a3b8",
        "content_bg":     "#020617",
        "header_fg":      "#f8fafc",
        "btn_primary":    "#3b82f6",
        "btn_primary_fg": "#ffffff",
        "btn_secondary":  "#334155",
        "btn_secondary_fg":"#ffffff",
        "btn_danger":     "#ef4444",
        "btn_warning":    "#f59e0b",
        "btn_warning_fg": "#ffffff",
        "status_ok":      "#10b981",
        "status_err":     "#ef4444",
        "status_info":    "#3b82f6",
        "cam_bg":         "#0f172a",
    },
    "Light": {
        "sidebar_bg":     "#f8fafc",
        "sidebar_fg":     "#334155",
        "sidebar_active": "#2563eb",
        "sidebar_hover":  "#2563eb",
        "sidebar_sub_bg": "#f1f5f9",
        "logo_fg":        "#0f172a",
        "logo_sub_fg":    "#64748b",
        "content_bg":     "#ffffff",
        "header_fg":      "#0f172a",
        "btn_primary":    "#2563eb",
        "btn_primary_fg": "#ffffff",
        "btn_secondary":  "#e2e8f0",
        "btn_secondary_fg":"#334155",
        "btn_danger":     "#ef4444",
        "btn_warning":    "#f59e0b",
        "btn_warning_fg": "#ffffff",
        "status_ok":      "#10b981",
        "status_err":     "#ef4444",
        "status_info":    "#2563eb",
        "cam_bg":         "#f1f5f9",
    },
}

_current_theme: dict = THEMES["AIAT"]   # default

def get_theme() -> dict:
    return _current_theme

def set_theme(name: str):
    global _current_theme
    _current_theme = THEMES.get(name, THEMES["AIAT"])

# ─── helpers ────────────────────────────────────────────────────────────────

_camera_resource_lock = threading.Lock()

class _CameraThread(threading.Thread):
    """
    Long-lived background thread: one camera open for the whole scan session.
    The processing function can be swapped at any time via set_process_fn()
    without closing/reopening the camera device.
    """
    def __init__(self, camera_index, process_fn, process_every=3):
        super().__init__(daemon=True)
        self._idx       = camera_index
        self._lock      = threading.Lock()
        self._proc      = process_fn
        self._every     = process_every
        self._display   = None   # latest annotated BGR ready to show
        self._result    = None   # latest non-None result from process_fn
        self._stop_evt  = threading.Event()

    def set_process_fn(self, fn, process_every=3):
        """Swap the processing function while keeping the camera open."""
        with self._lock:
            self._proc   = fn
            self._every  = process_every
            self._result = None   # clear stale results from previous mode

    def run(self):
        with _camera_resource_lock:
            cap = _open_camera(self._idx)
            if not cap.isOpened():
                return
            cap.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            cap.set(cv2.CAP_PROP_FPS, 30)
            # Minimise queued buffers so thread exits cleanly within 1 frame
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            n = 0
            try:
                while not self._stop_evt.is_set():
                    ret, frame = cap.read()
                    if not ret:
                        break
                    frame = cv2.flip(frame, 1)
                    n += 1
                    with self._lock:
                        proc  = self._proc
                        every = self._every
                    if n % every == 0:
                        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                        annotated, result = proc(rgb, frame.copy())
                        with self._lock:
                            self._display = annotated
                            if result is not None:
                                self._result = result
                    else:
                        with self._lock:
                            if self._display is None:
                                self._display = frame
            finally:
                cap.release()

    def latest_display(self):
        with self._lock:
            return self._display

    def pop_result(self):
        with self._lock:
            r, self._result = self._result, None
            return r

    def stop(self):
        self._stop_evt.set()

def _frame_to_photoimage(frame, w=PREVIEW_W, h=PREVIEW_H):
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    img = Image.fromarray(rgb)
    img.thumbnail((w, h))
    return ImageTk.PhotoImage(img)


# Optimal face-height ratio range (face height / frame height)
_DIST_MIN = 0.20   # too far below this
_DIST_MAX = 0.65   # too close above this


def _draw_distance_guide(bgr, locs):
    """
    Overlay distance guidance on *bgr* (in-place) based on detected face size.
    Returns (bgr, hint_str, color_bgr) so the UI status label can be updated.
    """
    h, w = bgr.shape[:2]

    # ── guide oval in centre ──
    cx, cy = w // 2, int(h * 0.45)
    ow, oh = int(w * 0.18), int(h * 0.40)
    cv2.ellipse(bgr, (cx, cy), (ow, oh), 0, 0, 360, (200, 200, 200), 2)

    if not locs:
        cv2.putText(bgr, "No face detected", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.75, (80, 80, 255), 2)
        return bgr, "No face detected — align your face with the oval", (80, 80, 255)

    # Use the largest face
    top, right, bottom, left = max(locs, key=lambda l: (l[2]-l[0]) * (l[1]-l[3]))
    face_h = (bottom - top) / h
    face_cx = (left + right) // 2
    face_cy = (top + bottom) // 2

    # ── distance assessment ──
    if face_h < _DIST_MIN:
        hint  = "Move CLOSER to the camera"
        color = (0, 80, 255)    # red-ish (BGR)
        arrow = "▲▲  CLOSER"
    elif face_h > _DIST_MAX:
        hint  = "Move BACK from the camera"
        color = (0, 180, 255)   # orange (BGR)
        arrow = "▼▼  BACK"
    else:
        # Good range — score within range for a finer bar
        ratio  = (face_h - _DIST_MIN) / (_DIST_MAX - _DIST_MIN)   # 0..1
        # Ideal is the middle 40–60 % of the range
        if 0.3 <= ratio <= 0.7:
            hint  = "Perfect distance — hold still"
            color = (50, 200, 50)   # green
            arrow = "✓  PERFECT"
        else:
            hint  = "Almost there — adjust slightly"
            color = (50, 200, 200)  # yellow-green
            arrow = "~  ADJUST"

    # ── face bounding box ──
    cv2.rectangle(bgr, (left, top), (right, bottom), color, 2)

    # ── distance bar (right edge) ──
    bar_x = w - 22
    bar_y0, bar_y1 = int(h * 0.1), int(h * 0.9)
    bar_h = bar_y1 - bar_y0
    cv2.rectangle(bgr, (bar_x, bar_y0), (bar_x + 14, bar_y1), (50, 50, 50), -1)
    fill = int(bar_h * min(face_h / _DIST_MAX, 1.0))
    cv2.rectangle(bgr, (bar_x, bar_y1 - fill), (bar_x + 14, bar_y1), color, -1)
    cv2.putText(bgr, "D", (bar_x - 2, bar_y0 - 6),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1)

    # ── hint text ──
    (tw, _), _ = cv2.getTextSize(arrow, cv2.FONT_HERSHEY_SIMPLEX, 0.75, 2)
    cv2.rectangle(bgr, (8, 8), (tw + 20, 38), (0, 0, 0), -1)
    cv2.putText(bgr, arrow, (12, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.75, color, 2)

    return bgr, hint, color

# ─── Custom Search Widget ───────────────────────────────────────────────────

class SearchEntry(tk.Frame):
    """
    A professional, modern search entry with an integrated magnifying glass icon,
    placeholder text, and a clear button (✕) that appears dynamically.
    """
    def __init__(self, parent, placeholder="Search...", command=None, textvariable=None, entry_width=20, **kwargs):
        super().__init__(parent, **kwargs)
        self.placeholder = placeholder
        self.command = command
        
        self.var = textvariable if textvariable is not None else tk.StringVar()
        self._internal_var = tk.StringVar()
        self._updating = False
        
        self.border_frame = tk.Frame(self)
        self.border_frame.pack(fill="both", expand=True)
        
        self.inner_frame = tk.Frame(self.border_frame)
        self.inner_frame.pack(fill="both", expand=True, padx=1, pady=1)
        
        self.icon_label = tk.Label(self.inner_frame, text="🔍", font=("Arial", 10))
        self.icon_label.pack(side="left", padx=(6, 2))
        
        self.entry = tk.Entry(self.inner_frame, textvariable=self._internal_var, relief=tk.FLAT, bd=0, font=("Arial", 10), width=entry_width)
        self.entry.pack(side="left", fill="both", expand=True, padx=4, pady=3)
        
        self.clear_btn = tk.Label(self.inner_frame, text="✕", font=("Arial", 9, "bold"), cursor="hand2")
        self.clear_btn.bind("<Button-1>", lambda e: self.clear())
        
        self.entry.bind("<FocusIn>", self._on_focus_in)
        self.entry.bind("<FocusOut>", self._on_focus_out)
        
        if self.command:
            self.entry.bind("<Return>", lambda e: self.command())
            self.icon_label.bind("<Button-1>", lambda e: self.command())
            
        self.showing_placeholder = False
        
        self._trace_internal_id = self._internal_var.trace_add("write", self._on_internal_write)
        self._trace_external_id = self.var.trace_add("write", self._on_external_write)
        
        val = self.var.get()
        if val:
            self._internal_var.set(val)
        else:
            self._show_placeholder()
            
        self.apply_theme()

    def _show_placeholder(self):
        self.showing_placeholder = True
        self._internal_var.set(self.placeholder)
        t = get_theme()
        is_dark = (t.get("content_bg", "#ffffff") in ("#020617", "#0f172a"))
        placeholder_color = "#64748b" if is_dark else "#94a3b8"
        self.entry.config(fg=placeholder_color)
        self.clear_btn.pack_forget()

    def _hide_placeholder(self):
        self.showing_placeholder = False
        self._internal_var.set("")
        t = get_theme()
        text_color = t.get("header_fg", "#000000")
        self.entry.config(fg=text_color)

    def _on_focus_in(self, event):
        self.border_frame.config(bg=self.border_focus)
        if self.showing_placeholder:
            self._hide_placeholder()

    def _on_focus_out(self, event):
        self.border_frame.config(bg=self.border_normal)
        if not self._internal_var.get().strip():
            self._show_placeholder()

    def _on_internal_write(self, *args):
        if self._updating:
            return
        self._updating = True
        try:
            val = self._internal_var.get()
            if self.showing_placeholder:
                self.var.set("")
            else:
                self.var.set(val)
                if val.strip():
                    self.clear_btn.pack(side="right", padx=(2, 6))
                else:
                    self.clear_btn.pack_forget()
        finally:
            self._updating = False

    def _on_external_write(self, *args):
        if self._updating:
            return
        self._updating = True
        try:
            val = self.var.get()
            if not val:
                if self.focus_get() != self.entry:
                    self._show_placeholder()
                else:
                    self._internal_var.set("")
                    self.showing_placeholder = False
                    self.clear_btn.pack_forget()
            else:
                self.showing_placeholder = False
                self._internal_var.set(val)
                t = get_theme()
                text_color = t.get("header_fg", "#000000")
                self.entry.config(fg=text_color)
                self.clear_btn.pack(side="right", padx=(2, 6))
        finally:
            self._updating = False

    def get(self):
        if self.showing_placeholder:
            return ""
        return self._internal_var.get()

    def set(self, val):
        self.var.set(val)

    def clear(self, trigger_command=True):
        self.var.set("")
        if not trigger_command:
            orig_command = self.command
            self.command = None
            try:
                if self.focus_get() != self.entry:
                    self._show_placeholder()
                else:
                    self._internal_var.set("")
                    self.showing_placeholder = False
                    self.clear_btn.pack_forget()
            finally:
                self.command = orig_command
        else:
            if self.focus_get() != self.entry:
                self._show_placeholder()
            else:
                self._internal_var.set("")
                self.showing_placeholder = False
                self.clear_btn.pack_forget()
            if self.command:
                self.command()

    def apply_theme(self):
        t = get_theme()
        is_dark = (t.get("content_bg", "#ffffff") in ("#020617", "#0f172a"))
        
        self.config(bg=t["content_bg"])
        self.bg_color = "#0f172a" if is_dark else "#ffffff"
        self.text_color = t.get("header_fg", "#000000")
        
        self.border_normal = "#334155" if is_dark else "#cbd5e1"
        self.border_focus = t.get("btn_primary", "#3b82f6")
        
        self.icon_color = "#94a3b8" if is_dark else "#64748b"
        self.clear_color = "#64748b" if is_dark else "#94a3b8"
        self.clear_hover_color = "#ef4444"
        
        self.border_frame.config(bg=self.border_normal)
        self.inner_frame.config(bg=self.bg_color)
        self.icon_label.config(bg=self.bg_color, fg=self.icon_color)
        self.entry.config(bg=self.bg_color, insertbackground=self.text_color)
        self.clear_btn.config(bg=self.bg_color, fg=self.clear_color)
        
        if self.showing_placeholder:
            placeholder_color = "#64748b" if is_dark else "#94a3b8"
            self.entry.config(fg=placeholder_color)
        else:
            self.entry.config(fg=self.text_color)
            
        self.clear_btn.bind("<Enter>", lambda e: self.clear_btn.config(fg=self.clear_hover_color))
        self.clear_btn.bind("<Leave>", lambda e: self.clear_btn.config(fg=self.clear_color))


# ─── Base page ───────────────────────────────────────────────────────────────

class Page(tk.Frame):
    """Base class for all pages."""
    def on_show(self):
        """Called every time this page becomes visible."""
    def on_hide(self):
        """Called every time this page is hidden (stop cameras etc.)."""


# ─── Sidebar ─────────────────────────────────────────────────────────────────

class Sidebar(tk.Frame):
    _ADMIN_PAGES = ("admin_history", "user_management", "product_manager", "analytics")

    def __init__(self, parent, show_page_cb, **kw):
        t = get_theme()
        super().__init__(parent, bg=t["sidebar_bg"], width=190, **kw)
        self.pack_propagate(False)
        self._show = show_page_cb
        self._btns = {}
        self._admin_visible = False

        self._logo  = tk.Label(self, text="STEMLAND", font=("Arial", 13, "bold"))
        self._logo.pack(pady=(20, 2))
        self._sub   = tk.Label(self, text="Inventory", font=("Arial", 9))
        self._sub.pack(pady=(0, 16))

        ttk.Separator(self, orient="horizontal").pack(fill="x", padx=10)
        self._add_btn("🏠  Home", "home")
        ttk.Separator(self, orient="horizontal").pack(fill="x", padx=10, pady=6)

        self._admin_label = tk.Label(self, text="ADMIN", font=("Arial", 8, "bold"))
        self._add_btn("🔐  Admin Login", "login")

        self._admin_btns_frame = tk.Frame(self)

        def _admin_btn(text, page):
            b = tk.Button(self._admin_btns_frame, text=text,
                          relief=tk.FLAT, font=("Arial", 10), anchor="w", padx=20,
                          command=lambda p=page: self._show(p))
            b.pack(fill="x", pady=1)
            self._btns[page] = b

        _admin_btn("  📋  History",  "admin_history")
        _admin_btn("  👤  Users",    "user_management")
        _admin_btn("  📦  Products", "product_manager")
        _admin_btn("  📊  Analytics", "analytics")

        self._logout_btn = tk.Button(self, text="🚪  Logout",
                                     relief=tk.FLAT, font=("Arial", 10),
                                     anchor="w", padx=16,
                                     command=self._logout)
        self.apply_theme()

    def _add_btn(self, text, page):
        b = tk.Button(self, text=text, relief=tk.FLAT,
                      font=("Arial", 11), anchor="w", padx=16,
                      command=lambda p=page: self._show(p))
        b.pack(fill="x", pady=2)
        self._btns[page] = b

    def apply_theme(self):
        t = get_theme()
        self.config(bg=t["sidebar_bg"])
        self._logo.config(bg=t["sidebar_bg"], fg=t["logo_fg"])
        self._sub.config(bg=t["sidebar_bg"], fg=t["logo_sub_fg"])
        self._admin_label.config(bg=t["sidebar_bg"], fg=t["logo_sub_fg"])
        self._admin_btns_frame.config(bg=t["sidebar_bg"])
        self._logout_btn.config(bg=t["btn_danger"], fg=t["sidebar_fg"],
                                activebackground=t["btn_danger"], activeforeground=t["sidebar_fg"])
        for name, btn in self._btns.items():
            if name in self._ADMIN_PAGES:
                btn.config(bg=t["sidebar_sub_bg"], fg=t["sidebar_fg"],
                           activebackground=t["sidebar_active"])
            else:
                btn.config(bg=t["sidebar_bg"], fg=t["sidebar_fg"],
                           activebackground=t["sidebar_active"])

    def set_active(self, page):
        t = get_theme()
        for name, btn in self._btns.items():
            if name == page:
                btn.config(bg=t["sidebar_active"])
            elif name in self._ADMIN_PAGES:
                btn.config(bg=t["sidebar_sub_bg"])
            else:
                btn.config(bg=t["sidebar_bg"])

    def show_admin_menu(self):
        if not self._admin_visible:
            self._admin_label.pack(pady=(6, 2))
            self._admin_btns_frame.pack(fill="x")
            self._logout_btn.pack(fill="x", pady=4, padx=10, side="bottom")
            self._btns["login"].pack_forget()
            self._admin_visible = True

    def hide_admin_menu(self):
        if self._admin_visible:
            self._admin_label.pack_forget()
            self._admin_btns_frame.pack_forget()
            self._logout_btn.pack_forget()
            self._btns["login"].pack(fill="x", pady=2)
            self._admin_visible = False

    def _logout(self):
        self.hide_admin_menu()
        self._show("home")


# ─── Home page ───────────────────────────────────────────────────────────────

class HomePage(Page):
    """Main check-in/out page with inline QR + face camera preview."""

    def __init__(self, parent, db_file, **kw):
        super().__init__(parent, **kw)
        self._db = db_file
        self._cam_thread = None
        self._running = False
        self._mode = None   # 'qr' | 'face'
        self._product_id = None
        self._face_results = []
        self._face_start = 0
        self._known_cache = None
        self._detector = cv2.QRCodeDetector()

        # ── top bar ──
        top = tk.Frame(self, pady=8)
        top.pack(fill="x")
        tk.Label(top, text="Check Product", font=("Arial", 16, "bold")).pack(side="left", padx=16)
        self._start_btn = tk.Button(top, text="▶  Start Scan", font=("Arial", 11),
                                    bg="#1abc9c", fg="white", relief=tk.FLAT, padx=12,
                                    command=self._start_qr)
        self._start_btn.pack(side="right", padx=16)
        self._cancel_btn = tk.Button(top, text="✖  Cancel", font=("Arial", 11),
                                     bg="#e74c3c", fg="white", relief=tk.FLAT, padx=12,
                                     state=tk.DISABLED, command=self._stop_camera)
        self._cancel_btn.pack(side="right", padx=4)

        # ── status ──
        self._status = tk.Label(self, text="Press 'Start Scan' to check a product in or out.",
                                font=("Arial", 11), fg="#555")
        self._status.pack(pady=4)

        # ── camera preview ──
        self._cam_label = tk.Label(self, bg="#1a1a2e", width=PREVIEW_W, height=PREVIEW_H)
        self._cam_label.pack(pady=6)

        # ── overdue alerts container ──
        self._overdue_container = tk.Frame(self)
        self._overdue_container.pack(fill="x", padx=16, pady=4)
        self._overdue_frame = tk.Frame(self._overdue_container, bg="#ffebee", bd=1, relief=tk.SOLID)
        self._overdue_label = tk.Label(self._overdue_frame, text="", fg="#c0392b", bg="#ffebee",
                                       font=("Arial", 11, "bold"), justify="left")
        self._overdue_label.pack(padx=10, pady=5, anchor="w")
        self._overdue_btn = tk.Button(self._overdue_frame, text="Read More...", fg="#2980b9", bg="#ffebee",
                                      activebackground="#ffebee", relief=tk.FLAT, font=("Arial", 10, "underline", "bold"),
                                      cursor="hand2", command=self._show_all_overdue)

        # ── today's history ──
        tk.Label(self, text="Today's History", font=("Arial", 13, "bold")).pack(anchor="w", padx=16)
        tree_frame = tk.Frame(self)
        tree_frame.pack(fill="both", expand=True, padx=12, pady=6)

        cols = ("product_id", "product_name", "user_id", "user_name",
                "check_out_time", "check_in_time")
        self._tree = ttk.Treeview(tree_frame, columns=cols, show="headings")
        self._tree.tag_configure("checked_out", background="#d6eaf8")
        self._tree.tag_configure("checked_in",  background="#d5f5e3")

        headers = ["Product ID", "Product Name", "User ID", "User Name",
                   "Check Out", "Check In"]
        widths  = [100, 180, 80, 140, 170, 170]
        for col, hdr, w in zip(cols, headers, widths):
            self._tree.heading(col, text=hdr)
            self._tree.column(col, anchor="center", width=w)

        sb = ttk.Scrollbar(tree_frame, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)
        self._tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        
        self._tree.bind("<Double-1>", self._show_user_details)

    def _show_user_details(self, event):
        sel = self._tree.selection()
        if not sel:
            return
        item = self._tree.item(sel[0])
        user_id = item['values'][2]
        if not user_id:
            return
            
        try:
            with sqlite3.connect(self._db) as conn:
                row = conn.execute("SELECT user_name, school, place FROM users WHERE user_id=?", (user_id,)).fetchone()
                if not row:
                    messagebox.showinfo("User Not Found", f"No details found for User ID {user_id}")
                    return
                user_name, school, place = row
                
                photo_row = conn.execute("SELECT face_image FROM face_encodings WHERE user_id=? AND face_image IS NOT NULL LIMIT 1", (user_id,)).fetchone()
        except Exception as e:
            messagebox.showerror("Database Error", f"Failed to fetch user details:\n{e}")
            return
            
        dlg = tk.Toplevel(self)
        dlg.title("User Details")
        dlg.transient(self.winfo_toplevel())
        try:
            dlg.wait_visibility()
            dlg.grab_set()
        except tk.TclError:
            pass
        dlg.lift()
        dlg.resizable(False, False)
        
        tk.Label(dlg, text="User Details", font=("Arial", 14, "bold"), pady=10).pack()
        info_frame = tk.Frame(dlg, padx=20, pady=10)
        info_frame.pack(fill="both", expand=True)
        
        if photo_row and photo_row[0]:
            import io
            try:
                pil_img = Image.open(io.BytesIO(photo_row[0])).resize((120, 120))
                photo = ImageTk.PhotoImage(pil_img)
                lbl_img = tk.Label(info_frame, image=photo, relief=tk.RIDGE, bd=2)
                lbl_img.image = photo
                lbl_img.grid(row=0, column=0, rowspan=4, padx=(0, 20))
            except Exception:
                tk.Label(info_frame, text="[Photo Error]", width=15, height=7, bg="#eee", relief=tk.RIDGE).grid(row=0, column=0, rowspan=4, padx=(0, 20))
        else:
            tk.Label(info_frame, text="[No Photo]", width=15, height=7, bg="#eee", relief=tk.RIDGE).grid(row=0, column=0, rowspan=4, padx=(0, 20))
            
        tk.Label(info_frame, text="ID:", font=("Arial", 11, "bold")).grid(row=0, column=1, sticky="e", pady=2)
        tk.Label(info_frame, text=f"{user_id}", font=("Arial", 11)).grid(row=0, column=2, sticky="w", pady=2)
        tk.Label(info_frame, text="Name:", font=("Arial", 11, "bold")).grid(row=1, column=1, sticky="e", pady=2)
        tk.Label(info_frame, text=f"{user_name}", font=("Arial", 11)).grid(row=1, column=2, sticky="w", pady=2)
        tk.Label(info_frame, text="School:", font=("Arial", 11, "bold")).grid(row=2, column=1, sticky="e", pady=2)
        tk.Label(info_frame, text=f"{school or '—'}", font=("Arial", 11)).grid(row=2, column=2, sticky="w", pady=2)
        tk.Label(info_frame, text="Place:", font=("Arial", 11, "bold")).grid(row=3, column=1, sticky="e", pady=2)
        tk.Label(info_frame, text=f"{place or '—'}", font=("Arial", 11)).grid(row=3, column=2, sticky="w", pady=2)
        
        tk.Button(dlg, text="Close", command=dlg.destroy, width=10).pack(pady=(0, 15))

    # ── public ──

    def on_show(self):
        self._refresh_history()

    def on_hide(self):
        self._stop_camera()

    # ── QR scanning ──

    def _qr_process(self, rgb, bgr):
        """Run QR decode; draw distance guide + info overlay."""
        h, w = bgr.shape[:2]
        data, points, _ = self._detector.detectAndDecode(bgr)

        if points is not None:
            pts = points[0].astype(int)
            # Compute QR code size relative to frame
            qr_w = int(pts[:, 0].max() - pts[:, 0].min())
            qr_h = int(pts[:, 1].max() - pts[:, 1].min())
            qr_ratio = max(qr_w / w, qr_h / h)

            # Distance hint based on QR size
            if qr_ratio < 0.12:
                hint, color = "Move CLOSER to the QR code", (0, 80, 255)
                arrow = "▲▲  CLOSER"
            elif qr_ratio > 0.75:
                hint, color = "Move BACK from the QR code", (0, 180, 255)
                arrow = "▼▼  BACK"
            else:
                hint, color = "Hold steady…", (50, 200, 50)
                arrow = "✓  GOOD"

            cv2.polylines(bgr, [pts], True, color, 2)
            (tw, _), _ = cv2.getTextSize(arrow, cv2.FONT_HERSHEY_SIMPLEX, 0.75, 2)
            cv2.rectangle(bgr, (8, 8), (tw + 20, 38), (0, 0, 0), -1)
            cv2.putText(bgr, arrow, (12, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.75, color, 2)

            # Distance bar on right edge
            bar_x = w - 22
            bar_y0, bar_y1 = int(h * 0.1), int(h * 0.9)
            bar_h = bar_y1 - bar_y0
            cv2.rectangle(bgr, (bar_x, bar_y0), (bar_x + 14, bar_y1), (50, 50, 50), -1)
            fill = int(bar_h * min(qr_ratio / 0.75, 1.0))
            cv2.rectangle(bgr, (bar_x, bar_y1 - fill), (bar_x + 14, bar_y1), color, -1)
            cv2.putText(bgr, "D", (bar_x - 2, bar_y0 - 6),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1)

            if data:
                # Show QR value at bottom
                label = f"QR: {data.strip()[:30]}"
                (lw, lh), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
                cv2.rectangle(bgr, (8, h - lh - 18), (lw + 20, h - 4), (0, 0, 0), -1)
                cv2.putText(bgr, label, (12, h - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (50, 255, 50), 2)
                return bgr, data.strip()
        else:
            # No QR detected — guide the user
            cx, cy = w // 2, h // 2
            # Dashed target rectangle
            for i in range(0, w // 3, 20):
                cv2.line(bgr, (cx - w//6 + i, cy - h//6), (cx - w//6 + i + 10, cy - h//6), (150, 150, 150), 1)
                cv2.line(bgr, (cx - w//6 + i, cy + h//6), (cx - w//6 + i + 10, cy + h//6), (150, 150, 150), 1)
            for i in range(0, h // 3, 20):
                cv2.line(bgr, (cx - w//6, cy - h//6 + i), (cx - w//6, cy - h//6 + i + 10), (150, 150, 150), 1)
                cv2.line(bgr, (cx + w//6, cy - h//6 + i), (cx + w//6, cy - h//6 + i + 10), (150, 150, 150), 1)
            msg = "Point QR code at the box"
            (mw, _), _ = cv2.getTextSize(msg, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
            cv2.rectangle(bgr, (8, 8), (mw + 20, 38), (0, 0, 0), -1)
            cv2.putText(bgr, msg, (12, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 200), 2)

        return bgr, None

    def _start_qr(self):
        self._running = True
        self._mode = "qr"
        self._face_results = []
        self._start_btn.config(state=tk.DISABLED)
        self._cancel_btn.config(state=tk.NORMAL)
        self._status.config(text="Point the QR code at the camera…", fg="#2980b9")
        # Start one long-lived camera thread; we'll swap the process fn for face mode
        self._cam_thread = _CameraThread(_active_camera_index, self._qr_process, process_every=2)
        self._cam_thread.start()
        self._render_loop_active = True
        self._render_loop()

    # ── Face recognition ──

    def _face_process(self, rgb, bgr):
        """
        InsightFace detection + ArcFace embedding + FAISS cosine matching.
        Returns (annotated_bgr, (uid, uname, hint, conf) | (None, None, hint, 0)).
        conf = cosine similarity scaled to 0-100.
        """
        h, w = bgr.shape[:2]
        cx, cy = w // 2, int(h * 0.45)
        ow, oh = int(w * 0.18), int(h * 0.40)

        faces = detect_faces(bgr)
        
        valid_faces = []
        bounds_violated = False
        for f in faces:
            left, top, right, bottom = f.bbox
            face_cx = (left + right) / 2
            face_cy = (top + bottom) / 2
            center_dist = ((face_cx - cx) ** 2 / (ow ** 2)) + ((face_cy - cy) ** 2 / (oh ** 2))
            
            # STRICT CHECK: Ensure the ENTIRE bounding box fits inside the oval's rectangular bounds
            if center_dist <= 0.15 and left >= cx - ow and right <= cx + ow and top >= cy - oh and bottom <= cy + oh:
                valid_faces.append(f)
            elif center_dist <= 1.5:
                bounds_violated = True
        faces = valid_faces

        mask = np.zeros((h, w), dtype=np.uint8)
        cv2.ellipse(mask, (cx, cy), (ow, oh), 0, 0, 360, 255, -1)
        blurred_bgr = cv2.GaussianBlur(bgr, (51, 51), 0)
        bgr = np.where(mask[:, :, None] == 255, bgr, blurred_bgr)

        locs  = faces_to_locations(faces)
        bgr, hint, _ = _draw_distance_guide(bgr, locs)
        result = None

        if not faces and bounds_violated:
            hint = "Center your full face strictly inside the oval"
            (tw, th), _ = cv2.getTextSize(hint, cv2.FONT_HERSHEY_SIMPLEX, 0.70, 2)
            cv2.rectangle(bgr, (8, 8), (tw + 20, 45), (0, 0, 0), -1)
            cv2.putText(bgr, hint, (12, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.70, (0, 165, 255), 2)

        if faces:
            h = bgr.shape[0]
            # Pick the largest face within the valid distance range
            for face, loc in zip(faces, locs):
                face_h_ratio = (loc[2] - loc[0]) / h
                if not (_DIST_MIN <= face_h_ratio <= _DIST_MAX):
                    continue
                
                if not check_liveness(bgr, face.bbox):
                    result = (None, None, "⚠ Liveness check failed (Suspected Spoof)", 0)
                    break

                enc   = get_face_embedding(face)
                known = self._known_cache
                if known:
                    uid, uname = find_matching_face(known, enc, tolerance=VERIFY_THRESHOLD)
                    if uid:
                        # Compute cosine similarity for confidence display
                        from utils.face_recognition_utils import build_faiss_index, find_matching_face_faiss
                        embs  = np.array([e[2] for e in known], dtype=np.float32)
                        norms = np.linalg.norm(embs, axis=1, keepdims=True)
                        norms[norms == 0] = 1
                        idx_  = build_faiss_index(embs / norms)
                        sims, _ = idx_.search(enc.reshape(1, -1), k=1)
                        sim  = float(sims[0][0])
                        conf = max(0, min(100, int(sim * 100)))
                        bar_color = (0, 200, 0) if conf >= 70 else \
                                    (0, 165, 255) if conf >= 40 else (0, 0, 220)
                        cv2.rectangle(bgr, (10, bgr.shape[0]-40),
                                      (10 + conf*3, bgr.shape[0]-20), bar_color, -1)
                        cv2.putText(bgr, f"Match: {conf}%  {uname}",
                                    (10, bgr.shape[0]-45),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, bar_color, 2)
                        result = (uid, uname, hint, conf)
                        break

        if result is None and locs:
            result = (None, None, hint, 0)
        return bgr, result

    # Votes needed for a confirmed match (higher = harder to spoof)
    _VOTES_NEEDED = 6

    def _switch_to_face(self):
        if not self._running:
            return
        self._mode = "face"
        self._face_results = []
        self._unknown_face_count = 0
        self._face_start = time.time()
        self._status.config(text=f"QR: {self._product_id}  —  Look at the camera…", fg="#27ae60")
        # Load known encodings ONCE here — not per frame
        self._known_cache = get_known_encodings(db_file=self._db)
        # Swap processing function — camera stays open, no device close/reopen
        if self._cam_thread:
            self._cam_thread.set_process_fn(self._face_process, process_every=3)

    # ── Unified render loop (runs at full display speed ~30 ms) ──

    def _render_loop(self):
        if not self._running or not getattr(self, "_render_loop_active", False):
            return
        frame = self._cam_thread.latest_display() if self._cam_thread else None
        if frame is not None:
            self._show_frame(frame)

        result = self._cam_thread.pop_result() if self._cam_thread else None

        if self._mode == "qr" and result:
            self._product_id = result
            self._switch_to_face()          # swap fn in-place, no stop/start

        elif self._mode == "face":
            if result:
                # The result tuple structure might vary, handle safely
                uid, uname, hint, conf = None, None, "", 0
                if isinstance(result, tuple):
                    if len(result) == 4:
                        uid, uname, hint, conf = result
                    elif len(result) == 3:
                        uid, uname, hint = result
                    elif len(result) == 2:
                        uid, uname = result
                
                # Update status with distance hint
                if hint:
                    self._status.config(text=hint,
                                        fg="#27ae60" if "Perfect" in hint else
                                           "#c0392b" if "Liveness" in hint else
                                           "#e67e22" if "BACK" in hint or "CLOSER" in hint else "#2980b9")
                if uid:
                    self._unknown_face_count = 0
                    self._face_results.append((uid, uname))
                    votes = len(self._face_results)
                    self._status.config(
                        text=f"Recognising {uname} — confidence {conf}%  ({votes}/{self._VOTES_NEEDED} votes)",
                        fg="#27ae60")
                else:
                    # Face in range but no match
                    if hint and "Perfect" in hint:
                        self._unknown_face_count += 1
                        if self._unknown_face_count >= 12:
                            self._stop_camera()
                            self._show_unregistered_popup()
                            return
                if len(self._face_results) >= self._VOTES_NEEDED:
                    from collections import Counter
                    (uid, uname), _ = Counter(self._face_results).most_common(1)[0]
                    self._stop_camera()
                    self._do_checkinout(uid, uname)
                    return
            if time.time() - self._face_start > 25:
                self._stop_camera()
                self._show_unregistered_popup()
                return

        self.after(30, self._render_loop)

    # ── Check-in / check-out DB logic ──

    def _do_checkinout(self, user_id, user_name):
        pid = self._product_id
        now_db = time.strftime("%Y-%m-%d %H:%M:%S")
        now_display = time.strftime("%d-%m-%Y %I:%M:%S %p")
        try:
            with sqlite3.connect(self._db) as conn:
                c = conn.cursor()
                
                c.execute("SELECT school FROM users WHERE user_id=?", (user_id,))
                user_row = c.fetchone()
                school_name = user_row[0] if user_row and user_row[0] else "N/A"

                c.execute("SELECT product_id, product_name FROM formatted_items WHERE product_id=?", (pid,))
                row = c.fetchone()
                if not row:
                    self._status.config(text=f"Unknown product: {pid}", fg="red")
                    text_to_speech("Invalid QR code")
                    self._start_btn.config(state=tk.NORMAL)
                    return
                pname = row[1]
                c.execute("SELECT * FROM product_history WHERE product_id=? AND check_in_time IS NULL", (pid,))
                open_rec = c.fetchone()
                if open_rec:
                    checkout_time = open_rec[5] if len(open_rec) > 5 else "—"
                    c.execute("UPDATE product_history SET check_in_time=? WHERE product_id=? AND check_in_time IS NULL",
                              (now_db, pid))
                    conn.commit()
                    self._status.config(text=f"✅  Checked IN: {pname}", fg="#27ae60")
                    text_to_speech(f"Checked in: {pname}")
                    self._refresh_history()
                    self._start_btn.config(state=tk.NORMAL)
                    self._cancel_btn.config(state=tk.DISABLED)
                    messagebox.showinfo(
                        "✅  Check-In Successful",
                        f"Product returned successfully!\n\n"
                        f"  Product : {pname}\n"
                        f"  ID      : {pid}\n"
                        f"  User    : {user_name}\n"
                        f"  School  : {school_name}\n"
                        f"  Time    : {now_display}")
                    return
                else:
                    # Check if the user has more than 2 unreturned products
                    c.execute("""
                        SELECT product_id, product_name, check_out_time
                        FROM product_history
                        WHERE user_id = ? AND check_in_time IS NULL
                    """, (user_id,))
                    unreturned_items = c.fetchall()
                    try:
                        with open("debug_borrow.txt", "a") as f:
                            f.write(f"{datetime.now()}: User {user_name} (ID {user_id}) has {len(unreturned_items)} unreturned items. Attempting to borrow {pname} ({pid}).\n")
                    except:
                        pass
                    if len(unreturned_items) > 2:
                        try:
                            with open("debug_borrow.txt", "a") as f:
                                f.write(f"{datetime.now()}: BLOCKED user {user_name} (ID {user_id}) from borrowing {pname} ({pid}).\n")
                        except:
                            pass
                        self._status.config(text=f"⚠ Scan blocked for {user_name}: return borrowed products.", fg="red")
                        self._start_btn.config(state=tk.NORMAL)
                        self._cancel_btn.config(state=tk.DISABLED)
                        self._show_user_overdue_block_popup(user_name, unreturned_items)
                        return

                    c.execute("""INSERT INTO product_history
                                 (product_id, product_name, user_id, user_name, check_out_time, check_in_time)
                                 VALUES (?,?,?,?,?,NULL)""", (pid, pname, user_id, user_name, now_db))
                    conn.commit()
                    self._status.config(text=f"✅  Checked OUT: {pname} by {user_name}", fg="#2980b9")
                    text_to_speech(f"Checked out: {pname}")
                    self._refresh_history()
                    self._start_btn.config(state=tk.NORMAL)
                    self._cancel_btn.config(state=tk.DISABLED)
                    messagebox.showinfo(
                        "✅  Check-Out Successful",
                        f"Product borrowed successfully!\n\n"
                        f"  Product : {pname}\n"
                        f"  ID      : {pid}\n"
                        f"  User    : {user_name}\n"
                        f"  School  : {school_name}\n"
                        f"  Time    : {now_display}")
                    return
        except sqlite3.Error as e:
            self._status.config(text=f"DB error: {e}", fg="red")
            messagebox.showerror("Database Error", f"Could not complete operation:\n\n{e}")
        self._refresh_history()
        self._start_btn.config(state=tk.NORMAL)
        self._cancel_btn.config(state=tk.DISABLED)

    # ── helpers ──

    def _show_unregistered_popup(self):
        """Alert shown when a face is detected but not found in the database."""
        text_to_speech("User not registered. Please contact the administrator.")
        self._status.config(text="⚠  Unrecognised user.", fg="red")

        dlg = tk.Toplevel(self)
        dlg.title("Unregistered User")
        dlg.transient(self.winfo_toplevel())
        try:
            dlg.wait_visibility()
            dlg.grab_set()
        except tk.TclError:
            pass
        dlg.lift()
        dlg.resizable(False, False)

        # Warning icon row
        icon_lbl = tk.Label(dlg, text="⚠", font=("Arial", 48), fg="#e67e22")
        icon_lbl.pack(pady=(18, 4))

        tk.Label(dlg, text="Unregistered User Detected",
                 font=("Arial", 14, "bold"), fg="#c0392b").pack()
        tk.Label(dlg,
                 text="This person is not registered in the system.\n"
                      "Please ask them to register with an administrator\n"
                      "before checking in or out any product.",
                 font=("Arial", 11), justify="center", wraplength=320,
                 pady=8).pack()

        bf = tk.Frame(dlg)
        bf.pack(pady=(4, 16))

        def _retry():
            dlg.destroy()
            self._start_btn.config(state=tk.NORMAL)
            self._cancel_btn.config(state=tk.DISABLED)
            # Re-start the scan so the user can try again
            self.after(200, self._start_qr)

        tk.Button(bf, text="🔄  Try Again", bg="#3498db", fg="white",
                  font=("Arial", 11), relief=tk.FLAT, padx=12,
                  command=_retry).pack(side="left", padx=8)
        tk.Button(bf, text="✖  Cancel", bg="#7f8c8d", fg="white",
                  font=("Arial", 11), relief=tk.FLAT, padx=12,
                  command=lambda: (dlg.destroy(),
                                   self._start_btn.config(state=tk.NORMAL),
                                   self._cancel_btn.config(state=tk.DISABLED))
                  ).pack(side="left", padx=8)

    def _show_frame(self, frame):
        photo = _frame_to_photoimage(frame)
        self._cam_label.config(image=photo)
        self._cam_label.image = photo

    def _stop_camera(self, msg=None):
        self._running = False
        self._render_loop_active = False
        self._mode = None
        if self._cam_thread:
            t = self._cam_thread
            self._cam_thread = None
            t.stop()
            threading.Thread(target=lambda: t.join(timeout=2.0), daemon=True).start()
        self._cam_label.config(image="", bg="#1a1a2e")
        self._cam_label.image = None
        self._start_btn.config(state=tk.NORMAL)
        self._cancel_btn.config(state=tk.DISABLED)
        if msg:
            self._status.config(text=msg, fg="red")

    def _check_overdue(self):
        if hasattr(self, '_overdue_timer'):
            self.after_cancel(self._overdue_timer)
        self._overdue_timer = self.after(60000, self._check_overdue)
        
        try:
            with sqlite3.connect(self._db) as conn:
                c = conn.cursor()
                c.execute("""
                    SELECT ph.product_id, ph.product_name, 
                           COALESCE(u.user_name, ph.user_name), 
                           ph.check_out_time 
                     FROM product_history ph
                     LEFT JOIN users u ON ph.user_id = u.user_id
                     WHERE ph.check_in_time IS NULL
                """)
                rows = c.fetchall()
        except Exception as e:
            try:
                with open("debug_overdue.txt", "a") as f:
                    f.write(f"{datetime.now()}: DB Query error in _check_overdue: {e}\n")
            except:
                pass
            return
            
        now = datetime.now()
        overdue_list = []
        self._overdue_raw_items = []
        for pid, pname, uname, cout in rows:
            try:
                cout_dt = datetime.strptime(cout, "%Y-%m-%d %H:%M:%S")
                # Overdue if it's from a previous day OR it's today and past 8:00 PM (20:00)
                if cout_dt.date() < now.date() or (cout_dt.date() == now.date() and now.hour >= 20):
                    overdue_list.append(f"• {pname} ({pid}) — Borrowed by {uname} at {cout_dt.strftime('%I:%M %p')}")
                    self._overdue_raw_items.append((pid, pname, uname, cout_dt))
            except Exception as e:
                try:
                    with open("debug_overdue.txt", "a") as f:
                        f.write(f"{datetime.now()}: Row parsing error in _check_overdue: {e}\n")
                except:
                    pass
                
        try:
            with open("debug_overdue.txt", "a") as f:
                f.write(f"{datetime.now()}: _check_overdue found {len(overdue_list)} items.\n")
        except:
            pass

        if overdue_list:
            if len(overdue_list) > 5:
                displayed = overdue_list[:5]
                self._overdue_btn.pack(padx=10, pady=(0, 5), anchor="w")
            else:
                displayed = overdue_list
                self._overdue_btn.pack_forget()
                
            msg = "⚠ OVERDUE ITEMS (Not returned by 8:00 PM):\n" + "\n".join(displayed)
            self._overdue_label.config(text=msg)
            if not self._overdue_frame.winfo_ismapped():
                self._overdue_frame.pack(fill="x")
        else:
            self._overdue_btn.pack_forget()
            if self._overdue_frame.winfo_ismapped():
                self._overdue_frame.pack_forget()

    def _show_all_overdue(self):
        """Open a beautiful modal dialog listing all overdue items."""
        dlg = tk.Toplevel(self)
        dlg.title("All Overdue Items")
        dlg.geometry("600x400")
        dlg.transient(self.winfo_toplevel())
        try:
            dlg.wait_visibility()
            dlg.grab_set()
        except tk.TclError:
            pass
        dlg.lift()

        # Style/Header
        hdr = tk.Frame(dlg, bg="#ffebee", pady=10)
        hdr.pack(fill="x")
        tk.Label(hdr, text="⚠  All Overdue Items", font=("Arial", 14, "bold"), fg="#c0392b", bg="#ffebee").pack()

        # Treeview list
        tf = tk.Frame(dlg)
        tf.pack(fill="both", expand=True, padx=10, pady=10)

        cols = ("pid", "pname", "uname", "time")
        widths = (80, 160, 140, 180)
        headers = ("Product ID", "Product Name", "Borrowed By", "Borrow Time")

        tree = ttk.Treeview(tf, columns=cols, show="headings")
        for c, h, w in zip(cols, headers, widths):
            tree.heading(c, text=h)
            tree.column(c, anchor="center", width=w)

        sb = ttk.Scrollbar(tf, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        if hasattr(self, "_overdue_raw_items"):
            for pid, pname, uname, cout_dt in self._overdue_raw_items:
                tree.insert("", "end", values=(pid, pname, uname, cout_dt.strftime("%d-%m-%Y %I:%M %p")))

        # Close button
        btn = tk.Button(dlg, text="Close", font=("Arial", 11, "bold"), bg="#c0392b", fg="white",
                        relief=tk.FLAT, padx=20, pady=6, command=dlg.destroy)
        btn.pack(pady=10)

    def _show_user_overdue_block_popup(self, user_name, unreturned_items):
        """Open a beautiful block popup when a user has >2 unreturned items and attempts to borrow."""
        text_to_speech("Scan blocked. Please return your borrowed products first.")
        self._status.config(text=f"⚠ Scan blocked for {user_name}: return borrowed products.", fg="red")

        dlg = tk.Toplevel(self)
        dlg.title("Overdue Block Alert")
        dlg.geometry("550x380")
        dlg.transient(self.winfo_toplevel())
        try:
            dlg.wait_visibility()
            dlg.grab_set()
        except tk.TclError:
            pass
        dlg.lift()
        dlg.resizable(False, False)

        # Main frame
        main_frame = tk.Frame(dlg, padx=20, pady=20)
        main_frame.pack(fill="both", expand=True)

        # Warning icon/header
        header_frame = tk.Frame(main_frame)
        header_frame.pack(fill="x", pady=(0, 10))

        warn_lbl = tk.Label(header_frame, text="⚠", font=("Arial", 36), fg="#e74c3c")
        warn_lbl.pack(side="left", padx=(0, 10))

        title_lbl = tk.Label(header_frame, text="Borrow Limit Blocked", font=("Arial", 16, "bold"), fg="#c0392b")
        title_lbl.pack(side="left", anchor="w")

        # Message description
        msg = f"Hello {user_name},\n\nYou have currently borrowed {len(unreturned_items)} products (limit is 2).\nYou must return these products before you can borrow any others."
        msg_lbl = tk.Label(main_frame, text=msg, font=("Arial", 11), justify="left", wraplength=480)
        msg_lbl.pack(anchor="w", pady=(0, 15))

        # List of unreturned items
        list_frame = tk.LabelFrame(main_frame, text="Items to Return", font=("Arial", 10, "bold"), padx=10, pady=10)
        list_frame.pack(fill="both", expand=True, pady=(0, 15))

        # Treeview for items
        cols = ("pid", "pname", "time")
        tree = ttk.Treeview(list_frame, columns=cols, show="headings", height=4)
        tree.heading("pid", text="Product ID")
        tree.heading("pname", text="Product Name")
        tree.heading("time", text="Borrowed Time")
        tree.column("pid", width=80, anchor="center")
        tree.column("pname", width=180, anchor="w")
        tree.column("time", width=160, anchor="center")

        sb = ttk.Scrollbar(list_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        for pid, pname, cout in unreturned_items:
            try:
                cout_dt = datetime.strptime(cout, "%Y-%m-%d %H:%M:%S")
                cout_str = cout_dt.strftime("%d-%m-%Y %I:%M %p")
            except Exception:
                cout_str = cout
            tree.insert("", "end", values=(pid, pname, cout_str))

        # Close/OK Button
        btn = tk.Button(main_frame, text="OK, I will return them", font=("Arial", 11, "bold"),
                        bg="#2980b9", fg="white", relief=tk.FLAT, padx=20, pady=8, command=dlg.destroy)
        btn.pack()

    def _refresh_history(self):
        show_items(self._tree, db_file=self._db)
        self._check_overdue()


# ─── Login page ──────────────────────────────────────────────────────────────

class LoginPage(Page):
    def __init__(self, parent, on_success_cb, **kw):
        super().__init__(parent, **kw)
        self._on_success = on_success_cb
        self.columnconfigure(0, weight=1)

        card = tk.Frame(self, relief=tk.GROOVE, bd=2, padx=40, pady=40)
        card.place(relx=0.5, rely=0.4, anchor="center")

        tk.Label(card, text="Admin Login", font=("Arial", 16, "bold")).pack(pady=(0, 20))

        tk.Label(card, text="Username").pack(anchor="w")
        self._user = tk.Entry(card, width=28, font=("Arial", 11))
        self._user.pack(pady=(2, 10))

        tk.Label(card, text="Password").pack(anchor="w")
        self._pw = tk.Entry(card, width=28, font=("Arial", 11), show="●")
        self._pw.pack(pady=(2, 16))

        self._err = tk.Label(card, text="", fg="red", font=("Arial", 10))
        self._err.pack()

        btn = tk.Button(card, text="Login", bg="#1abc9c", fg="white", relief=tk.FLAT,
                        font=("Arial", 12), padx=20, command=self._login)
        btn.pack(pady=8)

        self._user.bind("<Return>", lambda e: self._pw.focus())
        self._pw.bind("<Return>",   lambda e: self._login())

    def on_show(self):
        self._user.delete(0, tk.END)
        self._pw.delete(0, tk.END)
        self._err.config(text="")
        self._user.focus()

    def _login(self):
        username = self._user.get().strip()
        password = self._pw.get()
        if not username or not password:
            self._err.config(text="Enter both username and password.")
            return
        hashed = hash_password(password)
        try:
            with sqlite3.connect(DB_FILE) as conn:
                row = conn.execute("SELECT password FROM logusers WHERE username=?",
                                   (username,)).fetchone()
            if row and row[0] == hashed:
                self._err.config(text="")
                self._on_success()
            else:
                self._err.config(text="Invalid username or password.")
        except Exception as e:
            self._err.config(text=f"DB error: {e}")


# ─── Admin History page ───────────────────────────────────────────────────────

class AdminHistoryPage(Page):
    def __init__(self, parent, db_file, **kw):
        super().__init__(parent, **kw)
        self._db = db_file

        # ── toolbar ──
        self._bar = tk.Frame(self, pady=8)
        self._bar.pack(fill="x", padx=12)
        self._title_lbl = tk.Label(self._bar, text="History", font=("Arial", 15, "bold"))
        self._title_lbl.pack(side="left")

        self._refresh_btn = tk.Button(self._bar, text="🔄 Refresh", relief=tk.FLAT,
                                      command=self._refresh)
        self._refresh_btn.pack(side="right", padx=4)
        self._search_var = tk.StringVar()
        self._search_bar = SearchEntry(self._bar, placeholder="Search history...", command=self._do_search, textvariable=self._search_var, entry_width=22)
        self._search_bar.pack(side="right", padx=4)

        # ── tree ──
        self._tf = tk.Frame(self)
        self._tf.pack(fill="both", expand=True, padx=12, pady=6)
        cols = ("Product ID", "Product Name", "Check Out", "Check In", "User ID", "User Name")
        self._tree = ttk.Treeview(self._tf, columns=cols, show="headings")
        widths = [90, 170, 150, 150, 80, 150]
        for col, w in zip(cols, widths):
            self._tree.heading(col, text=col)
            self._tree.column(col, anchor="center", width=w)
        sb = ttk.Scrollbar(self._tf, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)
        self._tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        
        self._tree.bind("<Double-1>", self._show_user_details)

    def apply_theme(self):
        t = get_theme()
        self._bar.config(bg=t["content_bg"])
        self._title_lbl.config(bg=t["content_bg"], fg=t["header_fg"])
        self._refresh_btn.config(bg=t["btn_secondary"], fg=t["btn_secondary_fg"],
                                 activebackground=t["btn_secondary"], activeforeground=t["btn_secondary_fg"])
        self._tf.config(bg=t["content_bg"])
        self._search_bar.apply_theme()

    def _show_user_details(self, event):
        sel = self._tree.selection()
        if not sel:
            return
        item = self._tree.item(sel[0])
        user_id = item['values'][4]
        if not user_id:
            return
            
        try:
            with sqlite3.connect(self._db) as conn:
                row = conn.execute("SELECT user_name, school, place FROM users WHERE user_id=?", (user_id,)).fetchone()
                if not row:
                    messagebox.showinfo("User Not Found", f"No details found for User ID {user_id}")
                    return
                user_name, school, place = row
                
                photo_row = conn.execute("SELECT face_image FROM face_encodings WHERE user_id=? AND face_image IS NOT NULL LIMIT 1", (user_id,)).fetchone()
        except Exception as e:
            messagebox.showerror("Database Error", f"Failed to fetch user details:\n{e}")
            return
            
        dlg = tk.Toplevel(self)
        dlg.title("User Details")
        dlg.transient(self.winfo_toplevel())
        try:
            dlg.wait_visibility()
            dlg.grab_set()
        except tk.TclError:
            pass
        dlg.lift()
        dlg.resizable(False, False)
        
        tk.Label(dlg, text="User Details", font=("Arial", 14, "bold"), pady=10).pack()
        info_frame = tk.Frame(dlg, padx=20, pady=10)
        info_frame.pack(fill="both", expand=True)
        
        if photo_row and photo_row[0]:
            import io
            try:
                pil_img = Image.open(io.BytesIO(photo_row[0])).resize((120, 120))
                photo = ImageTk.PhotoImage(pil_img)
                lbl_img = tk.Label(info_frame, image=photo, relief=tk.RIDGE, bd=2)
                lbl_img.image = photo
                lbl_img.grid(row=0, column=0, rowspan=4, padx=(0, 20))
            except Exception:
                tk.Label(info_frame, text="[Photo Error]", width=15, height=7, bg="#eee", relief=tk.RIDGE).grid(row=0, column=0, rowspan=4, padx=(0, 20))
        else:
            tk.Label(info_frame, text="[No Photo]", width=15, height=7, bg="#eee", relief=tk.RIDGE).grid(row=0, column=0, rowspan=4, padx=(0, 20))
            
        tk.Label(info_frame, text="ID:", font=("Arial", 11, "bold")).grid(row=0, column=1, sticky="e", pady=2)
        tk.Label(info_frame, text=f"{user_id}", font=("Arial", 11)).grid(row=0, column=2, sticky="w", pady=2)
        tk.Label(info_frame, text="Name:", font=("Arial", 11, "bold")).grid(row=1, column=1, sticky="e", pady=2)
        tk.Label(info_frame, text=f"{user_name}", font=("Arial", 11)).grid(row=1, column=2, sticky="w", pady=2)
        tk.Label(info_frame, text="School:", font=("Arial", 11, "bold")).grid(row=2, column=1, sticky="e", pady=2)
        tk.Label(info_frame, text=f"{school or '—'}", font=("Arial", 11)).grid(row=2, column=2, sticky="w", pady=2)
        tk.Label(info_frame, text="Place:", font=("Arial", 11, "bold")).grid(row=3, column=1, sticky="e", pady=2)
        tk.Label(info_frame, text=f"{place or '—'}", font=("Arial", 11)).grid(row=3, column=2, sticky="w", pady=2)
        
        tk.Button(dlg, text="Close", command=dlg.destroy, width=10).pack(pady=(0, 15))

    def on_show(self):
        self._refresh()

    def _refresh(self):
        self._search_bar.clear(trigger_command=False)
        show_items_admin(self._tree, db_file=self._db)

    def _do_search(self):
        term = self._search_bar.get().strip()
        if not term:
            show_items_admin(self._tree, db_file=self._db)
            return
        try:
            with sqlite3.connect(self._db) as conn:
                rows = conn.execute("""
                    SELECT ph.product_id, ph.product_name, ph.check_out_time, ph.check_in_time,
                           ph.user_id, COALESCE(u.user_name, ph.user_name) AS user_name
                    FROM product_history ph
                    LEFT JOIN users u ON ph.user_id = u.user_id
                    WHERE ph.product_id LIKE ? OR ph.product_name LIKE ?
                       OR ph.user_id LIKE ?    OR COALESCE(u.user_name, ph.user_name) LIKE ?
                """, (f"%{term}%",)*4).fetchall()
            for i in self._tree.get_children():
                self._tree.delete(i)
                
            from datetime import datetime
            def format_date_str(date_str):
                if not date_str:
                    return date_str
                try:
                    dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
                    return dt.strftime("%d-%m-%Y %I:%M:%S %p")
                except ValueError:
                    return date_str
                    
            for r in rows:
                formatted_row = []
                for val in r:
                    if isinstance(val, str) and "-" in val and ":" in val:
                        formatted_row.append(format_date_str(val))
                    else:
                        formatted_row.append(val)
                self._tree.insert("", "end", values=tuple(formatted_row))
        except Exception as e:
            messagebox.showerror("Search error", str(e))


# ─── User Management page ─────────────────────────────────────────────────────

class UserManagementPage(Page):
    def __init__(self, parent, db_file, **kw):
        super().__init__(parent, **kw)
        self._db = db_file
        self._cam_thread = None
        self._running = False
        self._captured = []
        self._face_detected = False
        self._cur_faces = []
        self._cur_locs = []
        self._dist_hint = ""
        self._lock = threading.Lock()
        SAMPLE_TARGET = 4
        self._SAMPLE_TARGET = SAMPLE_TARGET

        # ── layout: left = add-user, right = user list ──
        self._pane = tk.PanedWindow(self, orient=tk.HORIZONTAL, sashrelief=tk.RAISED)
        self._pane.pack(fill="both", expand=True, padx=8, pady=8)

        # ── left panel ──
        self._left_panel = tk.Frame(self._pane, padx=10)
        self._pane.add(self._left_panel, minsize=660)

        self._add_user_title = tk.Label(self._left_panel, text="Add User", font=("Arial", 14, "bold"))
        self._add_user_title.pack(pady=(10, 4))

        # ---- form fields ----
        self._form_frame = tk.Frame(self._left_panel)
        self._form_frame.pack(fill="x", pady=2)
        
        self._form_labels = []
        self._form_entries = []
        for r, (lbl, attr) in enumerate([
            ("Name:",   "_name_var"),
            ("School:", "_school_var"),
            ("Place:",  "_place_var"),
        ]):
            lbl_widget = tk.Label(self._form_frame, text=lbl, width=8, anchor="e")
            lbl_widget.grid(row=r, column=0, pady=3, padx=4)
            self._form_labels.append(lbl_widget)
            var = tk.StringVar()
            setattr(self, attr, var)
            ent = tk.Entry(self._form_frame, textvariable=var, width=28, font=("Arial", 11))
            self._form_entries.append(ent)
            
            ent.grid(row=r, column=1, pady=3, padx=4, sticky="w")

        # Navigation binding for input fields: Enter moves focus to the next field.
        self._name_entry = self._form_entries[0]
        self._form_entries[0].bind("<Return>", lambda e: self._form_entries[1].focus_set())
        self._form_entries[1].bind("<Return>", lambda e: self._form_entries[2].focus_set())
        self._form_entries[2].bind("<Return>", lambda e: self._start_btn.focus_set())

        # ── Step 2: Start Camera button — placed immediately below the form ──
        self._start_btn = tk.Button(self._left_panel, text="📷  Start Face Capture",
                                    relief=tk.FLAT, font=("Arial", 13, "bold"),
                                    padx=14, pady=8, command=self._start_camera)
        self._start_btn.pack(fill="x", padx=4, pady=(6, 2))

        # camera preview (hidden until camera starts)
        self._cam_label = tk.Label(self._left_panel, bg="#1a1a2e", width=PREVIEW_W, height=PREVIEW_H)
        self._cam_label.pack(pady=4)

        self._status = tk.Label(self._left_panel, text="Fill in Name, School, Place — then press 'Start Face Capture'.",
                                 font=("Arial", 10), wraplength=380)
        self._status.pack(pady=2)

        # progress bar for samples
        self._progress = ttk.Progressbar(self._left_panel, maximum=SAMPLE_TARGET, length=360)
        self._progress.pack(pady=4)

        # Capture / Cancel row (active only while camera is running)
        self._btn_frame = tk.Frame(self._left_panel)
        self._btn_frame.pack(pady=2)
        self._capture_btn = tk.Button(self._btn_frame, text="📸  Capture Sample",
                                      relief=tk.FLAT, font=("Arial", 11), padx=10,
                                      state=tk.DISABLED, command=self._capture_sample)
        self._capture_btn.pack(side="left", padx=4)
        self._cancel_btn = tk.Button(self._btn_frame, text="✖  Cancel",
                                     relief=tk.FLAT, font=("Arial", 11), padx=10,
                                     state=tk.DISABLED, command=self._stop_camera)
        self._cancel_btn.pack(side="left", padx=4)

        # Register button — enabled only after all samples captured
        self._register_btn = tk.Button(self._left_panel, text="✅  Register User",
                                       relief=tk.FLAT, font=("Arial", 12, "bold"), padx=14, pady=6,
                                       state=tk.DISABLED, command=self._save_user)
        self._register_btn.pack(fill="x", padx=4, pady=(4, 8))

        # ── right panel ──
        self._right_panel = tk.Frame(self._pane, padx=6)
        self._pane.add(self._right_panel, minsize=360)

        self._hdr_frame = tk.Frame(self._right_panel)
        self._hdr_frame.pack(fill="x", pady=(10, 2))
        self._user_list_title = tk.Label(self._hdr_frame, text="User List", font=("Arial", 14, "bold"))
        self._user_list_title.pack(side="left")
        self._refresh_btn = tk.Button(self._hdr_frame, text="🔄", relief=tk.FLAT, width=3,
                                      command=self._refresh_list)
        self._refresh_btn.pack(side="right")

        # ── search and sort ──
        self._search_sort_frame = tk.Frame(self._right_panel)
        self._search_sort_frame.pack(fill="x", pady=(0, 4))
        
        self._search_var = tk.StringVar()
        self._search_bar = SearchEntry(self._search_sort_frame, placeholder="Search users...", command=None, textvariable=self._search_var, entry_width=15)
        self._search_bar.pack(side="left", padx=(0, 10))
        
        self._sort_label = tk.Label(self._search_sort_frame, text="Sort by:")
        self._sort_label.pack(side="left")
        self._sort_var = tk.StringVar(value="ID (Desc)")
        self._sort_cb = ttk.Combobox(self._search_sort_frame, textvariable=self._sort_var, 
                               values=["ID (Desc)", "ID (Asc)", "Name (A-Z)", "School (A-Z)"], 
                               state="readonly", width=12)
        self._sort_cb.pack(side="left", padx=2)
        self._sort_cb.bind("<<ComboboxSelected>>", lambda e: self._refresh_list())

        self._count_label = tk.Label(self._search_sort_frame, text="", font=("Arial", 9))
        self._count_label.pack(side="right")

        tf = tk.Frame(self._right_panel)
        tf.pack(fill="both", expand=True)
        cols = ("ID", "Name", "School", "Place", "Type")
        widths = (50, 130, 120, 90, 60)
        self._tree = ttk.Treeview(tf, columns=cols, show="headings", height=14)
        for col, w in zip(cols, widths):
            self._tree.heading(col, text=col)
            self._tree.column(col, anchor="center", width=w)
        sb = ttk.Scrollbar(tf, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)
        self._tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        self._edit_remove_frame = tk.Frame(self._right_panel)
        self._edit_remove_frame.pack(pady=6)
        self._edit_btn = tk.Button(self._edit_remove_frame, text="✏  Edit", relief=tk.FLAT,
                                   command=self._edit_user)
        self._edit_btn.pack(side="left", padx=4)
        self._bulk_btn = tk.Button(self._edit_remove_frame, text="📋  Bulk Rename", relief=tk.FLAT,
                                   command=self._bulk_rename)
        self._bulk_btn.pack(side="left", padx=4)
        self._remove_btn = tk.Button(self._edit_remove_frame, text="🗑  Remove", relief=tk.FLAT,
                                     command=self._remove_user)
        self._remove_btn.pack(side="left", padx=4)

        # Space key to capture
        self.bind_all("<space>", lambda e: self._capture_sample() if self._running else None)
        
        # Register search trace after tree is initialized to prevent early trigger error
        self._search_var.trace_add("write", lambda *args: self._refresh_list())
        
        self.apply_theme()

    def apply_theme(self):
        t = get_theme()
        is_dark = (t.get("content_bg", "#ffffff") in ("#020617", "#0f172a"))
        
        self.config(bg=t["content_bg"])
        self._pane.config(bg=t["content_bg"])
        self._left_panel.config(bg=t["content_bg"])
        self._form_frame.config(bg=t["content_bg"])
        self._right_panel.config(bg=t["content_bg"])
        self._hdr_frame.config(bg=t["content_bg"])
        self._search_sort_frame.config(bg=t["content_bg"])
        self._btn_frame.config(bg=t["content_bg"])
        self._edit_remove_frame.config(bg=t["content_bg"])
        
        self._add_user_title.config(bg=t["content_bg"], fg=t["header_fg"])
        self._user_list_title.config(bg=t["content_bg"], fg=t["header_fg"])
        self._status.config(bg=t["content_bg"], fg=t["logo_sub_fg"] if is_dark else "#555")
        self._sort_label.config(bg=t["content_bg"], fg=t["header_fg"])
        self._count_label.config(bg=t["content_bg"], fg=t["logo_sub_fg"] if is_dark else "#7f8c8d")
        
        for lbl in self._form_labels:
            lbl.config(bg=t["content_bg"], fg=t["header_fg"])
            
        for ent in self._form_entries:
            ent.config(bg="#0f172a" if is_dark else "#ffffff", fg=t["header_fg"], 
                       insertbackground=t["header_fg"])
                       
        self._refresh_btn.config(bg=t["btn_secondary"], fg=t["btn_secondary_fg"],
                                 activebackground=t["btn_secondary"], activeforeground=t["btn_secondary_fg"])
                                 
        self._start_btn.config(bg=t["btn_primary"], fg=t["btn_primary_fg"],
                               activebackground=t["btn_primary"], activeforeground=t["btn_primary_fg"])
        self._capture_btn.config(bg=t["btn_primary"], fg=t["btn_primary_fg"],
                                 activebackground=t["btn_primary"], activeforeground=t["btn_primary_fg"])
        self._cancel_btn.config(bg=t["btn_danger"], fg="#ffffff",
                                activebackground=t["btn_danger"], activeforeground="#ffffff")
        self._register_btn.config(bg=t["btn_secondary"], fg=t["btn_secondary_fg"],
                                  activebackground=t["btn_secondary"], activeforeground=t["btn_secondary_fg"])
                                  
        self._edit_btn.config(bg=t.get("status_ok", "#27ae60"), fg="#ffffff",
                              activebackground=t.get("status_ok", "#27ae60"), activeforeground="#ffffff")
        self._bulk_btn.config(bg=t.get("btn_warning", "#8e44ad"), fg=t.get("btn_warning_fg", "#ffffff"),
                              activebackground=t.get("btn_warning", "#8e44ad"), activeforeground=t.get("btn_warning_fg", "#ffffff"))
        self._remove_btn.config(bg=t.get("btn_danger", "#e74c3c"), fg="#ffffff",
                                activebackground=t.get("btn_danger"), activeforeground="#ffffff")
                                
        self._search_bar.apply_theme()

    def on_show(self):
        self._refresh_list()

    def on_hide(self):
        self._stop_camera()

    # ── camera ──

    def _face_process(self, rgb, bgr):
        """
        InsightFace detection for live preview + distance guide.
        Stores latest faces for the Capture button.
        """
        h, w = bgr.shape[:2]
        cx, cy = w // 2, int(h * 0.45)
        ow, oh = int(w * 0.18), int(h * 0.40)

        faces = detect_faces(bgr)
        
        valid_faces = []
        bounds_violated = False
        for f in faces:
            left, top, right, bottom = f.bbox
            face_cx = (left + right) / 2
            face_cy = (top + bottom) / 2
            center_dist = ((face_cx - cx) ** 2 / (ow ** 2)) + ((face_cy - cy) ** 2 / (oh ** 2))
            
            # STRICT CHECK: Ensure the ENTIRE bounding box fits inside the oval's rectangular bounds
            if center_dist <= 0.15 and left >= cx - ow and right <= cx + ow and top >= cy - oh and bottom <= cy + oh:
                valid_faces.append(f)
            elif center_dist <= 1.5:
                bounds_violated = True
        faces = valid_faces

        mask = np.zeros((h, w), dtype=np.uint8)
        cv2.ellipse(mask, (cx, cy), (ow, oh), 0, 0, 360, 255, -1)
        blurred_bgr = cv2.GaussianBlur(bgr, (51, 51), 0)
        bgr = np.where(mask[:, :, None] == 255, bgr, blurred_bgr)

        locs  = faces_to_locations(faces)
        bgr, hint, _ = _draw_distance_guide(bgr, locs)
        
        if not faces and bounds_violated:
            hint = "Center your full face strictly inside the oval"
            (tw, th), _ = cv2.getTextSize(hint, cv2.FONT_HERSHEY_SIMPLEX, 0.70, 2)
            cv2.rectangle(bgr, (8, 8), (tw + 20, 45), (0, 0, 0), -1)
            cv2.putText(bgr, hint, (12, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.70, (0, 165, 255), 2)

        with self._lock:
            self._face_detected = bool(faces)
            self._cur_faces = faces
            self._cur_locs  = locs
            self._dist_hint = hint
        n = len(self._captured)
        cv2.putText(bgr, f"Samples: {n}/{self._SAMPLE_TARGET}",
                    (10, bgr.shape[0] - 12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        return bgr, None

    def _start_camera(self):
        name = self._name_var.get().strip()
        school = self._school_var.get().strip()
        place = self._place_var.get().strip()

        missing = []
        if not name:
            missing.append("Name")
        if not school:
            missing.append("School")
        if not place:
            missing.append("Place")

        if missing:
            messagebox.showwarning("Missing Fields", f"Please enter the following fields first: {', '.join(missing)}.")
            return
        if not any(c.isalpha() for c in name):
            messagebox.showwarning("Invalid Name", "Name must contain at least one letter.")
            return
        try:
            with sqlite3.connect(self._db) as conn:
                if conn.execute("SELECT user_id FROM users WHERE LOWER(user_name) = LOWER(?)", (name,)).fetchone():
                    messagebox.showwarning("Duplicate Name", "This username already exists. Please add an initial or last name.")
                    return
        except Exception:
            pass
        self._running = True
        self._captured = []
        self._dist_hint = ""
        self._progress["value"] = 0
        self._start_btn.config(state=tk.DISABLED)
        self._capture_btn.config(state=tk.NORMAL)
        self._cancel_btn.config(state=tk.NORMAL)
        self._status.config(text="Click 'Capture Sample' (or press Space) when your face is visible.",
                             fg="#2980b9")
        self._cam_thread = _CameraThread(_active_camera_index, self._face_process, process_every=3)
        self._cam_thread.start()
        self._render_loop()

    def _render_loop(self):
        if not self._running:
            return
        frame = self._cam_thread.latest_display() if self._cam_thread else None
        if frame is not None:
            photo = _frame_to_photoimage(frame)
            self._cam_label.config(image=photo)
            self._cam_label.image = photo
        # Update status with live distance hint
        with self._lock:
            hint = getattr(self, "_dist_hint", "")
        if hint:
            if "Perfect" in hint:
                self._status.config(text=hint, fg="#27ae60")
            elif "CLOSER" in hint or "BACK" in hint:
                self._status.config(text=hint, fg="#e67e22")
            else:
                self._status.config(text=hint, fg="#2980b9")
        self.after(30, self._render_loop)

    def _capture_sample(self):
        if not self._running:
            return
        with self._lock:
            face_detected = self._face_detected
            faces = list(self._cur_faces)
            locs  = list(self._cur_locs)
            hint  = getattr(self, "_dist_hint", "")
        if not face_detected or not faces:
            self._status.config(text="No face detected — align your face with the oval.", fg="red")
            return
        if "CLOSER" in hint or "BACK" in hint or "Center" in hint:
            self._status.config(text=f"⚠  {hint} before capturing.", fg="#e67e22")
            return
        # Use largest face (first after sort by area)
        face = faces[0]
        enc  = get_face_embedding(face)
        if enc is None or enc.shape[0] == 0:
            self._status.config(text="Could not read face. Improve lighting.", fg="red")
            return
        # Crop face region and save as JPEG bytes for display in Edit dialog
        import io
        x1, y1, x2, y2 = [int(v) for v in face.bbox]
        pad = 20
        # face.bbox is in BGR frame coords — grab from the current BGR frame
        # We don't have bgr here but we can reconstruct from the display label
        # Instead: use locs (top, right, bottom, left) which are already from bgr
        top, right_px, bottom, left_px = locs[0]
        # Use the last display frame held by the camera thread for the crop
        raw_frame = self._cam_thread.latest_display() if self._cam_thread else None
        if raw_frame is not None:
            crop_bgr  = raw_frame[max(0, top-pad):bottom+pad, max(0, left_px-pad):right_px+pad]
            crop_rgb  = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)
            pil_crop  = Image.fromarray(crop_rgb)
        else:
            pil_crop  = Image.new("RGB", (112, 112), (200, 200, 200))
        buf = io.BytesIO()
        pil_crop.save(buf, format="JPEG", quality=85)
        face_img_bytes = buf.getvalue()
        self._captured.append((enc, face_img_bytes))
        n = len(self._captured)
        self._progress["value"] = n
        if n >= self._SAMPLE_TARGET:
            # Signal the camera thread to stop but DON'T enable Register yet.
            # Poll every 50 ms until the thread has fully exited (cap.release()
            # called) to avoid VIDIOC_QBUF errors from the thread still
            # reading frames while we write to the database.
            self._running = False
            t = self._cam_thread
            self._cam_thread = None
            if t:
                t.stop()
            self._cam_label.config(image="", bg="#1a1a2e")
            self._cam_label.image = None
            self._capture_btn.config(state=tk.DISABLED)
            self._cancel_btn.config(state=tk.DISABLED)
            self._status.config(text="Finishing capture… please wait.", fg="#e67e22")
            self._wait_for_thread_exit(t)
        else:
            self._status.config(text=f"Captured {n}/{self._SAMPLE_TARGET} samples.", fg="#27ae60")


    def _wait_for_thread_exit(self, thread, retries=20):
        """Poll every 50 ms until camera thread is dead, then save."""
        if thread and thread.is_alive():
            if retries > 0:
                self.after(50, lambda: self._wait_for_thread_exit(thread, retries - 1))
                return
        # Thread confirmed dead — save immediately
        self._status.config(text="Saving user data…", fg="#e67e22")
        self.update_idletasks()
        self._run_save_with_progress()

    def _countdown(self, secs_left):
        """(Unused) Show a live countdown, then auto-save when it hits 0."""
        pass

    def _run_save_with_progress(self):
        """Run _save_user in a background thread using the inline progress bar."""
        name   = self._name_var.get().strip()
        school = self._school_var.get().strip()
        place  = self._place_var.get().strip()

        # Validate before opening the window
        if not name:
            messagebox.showwarning("Missing Name", "Please enter the user's name.")
            self._register_btn.config(state=tk.NORMAL)
            self._status.config(text="Please fix the name and click 'Register User'.", fg="red")
            return
        if not any(c.isalpha() for c in name):
            messagebox.showwarning("Invalid Name", "Name must contain at least one letter.")
            self._register_btn.config(state=tk.NORMAL)
            self._status.config(text="Please fix the name and click 'Register User'.", fg="red")
            return
        if not self._captured:
            messagebox.showwarning("No Face Data", "No face samples found. Please capture again.")
            self._start_btn.config(state=tk.NORMAL)
            return
            
        try:
            with sqlite3.connect(self._db) as conn:
                if conn.execute("SELECT user_id FROM users WHERE LOWER(user_name) = LOWER(?)", (name,)).fetchone():
                    messagebox.showwarning("Duplicate Name", "This username already exists. Please add an initial or last name.")
                    self._register_btn.config(state=tk.NORMAL)
                    self._status.config(text="Please fix the name and click 'Register User'.", fg="red")
                    return
        except Exception:
            pass

        # Use inline progress bar
        self._progress.config(mode="indeterminate")
        self._progress.start(15)
        self.update_idletasks()

        captured_copy = list(self._captured)
        result_holder = {}

        def _do_save():
            try:
                # ── Dedup: majority-vote across all captured samples ──
                # A match is only flagged if ≥ 3 of 4 samples point to the
                # same registered user AND all pass a strict threshold.
                # This prevents a single noisy sample or a look-alike from
                # blocking a legitimate new registration.
                known = get_known_encodings(db_file=self._db)
                if known:
                    from collections import Counter as _Counter
                    votes = _Counter()
                    for enc, _img in captured_copy:
                        uid, ename = find_matching_face(known, enc, tolerance=ENROLL_THRESHOLD)
                        if uid:
                            votes[(uid, ename)] += 1
                    if votes:
                        (match_uid, match_name), count = votes.most_common(1)[0]
                        needed = max(3, len(captured_copy) - 1)  # 3-of-4
                        if count >= needed:
                            # Fetch stored face photo for visual confirmation
                            try:
                                with sqlite3.connect(self._db) as conn:
                                    row = conn.execute(
                                        "SELECT face_image FROM face_encodings "
                                        "WHERE user_id=? AND face_image IS NOT NULL LIMIT 1",
                                        (match_uid,)).fetchone()
                                stored_img = row[0] if row else None
                            except Exception:
                                stored_img = None
                            result_holder["dup"] = (match_uid, match_name, count,
                                                    len(captured_copy), stored_img)
                            return
            except Exception as e:
                print(f"[dedup warning] {e}")

            try:
                with sqlite3.connect(self._db) as conn:
                    c = conn.cursor()
                    c.execute(
                        "INSERT INTO users (user_name, school, place) VALUES (?,?,?)",
                        (name, school, place))
                    new_uid = c.lastrowid
                    for enc, img_bytes in captured_copy:
                        c.execute(
                            "INSERT INTO face_encodings (user_id, face_encoding, face_image) "
                            "VALUES (?,?,?)",
                            (new_uid, pickle.dumps(enc), img_bytes))
                    conn.commit()
                result_holder["ok"] = new_uid
            except Exception as e:
                result_holder["error"] = str(e)

        def _after_save():
            self._progress.stop()
            self._progress.config(mode="determinate")
            self._progress["value"] = 0

            if "dup" in result_holder:
                match_uid, match_name, count, total, stored_img = result_holder["dup"]
                self._show_dup_dialog(match_uid, match_name, count, total,
                                      stored_img, name, school, place, captured_copy)

            elif "error" in result_holder:
                messagebox.showerror("Registration Failed",
                                     f"Could not save user:\n\n{result_holder['error']}")
                self._start_btn.config(state=tk.NORMAL)

            elif "ok" in result_holder:
                new_uid = result_holder["ok"]
                self._captured = []
                self._progress["value"] = 0
                self._register_btn.config(state=tk.DISABLED)
                self._name_var.set("")
                self._school_var.set("")
                self._place_var.set("")
                self._status.config(text="", fg="#555")
                self._refresh_list()
                self._start_btn.config(state=tk.NORMAL)
                messagebox.showinfo(
                    "Registration Successful",
                    f"✅  User registered successfully!\n\n"
                    f"  Name   : {name}\n"
                    f"  School : {school or '—'}\n"
                    f"  Place  : {place or '—'}\n"
                    f"  User ID: {new_uid}")
            else:
                self._start_btn.config(state=tk.NORMAL)

        def _thread_target():
            _do_save()
            self.after(0, _after_save)

        threading.Thread(target=_thread_target, daemon=True).start()

    def _show_dup_dialog(self, match_uid, match_name, count, total,
                         stored_img, new_name, new_school, new_place, captured_copy):
        """Show the duplicate-face dialog with stored photo + Register Anyway option."""
        import io as _io

        dlg = tk.Toplevel(self)
        dlg.title("Possible Duplicate Detected")
        dlg.transient(self.winfo_toplevel())
        try:
            dlg.wait_visibility()
            dlg.grab_set()
        except tk.TclError:
            pass
        dlg.lift()
        dlg.resizable(False, False)

        tk.Label(dlg, text="⚠  Possible Duplicate Face",
                 font=("Arial", 13, "bold"), fg="#e67e22", pady=8).pack()
        tk.Label(dlg,
                 text=f"{count} of {total} face samples matched an existing user.\n"
                      "Please compare the photos below before deciding.",
                 font=("Arial", 10), justify="center", wraplength=420).pack(pady=(0, 8))

        photos_frame = tk.Frame(dlg)
        photos_frame.pack(padx=16, pady=4)

        # Left: stored registered photo
        left = tk.LabelFrame(photos_frame, text="Existing registered user", padx=6, pady=6)
        left.grid(row=0, column=0, padx=10)
        if stored_img:
            try:
                pil = Image.open(_io.BytesIO(stored_img)).resize((140, 140))
                ph = ImageTk.PhotoImage(pil)
                lbl = tk.Label(left, image=ph)
                lbl.image = ph
                lbl.pack()
            except Exception:
                tk.Label(left, text="(no photo)", fg="#888").pack()
        else:
            tk.Label(left, text="(no photo\nstored)", fg="#888").pack()
        tk.Label(left, text=f"Name: {match_name}\nID: {match_uid}",
                 font=("Arial", 9), fg="#555").pack(pady=4)

        # Right: newly captured photo (first sample)
        right = tk.LabelFrame(photos_frame, text="New capture (registering now)", padx=6, pady=6)
        right.grid(row=0, column=1, padx=10)
        if captured_copy:
            try:
                _, img_bytes = captured_copy[0]
                pil2 = Image.open(_io.BytesIO(img_bytes)).resize((140, 140))
                ph2 = ImageTk.PhotoImage(pil2)
                lbl2 = tk.Label(right, image=ph2)
                lbl2.image = ph2
                lbl2.pack()
            except Exception:
                tk.Label(right, text="(no photo)", fg="#888").pack()
        tk.Label(right, text=f"Name: {new_name}\n(new)",
                 font=("Arial", 9), fg="#555").pack(pady=4)

        btn_frame = tk.Frame(dlg)
        btn_frame.pack(pady=10)

        def _force_register():
            dlg.destroy()
            self._do_force_register(new_name, new_school, new_place, captured_copy)

        def _cancel():
            dlg.destroy()
            self._start_btn.config(state=tk.NORMAL)
            self._status.config(
                text="Registration cancelled. Re-capture if needed.", fg="#e67e22")

        tk.Button(btn_frame, text="✅  Register Anyway\n(different person)",
                  bg="#27ae60", fg="white", font=("Arial", 10, "bold"),
                  relief=tk.FLAT, padx=10, pady=6,
                  command=_force_register).grid(row=0, column=0, padx=8)
        tk.Button(btn_frame, text="✖  Cancel\n(same person)",
                  bg="#e74c3c", fg="white", font=("Arial", 10, "bold"),
                  relief=tk.FLAT, padx=10, pady=6,
                  command=_cancel).grid(row=0, column=1, padx=8)

    def _do_force_register(self, name, school, place, captured_copy):
        """Save user unconditionally (admin confirmed it's a different person)."""
        try:
            with sqlite3.connect(self._db) as conn:
                c = conn.cursor()
                c.execute("INSERT INTO users (user_name, school, place) VALUES (?,?,?)",
                          (name, school, place))
                new_uid = c.lastrowid
                for enc, img_bytes in captured_copy:
                    c.execute(
                        "INSERT INTO face_encodings (user_id, face_encoding, face_image) "
                        "VALUES (?,?,?)",
                        (new_uid, pickle.dumps(enc), img_bytes))
                conn.commit()
            self._captured = []
            self._progress["value"] = 0
            self._register_btn.config(state=tk.DISABLED)
            self._name_var.set("")
            self._school_var.set("")
            self._place_var.set("")
            self._status.config(text="", fg="#555")
            self._refresh_list()
            self._start_btn.config(state=tk.NORMAL)
            messagebox.showinfo(
                "Registration Successful",
                f"✅  User registered successfully!\n\n"
                f"  Name   : {name}\n"
                f"  School : {school or '—'}\n"
                f"  Place  : {place or '—'}\n"
                f"  User ID: {new_uid}")
        except Exception as e:
            self._start_btn.config(state=tk.NORMAL)
            messagebox.showerror("Registration Failed", f"Could not save user:\n\n{e}")

    def _save_user(self):
        """Called by the Register button — delegates to the progress-based save."""
        self._run_save_with_progress()

    def _stop_camera(self, msg=None, reset_register=True):
        self._running = False
        if self._cam_thread:
            t = self._cam_thread
            self._cam_thread = None
            t.stop()
            threading.Thread(target=lambda: t.join(timeout=2.0), daemon=True).start()
        self._cam_label.config(image="", bg="#1a1a2e")
        self._cam_label.image = None
        self._start_btn.config(state=tk.NORMAL)
        self._capture_btn.config(state=tk.DISABLED)
        self._cancel_btn.config(state=tk.DISABLED)
        if reset_register:
            self._register_btn.config(state=tk.DISABLED)
        if msg:
            self._status.config(text=msg, fg="red")

    def _restart_camera(self):
        """Called when admin changes the camera selection mid-session."""
        if self._running:
            self._stop_camera(reset_register=False)
            self.after(300, self._start_camera)

    # ── user list ──

    def _refresh_list(self):
        for i in self._tree.get_children():
            self._tree.delete(i)
            
        search_query = self._search_var.get().strip().lower()
        sort_opt = self._sort_var.get()
        
        order_by = "user_id DESC"
        if sort_opt == "ID (Asc)":
            order_by = "user_id ASC"
        elif sort_opt == "Name (A-Z)":
            order_by = "user_name COLLATE NOCASE ASC"
        elif sort_opt == "School (A-Z)":
            order_by = "school COLLATE NOCASE ASC"
            
        try:
            with sqlite3.connect(self._db) as conn:
                if search_query:
                    # Using LIKE for search
                    wildcard = f"%{search_query}%"
                    rows = conn.execute(
                        f"SELECT user_id, user_name, COALESCE(school,''), COALESCE(place,''), type "
                        f"FROM users "
                        f"WHERE LOWER(user_name) LIKE ? OR CAST(user_id AS TEXT) LIKE ? OR LOWER(COALESCE(school,'')) LIKE ? "
                        f"ORDER BY {order_by}",
                        (wildcard, wildcard, wildcard)
                    ).fetchall()
                else:
                    rows = conn.execute(
                        f"SELECT user_id, user_name, COALESCE(school,''), COALESCE(place,''), type "
                        f"FROM users ORDER BY {order_by}"
                    ).fetchall()
            for r in rows:
                self._tree.insert("", "end", values=r)
            self._count_label.config(text=f"{len(rows)} user(s)")
        except Exception:
            pass

    def _edit_user(self):
        """Open Edit User dialog: shows registered face photos + editable name/school/place."""
        sel = self._tree.selection()
        if not sel:
            self._status.config(text="Select a user from the list to edit.", fg="red")
            return
        vals = self._tree.item(sel[0])["values"]
        uid = vals[0]

        # Load current profile
        try:
            with sqlite3.connect(self._db) as conn:
                row = conn.execute(
                    "SELECT user_name, COALESCE(school,''), COALESCE(place,''), type "
                    "FROM users WHERE user_id=?", (uid,)).fetchone()
                face_images = conn.execute(
                    "SELECT face_image FROM face_encodings WHERE user_id=? AND face_image IS NOT NULL",
                    (uid,)).fetchall()
        except Exception as e:
            self._status.config(text=f"DB error: {e}", fg="red")
            return

        if not row:
            self._status.config(text="User not found.", fg="red")
            return

        cur_name, cur_school, cur_place, cur_type = row

        dlg = tk.Toplevel(self)
        dlg.title(f"Edit User — ID {uid}")
        dlg.transient(self.winfo_toplevel())
        try:
            dlg.wait_visibility()
            dlg.grab_set()
        except tk.TclError:
            pass
        dlg.lift()
        dlg.resizable(False, False)

        tk.Label(dlg, text=f"Editing User ID: {uid}", font=("Arial", 13, "bold"),
                 pady=6).pack()

        # ── Registered face photos ──
        photos_frame = tk.LabelFrame(dlg, text="Registered Face Photos", padx=8, pady=6)
        photos_frame.pack(fill="x", padx=12, pady=(0, 8))

        if face_images:
            import io
            thumb_refs = []  # keep references so GC doesn't collect them
            for idx, (img_blob,) in enumerate(face_images[:6]):  # max 6 thumbnails
                try:
                    pil_img = Image.open(io.BytesIO(img_blob)).resize((96, 96))
                    photo = ImageTk.PhotoImage(pil_img)
                    lbl = tk.Label(photos_frame, image=photo, relief=tk.RIDGE, bd=2)
                    lbl.grid(row=0, column=idx, padx=4, pady=4)
                    thumb_refs.append(photo)
                except Exception:
                    pass
            dlg._thumb_refs = thumb_refs  # attach to dialog to prevent GC
        else:
            tk.Label(photos_frame,
                     text="No face photos saved.\n(Photos are saved for new registrations.)",
                     fg="#888", font=("Arial", 9)).pack(pady=8)

        # ── Editable fields ──
        fields_frame = tk.LabelFrame(dlg, text="Profile Details", padx=10, pady=8)
        fields_frame.pack(fill="x", padx=12, pady=4)

        vars_map = {}
        for r, (lbl, key, cur_val) in enumerate([
            ("Name:",   "name",   cur_name),
            ("School:", "school", cur_school),
            ("Place:",  "place",  cur_place),
        ]):
            tk.Label(fields_frame, text=lbl, width=8, anchor="e").grid(row=r, column=0, pady=4, padx=4)
            v = tk.StringVar(value=str(cur_val))
            vars_map[key] = v
            tk.Entry(fields_frame, textvariable=v, width=30, font=("Arial", 11)).grid(
                row=r, column=1, pady=4, padx=4, sticky="w")

        err_lbl = tk.Label(dlg, text="", font=("Arial", 10), fg="red")
        err_lbl.pack(pady=2)

        def _save():
            new_name   = vars_map["name"].get().strip()
            new_school = vars_map["school"].get().strip()
            new_place  = vars_map["place"].get().strip()
            if not new_name:
                err_lbl.config(text="Name cannot be empty.")
                return
            if not any(c.isalpha() for c in new_name):
                err_lbl.config(text="Name must contain at least one letter.")
                return
            try:
                with sqlite3.connect(self._db) as conn:
                    if conn.execute("SELECT user_id FROM users WHERE LOWER(user_name) = LOWER(?) AND user_id != ?", (new_name, uid)).fetchone():
                        messagebox.showwarning("Duplicate Name", "This username already exists. Please add an initial or last name.")
                        return
                    conn.execute(
                        "UPDATE users SET user_name=?, school=?, place=? WHERE user_id=?",
                        (new_name, new_school, new_place, uid))
                    conn.commit()
                self._status.config(text=f"User ID {uid} updated successfully.", fg="#27ae60")
                self._refresh_list()
                dlg.destroy()
            except Exception as e:
                err_lbl.config(text=f"Error: {e}")

        bf = tk.Frame(dlg)
        bf.pack(pady=8)
        tk.Button(bf, text="💾  Save Changes", bg="#27ae60", fg="white", font=("Arial", 11),
                  relief=tk.FLAT, command=_save).pack(side="left", padx=6)
        tk.Button(bf, text="✖  Cancel", bg="#e74c3c", fg="white", font=("Arial", 11),
                  relief=tk.FLAT, command=dlg.destroy).pack(side="left", padx=6)

    def _bulk_rename(self):
        """Open a dialog to paste id,name pairs and rename multiple users at once."""
        from tkinter import simpledialog
        instructions = (
            "Paste one entry per line in the format:\n"
            "   user_id, new_name\n\n"
            "Example:\n"
            "   65, Arjun Kumar\n"
            "   56, Priya Nair\n"
            "   68, Rohit Sharma\n\n"
            "Current users with numeric names are shown in the list on the right."
        )
        # Show dialog with a Text widget for multi-line input
        dlg = tk.Toplevel(self)
        dlg.title("Bulk Rename Users")
        dlg.transient(self.winfo_toplevel())
        try:
            dlg.wait_visibility()
            dlg.grab_set()
        except tk.TclError:
            pass
        dlg.lift()
        dlg.resizable(False, False)
        tk.Label(dlg, text=instructions, justify="left", font=("Arial", 10),
                 padx=12, pady=8).pack(anchor="w")
        text_box = tk.Text(dlg, width=40, height=12, font=("Courier", 11))
        text_box.pack(padx=12, pady=4)
        # Pre-fill with numeric-named users as hints
        try:
            with sqlite3.connect(self._db) as conn:
                rows = conn.execute(
                    "SELECT user_id, user_name FROM users ORDER BY user_id").fetchall()
            for uid, uname in rows:
                if str(uname).strip().isdigit():
                    text_box.insert("end", f"{uid}, {uname}\n")
        except Exception:
            pass

        status_lbl = tk.Label(dlg, text="", font=("Arial", 10), fg="#27ae60")
        status_lbl.pack(pady=2)

        def _apply():
            raw = text_box.get("1.0", "end").strip()
            updated = 0
            errors = []
            try:
                with sqlite3.connect(self._db) as conn:
                    for line in raw.splitlines():
                        line = line.strip()
                        if not line:
                            continue
                        parts = line.split(",", 1)
                        if len(parts) != 2:
                            errors.append(f"Bad line: {line!r}")
                            continue
                        uid_s, new_name = parts[0].strip(), parts[1].strip()
                        if not uid_s.isdigit():
                            errors.append(f"Bad ID: {uid_s!r}")
                            continue
                        if not new_name or not any(c.isalpha() for c in new_name):
                            errors.append(f"Skipped invalid name for ID {uid_s}")
                            continue
                        conn.execute("UPDATE users SET user_name=? WHERE user_id=?",
                                     (new_name, int(uid_s)))
                        updated += 1
                    conn.commit()
            except Exception as e:
                status_lbl.config(text=f"Error: {e}", fg="red")
                return
            msg = f"Updated {updated} user(s)."
            if errors:
                msg += "  Skipped: " + "; ".join(errors)
            status_lbl.config(text=msg, fg="#27ae60" if not errors else "#e67e22")
            self._refresh_list()
            if not errors:
                dlg.after(1200, dlg.destroy)

        tk.Button(dlg, text="Apply Renames", bg="#8e44ad", fg="white",
                  command=_apply).pack(pady=6)

    def _remove_user(self):
        sel = self._tree.selection()
        if not sel:
            self._status.config(text="Select a user from the list to remove.", fg="red")
            return
        vals = self._tree.item(sel[0])["values"]
        uid, uname = vals[0], vals[1]
        if messagebox.askyesno("Remove User", f"Remove user '{uname}' (ID {uid})?\nThis also deletes all their face encodings."):
            remove_user(uid, db_file=self._db)
            self._status.config(text=f"User '{uname}' removed.", fg="#27ae60")
            self._refresh_list()


# ─── Product Manager page ─────────────────────────────────────────────────────

class ProductManagerPage(Page):
    def __init__(self, parent, db_file, **kw):
        super().__init__(parent, **kw)
        self._db = db_file
        self._checked_items = {}

        self._frame = tk.Frame(self, padx=16, pady=10)
        self._frame.pack(fill="both", expand=True)

        self._title_lbl = tk.Label(self._frame, text="Product Manager", font=("Arial", 15, "bold"))
        self._title_lbl.pack(pady=(0, 8))

        # entry + buttons row
        self._ef = tk.Frame(self._frame)
        self._ef.pack(fill="x")
        self._entry = tk.Entry(self._ef, width=30, font=("Arial", 11))
        self._entry.pack(side="left", padx=(0, 8))
        self._entry.bind("<Return>", lambda e: self._add_item())
        self._add_btn = tk.Button(self._ef, text="➕ Add", relief=tk.FLAT,
                                  command=self._add_item)
        self._add_btn.pack(side="left", padx=4)

        # search row
        self._sf = tk.Frame(self._frame)
        self._sf.pack(fill="x", pady=6)
        self._search_var = tk.StringVar()
        self._search_bar = SearchEntry(self._sf, placeholder="Search products...", command=self._search, textvariable=self._search_var, entry_width=24)
        self._search_bar.pack(side="left")
        
        self._refresh_btn = tk.Button(self._sf, text="🔄", command=self._refresh, relief=tk.FLAT)
        self._refresh_btn.pack(side="left", padx=4)

        # tree
        tf = tk.Frame(self._frame)
        tf.pack(fill="both", expand=True)
        self._tree = ttk.Treeview(tf, columns=("Select", "Product ID", "Product Name"), show="headings")
        self._tree.tag_configure("checked", background="#d5f5e3")
        self._tree.heading("Select",       text="Select")
        self._tree.heading("Product ID",   text="Product ID")
        self._tree.heading("Product Name", text="Product Name")
        self._tree.column("Select",       width=60, anchor="center")
        self._tree.column("Product ID",   width=130, anchor="center")
        self._tree.column("Product Name", width=260, anchor="center")
        sb = ttk.Scrollbar(tf, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)
        self._tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self._tree.bind("<<TreeviewSelect>>", self._on_select)
        self._tree.bind("<Double-1>", self._on_double_click)
        self._tree.bind("<Button-1>", self._on_tree_click)

        # QR row
        self._qf = tk.Frame(self._frame)
        self._qf.pack(pady=8)
        import math, qrcode as _qrcode
        from PIL import ImageFont, ImageDraw
        self._qrcode = _qrcode
        self._math = math
        self._ImageFont = ImageFont
        self._ImageDraw = ImageDraw

        self._size_cb = ttk.Combobox(self._qf, values=["20", "25", "30"], state="readonly", width=8)
        self._size_cb.set("25")
        self._size_cb.pack(side="left", padx=6)
        self._gen_qr_btn = tk.Button(self._qf, text="📄 Generate QR", relief=tk.FLAT,
                                     command=self._generate_qr)
        self._gen_qr_btn.pack(side="left", padx=6)

        self._bulk_print_btn = tk.Button(self._qf, text="📑 Bulk Print Listed", relief=tk.FLAT,
                                         command=self._generate_bulk_qr)
        self._bulk_print_btn.pack(side="left", padx=6)

        self._status = tk.Label(self._frame, text="", font=("Arial", 10))
        self._status.pack()

        self._conn = sqlite3.connect(db_file)
        self._cursor = self._conn.cursor()
        self._refresh()

        self.apply_theme()

    def apply_theme(self):
        t = get_theme()
        is_dark = (t.get("content_bg", "#ffffff") in ("#020617", "#0f172a"))
        
        self.config(bg=t["content_bg"])
        self._frame.config(bg=t["content_bg"])
        self._title_lbl.config(bg=t["content_bg"], fg=t["header_fg"])
        self._ef.config(bg=t["content_bg"])
        self._sf.config(bg=t["content_bg"])
        self._qf.config(bg=t["content_bg"])
        
        self._entry.config(bg="#0f172a" if is_dark else "#ffffff", fg=t["header_fg"],
                           insertbackground=t["header_fg"])
                           
        self._add_btn.config(bg=t["btn_primary"], fg=t["btn_primary_fg"],
                             activebackground=t["btn_primary"], activeforeground=t["btn_primary_fg"])
        self._refresh_btn.config(bg=t["btn_secondary"], fg=t["btn_secondary_fg"],
                                 activebackground=t["btn_secondary"], activeforeground=t["btn_secondary_fg"])
        self._gen_qr_btn.config(bg=t["btn_primary"], fg=t["btn_primary_fg"],
                                activebackground=t["btn_primary"], activeforeground=t["btn_primary_fg"])
        self._bulk_print_btn.config(bg=t["btn_secondary"], fg=t["btn_secondary_fg"],
                                    activebackground=t["btn_secondary"], activeforeground=t["btn_secondary_fg"])
                                    
        self._status.config(bg=t["content_bg"], fg=t["logo_sub_fg"] if is_dark else "#555")
        self._search_bar.apply_theme()

    def on_show(self):
        self._refresh()

    def _add_item(self):
        name = self._entry.get().strip()
        if not name:
            self._status.config(text="Enter a product name.", fg="red")
            return
        self._cursor.execute("INSERT INTO items (product_name) VALUES (?)", (name,))
        self._conn.commit()
        self._entry.delete(0, tk.END)
        self._status.config(text="Product added.", fg="#27ae60")
        messagebox.showinfo("Success", f"Product '{name}' added successfully!")
        self._refresh()

    def _refresh(self):
        self._search_bar.clear(trigger_command=False)
        self._load_items()

    def _search(self):
        term = self._search_bar.get().strip()
        self._load_items(term)

    def _load_items(self, term=None):
        for i in self._tree.get_children():
            self._tree.delete(i)
        self._checked_items.clear()
        if term:
            self._cursor.execute(
                "SELECT 'slof_'||id, product_name FROM items WHERE product_name LIKE ? OR ('slof_'||id) LIKE ?",
                (f"%{term}%", f"%{term}%"))
        else:
            self._cursor.execute("SELECT 'slof_'||id, product_name FROM items")
        for row in self._cursor.fetchall():
            item_id = self._tree.insert("", tk.END, values=("☐", row[0], row[1]))
            self._checked_items[item_id] = False

    def _on_select(self, _event=None):
        sel = self._tree.selection()
        self._entry.delete(0, tk.END)
        if len(sel) == 1:
            name = self._tree.item(sel[0])["values"][2]
            self._entry.insert(0, name)
        elif len(sel) > 1:
            self._entry.insert(0, f"[{len(sel)} items selected]")

    def _on_tree_click(self, event):
        region = self._tree.identify_region(event.x, event.y)
        if region != "cell":
            return

        column = self._tree.identify_column(event.x)
        if column == "#1":  # "Select" column
            item_id = self._tree.identify_row(event.y)
            if not item_id:
                return
            is_checked = not self._checked_items.get(item_id, False)
            self._checked_items[item_id] = is_checked
            current_values = self._tree.item(item_id, "values")
            new_char = "✅" if is_checked else "☐"
            self._tree.item(item_id, values=(new_char, current_values[1], current_values[2]))
            
            if is_checked:
                self._tree.item(item_id, tags=("checked",))
            else:
                self._tree.item(item_id, tags=())

    def _on_double_click(self, event):
        sel = self._tree.selection()
        if not sel:
            return
        
        item = self._tree.item(sel[0])
        pid = item["values"][1]
        pname = item["values"][2]
        
        dlg = tk.Toplevel(self)
        dlg.title(pid)
        dlg.transient(self.winfo_toplevel())
        try:
            dlg.wait_visibility()
            dlg.grab_set()
        except tk.TclError:
            pass
        dlg.lift()
        dlg.resizable(False, False)
        
        tk.Label(dlg, text="Product Details", font=("Arial", 14, "bold")).pack(pady=10)
        
        f = tk.Frame(dlg, padx=20, pady=10)
        f.pack(fill="both", expand=True)
        
        tk.Label(f, text="Product ID:", font=("Arial", 11, "bold")).grid(row=0, column=0, sticky="e", pady=5, padx=5)
        tk.Label(f, text=pid, font=("Arial", 11)).grid(row=0, column=1, sticky="w", pady=5, padx=5)
        
        tk.Label(f, text="Product Name:", font=("Arial", 11, "bold")).grid(row=1, column=0, sticky="e", pady=5, padx=5)
        
        name_var = tk.StringVar(value=pname)
        name_entry = tk.Entry(f, textvariable=name_var, font=("Arial", 11), state="disabled", width=25)
        name_entry.grid(row=1, column=1, sticky="w", pady=5, padx=5)
        
        btn_frame = tk.Frame(dlg, pady=10)
        btn_frame.pack()
        
        def _edit():
            name_entry.config(state="normal")
            name_entry.focus()
            edit_btn.config(text="Save Changes", command=_save, bg="#27ae60")
            
        def _save():
            new_name = name_var.get().strip()
            if not new_name:
                messagebox.showwarning("Warning", "Product name cannot be empty.", parent=dlg)
                return
            item_id = str(pid).replace("slof_", "")
            self._cursor.execute("UPDATE items SET product_name=? WHERE id=?", (new_name, item_id))
            self._conn.commit()
            self._refresh()
            self._status.config(text="Product modified.", fg="#27ae60")
            messagebox.showinfo("Success", "Product updated successfully.", parent=dlg)
            dlg.destroy()
            
        def _remove():
            if messagebox.askyesno("Confirm Remove", f"Are you sure you want to remove this product permanently?\n\nProduct: {pname}", parent=dlg):
                item_id = str(pid).replace("slof_", "")
                self._cursor.execute("DELETE FROM items WHERE id=?", (item_id,))
                self._conn.commit()
                self._refresh()
                self._status.config(text="Product removed.", fg="#e74c3c")
                messagebox.showinfo("Removed", "The product was removed.", parent=dlg)
                dlg.destroy()

        edit_btn = tk.Button(btn_frame, text="Edit", bg="#f39c12", fg="white", font=("Arial", 11), relief=tk.FLAT, command=_edit, width=12)
        edit_btn.grid(row=0, column=0, padx=10)
        
        remove_btn = tk.Button(btn_frame, text="Remove", bg="#e74c3c", fg="white", font=("Arial", 11), relief=tk.FLAT, command=_remove, width=12)
        remove_btn.grid(row=0, column=1, padx=10)

        def _download_qr():
            import os, math, qrcode
            from PIL import Image, ImageFont, ImageDraw
            
            box_size = max(1, math.ceil(25 / 0.264583) // 21)
            qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=box_size, border=1)
            qr.add_data(pid)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
            
            try:
                font = ImageFont.truetype("calibri.ttf", 14)
            except Exception:
                font = ImageFont.load_default()
                
            d = ImageDraw.Draw(img)
            tb = d.textbbox((0, 0), pid, font=font)
            tw, th = tb[2]-tb[0], tb[3]-tb[1]
            iw, ih = img.size
            new_img = Image.new("RGB", (iw, ih + th + 4), "white")
            new_img.paste(img, (0, 0))
            ImageDraw.Draw(new_img).text(((iw-tw)//2, ih), pid, font=font, fill="black")
            
            new_img.show()
            
            downloads_dir = os.path.join(os.path.expanduser('~'), 'Downloads')
            os.makedirs(downloads_dir, exist_ok=True)
            path = os.path.join(downloads_dir, f"{pid}.png")
            new_img.save(path)
            messagebox.showinfo("Downloaded", f"QR Code saved to Downloads folder:\n{path}", parent=dlg)

        dl_btn = tk.Button(dlg, text="⬇ Download QR Code", bg="#9b59b6", fg="white", font=("Arial", 11), relief=tk.FLAT, command=_download_qr, width=20)
        dl_btn.pack(pady=(0, 10))

    def _generate_qr(self):
        sel = self._tree.selection()
        if not sel:
            self._status.config(text="Select a product first.", fg="red")
            return
        pid = str(self._tree.item(sel[0])["values"][1])
        size_mm = int(self._size_cb.get())
        box_size = max(1, self._math.ceil(size_mm / 0.264583) // 21)
        qr = self._qrcode.QRCode(version=1,
                                  error_correction=self._qrcode.constants.ERROR_CORRECT_L,
                                  box_size=box_size, border=1)
        qr.add_data(pid)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
        try:
            font = self._ImageFont.truetype("calibri.ttf", 14)
        except Exception:
            font = self._ImageFont.load_default()
        d = self._ImageDraw.Draw(img)
        tb = d.textbbox((0, 0), pid, font=font)
        tw, th = tb[2]-tb[0], tb[3]-tb[1]
        iw, ih = img.size
        new_img = Image.new("RGB", (iw, ih + th + 4), "white")
        new_img.paste(img, (0, 0))
        self._ImageDraw.Draw(new_img).text(((iw-tw)//2, ih), pid, font=font, fill="black")
        os.makedirs("QR_codes", exist_ok=True)
        path = os.path.join("QR_codes", f"{pid}.png")
        new_img.save(path)
        new_img.show()
        self._status.config(text=f"QR saved to {path}", fg="#27ae60")

    def _generate_bulk_qr(self):
        items = [item_id for item_id, checked in self._checked_items.items() if checked]

        if not items:
            self._status.config(text="No items checked to generate.", fg="red")
            return
            
        if not messagebox.askyesno("Confirm Bulk Print", f"Are you sure you want to print QR codes for {len(items)} checked item(s)?"):
            self._status.config(text="Bulk print cancelled.", fg="#e67e22")
            return

        self._bulk_print_btn.config(state=tk.DISABLED)
        self._status.config(text="Generating PDF... please wait.", fg="#2980b9")
        
        item_data = []
        for item_id in items:
            values = self._tree.item(item_id)["values"]
            item_data.append({'pid': str(values[1]), 'pname': str(values[2])})
            
        threading.Thread(target=self._pdf_worker, args=(item_data,), daemon=True).start()

    def _pdf_worker(self, item_data):
        try:
            import os, time
            from PIL import Image
            
            A4_W, A4_H = 2480, 3508
            CELL_W, CELL_H = 370, 460
            GAP = 24  # approx 2mm safety gap
            COLS = (A4_W + GAP) // (CELL_W + GAP)
            ROWS = (A4_H + GAP) // (CELL_H + GAP)
            MARGIN_X = (A4_W - (COLS * CELL_W + (COLS - 1) * GAP)) // 2
            MARGIN_Y = (A4_H - (ROWS * CELL_H + (ROWS - 1) * GAP)) // 2
            
            pages = []
            current_page = None
            x_idx, y_idx = 0, 0
            
            for item in item_data:
                pid, pname = item['pid'], item['pname']
                
                if current_page is None:
                    current_page = Image.new("RGB", (A4_W, A4_H), "white")
                    pages.append(current_page)
                    x_idx, y_idx = 0, 0
                    
                qr = self._qrcode.QRCode(version=1, error_correction=self._qrcode.constants.ERROR_CORRECT_L, box_size=14, border=1)
                qr.add_data(pid)
                qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
                
                try:
                    font = self._ImageFont.truetype("calibri.ttf", 36)
                    font_small = self._ImageFont.truetype("calibri.ttf", 24)
                except Exception:
                    font, font_small = self._ImageFont.load_default(), self._ImageFont.load_default()
                    
                d = self._ImageDraw.Draw(qr_img)
                tb_id = d.textbbox((0, 0), pid, font=font)
                tw_id, th_id = tb_id[2]-tb_id[0], tb_id[3]-tb_id[1]
                
                short_name = pname[:20] + "..." if len(pname) > 20 else pname
                tb_name = d.textbbox((0, 0), short_name, font=font_small)
                tw_name, th_name = tb_name[2]-tb_name[0], tb_name[3]-tb_name[1]
                
                qw, qh = qr_img.size
                
                cell_img = Image.new("RGB", (CELL_W, CELL_H), "white")
                draw_cell = self._ImageDraw.Draw(cell_img)
                draw_cell.rectangle([0, 0, CELL_W - 1, CELL_H - 1], outline="black", width=1)
                
                pad_top = 25
                cell_img.paste(qr_img, ((CELL_W - qw)//2, pad_top))
                draw_cell.text(((CELL_W - tw_id)//2, pad_top + qh + 10), pid, font=font, fill="black")
                draw_cell.text(((CELL_W - tw_name)//2, pad_top + qh + th_id + 25), short_name, font=font_small, fill="#555555")
                
                paste_x = MARGIN_X + x_idx * (CELL_W + GAP)
                paste_y = MARGIN_Y + y_idx * (CELL_H + GAP)
                
                current_page.paste(cell_img, (paste_x, paste_y))
                
                x_idx += 1
                if x_idx >= COLS:
                    x_idx, y_idx = 0, y_idx + 1
                    if y_idx >= ROWS:
                        y_idx, current_page = 0, None
                        
            if pages:
                os.makedirs("QR_codes", exist_ok=True)
                pdf_path = os.path.join("QR_codes", f"Bulk_QRs_{time.strftime('%Y%m%d_%H%M%S')}.pdf")
                pages[0].save(pdf_path, "PDF", resolution=300.0, save_all=True, append_images=pages[1:])
                
                import sys, subprocess
                if sys.platform == "win32": os.startfile(pdf_path)
                elif sys.platform == "darwin": subprocess.call(["open", pdf_path])
                else:
                    try: subprocess.call(["xdg-open", pdf_path])
                    except: pass
                self.after(0, self._pdf_worker_done, pdf_path, None)
            else:
                self.after(0, self._pdf_worker_done, None, "No items to generate a PDF.")
        except Exception as e:
            self.after(0, self._pdf_worker_done, None, str(e))

    def _pdf_worker_done(self, pdf_path, error_msg):
        self._bulk_print_btn.config(state=tk.NORMAL)
        if error_msg:
            self._status.config(text=f"Error: {error_msg}", fg="red")
        elif pdf_path:
            self._status.config(text=f"Bulk PDF saved to {pdf_path}", fg="#27ae60")


# ─── Analytics Page ──────────────────────────────────────────────────────────

class AnalyticsPage(Page):
    def __init__(self, parent, db_file, **kw):
        super().__init__(parent, **kw)
        self._db = db_file
        self._create_widgets()

    def _create_widgets(self):
        self._container = tk.Frame(self)
        self._container.pack(fill="both", expand=True, padx=20, pady=20)

        # Title and Toolbar
        title_frame = tk.Frame(self._container)
        title_frame.pack(fill="x", pady=(0, 15))
        self._title_lbl = tk.Label(title_frame, text="📊 System Analytics", font=("Arial", 16, "bold"))
        self._title_lbl.pack(side="left")

        self._refresh_btn = tk.Button(title_frame, text="🔄 Refresh Data", font=("Arial", 10),
                                      relief=tk.FLAT, command=self._refresh)
        self._refresh_btn.pack(side="right")

        # KPI Cards Frame (4 columns)
        self._cards_frame = tk.Frame(self._container)
        self._cards_frame.pack(fill="x", pady=10)
        self._cards_frame.columnconfigure((0, 1, 2, 3), weight=1, uniform="equal")

        self._cards = []
        for i, title in enumerate(["Registered Users", "Total Products", "Currently Borrowed", "Today's Transactions"]):
            cf = tk.Frame(self._cards_frame, bd=0, highlightthickness=1, padx=15, pady=15)
            cf.grid(row=0, column=i, padx=8, sticky="nsew")
            
            num_lbl = tk.Label(cf, text="-", font=("Arial", 22, "bold"))
            num_lbl.pack(pady=(0, 5))
            
            tit_lbl = tk.Label(cf, text=title, font=("Arial", 10))
            tit_lbl.pack()
            
            self._cards.append((cf, num_lbl, tit_lbl))

        # Bottom section: Two columns
        bottom_frame = tk.Frame(self._container)
        bottom_frame.pack(fill="both", expand=True, pady=20)
        bottom_frame.columnconfigure((0, 1), weight=1, uniform="equal")

        # Left Column: Most Active Users
        left_col = tk.Frame(bottom_frame)
        left_col.grid(row=0, column=0, padx=(0, 10), sticky="nsew")
        self._user_sec_lbl = tk.Label(left_col, text="👥 Most Active Users (All-time)", font=("Arial", 12, "bold"))
        self._user_sec_lbl.pack(anchor="w", pady=(0, 5))
        
        self._user_tree = ttk.Treeview(left_col, columns=("Rank", "Name", "Check-outs"), show="headings", height=6)
        self._user_tree.pack(fill="both", expand=True)
        cols_user = [("Rank", 50), ("Name", 150), ("Check-outs", 100)]
        for col_name, width in cols_user:
            self._user_tree.heading(col_name, text=col_name, anchor="center")
            self._user_tree.column(col_name, width=width, anchor="center")

        # Right Column: Most Checked-Out Products
        right_col = tk.Frame(bottom_frame)
        right_col.grid(row=0, column=1, padx=(10, 0), sticky="nsew")
        self._prod_sec_lbl = tk.Label(right_col, text="📦 Most Popular Products", font=("Arial", 12, "bold"))
        self._prod_sec_lbl.pack(anchor="w", pady=(0, 5))

        self._prod_tree = ttk.Treeview(right_col, columns=("Rank", "Product Name", "Times Borrowed"), show="headings", height=6)
        self._prod_tree.pack(fill="both", expand=True)
        cols_prod = [("Rank", 50), ("Product Name", 180), ("Times Borrowed", 100)]
        for col_name, width in cols_prod:
            self._prod_tree.heading(col_name, text=col_name, anchor="center")
            self._prod_tree.column(col_name, width=width, anchor="center")

        self.apply_theme()

    def apply_theme(self):
        t = get_theme()
        self.config(bg=t["content_bg"])
        self._container.config(bg=t["content_bg"])
        self._container.master.config(bg=t["content_bg"])
        
        self._container.winfo_children()[0].config(bg=t["content_bg"])
        self._title_lbl.config(bg=t["content_bg"], fg=t["header_fg"])
        self._refresh_btn.config(bg=t["btn_primary"], fg=t["btn_primary_fg"],
                                  activebackground=t["sidebar_active"])

        self._cards_frame.config(bg=t["content_bg"])
        is_dark = t["content_bg"] == "#020617"
        card_bg = t["sidebar_sub_bg"] if is_dark else "#ffffff"
        card_border = "#334155" if is_dark else "#dddddd"
        card_fg = t["header_fg"]
        card_sub_fg = t["logo_sub_fg"] if is_dark else "#666666"

        for cf, num, tit in self._cards:
            cf.config(bg=card_bg, highlightbackground=card_border, highlightcolor=card_border)
            num.config(bg=card_bg, fg=card_fg)
            tit.config(bg=card_bg, fg=card_sub_fg)

        bottom_frame = self._container.winfo_children()[2]
        bottom_frame.config(bg=t["content_bg"])
        
        for frame in bottom_frame.winfo_children():
            frame.config(bg=t["content_bg"])
            frame.winfo_children()[0].config(bg=t["content_bg"], fg=t["header_fg"])

    def on_show(self):
        self._refresh()

    def _refresh(self):
        import sqlite3
        from datetime import datetime

        total_users = 0
        total_products = 0
        currently_borrowed = 0
        today_tx = 0

        top_users = []
        top_products = []

        try:
            conn = sqlite3.connect(self._db)
            c = conn.cursor()

            c.execute("SELECT COUNT(*) FROM users")
            total_users = c.fetchone()[0]

            c.execute("SELECT COUNT(*) FROM items")
            total_products = c.fetchone()[0]

            c.execute("SELECT COUNT(*) FROM product_history WHERE check_in_time IS NULL")
            currently_borrowed = c.fetchone()[0]

            today_prefix = datetime.now().strftime("%Y-%m-%d") + "%"
            c.execute("SELECT COUNT(*) FROM product_history WHERE (check_out_time LIKE ?) OR (check_in_time LIKE ?)", (today_prefix, today_prefix))
            today_tx = c.fetchone()[0]

            c.execute("""
                SELECT user_name, COUNT(*) as cnt 
                FROM product_history 
                GROUP BY user_id 
                ORDER BY cnt DESC 
                LIMIT 5
            """)
            top_users = c.fetchall()

            c.execute("""
                SELECT product_name, COUNT(*) as cnt 
                FROM product_history 
                GROUP BY product_id 
                ORDER BY cnt DESC 
                LIMIT 5
            """)
            top_products = c.fetchall()

            conn.close()
        except Exception as e:
            print(f"Analytics DB Error: {e}")

        stats = [total_users, total_products, currently_borrowed, today_tx]
        for i, val in enumerate(stats):
            self._cards[i][1].config(text=str(val))

        for row in self._user_tree.get_children():
            self._user_tree.delete(row)
        for rank, (name, count) in enumerate(top_users, 1):
            self._user_tree.insert("", tk.END, values=(rank, name, count))

        for row in self._prod_tree.get_children():
            self._prod_tree.delete(row)
        for rank, (name, count) in enumerate(top_products, 1):
            self._prod_tree.insert("", tk.END, values=(rank, name, count))

# ─── Main application ─────────────────────────────────────────────────────────

class InventoryApp(tk.Tk):
    def __init__(self):
        super().__init__()
        initialize_database(DB_FILE)
        self.title("STEMLAND — Inventory Management")
        self.geometry(f"{self.winfo_screenwidth()}x{self.winfo_screenheight()}")
        self.resizable(True, True)

        self._logged_in = False

        # ── outer layout ──
        outer = tk.Frame(self)
        outer.pack(fill="both", expand=True)

        self._sidebar = Sidebar(outer, self._show_page)
        self._sidebar.pack(side="left", fill="y")

        ttk.Separator(outer, orient="vertical").pack(side="left", fill="y")

        right_col = tk.Frame(outer)
        right_col.pack(side="left", fill="both", expand=True)

        # ── top bar with theme switcher ──
        t = get_theme()
        self._topbar = tk.Frame(right_col, bg=t["sidebar_bg"], pady=4)
        self._topbar.pack(fill="x")

        self._topbar_title = tk.Label(
            self._topbar, text="STEMLAND Inventory",
            font=("Arial", 11, "bold"), bg=t["sidebar_bg"], fg=t["logo_fg"])
        self._topbar_title.pack(side="left", padx=12)

        theme_frame = tk.Frame(self._topbar, bg=t["sidebar_bg"])
        theme_frame.pack(side="right", padx=12)
        self._theme_var = tk.StringVar(value="AIAT")
        self._theme_icon = tk.Label(theme_frame, text="☀️", bg=t["sidebar_bg"], fg=t["sidebar_fg"], font=("Arial", 12))
        self._theme_icon.pack(side="left", padx=4)
        self._theme_switch = tk.Canvas(theme_frame, width=44, height=24, highlightthickness=0, bd=0, bg=t["sidebar_bg"], cursor="hand2")
        self._theme_switch.pack(side="left")
        self._theme_switch.bind("<Button-1>", lambda e: self._toggle_theme())
        self._draw_switch(False)

        # ── Camera selector (admin topbar) ────────────────────
        cam_frame = tk.Frame(self._topbar, bg=t["sidebar_bg"])
        cam_frame.pack(side="right", padx=12)
        tk.Label(cam_frame, text="📷 Camera:", bg=t["sidebar_bg"],
                 fg=t["sidebar_fg"], font=("Arial", 9)).pack(side="left")

        self._cam_labels = _detect_cameras()   # [(index, label), ...]
        # Default: USB webcam (highest index) is first after sort
        default_cam = self._cam_labels[0]
        global _active_camera_index
        _active_camera_index = default_cam[0]

        self._cam_var = tk.StringVar(value=default_cam[1])
        self._cam_cb  = ttk.Combobox(cam_frame, textvariable=self._cam_var,
                                      values=[lbl for _, lbl in self._cam_labels],
                                      state="readonly", width=18, font=("Arial", 9))
        self._cam_cb.pack(side="left", padx=4)
        self._cam_cb.bind("<<ComboboxSelected>>", self._on_camera_change)

        self._content = tk.Frame(right_col, bg=t["content_bg"])
        self._content.pack(side="left", fill="both", expand=True)

        # ── pages ──
        self._pages: dict[str, Page] = {}
        self._current: Page | None = None
        bg = t["content_bg"]
        self._add_page("home",            HomePage(self._content, DB_FILE, bg=bg))
        self._add_page("login",           LoginPage(self._content, self._on_login_success, bg=bg))
        self._add_page("admin_history",   AdminHistoryPage(self._content, DB_FILE, bg=bg))
        self._add_page("user_management", UserManagementPage(self._content, DB_FILE, bg=bg))
        self._add_page("product_manager", ProductManagerPage(self._content, DB_FILE, bg=bg))
        self._add_page("analytics",       AnalyticsPage(self._content, DB_FILE, bg=bg))

        self._show_page("home")

        self.bind("<space>", lambda e: self._pages["home"]._start_qr()
                  if self._current is self._pages["home"]
                  and self._pages["home"]._mode is None else None)
        self.bind("<F2>", lambda e: self._show_page("login"))

    def _toggle_theme(self):
        current = self._theme_var.get()
        if current in ("AIAT", "Light"):
            new_theme = "Dark"
            is_dark = True
            icon = "🌙"
        else:
            new_theme = "Light"
            is_dark = False
            icon = "☀️"
            
        self._theme_var.set(new_theme)
        self._draw_switch(is_dark)
        self._theme_icon.config(text=icon)
        
        set_theme(new_theme)
        t = get_theme()
        self._theme_switch.config(bg=t["sidebar_bg"])
        self._theme_icon.config(bg=t["sidebar_bg"], fg=t["sidebar_fg"])
        
        # Topbar
        self._topbar.config(bg=t["sidebar_bg"])
        self._topbar_title.config(bg=t["sidebar_bg"], fg=t["logo_fg"])
        for w in self._topbar.winfo_children():
            if isinstance(w, tk.Frame):
                w.config(bg=t["sidebar_bg"])
                for c in w.winfo_children():
                    if isinstance(c, tk.Label):
                        c.config(bg=t["sidebar_bg"], fg=t["sidebar_fg"])
        # Sidebar
        self._sidebar.apply_theme()
        self._sidebar.set_active(
            next((k for k, v in self._pages.items() if v is self._current), "home"))
        # Content
        self._content.config(bg=t["content_bg"])
        for page in self._pages.values():
            try:
                page.config(bg=t["content_bg"])
                if hasattr(page, "apply_theme"):
                    page.apply_theme()
            except Exception:
                pass

    def _draw_switch(self, is_dark):
        self._theme_switch.delete("all")
        bg_color = "#3b82f6" if is_dark else "#cbd5e1"
        self._theme_switch.create_arc(2, 2, 22, 22, start=90, extent=180, fill=bg_color, outline=bg_color)
        self._theme_switch.create_arc(22, 2, 42, 22, start=-90, extent=180, fill=bg_color, outline=bg_color)
        self._theme_switch.create_rectangle(12, 2, 32, 22, fill=bg_color, outline=bg_color)
        if is_dark:
            self._theme_switch.create_oval(24, 4, 40, 20, fill="#ffffff", outline="")
        else:
            self._theme_switch.create_oval(4, 4, 20, 20, fill="#ffffff", outline="")

    def _on_camera_change(self, _event=None):
        global _active_camera_index
        selected_label = self._cam_var.get()
        for idx, lbl in self._cam_labels:
            if lbl == selected_label:
                _active_camera_index = idx
                break
                
        # Cleanly stop camera on any active page using proper lifecycle methods
        # to ensure the UI loop doesn't get broken/frozen.
        if self._current is self._pages.get("home"):
            page = self._pages["home"]
            if page._running:
                was_mode = page._mode
                page._stop_camera()
                if was_mode == "qr":
                    page.after(400, page._start_qr)
                # Note: if it was in 'face' mode, we let the user start over 
                # to ensure security and state consistency.
        elif self._current is self._pages.get("user_management"):
            page = self._pages["user_management"]
            if page._running:
                page._restart_camera()

    def _add_page(self, name: str, page: Page):
        self._pages[name] = page

    def _show_page(self, name: str):
        if name in ("admin_history", "user_management", "product_manager") and not self._logged_in:
            self._show_page("login")
            return
        if self._current:
            self._current.on_hide()
            self._current.pack_forget()
        page = self._pages[name]
        page.pack(fill="both", expand=True)
        page.on_show()
        self._current = page
        self._sidebar.set_active(name)

    def _on_login_success(self):
        self._logged_in = True
        self._sidebar.show_admin_menu()
        self._show_page("admin_history")

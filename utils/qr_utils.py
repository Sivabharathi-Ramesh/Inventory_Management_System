"""
QR code utilities module for QR code scanning and processing.
"""
import os
import sys
import warnings

# Suppress warnings and OpenCV output
warnings.filterwarnings("ignore")
os.environ['OPENCV_LOG_LEVEL'] = 'SILENT'

import cv2
import time
import threading
import queue

def _cv2_has_gui():
    try:
        cv2.namedWindow("__test__", cv2.WINDOW_NORMAL)
        cv2.destroyWindow("__test__")
        return True
    except cv2.error:
        return False

_CV2_GUI = _cv2_has_gui()
from PIL import Image, ImageTk
import tkinter as _tk
from .text_utils import text_to_speech

# Camera device index: 0 = built-in, 1+ = external/USB cameras
CAMERA_DEVICE_INDEX = 1


def zoom_in_on_qr_code(frame, points, zoom_factor=1.5):
    """
    Zoom into the region containing the QR code if it's smaller than a threshold.
    
    Args:
        frame (numpy.ndarray): The current video frame.
        points (numpy.ndarray): Coordinates of the detected QR code.
        zoom_factor (float): Factor by which to zoom into the QR code.
        
    Returns:
        numpy.ndarray: The processed frame (zoomed or original).
    """
    x_min = int(min(points[:, 0]))
    y_min = int(min(points[:, 1]))
    x_max = int(max(points[:, 0]))
    y_max = int(max(points[:, 1]))

    # Dimensions of the detected QR code
    qr_width = x_max - x_min
    qr_height = y_max - y_min

    # Threshold for zooming based on QR code size
    min_qr_size = 100

    # If the QR code is too small, zoom into the region
    if qr_width < min_qr_size or qr_height < min_qr_size:
        center_x = x_min + qr_width // 2
        center_y = y_min + qr_height // 2

        new_w = int(qr_width * zoom_factor)
        new_h = int(qr_height * zoom_factor)

        x_start = max(0, center_x - new_w // 2)
        y_start = max(0, center_y - new_h // 2)
        x_end = min(frame.shape[1], center_x + new_w // 2)
        y_end = min(frame.shape[0], center_y + new_h // 2)

        cropped_frame = frame[y_start:y_end, x_start:x_end]
        zoomed_frame = cv2.resize(cropped_frame, (frame.shape[1], frame.shape[0]), interpolation=cv2.INTER_LINEAR)
        return zoomed_frame

    return frame


def scan_qr_code():
    """
    Scans for a QR code using the webcam, zooming in if the QR code is too small.
    
    Features:
        - Timeout is 30 seconds.
        - The camera frame is mirrored (horizontal flip) for user-friendly preview.
        
    Returns:
        str or None: The decoded QR code data, or None if not found/cancelled.
    """
    cap = cv2.VideoCapture(CAMERA_DEVICE_INDEX)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 720)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    max_duration = 30  # seconds
    start_time = time.time()

    while True:
        # Check if maximum time exceeded
        if time.time() - start_time > max_duration:
            text = "QR scan timed out."
            text_to_speech(text)
            break

        ret, frame = cap.read()
        if not ret:
            text = "Failed to capture frame"
            text_to_speech(text)
            break

        frame = cv2.flip(frame, 1)  # Mirror the camera frame (horizontal flip)

        detector = cv2.QRCodeDetector()
        data, points, _ = detector.detectAndDecode(frame)

        if points is not None:
            points = points[0]
            cv2.polylines(frame, [points.astype(int)], isClosed=True, color=(0, 255, 0), thickness=2)

            # Apply zoom if QR code dimensions are below threshold
            frame = zoom_in_on_qr_code(frame, points)

            if data:
                cv2.putText(frame, data, (int(points[0][0]), int(points[0][1] - 10)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)
                product_id = data

                cap.release()
                if _CV2_GUI:
                    cv2.destroyAllWindows()
                return product_id

        # Do not call cv2.imshow or cv2.waitKey here; this function may run
        # in a background thread (called from Tkinter). We only process frames
        # and return the decoded data. Preview rendering is intentionally
        # omitted to avoid OpenCV GUI calls from non-main threads.

    cap.release()
    if _CV2_GUI:
        cv2.destroyAllWindows()
    return None


def scan_qr_code_with_tk_preview(parent, timeout=30):
    """Scan QR with a Tkinter preview window. Blocks until a QR is found, cancelled, or timeout.

    Returns decoded data or None.
    """
    result_q = queue.Queue()
    stop_event = threading.Event()

    # Create preview window
    try:
        top = _tk.Toplevel(parent)
        top.title("QR Preview")
        top.geometry("640x480")
        top.transient(parent)
        lbl = _tk.Label(top)
        lbl.pack(fill=_tk.BOTH, expand=True)
        cancel_btn = _tk.Button(top, text="Cancel", command=lambda: stop_event.set())
        cancel_btn.pack(side=_tk.BOTTOM)
        # Ensure closing the window stops the worker
        top.protocol("WM_DELETE_WINDOW", stop_event.set)
    except Exception:
        top = None
        lbl = None

    def worker():
        cap = cv2.VideoCapture(CAMERA_DEVICE_INDEX)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 720)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        start_time = time.time()
        detector = cv2.QRCodeDetector()

        try:
            while not stop_event.is_set():
                if time.time() - start_time > timeout:
                    text_to_speech("QR scan timed out.")
                    break

                ret, frame = cap.read()
                if not ret:
                    text_to_speech("Failed to capture frame")
                    break

                frame = cv2.flip(frame, 1)
                data, points, _ = detector.detectAndDecode(frame)
                if points is not None:
                    points = points[0]
                    cv2.polylines(frame, [points.astype(int)], isClosed=True, color=(0, 255, 0), thickness=2)
                    if data:
                        result_q.put(data)
                        break

                # Send preview frame to Tk
                if lbl is not None:
                    try:
                        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                        im = Image.fromarray(rgb)
                        imgtk = ImageTk.PhotoImage(image=im)
                        def _safe_set_image(widget, image):
                            try:
                                if widget.winfo_exists():
                                    widget.imgtk = image
                                    widget.config(image=image)
                            except Exception:
                                pass

                        lbl.after(0, lambda imgtk=imgtk: _safe_set_image(lbl, imgtk))
                    except Exception:
                        pass

                time.sleep(0.02)

        finally:
            try:
                cap.release()
            except Exception:
                pass

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    # Poll for result or stop
    start = time.time()
    res = None
    while True:
        try:
            if not result_q.empty():
                res = result_q.get_nowait()
                break
        except Exception:
            res = None

        if stop_event.is_set():
            res = None
            break

        if time.time() - start > timeout:
            res = None
            break

        try:
            parent.update()
        except Exception:
            pass
        time.sleep(0.05)

    # close preview
    try:
        if top is not None:
            top.destroy()
    except Exception:
        pass

    return res

#!/usr/bin/env python3
"""
Camera device detection utility.
Helps identify which camera device index corresponds to your connected camera.
"""
import cv2
import os
import sys
from contextlib import contextmanager

@contextmanager
def suppress_stdout_stderr():
    """Context manager to suppress stdout and stderr from C/C++ libraries."""
    save_stdout = sys.stdout
    save_stderr = sys.stderr
    sys.stdout = open(os.devnull, 'w')
    sys.stderr = open(os.devnull, 'w')
    try:
        yield
    finally:
        sys.stdout.close()
        sys.stderr.close()
        sys.stdout = save_stdout
        sys.stderr = save_stderr

def detect_available_cameras(max_cameras=5):
    """
    Detect available camera devices.
    
    Args:
        max_cameras (int): Maximum number of devices to check.
        
    Returns:
        list: Available camera device indices.
    """
    available_cameras = []
    
    print("Scanning for available cameras...")
    for i in range(max_cameras):
        try:
            with suppress_stdout_stderr():
                cap = cv2.VideoCapture(i)
                if cap.isOpened():
                    ret, frame = cap.read()
                    if ret and frame is not None:
                        available_cameras.append(i)
                    cap.release()
            
            if i in available_cameras:
                print(f"✓ Camera found at device index: {i}")
                # Get camera properties (do this outside suppression)
                cap = cv2.VideoCapture(i)
                width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                fps = int(cap.get(cv2.CAP_PROP_FPS))
                print(f"  Resolution: {width}x{height}, FPS: {fps}")
                cap.release()
        except Exception:
            pass
    
    return available_cameras

if __name__ == "__main__":
    cameras = detect_available_cameras()
    
    if not cameras:
        print("\n✗ No cameras found!")
    else:
        print(f"\n✓ Found {len(cameras)} camera(s): {cameras}")
        print("\nTo use an external camera, update the CAMERA_DEVICE_INDEX in:")
        print("  - utils/qr_utils.py")
        print("  - utils/face_recognition_utils.py")
        print("  - check_out_check_in_2_2.py")
        print("  - ui/user_management_ui.py")
        print("\nSet CAMERA_DEVICE_INDEX to the desired camera index from the list above.")

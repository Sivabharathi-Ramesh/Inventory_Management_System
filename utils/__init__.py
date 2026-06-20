"""Utilities module package."""
from .ui_utils import setup_placeholder, resource_path
from .text_utils import text_to_speech
from .qr_utils import scan_qr_code, zoom_in_on_qr_code
from .face_recognition_utils import (
    load_known_encodings,
    find_matching_face,
    recognize_user,
    check_liveness
)

__all__ = [
    'setup_placeholder',
    'resource_path',
    'text_to_speech',
    'scan_qr_code',
    'zoom_in_on_qr_code',
    'load_known_encodings',
    'find_matching_face',
    'recognize_user',
    'check_liveness'
]

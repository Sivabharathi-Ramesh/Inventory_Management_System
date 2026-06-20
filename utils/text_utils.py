"""
Text-to-speech utility module.
"""
import os
import sys
import subprocess
import shutil


def text_to_speech(text):
    """
    Convert text to speech using the best available system command.

    macOS: uses `say`
    Linux: tries `pico2wave` + `aplay` if available
    Fallback: prints the text (no audio)
    """
    try:
        if sys.platform == 'darwin':
            # macOS built-in TTS
            subprocess.run(['say', text], check=False)
            return

        # Try pico2wave (common on some Linux systems)
        pico = shutil.which('pico2wave')
        aplay = shutil.which('aplay')
        if pico and aplay:
            # create temporary wav and play
            subprocess.run([pico, '-w', 'output.wav', text], check=False)
            subprocess.run([aplay, 'output.wav'], check=False)
            return

    except Exception:
        pass

    # Last-resort fallback
    print(f"TTS: {text}")

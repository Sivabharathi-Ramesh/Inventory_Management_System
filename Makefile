# Use bash instead of sh for shell compatibility (source command support)
SHELL := /bin/bash

# Paths
PROJECT_DIR := /home/stemland/Desktop/ojt
VENV_DIR := $(PROJECT_DIR)/env
SCRIPT := "check_out_check_in_2_2.py"


# PyInstaller flags
PYI_FLAGS := \
  --noconfirm --onefile --console --collect-submodules PIL \
  --add-data "icons/admin_icon.ico:icons" \
  --add-data "icons/reload.ico:icons" \
  --add-data "icons/search_icon.ico:icons" \
  --add-data "env/lib/python3.11/site-packages/face_recognition_models/models/dlib_face_recognition_resnet_model_v1.dat:face_recognition_models/models" \
  --add-data "env/lib/python3.11/site-packages/face_recognition_models/models/mmod_human_face_detector.dat:face_recognition_models/models" \
  --add-data "env/lib/python3.11/site-packages/face_recognition_models/models/shape_predictor_5_face_landmarks.dat:face_recognition_models/models" \
  --add-data "env/lib/python3.11/site-packages/face_recognition_models/models/shape_predictor_68_face_landmarks.dat:face_recognition_models/models" \
  --add-data "haarcascade_eye.xml:cv2/data" \
  --add-data "haarcascade_frontalface_default.xml:cv2/data"

# Default target
build:

	pyinstaller $(PYI_FLAGS) "$(SCRIPT)"

# Optional clean target
clean:
	rm -rf $(PROJECT_DIR)/build $(PROJECT_DIR)/dist $(PROJECT_DIR)/*.spec

.PHONY: build clean

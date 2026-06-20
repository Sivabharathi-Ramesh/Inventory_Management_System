import face_recognition
import os
import pickle

# Folder containing face images
image_folder = "faces"

# Lists to store encodings and names
known_encodings = []
known_names = []

# Loop through all images in the folder
for filename in os.listdir(image_folder):
    if filename.endswith((".jpg", ".jpeg", ".png")):
        image_path = os.path.join(image_folder, filename)

        # Load image
        image = face_recognition.load_image_file(image_path)

        # Get face encodings
        encodings = face_recognition.face_encodings(image)

        if len(encodings) > 0:
            known_encodings.append(encodings[0])

            # Use filename (without extension) as name
            name = os.path.splitext(filename)[0]
            known_names.append(name)

            print(f"Encoded: {name}")
        else:
            print(f"No face found in {filename}")

# Save encodings to file
data = {
    "encodings": known_encodings,
    "names": known_names
}

with open("face_encodings.pkl", "wb") as f:
    pickle.dump(data, f)

print("Face encodings saved to face_encodings.pkl")
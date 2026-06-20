import pickle
import sqlite3

# Load face encodings from pickle file
with open("face_encodings.pkl", "rb") as f:
    data = pickle.load(f)

encodings = data["encodings"]
names = data["names"]

# Connect to database
conn = sqlite3.connect("DB_FILE")
cursor = conn.cursor()

# Insert or get user IDs and insert face encodings
for name, encoding in zip(names, encodings):
    # Insert user if not exists and get user_id
    cursor.execute("""
    INSERT OR IGNORE INTO users (user_name, type)
    VALUES (?, 'User')
    """, (name,))
    
    # Get user_id
    cursor.execute("SELECT user_id FROM users WHERE user_name = ?", (name,))
    user_id = cursor.fetchone()[0]
    
    # Insert face encoding
    cursor.execute("""
    INSERT INTO face_encodings (user_id, face_encoding)
    VALUES (?, ?)
    """, (user_id, pickle.dumps(encoding)))
    
    print(f"Inserted encoding for user: {name}")

# Commit and close
conn.commit()
conn.close()

print(f"\nSuccessfully inserted {len(encodings)} face encodings into the database")

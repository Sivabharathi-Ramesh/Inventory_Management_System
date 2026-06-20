"""
InsightFace + FAISS face recognition module.

Model  : buffalo_sc  (det_500m + w600k_mbf / ArcFace / MobileFaceNet)
Vectors: 512-dim, L2-normalised by the model
Index  : FAISS IndexFlatIP  (inner product = cosine similarity on unit vectors)
Match  : IP > VERIFY_THRESHOLD  (higher = stricter)
"""
import os
import warnings
import threading
import sqlite3
import pickle
import numpy as np

warnings.filterwarnings("ignore")
os.environ['OPENCV_LOG_LEVEL'] = 'SILENT'

import cv2
import faiss

# ── InsightFace singleton ────────────────────────────────────────────────────

_insight_lock = threading.Lock()
_insight_app  = None

def _get_insight_app():
    global _insight_app
    with _insight_lock:
        if _insight_app is None:
            from insightface.app import FaceAnalysis
            app = FaceAnalysis(
                name='buffalo_sc',
                providers=['CPUExecutionProvider']
            )
            app.prepare(ctx_id=0, det_size=(320, 320))
            _insight_app = app
        return _insight_app


# ── Face detection helpers ───────────────────────────────────────────────────

def detect_faces(bgr_frame):
    """Return list of InsightFace face objects sorted largest-first."""
    app   = _get_insight_app()
    faces = app.get(bgr_frame)
    if not faces:
        return []
    # Sort by bbox area descending
    faces.sort(key=lambda f: (f.bbox[2]-f.bbox[0])*(f.bbox[3]-f.bbox[1]), reverse=True)
    return faces


def faces_to_locations(faces):
    """Convert InsightFace bboxes → (top, right, bottom, left) tuples."""
    locs = []
    for f in faces:
        x1, y1, x2, y2 = [int(v) for v in f.bbox]
        locs.append((y1, x2, y2, x1))   # face_recognition convention
    return locs


def get_face_embedding(face):
    """Return L2-normalised 512-dim embedding from an InsightFace face object."""
    emb = np.array(face.embedding, dtype=np.float32)
    norm = np.linalg.norm(emb)
    if norm > 0:
        emb = emb / norm
    return emb


# ── Database loading ─────────────────────────────────────────────────────────

# Cosine similarity threshold for a VALID match (higher = stricter).
# ArcFace embeddings: same person typically > 0.35, different person < 0.25.
VERIFY_THRESHOLD = 0.55   # verification (check-in/out) — strict
ENROLL_THRESHOLD = 0.50   # dedup during registration — slightly looser

EMBEDDING_DIM = 512


def _load_known_encodings_faiss(db_file='DB_FILE'):
    """
    Load InsightFace (512-dim) encodings from the DB and return ONE mean
    embedding per user.  Dlib 128-dim legacy encodings are silently skipped.
    """
    conn   = sqlite3.connect(db_file)
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT u.user_id, u.user_name, f.face_encoding
            FROM users u
            JOIN face_encodings f ON u.user_id = f.user_id
            UNION ALL
            SELECT user_id, user_name, face_encoding
            FROM users
            WHERE face_encoding IS NOT NULL
        """)
    except sqlite3.OperationalError:
        cursor.execute("SELECT user_id, user_name, face_encoding FROM users")

    rows = cursor.fetchall()
    conn.close()

    from collections import defaultdict
    user_info = {}
    user_encs = defaultdict(list)

    for uid, uname, blob in rows:
        if blob is None:
            continue
        try:
            try:
                enc = pickle.loads(blob)
            except Exception:
                enc = np.frombuffer(blob, dtype=np.float64)
            enc = np.array(enc, dtype=np.float32)
            if enc.shape[0] != EMBEDDING_DIM:
                continue          # skip legacy 128-dim dlib encodings
            norm = np.linalg.norm(enc)
            if norm > 0:
                enc = enc / norm
            user_encs[uid].append(enc)
            user_info[uid] = uname
        except Exception:
            continue

    if not user_encs:
        return np.array([]), []

    encodings, labels = [], []
    for uid, encs in user_encs.items():
        mean_enc = np.mean(encs, axis=0).astype(np.float32)
        norm = np.linalg.norm(mean_enc)
        if norm > 0:
            mean_enc = mean_enc / norm
        encodings.append(mean_enc)
        labels.append((uid, user_info[uid]))

    return np.array(encodings, dtype=np.float32), labels


# ── FAISS index (cosine / inner product) ────────────────────────────────────

def build_faiss_index(embeddings):
    """Build a FAISS IndexFlatIP for cosine similarity on unit vectors."""
    dim   = embeddings.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(embeddings)
    return index


def find_matching_face_faiss(index, labels, test_embedding, threshold=VERIFY_THRESHOLD):
    """
    Return (uid, uname) if cosine similarity >= threshold, else (None, None).
    """
    if test_embedding is None or len(test_embedding) == 0:
        return None, None

    enc = np.array(test_embedding, dtype=np.float32)
    norm = np.linalg.norm(enc)
    if norm > 0:
        enc = enc / norm
    enc = enc.reshape(1, -1)

    sims, idxs = index.search(enc, k=1)
    sim = float(sims[0][0])
    idx = int(idxs[0][0])

    if sim >= threshold:
        return labels[idx]
    return None, None


# ── Backwards-compatible wrappers ────────────────────────────────────────────

def load_known_encodings(db_file='DB_FILE'):
    """Return [(uid, uname, embedding)] — mean InsightFace embedding per user."""
    embeddings, labels = _load_known_encodings_faiss(db_file)
    if embeddings.size == 0:
        return []
    return [(uid, uname, embeddings[i]) for i, (uid, uname) in enumerate(labels)]


def find_matching_face(known_encodings, test_encoding, tolerance=VERIFY_THRESHOLD):
    """Match test_encoding against pre-loaded list of (uid, uname, embedding)."""
    if not known_encodings or test_encoding is None:
        return None, None
    try:
        embs   = np.array([e[2] for e in known_encodings], dtype=np.float32)
        norms  = np.linalg.norm(embs, axis=1, keepdims=True)
        norms[norms == 0] = 1
        embs   = embs / norms
        labels = [(e[0], e[1]) for e in known_encodings]
        index  = build_faiss_index(embs)
        return find_matching_face_faiss(index, labels, test_encoding, threshold=tolerance)
    except Exception:
        return None, None

def check_liveness(bgr_frame, bbox, threshold=80.0):
    """
    Perform a texture-based liveness check on the cropped face region.
    Returns True if live, False if a suspected spoof (flat screen/printed paper).
    """
    try:
        x1, y1, x2, y2 = [int(v) for v in bbox]
        h, w = bgr_frame.shape[:2]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)
        
        crop = bgr_frame[y1:y2, x1:x2]
        if crop.size == 0:
            return True
            
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        variance = cv2.Laplacian(gray, cv2.CV_64F).var()
        
        # Print variance for configuration debugging
        print(f"[LIVENESS DEBUG] Face Size: {crop.shape[1]}x{crop.shape[0]}, Variance: {variance:.2f} (Threshold: {threshold})")
        
        # Unusually low texture/high-frequency detail indicates print or screen spoof
        if variance < threshold:
            return False
            
        return True
    except Exception as e:
        print(f"[LIVENESS ERROR] Check failed: {e}")
        return True


def recognize_user(timeout=30, db_file='DB_FILE'):
    """Legacy wrapper used by older code paths."""
    return None, None

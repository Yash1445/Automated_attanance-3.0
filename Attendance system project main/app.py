# 🔹 imports FIRST
import os
import base64
import numpy as np
import cv2

from flask import Flask, request, render_template, redirect, url_for

# 🔹 create app
app = Flask(__name__)

# 🔹 your existing setup (db, config, etc)
init_db_config(app)

# 🔹 THEN routes

@app.route('/api/recognize', methods=['POST'])
def recognize():
    data = request.json['image']

    encoded = data.split(",")[1]
    img_bytes = base64.b64decode(encoded)
    np_arr = np.frombuffer(img_bytes, np.uint8)
    frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

    print("✅ Frame received from frontend")

    return {"status": "received"}
import cv2  
import os
import numpy as np
try:
    import face_recognition
except:
    face_recognition = None
from flask import Flask, request, render_template, redirect, url_for, session, flash, Response
from datetime import date, datetime
import pandas as pd
import joblib
import time
import shutil
from functools import wraps
import hashlib
import csv
from collections import Counter, defaultdict
import threading
from queue import Queue
from sqlalchemy import text

from database import init_db_config, db
from models import Admin, Student, Attendance
from helpers import save_student_with_encoding, mark_attendance

# VARIABLES
MESSAGE = "WELCOME! Instruction: to register your attendance kindly click on 'a' on keyboard"
STRICT_THRESHOLD = float(os.environ.get('FACE_STRICT_THRESHOLD', '0.48'))
MIN_FACE_SIZE = int(os.environ.get('FACE_MIN_SIZE', '60'))
AMBIGUITY_MARGIN = float(os.environ.get('FACE_AMBIGUITY_MARGIN', '0.03'))
TOP_K_PER_USER = int(os.environ.get('FACE_TOP_K', '3'))
PREDICTION_BUFFER_SIZE = int(os.environ.get('FACE_PREDICTION_BUFFER', '5'))
CONFIRM_FRAMES = int(os.environ.get('FACE_CONFIRM_FRAMES', '3'))
MAX_MISSES_BEFORE_RESET = int(os.environ.get('FACE_MAX_MISSES', '8'))
UNKNOWN_LOG_COOLDOWN_SEC = float(os.environ.get('FACE_UNKNOWN_LOG_COOLDOWN', '3'))

#### PERFORMANCE OPTIMIZATION SETTINGS FOR LOW-END DEVICES
FRAME_SKIP = int(os.environ.get('FRAME_SKIP', '3'))  # Process every 3rd frame (improves FPS 3x)
FACE_DETECTION_SCALE = float(os.environ.get('FACE_DETECTION_SCALE', '0.4'))  # Lower resolution for detection
FACE_DETECTION_UPSAMPLE = int(os.environ.get('FACE_DETECTION_UPSAMPLE', '1'))  # Reduced from 2 to 1
MODEL_CACHE_ENABLED = os.environ.get('MODEL_CACHE_ENABLED', 'true').lower() == 'true'

# Global model cache (loaded once, reused for all frames)
_ENCODING_CACHE = None
_ENCODING_CACHE_TIMESTAMP = 0
_ENCODING_CACHE_LOCK = threading.Lock()
_CACHE_EXPIRY_SECONDS = 300  # Refresh cache every 5 minutes

#### Defining Flask App
from flask import Flask
from flask_cors import CORS

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "fallback-key")

init_db_config(app)
CORS(app)

with app.app_context():
    db.create_all()
#### Saving Date today in 2 different formats
datetoday = date.today().strftime("%m_%d_%y")
datetoday2 = date.today().strftime("%d-%B-%Y")

#### Initializing VideoCapture object to access WebCam
face_detector = cv2.CascadeClassifier('haarcascade_frontalface_default.xml')  # type: ignore
# Do not hold a global camera handle here; open it on demand in routes
cap = None

# Robust camera opener for Windows (deterministic order)
def open_camera():
    print("Starting camera initialization...")
    # Release any lingering handles
    for i in range(5):
        tmp = cv2.VideoCapture(i)
        tmp.release()
    time.sleep(0.3)

    devices = [0, 1]

    def try_open(device, backend, delay):
        backend_name = {cv2.CAP_DSHOW: "DSHOW", cv2.CAP_MSMF: "MSMF", cv2.CAP_ANY: "ANY"}.get(backend, "UNKNOWN")
        print(f"Trying device {device} with backend {backend_name}...")
        
        cap = cv2.VideoCapture(device, backend)
        time.sleep(delay)
        
        if not cap.isOpened():
            print(f"  Device {device} ({backend_name}): Failed to open")
            cap.release()
            return None
            
        print(f"  Device {device} ({backend_name}): Opened successfully")
        
        # Set properties
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        cap.set(cv2.CAP_PROP_FPS, 30)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        fourcc_fn = getattr(cv2, "VideoWriter_fourcc", None)
        if callable(fourcc_fn):
            fourcc_val = fourcc_fn(*'MJPG')
            if isinstance(fourcc_val, (int, float)):
                cap.set(cv2.CAP_PROP_FOURCC, float(fourcc_val))

        # Grab a few frames to validate
        print(f"  Validating frames from device {device}...")
        good = 0
        for i in range(10):  # Try more frames for validation
            ret, frame = cap.read()
            if ret and frame is not None and frame.size > 0:
                mean_val = frame.mean()
                if 1 < mean_val < 254:
                    good += 1
                    print(f"    Frame {i+1}: Valid (mean={mean_val:.1f})")
                else:
                    print(f"    Frame {i+1}: Invalid mean ({mean_val:.1f})")
            else:
                print(f"    Frame {i+1}: Failed (ret={ret})")
            time.sleep(0.05)  # Longer delay between validation frames
        
        print(f"  Device {device} ({backend_name}): {good}/10 valid frames")
        
        if good >= 3:  # Only need 3 valid frames instead of 2
            print(f"  SUCCESS: Using device {device} with backend {backend_name}")
            return cap
            
        cap.release()
        return None

    # Deterministic order: DSHOW device0, DSHOW device1, MSMF device0, MSMF device1
    for backend, delay in [(cv2.CAP_DSHOW, 0.6), (cv2.CAP_MSMF, 1.0)]:
        for device in devices:
            cap = try_open(device, backend, delay)
            if cap:
                return cap

    # Last resort: default backend
    print("Trying default backend as last resort...")
    for device in devices:
        cap = try_open(device, cv2.CAP_ANY, 0.6)
        if cap:
            return cap
    
    print("ERROR: Could not open any camera device!")
    return None

def warmup_camera(cap, frames=20):
    """Warmup camera and verify it's producing valid frames"""
    valid_frames = 0
    for i in range(frames):
        ret, frame = cap.read()
        if ret and frame is not None and frame.size > 0:
            valid_frames += 1
            print(f"  Warmup frame {i+1}/{frames}: Valid (shape={frame.shape})")
        else:
            print(f"  Warmup frame {i+1}/{frames}: Failed (ret={ret})")
        time.sleep(0.02)
    
    time.sleep(0.3)
    success = valid_frames >= 3  # Only need at least 3 valid frames
    print(f"Camera warmup: {valid_frames}/{frames} valid frames, success={success}")
    return success

#### If these directories don't exist, create them
if not os.path.isdir('Attendance'):
    os.makedirs('Attendance')
if not os.path.isdir('static'):
    os.makedirs('static')
if not os.path.isdir('static/faces'):
    os.makedirs('static/faces')
# Attendance is persisted in PostgreSQL (single source of truth)

def initialize_database():
    with app.app_context():
        db.create_all()

        # create default admin
        default_admin = Admin.query.filter_by(username='admin').first()
        if default_admin is None:
            default_admin = Admin()
            default_admin.username = 'admin'
            default_admin.password = hashlib.sha256('admin123'.encode()).hexdigest()
            default_admin.email = 'admin@example.com'
            db.session.add(default_admin)
            db.session.commit()


initialize_database()


def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()


def verify_user(username, password):
    hashed_password = hash_password(password)
    user = Admin.query.filter_by(username=username, password=hashed_password).first()
    return user is not None


def create_user(username, password, email):
    if Admin.query.filter_by(username=username).first() is not None:
        return False

    user = Admin()
    user.username = username
    user.password = hash_password(password)
    user.email = email
    db.session.add(user)
    db.session.commit()
    return True


def username_exists(username):
    return Admin.query.filter_by(username=username).first() is not None


def reset_password(username, new_password):
    user = Admin.query.filter_by(username=username).first()
    if user:
        user.password = hash_password(new_password)
        db.session.commit()

# Login required decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('adminlogin'))
        return f(*args, **kwargs)
    return decorated_function

#### get a number of total registered users
def totalreg():
    try:
        return Student.query.count()
    except Exception:
        # Fallback for environments where DB is temporarily unavailable
        return len(os.listdir('static/faces')) if os.path.isdir('static/faces') else 0

def get_registered_users():
    try:
        students = Student.query.order_by(Student.name.asc()).all()
        return [{'name': s.name, 'id': str(s.roll_no)} for s in students]
    except Exception:
        # Fallback to folder-based parsing if DB query fails
        users = []
        faces_dir = 'static/faces'
        if os.path.exists(faces_dir):
            for folder in os.listdir(faces_dir):
                folder_path = os.path.join(faces_dir, folder)
                if os.path.isdir(folder_path) and '_' in folder:
                    try:
                        name, user_id = folder.rsplit('_', 1)
                        users.append({'name': name, 'id': user_id})
                    except ValueError:
                        continue
        users.sort(key=lambda x: x['name'])
        return users

def debug_users_folders():
    """Helper function to debug user folders"""
    faces_dir = 'static/faces'
    debug_info = []
    
    if not os.path.exists(faces_dir):
        debug_info.append(f"Faces directory '{faces_dir}' does not exist!")
        return debug_info
        
    for item in os.listdir(faces_dir):
        item_path = os.path.join(faces_dir, item)
        if os.path.isdir(item_path):
            # Count images in the folder
            image_count = len([f for f in os.listdir(item_path) 
                              if f.lower().endswith(('.jpg', '.jpeg', '.png'))])
            debug_info.append(f"Folder: {item}, isdir: {os.path.isdir(item_path)}, Images: {image_count}")
        else:
            debug_info.append(f"File: {item}, isdir: False")
    
    return debug_info

@app.route('/debug_folders')
@login_required
def debug_folders():
    debug_info = debug_users_folders()
    return render_template('debug.html', debug_info=debug_info)

@app.route('/test_camera')
@login_required
def test_camera():
    """Test camera and display diagnostic information"""
    debug_info = []
    
    try:
        debug_info.append("=== Camera Test Started ===")
        cap = open_camera()
        
        if cap is None:
            debug_info.append("ERROR: Camera could not be opened!")
            return render_template('debug.html', debug_info=debug_info)
        
        debug_info.append("SUCCESS: Camera opened!")
        
        # Test frame capture
        debug_info.append("\n=== Testing Frame Capture ===")
        for i in range(10):
            ret, frame = cap.read()
            if ret and frame is not None:
                debug_info.append(f"Frame {i+1}: SUCCESS - Shape: {frame.shape}, Mean: {frame.mean():.2f}")
            else:
                debug_info.append(f"Frame {i+1}: FAILED - ret={ret}, frame is None: {frame is None}")
            time.sleep(0.1)
        
        cap.release()
        debug_info.append("\n=== Camera Test Completed ===")
        
    except Exception as e:
        debug_info.append(f"ERROR: {str(e)}")
        import traceback
        debug_info.append(traceback.format_exc())
    
    return render_template('debug.html', debug_info=debug_info)

def extract_faces(img, scale_factor=1.05, min_neighbors=3):
    """
    Extract faces from image using Cascade Classifier
    More tolerant parameters for rotated faces
    """
    if img is not None:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        # Use lower scale_factor and min_neighbors for better detection of rotated faces
        face_points = face_detector.detectMultiScale(gray, scaleFactor=scale_factor, minNeighbors=min_neighbors)
        return face_points
    else:
        return []

def preprocess_face(face):
    try:
        # Convert to grayscale
        gray = cv2.cvtColor(face, cv2.COLOR_BGR2GRAY)
        
        # Apply histogram equalization for better contrast
        gray = cv2.equalizeHist(gray)
        
        # Apply Gaussian blur to reduce noise
        gray = cv2.GaussianBlur(gray, (5, 5), 0)
        
        # Resize to standard dimensions
        gray = cv2.resize(gray, (50, 50))
        
        # Normalize pixel values
        gray = gray.astype('float32') / 255.0
        
        return gray
    except Exception as e:
        print(f"Error preprocessing face: {str(e)}")
        return None

#### Identify face using face_recognition encodings

def _load_encoding_store():
    """Load encoding store with caching for better performance on low-end devices"""
    global _ENCODING_CACHE, _ENCODING_CACHE_TIMESTAMP
    
    if not MODEL_CACHE_ENABLED:
        # Original behavior: load from disk every time (slower)
        model_path = 'static/face_recognition_model.pkl'
        if not os.path.exists(model_path):
            return [], []
        data = joblib.load(model_path)
        if isinstance(data, dict):
            encodings = data.get('encodings', [])
            names = data.get('names', [])
            return encodings, names
        return [], []
    
    # Optimized: use cache with expiry
    current_time = time.time()
    
    with _ENCODING_CACHE_LOCK:
        # Check if cache is valid
        if (_ENCODING_CACHE is not None and 
            current_time - _ENCODING_CACHE_TIMESTAMP < _CACHE_EXPIRY_SECONDS):
            return _ENCODING_CACHE
        
        # Cache miss or expired - reload
        model_path = 'static/face_recognition_model.pkl'
        if not os.path.exists(model_path):
            _ENCODING_CACHE = ([], [])
            _ENCODING_CACHE_TIMESTAMP = current_time
            return [], []
        
        try:
            data = joblib.load(model_path)
            if isinstance(data, dict):
                encodings = data.get('encodings', [])
                names = data.get('names', [])
                _ENCODING_CACHE = (encodings, names)
                _ENCODING_CACHE_TIMESTAMP = current_time
                return encodings, names
        except Exception as e:
            print(f"Error loading encoding cache: {e}")
            _ENCODING_CACHE = ([], [])
            _ENCODING_CACHE_TIMESTAMP = current_time
            return [], []
        
        _ENCODING_CACHE = ([], [])
        _ENCODING_CACHE_TIMESTAMP = current_time
        return [], []


def recognize_face(face_encoding, known_encodings, known_names):
    if len(known_encodings) == 0:
        return "unknown", 1.0, False

    distances = face_recognition.face_distance(known_encodings, face_encoding)

    user_to_distances = defaultdict(list)
    for d, user in zip(distances, known_names):
        user_to_distances[user].append(float(d))

    if not user_to_distances:
        return "unknown", 1.0, False

    user_scores = {}
    for user, dists in user_to_distances.items():
        dists_sorted = sorted(dists)
        k = min(TOP_K_PER_USER, len(dists_sorted))
        user_scores[user] = float(np.mean(dists_sorted[:k]))

    best_user = min(user_scores, key=lambda x: user_scores[x])
    best_score = user_scores[best_user]

    sorted_scores = sorted(user_scores.values())
    second_score = sorted_scores[1] if len(sorted_scores) > 1 else 1.0
    margin_ok = (second_score - best_score) >= AMBIGUITY_MARGIN

    if best_score <= STRICT_THRESHOLD and margin_ok:
        return best_user, best_score, True

    return "unknown", best_score, False


def identify_face(face_encoding):
    try:
        known_encodings, known_names = _load_encoding_store()
        return recognize_face(face_encoding, known_encodings, known_names)
    except Exception as e:
        print(f"Error in face recognition: {str(e)}")
        return "unknown", 1.0, False


#### Build encoding store from all faces in dataset
def train_model():
    try:
        known_face_encodings = []
        known_face_names = []
        userlist = os.listdir('static/faces')

        if len(userlist) == 0:
            print("No users to train on!")
            return False

        for user in userlist:
            user_folder = f'static/faces/{user}'
            if not os.path.isdir(user_folder):
                continue

            image_files = [f for f in os.listdir(user_folder) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
            if len(image_files) == 0:
                print(f"No images for user {user}")
                continue

            print(f"Training on {len(image_files)} images for {user}")
            for imgname in image_files:
                img_path = f'{user_folder}/{imgname}'
                try:
                    image = face_recognition.load_image_file(img_path)
                    locations = face_recognition.face_locations(image, model='hog', number_of_times_to_upsample=FACE_DETECTION_UPSAMPLE)
                    encodings = face_recognition.face_encodings(image, locations)
                    if len(encodings) == 0:
                        print(f"No face encoding found: {img_path}")
                        continue

                    # Store first face encoding from each image
                    known_face_encodings.append(encodings[0])
                    known_face_names.append(user)
                except Exception as ex:
                    print(f"Failed to encode {img_path}: {ex}")

        if len(known_face_encodings) == 0:
            print("No valid face encodings found for training!")
            return False

        data = {
            'encodings': known_face_encodings,
            'names': known_face_names,
            'threshold': STRICT_THRESHOLD,
            'updated_at': datetime.now().isoformat()
        }
        joblib.dump(data, 'static/face_recognition_model.pkl')
        print(f"Encoding store saved with {len(known_face_encodings)} samples from {len(set(known_face_names))} users")
        return True
    except Exception as e:
        print(f"Error training model: {str(e)}")
        return False

#### Extract today's attendance from PostgreSQL (single source of truth)
def extract_attendance():
    try:
        today = date.today()
        rows = (
            db.session.query(Student.name, Student.roll_no, Attendance.time)
            .join(Attendance, Attendance.student_id == Student.id)
            .filter(Attendance.date == today)
            .order_by(Attendance.time.asc())
            .all()
        )

        names = [r[0] for r in rows]
        rolls = [str(r[1]) for r in rows]
        times = [r[2].strftime("%H:%M:%S") if r[2] else "" for r in rows]
        return names, rolls, times, len(rows)
    except Exception as e:
        print(f"Error extracting attendance from DB: {str(e)}")
        return [], [], [], 0

#### Add attendance of a specific user (DB-only)
def add_attendance(name, roll):
    try:
        if not name or str(name).strip().lower() == "unknown":
            print("Skipping unknown face - name is unknown")
            return False

        name = str(name).strip()
        roll = str(roll).strip()

        with app.app_context():
            student = Student.query.filter_by(roll_no=roll).first()
            if student is None:
                student = save_student_with_encoding(roll, name, department="General")

            record, created = mark_attendance(
                student.id,
                student_name=student.name,
                roll_no=student.roll_no,
                department=student.department,
            )
            if created:
                print(f"✓ Attendance recorded in PostgreSQL for {name}_{roll}")
                return True

            print(f"Attendance already marked for {name}_{roll} today")
            return False

    except Exception as e:
        print(f"✗ Error adding attendance: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

################## ROUTING FUNCTIONS ##############################

#### Our main page - NOW REQUIRES LOGIN
@app.route('/')
@login_required
def home():
    names, rolls, times, l = extract_attendance()
    registered_users = get_registered_users()
    return render_template('home.html', names=names, rolls=rolls, times=times, l=l,
                           registered_users=registered_users, totalreg=totalreg(),
                           datetoday2=datetoday2, mess=MESSAGE)

#### This function will run when we click on Take Attendance Button - REQUIRES LOGIN
@app.route('/start', methods=['GET', 'POST'])
@login_required
def start():
    ATTENDANCE_MARKED = False
    message = ""

    # 🚀 BLOCK CAMERA ON RENDER
    if os.environ.get("RENDER") == "true":
        message = "⚠️ Camera not supported on cloud. Use local system for attendance."
        registered_users = get_registered_users()
        names, rolls, times, l = extract_attendance()

        return render_template(
            'home.html',
            names=names,
            rolls=rolls,
            times=times,
            l=l,
            registered_users=registered_users,
            totalreg=totalreg(),
            datetoday2=datetoday2,
            mess=message
        )

    # ✅ LOCAL MACHINE CAMERA LOGIC
    try:
        print("Initializing camera...")
        cap = open_camera()

        if cap is None:
            message = "Could not access camera"
            registered_users = get_registered_users()

            return render_template(
                'home.html',
                names=[], rolls=[], times=[], l=0,
                registered_users=registered_users,
                totalreg=totalreg(),
                datetoday2=datetoday2,
                mess=message
            )

        # 👉 Continue your existing camera logic here

    except Exception as e:
        print("Error:", str(e))
        message = "Error starting camera"

        registered_users = get_registered_users()
        return render_template(
            'home.html',
            names=[], rolls=[], times=[], l=0,
            registered_users=registered_users,
            totalreg=totalreg(),
            datetoday2=datetoday2,
            mess=message
        )
        
        # Check if model exists
        if not os.path.exists('static/face_recognition_model.pkl'):
            message = "Face recognition model not found! Please register users first."
            print(message)
            cap.release()
            registered_users = get_registered_users()
            return render_template('home.html', names=[], rolls=[], times=[], l=0, 
                                  registered_users=registered_users, totalreg=totalreg(), 
                                  datetoday2=datetoday2, mess=message)
        
        # Helper: load today's already-marked set to avoid duplicates
        def get_marked_set():
            try:
                names, rolls, _, _ = extract_attendance()
                # Normalize to strings to avoid int/string mismatches that cause duplicates
                return set((str(n), str(r)) for n, r in zip(names, rolls))
            except Exception:
                return set()

        marked_set = get_marked_set()

        # Main attendance loop (supports multiple faces)
        consecutive_fail = 0
        frame_count = 0
        last_unknown_log_ts = 0.0
        last_predictions = []  # Cache recent predictions for smooth display
        fps_timer = time.time()
        fps_counter = 0
        current_fps = 0.0

        while True:
            ret, frame = cap.read()
            if not ret or frame is None:
                message = "Failed to capture frame from camera"
                print(f"Frame read failed: ret={ret}, frame is None: {frame is None}")
                consecutive_fail += 1
                if consecutive_fail > 30:  # Increased threshold
                    message = f"Camera connection lost after {consecutive_fail} failed attempts. Please check camera connection and try again."
                    print(message)
                    break
                time.sleep(0.05)  # Longer sleep between retries
                continue

            # Validate frame
            if frame.size == 0 or frame.shape[0] < 10 or frame.shape[1] < 10:
                print(f"Invalid frame dimensions: {frame.shape if frame is not None else 'None'}")
                consecutive_fail += 1
                if consecutive_fail > 30:
                    message = "Camera producing invalid frames. Please restart the application."
                    break
                time.sleep(0.05)
                continue

            consecutive_fail = 0
            frame_count += 1

            # Per-frame reset to avoid cross-face contamination
            recognized_names = []
            predictions = []

            # OPTIMIZATION: Only process face detection every Nth frame (skip frames for low-end devices)
            should_detect_faces = (frame_count % FRAME_SKIP) == 0
            
            if should_detect_faces:
                # Optimized face detection with lower resolution and reduced upsampling
                small_frame = cv2.resize(frame, (0, 0), fx=FACE_DETECTION_SCALE, fy=FACE_DETECTION_SCALE)
                rgb_small = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)
                face_locations = face_recognition.face_locations(
                    rgb_small,
                    model="hog",
                    number_of_times_to_upsample=FACE_DETECTION_UPSAMPLE
                )
                face_encodings = face_recognition.face_encodings(rgb_small, face_locations)

                # Stable left-to-right ordering prevents identity jumping between faces
                face_pairs = sorted(zip(face_locations, face_encodings), key=lambda p: p[0][3])

                # Scale coordinates back to original frame size while keeping small-face location
                scale_factor = 1.0 / FACE_DETECTION_SCALE
                converted_pairs = []
                for (top, right, bottom, left), encoding in face_pairs:
                    converted_pairs.append({
                        'big_loc': (
                            int(top * scale_factor),
                            int(right * scale_factor),
                            int(bottom * scale_factor),
                            int(left * scale_factor),
                        ),
                        'small_loc': (top, right, bottom, left),
                        'encoding': encoding,
                    })
                face_pairs = converted_pairs
            else:
                # Reuse predictions from previous frame to maintain smooth display
                face_pairs = []

            for face_obj in face_pairs:
                top, right, bottom, left = face_obj['big_loc']
                face_encoding = face_obj['encoding']
                w = right - left
                h = bottom - top

                # Independent state for each face
                person = "unknown"
                distance = 1.0

                if w >= MIN_FACE_SIZE and h >= MIN_FACE_SIZE:
                    raw_person, distance, is_known = identify_face(face_encoding)
                    if is_known:
                        person = raw_person
                        recognized_names.append(person)

                color = (0, 255, 0) if person != "unknown" else (0, 0, 255)
                cv2.rectangle(frame, (left, top), (right, bottom), color, 2)

                if person != "unknown" and '_' in person:
                    name, roll = person.rsplit('_', 1)
                    label_text = f"{name} (ID: {roll}) Confidence: {distance:.2f}"
                elif person != "unknown":
                    label_text = f"{person} Confidence: {distance:.2f}"
                else:
                    label_text = "Unknown Person Detected"
                    now_ts = time.time()
                    if now_ts - last_unknown_log_ts >= UNKNOWN_LOG_COOLDOWN_SEC:
                        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Unknown face detected")
                        last_unknown_log_ts = now_ts

                cv2.putText(frame, label_text, (left, max(20, top - 10)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
                predictions.append((left, top, w, h, person, distance))

            # Cache predictions for smooth display even when skipping frames
            if should_detect_faces and predictions:
                last_predictions = predictions

            # Show instruction text once per frame
            cv2.putText(frame, "Press 'a' to mark ALL visible faces", (30, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
            
            # Display FPS counter for performance monitoring
            fps_counter += 1
            elapsed = time.time() - fps_timer
            if elapsed >= 1.0:
                current_fps = fps_counter / elapsed
                fps_timer = time.time()
                fps_counter = 0
            
            fps_text = f"FPS: {current_fps:.1f} | Processing: {'YES' if should_detect_faces else 'NO (cached)'}"
            cv2.putText(frame, fps_text, (30, frame.shape[0] - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)

            # Process key press (single press marks multiple faces)
            key = cv2.waitKey(1)
            if key == ord('a'):
                marked_count = 0
                already_marked_count = 0
                # Use cached predictions if current detection didn't find faces
                active_predictions = predictions if predictions else last_predictions
                for (x, y, w, h, person, distance) in active_predictions:
                    if person == "unknown":
                        # Optional: indicate unknown
                        cv2.putText(frame, f"Unknown (d={distance:.2f})", (x, max(0, y - 30)),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
                        continue

                    if '_' in person:
                        name, roll = person.rsplit('_', 1)
                        if (name, roll) not in marked_set:
                            # Mark attendance for new user
                            add_attendance(name, roll)
                            marked_set.add((name, roll))
                            ATTENDANCE_MARKED = True
                            marked_count += 1
                            # Visual confirmation near that specific face - clear "Marked" message
                            cv2.putText(frame, "Marked", (x, y + h + 25),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                        else:
                            # User already marked today
                            already_marked_count += 1
                            cv2.putText(frame, "Already Marked Today", (x, y + h + 25),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 165, 0), 2)

                # Build professional message
                if marked_count > 0 and already_marked_count > 0:
                    message = f"Attendance marked for {marked_count} user(s). {already_marked_count} already marked today."
                elif marked_count > 0:
                    message = f"Attendance marked for {marked_count} user(s)"
                elif already_marked_count > 0:
                    message = f"{already_marked_count} user(s) already marked today"
                else:
                    message = "No known faces to mark"

                # Show frame with confirmations briefly
                #cv2.imshow('Attendance Check, press "q" to exit', frame)
                #cv2.waitKey(1500)

           

            elif len(predictions) == 0 and frame_count % 3 == 0:
                # No face detected
                cv2.putText(frame, "No face detected", (30, 70),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

            # Show frame
            #cv2.imshow('Attendance Check, press "q" to exit', frame)

            # Exit is handled in the single key poll above
    
        # Clean up
        if cap is not None:
            cap.release()
        cv2.destroyAllWindows()
        
        # Update attendance records
        names, rolls, times, l = extract_attendance()
        registered_users = get_registered_users()
        
        # Set final message
        if not message:
            message = 'Attendance taken successfully' if ATTENDANCE_MARKED else 'No attendance taken'
        
        return render_template('home.html', names=names, rolls=rolls, times=times, l=l, 
                              registered_users=registered_users, totalreg=totalreg(), 
                              datetoday2=datetoday2, mess=message)
    except Exception as e:
        message = f"Error: {str(e)}"
        print(message)
        import traceback
        traceback.print_exc()
        try:
            if 'cap' in locals() and cap is not None:
                cap.release()
            cv2.destroyAllWindows()
        except:
            pass
        registered_users = get_registered_users()
        return render_template('home.html', names=[], rolls=[], times=[], l=0, 
                              registered_users=registered_users, totalreg=totalreg(), 
                              datetoday2=datetoday2, mess=message)


@app.route('/instructions')
@login_required
def instructions():
    return render_template('attendance_instructions.html')

@app.route('/add', methods=['POST'])
def add():
    try:
        # Get form data
        newusername = request.form['newusername']
        newuserid = request.form['newuserid']
        
        # Validate input
        if not newusername or not newuserid:
            print("Username or ID is empty")
            return redirect(url_for('home'))
            
        # Create folder path
        userimagefolder = 'static/faces/'+newusername+'_'+str(newuserid)
        
        # Remove existing folder if it exists
        if os.path.isdir(userimagefolder):
            shutil.rmtree(userimagefolder)
            print(f"Removed existing folder: {userimagefolder}")
            
        # Create new folder
        os.makedirs(userimagefolder)
        print(f"Created folder: {userimagefolder}")
        
        # Initialize camera
        cap = open_camera()
        if cap is None:
            print("Could not access camera")
            return redirect(url_for('home'))

        # Warm up camera
        print("Warming up camera...")
        warmup_camera(cap, frames=30)
        time.sleep(0.2)
        
        # Capture images without directional head-pose steps
        captured_images = 0
        capture_interval_frames = 5
        capture_timer = 0
        no_face_frames = 0
        
        while captured_images < 25:
            ret, frame = cap.read()
            if not ret:
                print("Failed to capture frame")
                break
            
            display_frame = frame.copy()
            
            # Detect faces for visual feedback (with more tolerant parameters)
            faces = extract_faces(frame, scale_factor=1.05, min_neighbors=3)
            
            # Display header
            cv2.putText(display_frame, "LOOK AT CAMERA", (20, 50),
                       cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 165, 255), 2)
            cv2.putText(display_frame, "Keep face inside box", (20, 100),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 165, 255), 2)
            cv2.putText(display_frame, f"Progress: {captured_images}/25", (20, 150),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
            
            if len(faces) == 0:
                # No face detected, keep waiting
                no_face_frames += 1
                capture_timer = 0
                
                cv2.putText(display_frame, f"NO FACE DETECTED", (20, 200),
                           cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 2)
                cv2.putText(display_frame, f"Position your face in frame", (20, 250),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 165, 0), 2)
            else:
                # Face detected
                no_face_frames = 0
                # Use the largest face as capture target
                x, y, w, h = max(faces, key=lambda box: box[2] * box[3])
                cv2.rectangle(display_frame, (x, y), (x + w, y + h), (0, 255, 0), 3)

                y_margin = int(h * 0.2)
                x_margin = int(w * 0.2)
                y1 = max(0, y - y_margin)
                y2 = min(frame.shape[0], y + h + y_margin)
                x1 = max(0, x - x_margin)
                x2 = min(frame.shape[1], x + w + x_margin)

                capture_timer += 1
                wait_count = max(0, capture_interval_frames - capture_timer)
                cv2.putText(display_frame, f"Hold steady ({wait_count})", (20, 200),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 165, 255), 2)

                if capture_timer >= capture_interval_frames:
                    face_region = display_frame[y1:y2, x1:x2]
                    if face_region.size > 0:
                        img_name = f"{newusername}_{captured_images}.jpg"
                        img_path = os.path.join(userimagefolder, img_name)
                        cv2.imwrite(img_path, face_region)
                        print(f"Saved image {captured_images+1}: {img_name}")
                        captured_images += 1
                        cv2.putText(display_frame, "✓ CAPTURED!", (20, 250),
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)
                    capture_timer = 0
            
            # Show frame
            cv2.imshow('Adding new User', display_frame)
            
            # Check for exit
            if cv2.waitKey(1) == 27:  # ESC key
                break
        
        # Clean up
        if cap is not None:
            cap.release()
        cv2.destroyAllWindows()
        
        # Train model with new data
        print("Training model with new user data...")
        train_model()

        # Persist student + binary face encoding in PostgreSQL
        save_student_with_encoding(
            roll_no=str(newuserid),
            name=newusername,
            department="General",
            folder_path=userimagefolder,
        )

        return redirect(url_for('home'))
    except Exception as e:
        print(f"Error in add user: {str(e)}")
        import traceback
        traceback.print_exc()
        try:
            if 'cap' in locals() and cap is not None:
                cap.release()
            cv2.destroyAllWindows()
        except:
            pass
        return redirect(url_for('home'))

@app.route('/admin')
@login_required
def admin():
    # Get attendance data
    names, rolls, times, l = extract_attendance()
    registered_users = get_registered_users()
    
    # Count UNIQUE attendees (not duplicate marks)
    # If same user marked attendance twice, count only once
    unique_attendees = len(set(zip(names, rolls))) if names else 0
    daily_attendance = unique_attendees
    absent_count = max(0, totalreg() - unique_attendees)
    
    return render_template('admin.html', 
                          names=names, 
                          rolls=rolls, 
                          times=times, 
                          l=l,
                          registered_users=registered_users, 
                          totalreg=totalreg(),
                          daily_attendance=daily_attendance,
                          absent_count=absent_count,
                          datetoday2=datetoday2)

@app.route('/admin/user/delete', methods=['POST'])
@login_required
def admin_delete_user():
    name = request.form.get('name')
    user_id = request.form.get('id')
    if not name or not user_id:
        return redirect(url_for('admin'))

    folder = os.path.join('static', 'faces', f"{name}_{user_id}")
    try:
        if os.path.isdir(folder):
            shutil.rmtree(folder)
            print(f"Deleted user folder: {folder}")
        else:
            print(f"Folder not found for deletion: {folder}")

        student = Student.query.filter_by(roll_no=str(user_id)).first()
        if student:
            db.session.delete(student)
            db.session.commit()

        # Retrain model after deletion
        train_model()
    except Exception as e:
        print(f"Error deleting user {name}_{user_id}: {str(e)}")
    return redirect(url_for('admin'))

@app.route('/admin/user/edit', methods=['POST'])
@login_required
def admin_edit_user():
    old_name = request.form.get('old_name')
    old_id = request.form.get('old_id')
    new_name = request.form.get('new_name')
    new_id = request.form.get('new_id')

    if not old_name or not old_id or not new_name or not new_id:
        return redirect(url_for('admin'))

    old_name = old_name.strip()
    old_id = str(old_id).strip()
    new_name = new_name.strip()
    new_id = str(new_id).strip()

    old_folder = os.path.join('static', 'faces', f"{old_name}_{old_id}")
    new_folder = os.path.join('static', 'faces', f"{new_name}_{new_id}")
    rename_needed = (old_folder != new_folder)

    try:
        student = Student.query.filter_by(roll_no=str(old_id)).first()
        if not student:
            print(f"Student not found for edit: {old_id}")
            return redirect(url_for('admin'))

        final_folder = old_folder
        if rename_needed:
            if os.path.isdir(old_folder):
                # If destination exists (different folder), remove it first to avoid rename errors
                if os.path.isdir(new_folder):
                    shutil.rmtree(new_folder)
                os.rename(old_folder, new_folder)
                final_folder = new_folder
                print(f"Renamed {old_folder} -> {new_folder}")
            else:
                # Continue with DB update even if folder is missing/mismatched.
                final_folder = new_folder
                print(f"Source folder not found for rename: {old_folder}. Continuing with DB update.")
        else:
            print("Edit requested with unchanged name/id; skipping folder rename")

        student.roll_no = str(new_id)
        student.name = new_name
        db.session.commit()

        # Update stored encoding only when a usable folder exists.
        folder_for_encoding = final_folder if os.path.isdir(final_folder) else None
        save_student_with_encoding(
            str(new_id),
            new_name,
            department=student.department or "General",
            folder_path=folder_for_encoding,
        )

        # Retrain model so labels reflect new folder/name when available.
        train_model()
    except Exception as e:
        print(f"Error renaming user folder: {str(e)}")
    return redirect(url_for('admin'))

@app.route('/adminlogin', methods=['GET', 'POST'])
def adminlogin():
    if request.method == 'POST':
        username = request.form.get('userName')
        password = request.form.get('password')
        
        # Use database authentication
        if verify_user(username, password):
            session['logged_in'] = True
            session['username'] = username
            return redirect(url_for('home'))
        else:
            return render_template('adminlogin.html', error="Invalid credentials")
    
    # If already logged in, redirect to home
    if 'logged_in' in session:
        return redirect(url_for('home'))
    
    return render_template('adminlogin.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        email = request.form.get('email')
        
        # Validation
        if not username or not password or not email:
            return render_template('sign.html', error="All fields are required")
        
        if password != confirm_password:
            return render_template('sign.html', error="Passwords do not match")
        
        if len(password) < 6:
            return render_template('sign.html', error="Password must be at least 6 characters")
        
        # Create user
        if create_user(username, password, email):
            session['logged_in'] = True
            session['username'] = username
            return redirect(url_for('home'))
        else:
            return render_template('sign.html', error="Username already exists")
    
    return render_template('sign.html')

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        username = request.form.get('username')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        if not username or not new_password:
            return render_template('forgot_password.html', error="All fields are required")
        
        if new_password != confirm_password:
            return render_template('forgot_password.html', error="Passwords do not match")
        
        if len(new_password) < 6:
            return render_template('forgot_password.html', error="Password must be at least 6 characters")
        
        if not username_exists(username):
            return render_template('forgot_password.html', error="Username not found")
        
        reset_password(username, new_password)
        return render_template('forgot_password.html', success="Password reset successfully! You can now login.")
    
    return render_template('forgot_password.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('adminlogin'))

@app.route('/admin/export')
@login_required
def export_data():
    # Export attendance data logic here
    return redirect(url_for('admin'))

@app.route('/admin/retrain')
@login_required
def retrain_model():
    # Call your train_model function
    train_model()
    return redirect(url_for('admin'))

@app.route('/attendance/today')
@login_required
def download_today_csv():
    try:
        # Export today's DB attendance as CSV (generated on the fly, no file dependency)
        today = date.today()
        rows = (
            db.session.query(Student.name, Student.roll_no, Attendance.date, Attendance.time)
            .join(Attendance, Attendance.student_id == Student.id)
            .filter(Attendance.date == today)
            .order_by(Attendance.time.asc())
            .all()
        )

        output = ["Name,Roll,Date,Time"]
        for name, roll, att_date, att_time in rows:
            output.append(f"{name},{roll},{att_date.strftime('%Y-%m-%d')},{att_time.strftime('%H:%M:%S') if att_time else ''}")

        csv_data = "\n".join(output)
        return Response(
            csv_data,
            mimetype="text/csv",
            headers={"Content-Disposition": f"inline; filename=attendance-{today.strftime('%Y-%m-%d')}.csv"}
        )
    except Exception as e:
        print(f"Error serving today's attendance CSV from DB: {str(e)}")
        return redirect(url_for('home'))

#### Our main function which runs the Flask App
if __name__ == '__main__':
    app.run(debug=True, port=1000)
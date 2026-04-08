# 🔹 imports FIRST
# 🔹 ALL IMPORTS FIRST
import base64
import numpy as np
import cv2
from database import init_db_config, db
from flask_cors import CORS
import os
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass
# Load Haar Cascade for face detection
cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
if not cascade_path or not os.path.exists(cascade_path):
    cascade_path = 'haarcascade_frontalface_default.xml'

face_cascade = cv2.CascadeClassifier(cascade_path)
if face_cascade.empty():
    print("WARNING: Could not load Haar Cascade")
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
from models import Admin, Student, Attendance
from helpers import save_student_with_encoding, mark_attendance
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "fallback-key")

init_db_config(app)
CORS(app)
# 🔹 ROUTES
@app.route('/api/recognize', methods=['POST'])
def recognize():
    try:
        data = request.json['image']

        encoded = data.split(",")[1]
        img_bytes = base64.b64decode(encoded)
        np_arr = np.frombuffer(img_bytes, np.uint8)
        frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

        face_locations = detect_faces_cascade(frame)
        if len(face_locations) == 0:
            return {"status": "No face detected"}

        for (top, right, bottom, left) in face_locations:
            face_roi = frame[top:bottom, left:right]
            if face_roi.size == 0:
                continue

            person, confidence, is_known = identify_face(face_roi)
            if is_known and "_" in person:
                name, roll_no = person.rsplit("_", 1)
                saved = add_attendance(name.strip(), roll_no.strip())
                if saved:
                    return {"status": f"Attendance marked for {person} (confidence: {confidence:.2f})"}
                return {"status": f"Already marked for {person} today"}

        return {"status": "Unknown face"}
    except Exception as e:
        return {"status": f"Recognition error: {str(e)}"}
    
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

from flask import Flask, request, render_template, redirect, url_for
from flask_cors import CORS
from database import init_db_config, db


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

def detect_faces_cascade(frame):
    """Detect faces using Haar Cascade"""
    try:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
        # Convert to (top, right, bottom, left) format
        face_locs = []
        for (x, y, w, h) in faces:
            face_locs.append((y, x + w, y + h, x))
        return face_locs
    except Exception as e:
        print(f"Error in face detection: {e}")
        return []

def extract_face_descriptor(face_roi):
    """Extract SIFT/ORB descriptor from a face region"""
    if face_roi is None or face_roi.size == 0:
        return None
    
    try:
        gray = cv2.cvtColor(face_roi, cv2.COLOR_BGR2GRAY)
        
        # Try SIFT first, fallback to ORB
        try:
            sift = cv2.SIFT_create()
            kp, des = sift.detectAndCompute(gray, None)
        except:
            orb = cv2.ORB_create(nfeatures=200)
            kp, des = orb.detectAndCompute(gray, None)
        
        if des is None or len(des) == 0:
            hist = cv2.calcHist([gray], [0], None, [256], [0, 256])
            return hist.flatten()
        
        return des
    except Exception as e:
        print(f"Error extracting features: {e}")
        return None

def match_face_descriptors(test_desc, ref_desc):
    """Match two face descriptors and return similarity score"""
    if test_desc is None or ref_desc is None:
        return 0.0
    
    try:
        # Histogram comparison
        if test_desc.ndim == 1 and ref_desc.ndim == 1:
            distance = cv2.compareHist(
                test_desc.astype(np.uint8) if test_desc.dtype != np.uint8 else test_desc,
                ref_desc.astype(np.uint8) if ref_desc.dtype != np.uint8 else ref_desc,
                cv2.HISTCMP_BHATTACHARYYA
            )
            return 1.0 - distance
        
        # Feature descriptor matching
        if test_desc.ndim == 2 and ref_desc.ndim == 2:
            bf = cv2.BFMatcher(cv2.NORM_L2, crossCheck=False)
            knn_matches = bf.knnMatch(test_desc, ref_desc, k=2)
            
            good_matches = []
            for match_pair in knn_matches:
                if len(match_pair) == 2:
                    m, n = match_pair
                    if m.distance < 0.75 * n.distance:
                        good_matches.append(m)
            
            if len(good_matches) == 0:
                return 0.0
            
            return min(1.0, len(good_matches) / 15.0)
    except:
        pass
    
    return 0.0

def identify_face(face_roi):
    """Identify face by comparing with registered users"""
    test_desc = extract_face_descriptor(face_roi)
    if test_desc is None:
        return "unknown", 0.0, False
    
    faces_dir = 'static/faces'
    if not os.path.exists(faces_dir):
        return "unknown", 0.0, False
    
    best_match = "unknown"
    best_score = 0.0
    scores_by_user = defaultdict(list)
    
    # Compare with each registered user
    for user in os.listdir(faces_dir):
        user_path = os.path.join(faces_dir, user)
        if not os.path.isdir(user_path):
            continue
        
        images = [f for f in os.listdir(user_path) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
        if not images:
            continue
        
        # ✅ USE ALL REFERENCE IMAGES (better for multi-angle)
        for img_name in images:
            try:
                img_path = os.path.join(user_path, img_name)
                ref_img = cv2.imread(img_path)
                if ref_img is None:
                    continue
                
                # Detect faces in reference image
                ref_faces = detect_faces_cascade(ref_img)
                if not ref_faces:
                    continue
                
                # Use first detected face
                top, right, bottom, left = ref_faces[0]
                ref_roi = ref_img[top:bottom, left:right]
                
                ref_desc = extract_face_descriptor(ref_roi)
                if ref_desc is None:
                    continue
                
                # Match descriptors
                score = match_face_descriptors(test_desc, ref_desc)
                scores_by_user[user].append(score)
            except Exception as e:
                continue
    
    # ✅ Use MEDIAN (more robust than mean for multi-angle)
    if scores_by_user:
        for user, scores in scores_by_user.items():
            median_score = np.median(scores)
            if median_score > best_score:
                best_score = median_score
                best_match = user
    
    # ✅ LOWER THRESHOLD for angle tolerance
    if best_score > 0.20:  # Was 0.30
        return best_match, best_score, True
    
    return "unknown", best_score, False

def train_model():
    """Training is not needed with feature-based matching"""
    print("Feature-based matching doesn't require explicit training")
    return True


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

#### Global camera for streaming
global_cap = None
global_cap_lock = threading.Lock()

#### This function will run when we click on Take Attendance Button - REQUIRES LOGIN
@app.route('/start', methods=['GET', 'POST'])
@login_required
def start():
    return render_template('camera.html', datetoday2=datetoday2)

@app.route('/video_feed')
@login_required
def video_feed():
    """Stream video frames to browser"""
    def generate():
        global global_cap, global_cap_lock
        
        try:
            with global_cap_lock:
                if global_cap is None:
                    global_cap = open_camera()
                cap = global_cap
            
            if cap is None:
                print("Camera failed to open")
                return
            
            # No explicit model check needed for feature-based matching
            
            # Load marked set
            try:
                names, rolls, _, _ = extract_attendance()
                marked_set = set((str(n), str(r)) for n, r in zip(names, rolls))
            except:
                marked_set = set()
            
            frame_count = 0
            consecutive_fail = 0
            
            while True:
                with global_cap_lock:
                    ret, frame = cap.read()
                
                if not ret or frame is None:
                    consecutive_fail += 1
                    if consecutive_fail > 30:
                        break
                    time.sleep(0.05)
                    continue
                
                consecutive_fail = 0
                frame_count += 1
                
                # Detect and mark faces
                should_detect = (frame_count % FRAME_SKIP) == 0
                
                try:
                    if should_detect:
                        # Detect faces using Haar Cascade
                        face_locations = detect_faces_cascade(frame)
                        
                        for (top, right, bottom, left) in face_locations:
                            # Extract face region
                            face_roi = frame[top:bottom, left:right]
                            if face_roi.size == 0:
                                continue
                            
                            # Identify the face
                            person, confidence, is_known = identify_face(face_roi)
                            
                            if is_known and '_' in person:
                                name, roll = person.rsplit('_', 1)
                                color = (0, 255, 0)
                                
                                if (name, roll) not in marked_set:
                                    add_attendance(name.strip(), roll.strip())
                                    marked_set.add((name, roll))
                                    label = f"✓ {name} ({roll}) - {confidence:.0%}"
                                else:
                                    label = f"✓ {name} ({roll}) - Already marked"
                            else:
                                color = (0, 0, 255)
                                label = f"Unknown"
                            
                            cv2.rectangle(frame, (left, top), (right, bottom), color, 2)
                            cv2.putText(frame, label, (left, max(20, top - 10)),
                                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
                
                    # Add instruction text
                    cv2.putText(frame, "Press 'q' to close", (10, 30),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
                    
                except Exception as e:
                    print(f"Face detection error: {e}")
                
                # Encode frame to JPEG
                ret, buffer = cv2.imencode('.jpg', frame)
                frame_bytes = buffer.tobytes()
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n'
                       b'Content-Length: ' + str(len(frame_bytes)).encode() + b'\r\n\r\n'
                       + frame_bytes + b'\r\n')
                
                time.sleep(0.03)
        
        except Exception as e:
            print(f"Stream error: {e}")
        finally:
            with global_cap_lock:
                if global_cap is not None:
                    global_cap.release()
                    global_cap = None
            cv2.destroyAllWindows()
    
    return Response(generate(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/stop_camera', methods=['POST'])
@login_required
def stop_camera():
    """Stop camera and return attendance data"""
    global global_cap, global_cap_lock
    
    with global_cap_lock:
        if global_cap is not None:
            global_cap.release()
            global_cap = None
    cv2.destroyAllWindows()
    
    names, rolls, times, l = extract_attendance()
    registered_users = get_registered_users()
    message = "Attendance marking complete"
    
    return render_template('home.html', names=names, rolls=rolls, times=times, l=l, 
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
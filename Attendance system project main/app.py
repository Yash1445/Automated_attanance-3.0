import cv2  # type: ignore
import os
import numpy as np
from flask import Flask, request, render_template, redirect, url_for, session, flash, send_from_directory
from datetime import date, datetime
import pandas as pd
import joblib
import time
import shutil
from functools import wraps
import hashlib

from database import init_db_config, db
from models import Admin, Student
from helpers import save_student_with_encoding, mark_attendance

# VARIABLES
MESSAGE = "WELCOME! Instruction: to register your attendance kindly click on 'a' on keyboard"

#### Defining Flask App
app = Flask(__name__)
app.secret_key = 'your-secret-key-here-change-this-in-production'  # Change this to a random secret key
init_db_config(app)

#### Saving Date today in 2 different formats
datetoday = date.today().strftime("%m_%d_%y")
datetoday2 = date.today().strftime("%d-%B-%Y")

#### Initializing VideoCapture object to access WebCam
face_detector = cv2.CascadeClassifier('haarcascade_frontalface_default.xml')  # type: ignore
# Do not hold a global camera handle here; open it on demand in routes
cap = None

# Robust camera opener for Windows (deterministic order)
def open_camera():
    # Release any lingering handles
    for i in range(5):
        tmp = cv2.VideoCapture(i)
        tmp.release()
    time.sleep(0.3)

    devices = [0, 1]

    def try_open(device, backend, delay):
        cap = cv2.VideoCapture(device, backend)
        time.sleep(delay)
        if cap.isOpened():
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
            good = 0
            for _ in range(5):
                ret, frame = cap.read()
                if ret and frame is not None and frame.size > 0 and 1 < frame.mean() < 254:
                    good += 1
                time.sleep(0.02)
            if good >= 2:
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
    for device in devices:
        cap = try_open(device, cv2.CAP_ANY, 0.6)
        if cap:
            return cap
    return None

def warmup_camera(cap, frames=20):
    for _ in range(frames):
        cap.read()
    time.sleep(0.3)
    return True

#### If these directories don't exist, create them
if not os.path.isdir('Attendance'):
    os.makedirs('Attendance')
if not os.path.isdir('static'):
    os.makedirs('static')
if not os.path.isdir('static/faces'):
    os.makedirs('static/faces')
if f'Attendance-{datetoday}.csv' not in os.listdir('Attendance'):
    with open(f'Attendance/Attendance-{datetoday}.csv','w') as f:
        f.write('Name,Roll,Time')

def initialize_database():
    with app.app_context():
        db.create_all()
        default_admin = Admin.query.filter_by(username='admin').first()
        if default_admin is None:
            default_admin = Admin(
                username='admin',
                password=hashlib.sha256('admin123'.encode()).hexdigest(),
                email='admin@example.com',
            )
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

    user = Admin(username=username, password=hash_password(password), email=email)
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
    return len(os.listdir('static/faces'))

def get_registered_users():
    users = []
    faces_dir = 'static/faces'
    if os.path.exists(faces_dir):
        for folder in os.listdir(faces_dir):
            folder_path = os.path.join(faces_dir, folder)
            # Only process directories, not files
            if os.path.isdir(folder_path) and '_' in folder:
                try:
                    name, user_id = folder.rsplit('_', 1)
                    users.append({'name': name, 'id': user_id})
                except ValueError:
                    # Skip folders that don't match the expected format
                    continue
    # Sort users alphabetically by name for consistent display
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

def extract_faces(img):
    if img is not None:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        face_points = face_detector.detectMultiScale(gray, 1.3, 5)
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

#### Identify face using ML model
def identify_face(facearray):
    try:
        # Load model
        model_path = 'static/face_recognition_model.pkl'
        if not os.path.exists(model_path):
            print("Model file doesn't exist!")
            return "unknown", 999.0
            
        model = joblib.load(model_path)
        
        # Ensure proper normalization
        if facearray.max() > 1.0:
            facearray = facearray.astype('float32') / 255.0
        
        # Get all registered users
        registered_users = [f for f in os.listdir('static/faces') if os.path.isdir(f'static/faces/{f}')]
        if len(registered_users) == 0:
            return "unknown", 999.0
        
        # Recognition threshold (lower is stricter). Using the more lenient value we had when marked attendance was working.
        threshold = 14.0
        distances, indices = model.kneighbors(facearray)
        nearest_distance = distances[0][0]
        
        print(f"Recognition distance: {nearest_distance}")
        
        # If distance is too high, mark as unknown
        if nearest_distance > threshold:
            return "unknown", nearest_distance
            
        # Get prediction
        pred = model.predict(facearray)
        return pred[0], nearest_distance
    except Exception as e:
        print(f"Error in face recognition: {str(e)}")
        return "unknown", 999.0

#### A function which trains the model on all the faces available in faces folder
def train_model():
    try:
        faces = []
        labels = []
        userlist = os.listdir('static/faces')
        
        # Ensure we have users to train on
        if len(userlist) == 0:
            print("No users to train on!")
            return False
            
        for user in userlist:
            user_folder = f'static/faces/{user}'
            if not os.path.isdir(user_folder):
                continue
                
            image_files = os.listdir(user_folder)
            if len(image_files) == 0:
                print(f"No images for user {user}")
                continue
                
            print(f"Training on {len(image_files)} images for {user}")
            
            for imgname in image_files:
                if not imgname.lower().endswith(('.jpg', '.jpeg', '.png')):
                    continue
                    
                img_path = f'{user_folder}/{imgname}'
                img = cv2.imread(img_path)
                
                if img is None:
                    print(f"Could not read image: {img_path}")
                    continue
                    
                # Apply same preprocessing as during recognition
                processed_face = preprocess_face(img)
                if processed_face is None:
                    continue
                    
                # Flatten the face image into a 1D array
                faces.append(processed_face.ravel())
                labels.append(user)
        
        if len(faces) == 0:
            print("No faces found for training!")
            return False
            
        # Convert to numpy arrays
        faces = np.array(faces)
        
        # Create and train model
        # Use 1-NN for exact matching
        from sklearn.neighbors import KNeighborsClassifier
        knn = KNeighborsClassifier(n_neighbors=1, weights='uniform')
        knn.fit(faces, labels)
        
        # Save the model
        joblib.dump(knn, 'static/face_recognition_model.pkl')
        
        print(f"Model trained successfully with {len(faces)} images from {len(set(labels))} users")
        return True
    except Exception as e:
        print(f"Error training model: {str(e)}")
        return False

#### Extract info from today's attendance file in attendance folder
def extract_attendance():
    try:
        from datetime import date
        datetoday = date.today().strftime("%m_%d_%y")
        filename = f'Attendance/Attendance-{datetoday}.csv'
        
        if not os.path.exists(filename):
            return [], [], [], 0
            
        df = pd.read_csv(filename)
        names = df['Name'].tolist()
        rolls = df['Roll'].tolist()
        times = df['Time'].tolist()
        l = len(df)
        
        return names, rolls, times, l
    except Exception as e:
        print(f"Error extracting attendance: {str(e)}")
        return [], [], [], 0

#### Add Attendance of a specific user
def add_attendance(name, roll):
    try:
        from datetime import datetime
        datetoday = datetime.now().strftime("%m_%d_%y")
        filename = f'Attendance/Attendance-{datetoday}.csv'

        student = Student.query.filter_by(roll_no=str(roll)).first()
        if student is None:
            student = save_student_with_encoding(str(roll), name, department="General")

        _, created = mark_attendance(student.id)
        if not created:
            print(f"Attendance already marked for {name}_{roll}")
            return False

        if not os.path.exists(filename):
            with open(filename, 'w') as f:
                f.write('Name,Roll,Time')

        current_time = datetime.now().strftime("%H:%M:%S")
        with open(filename, 'a') as f:
            f.write(f'\n{name},{roll},{current_time}')

        print(f"Attendance marked for {name}_{roll}")
        return True
    except Exception as e:
        print(f"Error adding attendance: {str(e)}")
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
    
    try:
        # Initialize camera using robust opener
        print("Initializing camera...")
        cap = open_camera()
        if cap is None:
            message = "Could not access camera"
            print(message)
            registered_users = get_registered_users()
            return render_template('home.html', names=[], rolls=[], times=[], l=0, 
                                  registered_users=registered_users, totalreg=totalreg(), 
                                  datetoday2=datetoday2, mess=message)

        print("Warming up camera...")
        warmup_ok = warmup_camera(cap, frames=50)
        time.sleep(0.2)
        print("Camera ready!" if warmup_ok else "Camera warmup had no successful frames")
        
        # Check if we have registered users
        if totalreg() == 0:
            message = "No registered users! Please register users first."
            print(message)
            cap.release()
            registered_users = get_registered_users()
            return render_template('home.html', names=[], rolls=[], times=[], l=0, 
                                  registered_users=registered_users, totalreg=totalreg(), 
                                  datetoday2=datetoday2, mess=message)
        
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
        last_predictions = []  # Cache predictions for smoother display
        
        while True:
            ret, frame = cap.read()
            if not ret or frame is None:
                message = "Failed to capture frame from camera"
                print(message)
                consecutive_fail += 1
                if consecutive_fail > 15:
                    break
                time.sleep(0.01)
                continue
            consecutive_fail = 0
            frame_count += 1

            # Detect faces only every 2nd frame to improve speed while keeping responsiveness
            predictions = []
            if frame_count % 2 == 0:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                # Optimized face detection: faster parameters
                faces = face_detector.detectMultiScale(gray, scaleFactor=1.2, minNeighbors=4, 
                                                       flags=cv2.CASCADE_SCALE_IMAGE)

                # Collect predictions for all faces in the frame
                if len(faces) > 0:
                    for (x, y, w, h) in faces:
                        # Skip very small faces to reduce false positives
                        if w < 50 or h < 50:
                            continue

                        # Draw rectangle around each face
                        cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)

                        # Expand ROI slightly to capture whole face
                        y_margin = int(h * 0.1)
                        x_margin = int(w * 0.1)
                        y1 = max(0, y - y_margin)
                        y2 = min(frame.shape[0], y + h + y_margin)
                        x1 = max(0, x - x_margin)
                        x2 = min(frame.shape[1], x + w + x_margin)
                        face_roi = frame[y1:y2, x1:x2]

                        label_text = "Unknown"
                        distance = 999.0
                        person = "unknown"
                        if face_roi is not None and face_roi.size > 0:
                            processed_face = preprocess_face(face_roi)
                            if processed_face is not None:
                                person, distance = identify_face(processed_face.reshape(1, -1))
                                if person != "unknown" and '_' in person:
                                    name, roll = person.rsplit('_', 1)
                                    label_text = f"{name} (ID: {roll})"

                        # Draw per-face label above the head
                        cv2.putText(frame, label_text, (x, max(0, y - 10)),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                                    (0, 255, 0) if person != "unknown" else (0, 0, 255), 2)

                        predictions.append((x, y, w, h, person, distance))
                
                # Update cached predictions
                last_predictions = predictions
            else:
                # Use cached predictions on frames where we don't detect
                predictions = last_predictions
                # Redraw cached boxes
                for (x, y, w, h, person, distance) in predictions:
                    cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
                    if person != "unknown" and '_' in person:
                        name, roll = person.rsplit('_', 1)
                        label_text = f"{name} (ID: {roll})"
                    else:
                        label_text = "Unknown"
                    cv2.putText(frame, label_text, (x, max(0, y - 10)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                                (0, 255, 0) if person != "unknown" else (0, 0, 255), 2)

            # Show instruction text once per frame
            cv2.putText(frame, "Press 'a' to mark ALL visible faces", (30, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)

            # Process key press (single press marks multiple faces)
            key = cv2.waitKey(1)
            if key == ord('a'):
                marked_count = 0
                already_marked_count = 0
                for (x, y, w, h, person, distance) in predictions:
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
                cv2.imshow('Attendance Check, press "q" to exit', frame)
                cv2.waitKey(1500)

            elif len(predictions) == 0 and frame_count % 3 == 0:
                # No face detected
                cv2.putText(frame, "No face detected", (30, 70),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

            # Show frame
            cv2.imshow('Attendance Check, press "q" to exit', frame)

            # Exit when user presses 'q'; do not auto-exit after first mark
            if cv2.waitKey(1) == ord('q'):
                break
    
        # Clean up
        if cap is not None:
            cap.release()
        cv2.destroyAllWindows()
        cv2.waitKey(1)
        
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

@app.route('/add', methods=['GET', 'POST'])
@login_required
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
        
        # Capture images
        i, j = 0, 0
        while i < 25:  # Capture more images for better training
            ret, frame = cap.read()
            if not ret:
                print("Failed to capture frame")
                break
                
            # Detect faces
            faces = extract_faces(frame)
            
            for (x, y, w, h) in faces:
                # Create larger face region
                y_margin = int(h * 0.2)
                x_margin = int(w * 0.2)
                y1 = max(0, y - y_margin)
                y2 = min(frame.shape[0], y + h + y_margin)
                x1 = max(0, x - x_margin)
                x2 = min(frame.shape[1], x + w + x_margin)
                
                # Draw rectangle
                cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 0, 20), 2)
                cv2.putText(frame, f'Images: {i}/25', (30, 30), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 0, 20), 2)
                
                # Capture image at interval (every 5 frames)
                if j % 5 == 0 and i < 25:
                    # Extract face region
                    face = frame[y1:y2, x1:x2]
                    
                    # Save original image
                    img_name = f"{newusername}_{i}.jpg"
                    img_path = os.path.join(userimagefolder, img_name)
                    cv2.imwrite(img_path, face)
                    
                    # Save with slight variations for better training
                    if i % 3 == 0:
                        # Save slightly brighter version
                        bright = cv2.convertScaleAbs(face, alpha=1.1, beta=10)
                        cv2.imwrite(os.path.join(userimagefolder, f"{newusername}_bright_{i}.jpg"), bright)
                        
                        # Save slightly darker version
                        dark = cv2.convertScaleAbs(face, alpha=0.9, beta=-10)
                        cv2.imwrite(os.path.join(userimagefolder, f"{newusername}_dark_{i}.jpg"), dark)
                    
                    print(f"Saved image {i}: {img_name}")
                    i += 1
                    
                    # Show success message
                    cv2.putText(frame, "Image captured!", (30, 60), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
                    cv2.imshow('Adding new User', frame)
                    cv2.waitKey(200)  # Slight pause
                
                j += 1
            
            # Show frame
            cv2.imshow('Adding new User', frame)
            
            # Check for exit
            if cv2.waitKey(1) == 27 or i >= 25:  # ESC key
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

    old_folder = os.path.join('static', 'faces', f"{old_name}_{old_id}")
    new_folder = os.path.join('static', 'faces', f"{new_name}_{new_id}")

    try:
        if os.path.isdir(old_folder):
            # If destination exists, remove it first to avoid errors
            if os.path.isdir(new_folder):
                shutil.rmtree(new_folder)
            os.rename(old_folder, new_folder)
            print(f"Renamed {old_folder} -> {new_folder}")

            student = Student.query.filter_by(roll_no=str(old_id)).first()
            if student:
                student.roll_no = str(new_id)
                student.name = new_name
                db.session.commit()
                save_student_with_encoding(str(new_id), new_name, department=student.department or "General", folder_path=new_folder)

            # Retrain model so labels reflect new folder name
            train_model()
        else:
            print(f"Source folder not found for edit: {old_folder}")
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
        today_key = date.today().strftime("%m_%d_%y")
        folder = 'Attendance'
        filename = f'Attendance-{today_key}.csv'
        full_path = os.path.join(folder, filename)

        if not os.path.exists(full_path):
            # Render home with a friendly message if file missing
            names, rolls, times, l = extract_attendance()
            registered_users = get_registered_users()
            return render_template('home.html', names=names, rolls=rolls, times=times, l=l,
                                   registered_users=registered_users, totalreg=totalreg(),
                                   datetoday2=datetoday2, mess="No attendance file for today yet.")

        # Serve the CSV (inline view in browser)
        return send_from_directory(folder, filename, as_attachment=False)
    except Exception as e:
        print(f"Error serving today's CSV: {str(e)}")
        return redirect(url_for('home'))

#### Our main function which runs the Flask App
if __name__ == '__main__':
    app.run(debug=True, port=1000)
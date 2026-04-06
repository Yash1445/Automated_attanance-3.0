#!/usr/bin/env python3
"""
Debug script to diagnose face recognition issues
"""
import os
import sys
import joblib
import cv2
import numpy as np
from pathlib import Path

try:
    import face_recognition
    print("✓ face_recognition library imported successfully")
except ImportError as e:
    print(f"✗ ERROR: face_recognition not installed: {e}")
    sys.exit(1)

# Check if face detection cascade is available
cascade_path = 'haarcascade_frontalface_default.xml'
if os.path.exists(cascade_path):
    print(f"✓ Cascade file found: {cascade_path}")
else:
    print(f"✗ ERROR: Cascade file not found: {cascade_path}")

# Check faces folder structure
faces_dir = 'static/faces'
print(f"\n{'='*60}")
print(f"Checking faces directory: {faces_dir}")
print(f"{'='*60}")

if not os.path.exists(faces_dir):
    print(f"✗ ERROR: {faces_dir} directory not found!")
    sys.exit(1)

users = os.listdir(faces_dir)
print(f"✓ Found {len(users)} user folder(s):")

total_images = 0
for user in users:
    user_path = os.path.join(faces_dir, user)
    if not os.path.isdir(user_path):
        print(f"  ✗ {user} (NOT A DIRECTORY)")
        continue
    
    images = [f for f in os.listdir(user_path) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
    print(f"  ✓ {user}: {len(images)} image(s)")
    total_images += len(images)
    
    if len(images) > 0:
        for imgname in images[:2]:  # Show first 2
            print(f"      - {imgname}")

print(f"\nTotal images across all users: {total_images}")

# Check model file
model_path = 'static/face_recognition_model.pkl'
print(f"\n{'='*60}")
print(f"Checking model file: {model_path}")
print(f"{'='*60}")

if not os.path.exists(model_path):
    print(f"✗ ERROR: Model file does not exist! Need to train first.")
    print(f"\nTo fix: Train the model by registering faces in the web app, or run:")
    print(f"  python app.py (and register users)")
else:
    file_size = os.path.getsize(model_path)
    print(f"✓ Model file exists (size: {file_size} bytes)")
    
    try:
        data = joblib.load(model_path)
        if isinstance(data, dict):
            encodings = data.get('encodings', [])
            names = data.get('names', [])
            threshold = data.get('threshold', 0.48)
            print(f"✓ Model loaded successfully")
            print(f"  - Encodings: {len(encodings)}")
            print(f"  - Names: {len(names)}")
            print(f"  - Threshold: {threshold}")
            
            if len(names) > 0:
                print(f"  - Users trained: {set(names)}")
        else:
            print(f"✗ ERROR: Model format is wrong (not a dict)")
    except Exception as e:
        print(f"✗ ERROR: Could not load model: {e}")

# Test face detection
print(f"\n{'='*60}")
print(f"Testing face detection")
print(f"{'='*60}")

test_images = []
for user in users[:1]:  # Test with first user
    user_path = os.path.join(faces_dir, user)
    images = [f for f in os.listdir(user_path) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
    if images:
        test_images.append((user, os.path.join(user_path, images[0])))
        break

if test_images:
    user, img_path = test_images[0]
    print(f"Testing with: {img_path}")
    
    try:
        image = face_recognition.load_image_file(img_path)
        print(f"✓ Image loaded: shape={image.shape}")
        
        faces = face_recognition.face_locations(image, model='hog', number_of_times_to_upsample=1)
        print(f"✓ Faces detected: {len(faces)}")
        
        if len(faces) > 0:
            encodings = face_recognition.face_encodings(image, faces)
            print(f"✓ Encodings generated: {len(encodings)}")
            
            if len(encodings) > 0:
                enc = encodings[0]
                print(f"  - Encoding shape: {enc.shape}")
                print(f"  - Encoding sample: {enc[:5]}")
        else:
            print(f"✗ WARNING: No faces detected in test image!")
    except Exception as e:
        print(f"✗ ERROR during face detection: {e}")
        import traceback
        traceback.print_exc()

print(f"\n{'='*60}")
print(f"DIAGNOSIS COMPLETE")
print(f"{'='*60}")

# Print recommendations
print("\nRECOMMENDATIONS:")
if not os.path.exists(model_path):
    print("1. Register user faces through the web app's registration page")
    print("2. The model will be trained automatically")
elif total_images < 3:
    print("1. Add more images per user (at least 3-5 recommended)")
    print("2. Retrain by registering more faces")
else:
    print("1. Verify face is clearly visible in test images") 
    print("2. Check that lighting is good when taking attendance")
    print("3. Adjust FACE_STRICT_THRESHOLD in app.py if faces won't match")
    print("4. Ensure your face matches the registered images")

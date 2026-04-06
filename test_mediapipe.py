#!/usr/bin/env python3
"""
Test script for MediaPipe-based face detection
"""
import os
import sys
import cv2
import numpy as np

try:
    import mediapipe as mp
    print("✓ MediaPipe imported successfully")
    mp_face_detection = mp.solutions.face_detection
    face_detector = mp_face_detection.FaceDetection(model_selection=1, min_detection_confidence=0.5)
    print("✓ MediaPipe face detector initialized")
except ImportError as e:
    print(f"✗ ERROR: MediaPipe not available: {e}")
    sys.exit(1)

# Check faces folder
faces_dir = 'static/faces'
print(f"\n{'='*60}")
print(f"Checking {faces_dir}")
print(f"{'='*60}")

if not os.path.exists(faces_dir):
    print(f"✗ {faces_dir} not found")
    sys.exit(1)

users = [d for d in os.listdir(faces_dir) if os.path.isdir(os.path.join(faces_dir, d))]
print(f"Found {len(users)} user(s): {users}")

# Test face detection on a sample image
print(f"\n{'='*60}")
print(f"Testing face detection")
print(f"{'='*60}")

test_count = 0
for user in users[:2]:
    user_path = os.path.join(faces_dir, user)
    images = [f for f in os.listdir(user_path) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
    
    if not images:
        print(f"  No images for {user}")
        continue
    
    img_path = os.path.join(user_path, images[0])
    print(f"\nTesting with: {img_path}")
    
    img = cv2.imread(img_path)
    if img is None:
        print("  ✗ Could not read image")
        continue
    
    print(f"  Image shape: {img.shape}")
    
    rgb_img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    results = face_detector.process(rgb_img)
    
    if results.detections:
        print(f"  ✓ Faces detected: {len(results.detections)}")
        for i, det in enumerate(results.detections):
            bbox = det.location_data.bounding_box
            print(f"    Face {i+1}: conf={det.score[0]:.2f}")
        test_count += 1
    else:
        print(f"  ✗ No faces detected")

print(f"\n✓ Successfully detected faces in {test_count} test images")
print("\n✓ Face detection setup is working!")

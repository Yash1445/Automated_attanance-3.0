"""
Simplified face recognition using OpenCV Haar Cascade and ORB features
This doesn't require dlib or complex dependencies
"""
import os
import cv2
import numpy as np
from collections import defaultdict

# Load Haar Cascade
cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
face_cascade = cv2.CascadeClassifier(cascade_path)

if face_cascade.empty():
    print("Warning: Could not load cascade classifier")

def detect_faces_cascade(frame):
    """Detect faces using Haar Cascade"""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
    # Convert to (top, right, bottom, left) format
    face_locs = []
    for (x, y, w, h) in faces:
        face_locs.append((y, x + w, y + h, x))
    return face_locs

def extract_face_desc(face_roi):
    """Extract descriptor from face using SIFT/ORB"""
    if face_roi is None or face_roi.size == 0:
        return None
    
    gray = cv2.cvtColor(face_roi, cv2.COLOR_BGR2GRAY)
    
    # Try SIFT first, fallback to ORB
    try:
        sift = cv2.SIFT_create()
        kp, des = sift.detectAndCompute(gray, None)
    except:
        orb = cv2.ORB_create(nfeatures=200)
        kp, des = orb.detectAndCompute(gray, None)
    
    if des is None:
        # Fallback to histogram if no features found
        hist = cv2.calcHist([gray], [0], None, [256], [0, 256])
        return hist.flatten()
    
    return des

def match_faces(test_descriptor, ref_descriptor):
    """Match two face descriptors"""
    if test_descriptor is None or ref_descriptor is None:
        return 0.0
    
    # If they're 1D arrays (histograms), use histogram comparison
    if test_descriptor.ndim == 1 and ref_descriptor.ndim == 1:
        distance = cv2.compareHist(
            test_descriptor.astype(np.uint8) if test_descriptor.dtype != np.uint8 else test_descriptor,
            ref_descriptor.astype(np.uint8) if ref_descriptor.dtype != np.uint8 else ref_descriptor,
            cv2.HISTCMP_BHATTACHARYYA
        )
        return 1.0 - distance  # Convert distance to similarity
    
    # Otherwise use feature matching
    if test_descriptor.ndim == 2 and ref_descriptor.ndim == 2:
        try:
            # Use BFMatcher for feature matching
            bf = cv2.BFMatcher(cv2.NORM_L2, crossCheck=False)
            matches = bf.knnMatch(test_descriptor, ref_descriptor, k=2)
            
            # Apply Lowe's ratio test
            good_matches = []
            for match_pair in matches:
                if len(match_pair) == 2:
                    m, n = match_pair
                    if m.distance < 0.75 * n.distance:
                        good_matches.append(m)
            
            # Score based on number of good matches
            if len(good_matches) == 0:
                return 0.0
            
            similarity = min(1.0, len(good_matches) / 20.0)  # Normalize
            return similarity
        except Exception as e:
            print(f"Error in feature matching: {e}")
            return 0.0
    
    return 0.0

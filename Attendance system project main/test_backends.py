import cv2
import time
import numpy as np

# Test 1: DirectShow
print("Testing DirectShow...")
cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
time.sleep(2)

for i in range(30):
    cap.read()
    
ret, frame = cap.read()
print(f"DirectShow - Brightness: {np.mean(frame):.2f}")
cap.release()

# Test 2: Media Foundation  
print("\nTesting Media Foundation...")
cap = cv2.VideoCapture(0, cv2.CAP_MSMF)
time.sleep(2)

for i in range(30):
    cap.read()
    
ret, frame = cap.read()
print(f"Media Foundation - Brightness: {np.mean(frame):.2f}")
cap.release()

print("\nDone! Higher brightness = working camera")
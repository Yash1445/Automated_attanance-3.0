"""
Simple standalone camera test script
Run this OUTSIDE of Flask to test if OpenCV camera works
Usage: python test_camera_simple.py
"""

import cv2
import sys

print("="*60)
print("CAMERA TEST SCRIPT")
print("="*60)

# Test 1: Check OpenCV version
print(f"\n1. OpenCV Version: {cv2.__version__}")

# Test 2: Try to open camera
print("\n2. Opening camera 0...")
cap = cv2.VideoCapture(0)

if not cap.isOpened():
    print("   ❌ Camera 0 failed, trying camera 1...")
    cap = cv2.VideoCapture(1)

if not cap.isOpened():
    print("   ❌ ERROR: Could not open any camera!")
    print("\n   Possible issues:")
    print("   - No camera connected")
    print("   - Camera in use by another application")
    print("   - Permission issues")
    sys.exit(1)

print("   ✅ Camera opened successfully!")

# Test 3: Read a frame
print("\n3. Reading frame...")
ret, frame = cap.read()

if not ret:
    print("   ❌ ERROR: Could not read frame!")
    cap.release()
    sys.exit(1)

print(f"   ✅ Frame captured! Size: {frame.shape}")

# Test 4: Create and show window
print("\n4. Creating window...")
window_name = 'Camera Test - Press Q to close'

try:
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window_name, 800, 600)
    print("   ✅ Window created!")
except Exception as e:
    print(f"   ❌ Error creating window: {e}")
    cap.release()
    sys.exit(1)

# Test 5: Show live feed
print("\n5. Displaying live feed...")
print("   👀 CHECK YOUR SCREEN NOW!")
print("   ⌨️  Press 'Q' to close the window")
print("\n" + "="*60)

frame_count = 0
try:
    while True:
        ret, frame = cap.read()
        if not ret:
            print("   ❌ Lost camera connection")
            break
        
        frame_count += 1
        
        # Add text overlay
        cv2.putText(frame, f"Frame: {frame_count}", (10, 30),
                   cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        cv2.putText(frame, "Press Q to close", (10, 70),
                   cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        
        # Show frame
        cv2.imshow(window_name, frame)
        
        # Check for Q key
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q') or key == ord('Q'):
            print(f"\n   ✅ User pressed Q (frame {frame_count})")
            break
        
        # Auto-close after 300 frames (~10 seconds at 30fps)
        if frame_count >= 300:
            print(f"\n   ⏱️  Auto-closing after {frame_count} frames")
            break

except KeyboardInterrupt:
    print("\n   ⚠️  Interrupted by user")
except Exception as e:
    print(f"\n   ❌ Exception: {e}")
    import traceback
    traceback.print_exc()

# Cleanup
print("\n6. Cleaning up...")
cap.release()
cv2.destroyAllWindows()
cv2.waitKey(1)

print("   ✅ Camera released")
print("\n" + "="*60)
print("TEST COMPLETE!")
print("="*60)

if frame_count > 0:
    print(f"\n✅ SUCCESS! Captured {frame_count} frames")
    print("If you saw the window, your camera works fine!")
else:
    print("\n❌ FAILED! No frames were captured")

print("\nIf the window didn't appear:")
print("1. Check if it's minimized in taskbar")
print("2. Try Alt+Tab to find the window")
print("3. Check if running in a VM/container without display")
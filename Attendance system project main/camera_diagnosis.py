"""
Detailed camera diagnostic script
This will test multiple camera backends and configurations
"""

import cv2
import numpy as np
import time

print("="*70)
print("DETAILED CAMERA DIAGNOSTIC")
print("="*70)

# Test different backends
backends = [
    (cv2.CAP_DSHOW, "DirectShow (Windows)"),
    (cv2.CAP_MSMF, "Media Foundation (Windows)"),
    (cv2.CAP_ANY, "Auto-detect"),
]

working_configs = []

for backend_id, backend_name in backends:
    print(f"\n{'='*70}")
    print(f"Testing: {backend_name}")
    print(f"{'='*70}")
    
    for camera_index in range(3):  # Test cameras 0, 1, 2
        print(f"\n  Camera {camera_index}:")
        
        try:
            # Open camera
            cap = cv2.VideoCapture(camera_index, backend_id)
            
            if not cap.isOpened():
                print(f"    ❌ Could not open")
                continue
            
            # Get camera properties
            width = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
            height = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
            fps = cap.get(cv2.CAP_PROP_FPS)
            
            print(f"    ✅ Opened: {int(width)}x{int(height)} @ {fps}fps")
            
            # Try to read frame
            ret, frame = cap.read()
            
            if not ret or frame is None:
                print(f"    ❌ Could not read frame")
                cap.release()
                continue
            
            # Check if frame is black
            mean_brightness = np.mean(frame)
            print(f"    📊 Frame brightness: {mean_brightness:.2f} (0=black, 255=white)")
            
            if mean_brightness < 5:
                print(f"    ⚠️  Frame is completely black!")
            elif mean_brightness < 30:
                print(f"    ⚠️  Frame is very dark")
            else:
                print(f"    ✅ Frame has content!")
                working_configs.append((camera_index, backend_id, backend_name))
            
            # Show frame info
            print(f"    📐 Frame shape: {frame.shape}")
            print(f"    🎨 Frame dtype: {frame.dtype}")
            print(f"    📊 Min/Max values: {frame.min()}/{frame.max()}")
            
            cap.release()
            
        except Exception as e:
            print(f"    ❌ Error: {e}")

print("\n" + "="*70)
print("SUMMARY")
print("="*70)

if working_configs:
    print(f"\n✅ Found {len(working_configs)} working configuration(s):\n")
    for idx, (cam_idx, backend_id, backend_name) in enumerate(working_configs, 1):
        print(f"  {idx}. Camera {cam_idx} with {backend_name}")
    
    print("\n" + "="*70)
    print("RECOMMENDED CONFIGURATION:")
    print("="*70)
    
    cam_idx, backend_id, backend_name = working_configs[0]
    print(f"\nUse: cv2.VideoCapture({cam_idx}, cv2.CAP_{backend_name.split()[0].upper()})")
    
    # Test the working configuration with live display
    print("\n" + "="*70)
    print("TESTING BEST CONFIGURATION WITH LIVE DISPLAY")
    print("="*70)
    
    cap = cv2.VideoCapture(cam_idx, backend_id)
    
    # Wait for camera to warm up
    print("\nWarming up camera...")
    for i in range(20):
        cap.read()
        time.sleep(0.1)
    
    print("✅ Opening live window...")
    print("👀 Check your screen!")
    print("⌨️  Press 'q' to close\n")
    
    window_name = 'Working Camera - Press Q to close'
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window_name, 800, 600)
    
    for i in range(100):  # Show for ~3 seconds
        ret, frame = cap.read()
        if ret and frame is not None:
            cv2.putText(frame, f"Frame: {i}", (10, 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
            cv2.putText(frame, "Press Q to close", (10, 70),
                       cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
            cv2.imshow(window_name, frame)
        
        if cv2.waitKey(30) & 0xFF == ord('q'):
            break
    
    cap.release()
    cv2.destroyAllWindows()
    print("\n✅ Test complete!")
    
else:
    print("\n❌ No working camera configurations found!")
    print("\nPossible issues:")
    print("  1. Camera is covered or disabled")
    print("  2. Camera driver issues")
    print("  3. Another application is using the camera")
    print("  4. Privacy settings blocking camera access")
    print("\nTry:")
    print("  - Close any apps that might use the camera (Zoom, Teams, etc.)")
    print("  - Check Windows Settings > Privacy > Camera")
    print("  - Try a different USB port (if external camera)")
    print("  - Restart your computer")

print("\n" + "="*70)
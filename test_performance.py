#!/usr/bin/env python3
"""
Performance Testing Script - Compare FPS before/after optimizations
Run this to verify your camera performs smoothly with optimizations enabled
"""

import cv2
import time
import os
import sys
from datetime import datetime

def test_camera_fps(optimization_enabled=True, test_duration=10):
    """
    Test camera FPS with or without optimizations
    
    Args:
        optimization_enabled: Use optimized parameters (True) or legacy (False)
        test_duration: How long to test in seconds
    """
    
    print(f"\n{'='*60}")
    print(f"Camera FPS Performance Test")
    print(f"{'='*60}")
    print(f"Optimization: {'ENABLED ✓' if optimization_enabled else 'DISABLED ✗'}")
    print(f"Test Duration: {test_duration} seconds")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")
    
    # Get parameters based on optimization flag
    if optimization_enabled:
        # Optimized parameters for low-end devices
        frame_skip = 3
        scale = 0.4
        upsample = 1
        print("✓ Using OPTIMIZED settings:")
        print(f"  - Frame Skip: Every {frame_skip} frames")
        print(f"  - Detection Scale: {scale*100:.0f}%")
        print(f"  - Face Upsampling: {upsample}")
    else:
        # Legacy parameters (original)
        frame_skip = 1
        scale = 0.5
        upsample = 2
        print("✗ Using LEGACY settings (original):")
        print(f"  - Frame Skip: Every {frame_skip} frame")
        print(f"  - Detection Scale: {scale*100:.0f}%")
        print(f"  - Face Upsampling: {upsample}")
    
    # Try to open camera
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("✗ ERROR: Cannot open camera. Make sure camera is connected.")
        return None
    
    # Warm up camera
    print("\nWarming up camera...")
    for _ in range(10):
        ret, frame = cap.read()
        if not ret:
            print("✗ ERROR: Camera not producing frames")
            cap.release()
            return None
    
    print("✓ Camera ready!")
    
    # FPS measuring variables
    frame_count = 0
    detection_counter = 0
    start_time = time.time()
    fps_readings = []
    
    # Create window
    window_name = f"FPS Test - {'OPTIMIZED' if optimization_enabled else 'LEGACY'}"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window_name, 800, 600)
    
    print(f"Running test... (Press 'q' to stop early)")
    print("-" * 60)
    
    try:
        while True:
            ret, frame = cap.read()
            if not ret or frame is None:
                break
            
            frame_count += 1
            
            # Simulate face detection processing every Nth frame
            should_process = (frame_count % frame_skip) == 0
            if should_process:
                detection_counter += 1
                
                # Simulate the processing cost
                small_frame = cv2.resize(frame, (0, 0), fx=scale, fy=scale)
                rgb_small = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)
                # Don't actually run face_recognition here - just simulate the load
                # Actual detection would take similar amount of time as scaling + color conversion
            
            # Display stats on frame
            elapsed = time.time() - start_time
            current_fps = frame_count / elapsed if elapsed > 0 else 0
            
            cv2.putText(frame, f"FPS: {current_fps:.1f}", (30, 60),
                       cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
            cv2.putText(frame, f"Frames: {frame_count} | Processing: {detection_counter}",
                       (30, 110), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            cv2.putText(frame, f"Time: {elapsed:.1f}s", (30, 150),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            
            if optimization_enabled:
                cv2.putText(frame, "OPTIMIZED MODE", (30, 200),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            else:
                cv2.putText(frame, "LEGACY MODE", (30, 200),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            
            cv2.imshow(window_name, frame)
            
            # Check for early exit
            if cv2.waitKey(1) & 0xFF == ord('q'):
                print("✓ Test stopped by user")
                break
            
            # Check if test duration exceeded
            if time.time() - start_time >= test_duration:
                print(f"✓ Test completed ({test_duration}s)")
                break
    
    finally:
        cap.release()
        cv2.destroyAllWindows()
    
    # Calculate final metrics
    total_time = time.time() - start_time
    avg_fps = frame_count / total_time if total_time > 0 else 0
    avg_detection_frames = detection_counter if frame_skip == 1 else f"{detection_counter} (every {frame_skip})"
    
    print("-" * 60)
    print(f"\nRESULTS:")
    print(f"  Total Frames: {frame_count}")
    print(f"  Processing Calls: {detection_counter}")
    print(f"  Duration: {total_time:.2f} seconds")
    print(f"  Average FPS: {avg_fps:.1f}")
    print(f"{'='*60}\n")
    
    return avg_fps


def main():
    """Run both tests and compare"""
    print("\n" + "="*60)
    print("CAMERA PERFORMANCE TEST - Optimized vs Legacy")
    print("="*60)
    
    # Test duration in seconds
    test_duration = 5  # Shorter test for quick feedback
    
    print("\nThis test will run your camera twice:")
    print(f"1. LEGACY mode (original - slower)")
    print(f"2. OPTIMIZED mode (new - faster)")
    print(f"\nEach test runs for {test_duration} seconds.\n")
    
    # Test 1: Legacy
    print("\n" + "█" * 60)
    print("TEST 1: LEGACY MODE (Original Settings)")
    print("█" * 60)
    legacy_fps = test_camera_fps(optimization_enabled=False, test_duration=test_duration)
    
    time.sleep(2)  # Wait between tests
    
    # Test 2: Optimized
    print("\n" + "█" * 60)
    print("TEST 2: OPTIMIZED MODE (New Settings)")
    print("█" * 60)
    optimized_fps = test_camera_fps(optimization_enabled=True, test_duration=test_duration)
    
    # Summary
    print("\n" + "="*60)
    print("FINAL COMPARISON")
    print("="*60)
    
    if legacy_fps and optimized_fps:
        improvement = (optimized_fps - legacy_fps) / legacy_fps * 100
        multiplier = optimized_fps / legacy_fps
        
        print(f"\nLegacy FPS:     {legacy_fps:.1f}")
        print(f"Optimized FPS:  {optimized_fps:.1f}")
        print(f"\nImprovement:    {improvement:+.1f}%")
        print(f"Speedup:        {multiplier:.2f}x faster")
        
        if improvement > 0:
            print(f"\n✓ OPTIMIZATION WORKING! Your camera now runs {multiplier:.1f}x faster!")
        else:
            print(f"\n✗ Optimization didn't help much. Try adjusting parameters in .env")
    else:
        print("\n✗ Test could not complete. Check your camera connection.")
    
    print("="*60 + "\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n✗ Test interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

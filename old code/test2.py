from picamera2 import Picamera2, Preview
import numpy as np
import cv2
import threading
import time

# Initialize camera with buffer_count=2 for smooth frame capture
picam2 = Picamera2()
config = picam2.create_still_configuration(
    raw={"format": "SRGGB12", "size": (2028, 1520)}, buffer_count=4
)
picam2.configure(config)

# Start QTGL preview
picam2.start_preview(Preview.QTGL)
picam2.start()

# Frame processing thread
def process_frames():
    while True:
        # Fast non-blocking capture
        raw_data = picam2.capture_array("raw").view(np.uint16)

        # Convert 12-bit to 8-bit using NumPy (FAST)
        raw_8bit = (raw_data >> 8).astype(np.uint8)

        # Demosaic Bayer to RGB (FAST)
        rgb_image = cv2.cvtColor(raw_8bit, cv2.COLOR_BAYER_RG2RGB)

        # Convert RGB888 to RGB8888 (adds alpha channel)
        rgba_image = cv2.cvtColor(rgb_image, cv2.COLOR_RGB2RGBA)

        # Update preview overlay
        picam2.set_overlay(rgba_image)

        time.sleep(0.0001)  # Prevents thread overload

# Run processing in a separate thread
thread = threading.Thread(target=process_frames, daemon=True)
thread.start()

# Keep script running
while True:
    time.sleep(1)

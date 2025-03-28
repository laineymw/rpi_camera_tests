from picamera2 import Picamera2, Preview
import numpy as np
import cv2
import threading
import time
import json

## This is as fast as i can get it without using openGL 
## using raw frames i can get it about 35 fps

def sort_dict(d):
    d_keys = list(d.keys())
    d_keys.sort()
    d = {i: d[i] for i in d_keys}
    return d

# Initialize camera with fast buffer handling
picam2 = Picamera2()
config = picam2.create_still_configuration(
    raw={"format": "SRGGB12", "size": (2028, 1520)}, buffer_count=4  # Increase buffer for smoother flow
)
picam2.configure(config)

# Open the default image metadata and read in the settings as a sorted dict
with open("/home/r/rpi_camera_tests/camera_settings.txt") as f:
    default_image_settings = f.read()
default_image_settings = json.loads(default_image_settings)
default_image_settings = sort_dict(default_image_settings)

# Apply the default settings to the current camera
for key in default_image_settings:
    try:
        picam2.set_controls({key:default_image_settings[key]})
        print(key,default_image_settings[key])
    except:
        print('FAIL to set camera setting')
        print(key,default_image_settings[key])

# Exposure settings for testing
exp_time = 1/60
exp_time_us = int(round(exp_time * 1000000))
picam2.set_controls({"ExposureTime": exp_time_us}) # Overwrite the exposure for testing

# FPS tracking variables
frame_count = 0
start_time = time.time()
fps = 0

# Start QTGL preview
picam2.start_preview(Preview.QTGL)
picam2.start()

# Target FPS (30 FPS)
target_fps = 30
frame_duration = 1 / target_fps  # Duration per frame (seconds)

# Process frames asynchronously
def process_frames():
    global frame_count, fps, start_time
    while True:
        # Capture frame at fixed interval
        request = picam2.capture_request()
        m = request.make_array("raw")  # Zero-copy buffer access
        raw_data = m.view(np.uint16)
        request.release()  # Release immediately

        # Convert 12-bit to 8-bit (Vectorized NumPy operation)
        raw_8bit = (raw_data >> 8).astype(np.uint8)

        # Use OpenCV for faster processing
        rgb_image = cv2.cvtColor(raw_8bit, cv2.COLOR_BAYER_RG2RGB)

        # Convert RGB888 → RGB8888 (QTGL requires 4 channels)
        rgba_image = cv2.cvtColor(rgb_image, cv2.COLOR_RGB2RGBA)

        # Compute FPS every second
        frame_count += 1
        elapsed_time = time.time() - start_time
        if elapsed_time >= 1.0:
            fps = frame_count / elapsed_time
            frame_count = 0
            start_time = time.time()

        # Draw FPS counter on the frame
        fps_text = f"FPS: {int(fps)}"
        cv2.putText(rgba_image, fps_text, (30, 50), cv2.FONT_HERSHEY_SIMPLEX, 
                    1, (255, 0, 0, 255), 2, cv2.LINE_AA)

        # Send to preview
        picam2.set_overlay(rgba_image)

        # Sleep to lock the frame rate to 30 FPS
        time.sleep(frame_duration)  # Ensures 30 FPS

# Launch the frame processing in a background thread
thread = threading.Thread(target=process_frames, daemon=True)
thread.start()

# Keep the script alive
while True:
    try:
        time.sleep(1)  # Keep main thread running
    except KeyboardInterrupt:
        print("Interrupted by user.")
        break

# import libraries
from utils import *
import os, time, cv2, serial, csv
import numpy as np
import get_settings
import camera_control
# import matplotlib.pyplot as plt
# from tkinter import Tk
# from movement import simple_stream

def send_command(ser, command):
    try:
        # Send the command to the CNC
        ser.write(f"{command}\n".encode())
        print(f"Sent: {command}")

        # Wait for an "OK" response from the CNC
        while True:
            response = ser.readline().decode().strip()
            if response:
                print(f"Response: {response}")
                if response.lower() == "ok":  # CNC signals completion
                    print("Command sent.")
                    break
                elif "error" in response.lower():
                    print(f"Error received: {response}")
                    break
    except Exception as e:
        print(f"Error sending command: {e}")

def move_to(ser, x, y, z):
    send_command(ser, f'G0 X{x} Y{y} Z{z}')


# finds the z position that gets the best focus
def run_autofocus_at_current_position(ser, starting_location,
        autofocus_min_max=[1, -1], autofocus_delta_z=0.10, cap=None):

    print("FOCUSING CAMERA")
    autofocus_steps = int(abs(np.diff(autofocus_min_max) / autofocus_delta_z)) + 1
    z_limit = [10, -94]
    offset = 25  # this is for the autofocus algorithm, how many pixels apart is the focus to be measured
    thresh = 5  # same as above but now ignores all the values under thresh

    # find the z locations for the loop to step through
    z_positions_start = np.linspace(
        starting_location['z_pos'] + autofocus_min_max[0],
        starting_location['z_pos'] + autofocus_min_max[1],
        num=autofocus_steps
    )
    z_positions = []
    images = []
    uncalib_fscore = []

    for counter, z_pos in enumerate(z_positions_start):
        this_location = starting_location.copy()
        this_location['z_pos'] = z_pos
        if z_limit[0] > z_pos > z_limit[1]:
            z_positions.append(z_pos)

            move_to(ser, this_location['x_pos'], this_location['y_pos'], this_location['z_pos'])
            # get rid of buffer for camera
            for _ in range(10):
                ret, frame = cap.read()
            ret, frame = cap.read()
            frame = frame[:,:,2]
            images.append(frame)
            temp = sq_grad(frame, thresh=thresh, offset=offset)
            uncalib_fscore.append(np.sum(temp))
            camera_control.imshow_resize(frame_name="stream", frame=frame)
   
    output_dir = "autofocus_images"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    for i, img in enumerate(images):
        img_path = os.path.join(output_dir, f"image_{i}.png")
        cv2.imwrite(img_path, img)

    assumed_focus_idx = np.argmax(uncalib_fscore)
    z_pos = z_positions[assumed_focus_idx]  # for the final output
    this_location = starting_location.copy()
    this_location['z_pos'] = z_positions[assumed_focus_idx] + 0.05
    move_to(ser, this_location['x_pos'], this_location['y_pos'], this_location['z_pos'])

    s_camera_settings = get_settings.get_basic_camera_settings()
    frame, cap = camera_control.capture_fluor_img_return_img(
        s_camera_settings, cap=cap, return_cap=True, clear_N_images_from_buffer=2
    )
    camera_control.imshow_resize(frame_name="stream", frame=frame)
    print('CAMERA FOCUSED')
    return z_pos, cap


# function used within autofocus
def sq_grad(img, thresh=50, offset=10):
    shift = int(0 - offset)
    offset = int(offset)

    img1 = img[:, 0:shift].astype(np.float32)
    img2 = img[:, offset:].astype(np.float32)

    diff = np.abs(img2 - img1)
    mask = diff > thresh
    squared_gradient = diff * diff * mask

    return squared_gradient


# set up controller class for movement
class CNCController:
    def __init__(self, port, baudrate):
        import re
        self.ser = serial.Serial(port, baudrate, timeout=1)
        time.sleep(2)

    def send_command(self, command):
        self.ser.reset_input_buffer()  # flush the input and the output
        self.ser.reset_output_buffer()
        time.sleep(0.025)
        self.ser.write(command.encode())
        time.sleep(0.025)

        return self.ser.readline().decode().strip()

    def move_XYZ(self, position):
        command = f'G1 X{position["x_pos"]} Y{position["y_pos"]} Z{position["z_pos"]} F2500'
        return self.send_command(command)


# reading CSV file of well positions
def read_positions_from_csv(filename):
    positions = []
    with open(filename, 'r') as file:
        reader = csv.reader(file)
        next(reader)  # skipping the header
        for row in reader:
            x, y, z = map(float, row[:3])  # Extract first three columns as positions
            name = row[3]
            positions.append((x, y, z, name))  # Append to positions list
    return positions
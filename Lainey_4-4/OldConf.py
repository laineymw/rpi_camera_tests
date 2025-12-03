#!/usr/bin/env python3

import time, serial, cv2, libcamera
import numpy as np
from picamera2 import Picamera2, Preview
from focus import run_autofocus_at_current_position
import RPi.GPIO as GPIO
from datetime import datetime
import tkinter as tk
from pathlib import Path

class CNCController:
    def __init__(self, port, baudrate):
        import re
        self.ser = serial.Serial(port, baudrate, timeout=1)
        time.sleep(2)

    def wait_for_movement_completion(self,cleaned_line):

        # print("waiting on: " + str(cleaned_line))

        if ('$X' not in cleaned_line) and ('$$' not in cleaned_line) and ('?' not in cleaned_line):
            idle_counter = 0
            time.sleep(0.025)
            while True:
                self.ser.reset_input_buffer()
                self.ser.reset_output_buffer()
                time.sleep(0.025)
                command = str.encode("?"+ "\n")
                self.ser.write(command)
                time.sleep(0.025)
                grbl_out = self.ser.readline().decode().strip()
                grbl_response = grbl_out.strip()

                if 'ok' not in grbl_response.lower():  
                    if 'idle' in grbl_response.lower():
                        idle_counter += 1
                    else:
                        if grbl_response != '':
                            pass
                            # print(grbl_response)
                if idle_counter == 1 or idle_counter == 2:
                    # print(grbl_response)
                    pass
                if idle_counter > 3:
                    break
                if 'alarm' in grbl_response.lower():
                    raise ValueError(grbl_response)

    def send_command(self, command):
        self.ser.reset_input_buffer() # flush the input and the output
        self.ser.reset_output_buffer()
        time.sleep(0.025)
        self.ser.write(command.encode())
        time.sleep(0.025)

        CNCController.wait_for_movement_completion(self,command)
        out = []
        for i in range(50):
            time.sleep(0.001)
            response = self.ser.readline().decode().strip()
            time.sleep(0.001)
            out.append(response)
            if 'error' in response.lower():
                print('error--------------------------------------------------')
            if 'ok' in response:
                break
            # print(response)
        return response, out
   
    def get_current_position(self):

        command = "? " + "\n"
        response, out = CNCController.send_command(self,command)
        MPos = out[0] # get the idle output
        MPos = MPos.split('|')[1] # get the specific output
        MPos = MPos.split(',')
        MPos[0] = MPos[0].split(':')[1]

        position = dict()

        position['x_pos'] = float(MPos[0])
        position['y_pos'] = float(MPos[1])
        position['z_pos'] = float(MPos[2])

        return position
   
    def move_XY_at_Z_travel(self, position, z_travel_height):

        current_position = CNCController.get_current_position(self)

        if round(float(current_position['z_pos']),1) != float(z_travel_height):
            #### go to z travel height
            # command = "G0 z" + str(z_travel_height) + " " + "\n"
            command = "G1 z" + str(z_travel_height) + " F2500" #+ "\n"
            response, out = CNCController.send_command(self,command)
       
        # print('moving to XY')
        # command = 'G0 ' + 'X' + str(position['x_pos']) + ' ' + 'Y' + str(position['y_pos'])
        command = 'G1 ' + 'X' + str(position['x_pos']) + ' ' + 'Y' + str(position['y_pos']) + ' F2500'
        response, out = CNCController.send_command(self,command)
        ##### move z
        # print('moving to Z')
        # command = 'G0 ' + 'Z' + str(position['z_pos'])
        command = 'G1 ' + 'Z' + str(position['z_pos']) + ' F2500'
        response, out = CNCController.send_command(self,command)

        return CNCController.get_current_position(self)
   
    def move_XYZ(self, position, return_position = False):

        ##### move xyz
        # print('moving to XYZ')
        # command = 'G0 ' + 'X' + str(position['x_pos']) + ' ' + 'Y' + str(position['y_pos']) + ' ' + 'Z' + str(position['z_pos'])
        command = 'G1 ' + 'X' + str(position['x_pos']) + ' ' + 'Y' + str(position['y_pos']) + ' ' + 'Z' + str(position['z_pos']) + ' F2500'
        response, out = CNCController.send_command(self,command)

        if return_position:
            return CNCController.get_current_position(self)
        else:
            return response
   
    def home_grbl(self):
        print("HOMING CNC")
        command = "$H"+ "\n"
        response, out = CNCController.send_command(self,command)
   
    def set_up_grbl(self, home = True):
        # unlock
        command = "$X"+ "\n"
        response, out = CNCController.send_command(self,command)

        command = "?"+ "\n"
        response, out = CNCController.send_command(self,command)

        if home:
            CNCController.home_grbl(self)

    def close_connection(self):
        self.ser.close()

def process_raw(input_array,R = False, G = False, G1 = False, G2 = False, B = False, RGB = True, RGB2 = False, rgb_or_bgr = True, mono = False):
    if 'uint16' not in str(input_array.dtype):
        input_array = input_array.view(np.uint16)
        if mono:
            return input_array

    if R or G or B or G1 or G2 or RGB2:
        RGB = False

    if RGB: # return an rgb array
        blue_pixels = input_array[0::2,0::2]
        red_pixels = input_array[1::2,1::2]
        green1_pixels = input_array[0::2,1::2]
        green2_pixels = input_array[1::2,0::2]

        avg_green = ((green1_pixels&green2_pixels) + (green1_pixels^green2_pixels)/2).astype(np.uint16)

        if rgb_or_bgr:
            out = np.asarray([red_pixels,avg_green,blue_pixels]).transpose(1,2,0)
        else:
            out = np.asarray([blue_pixels,avg_green,red_pixels]).transpose(1,2,0)
    if R: # just the red pixels
        out = input_array[1::2,1::2]
    if G: # just the green pixels (averaged)
        green1_pixels = input_array[0::2,1::2]
        green2_pixels = input_array[1::2,0::2]

        out = ((green1_pixels&green2_pixels) + (green1_pixels^green2_pixels)/2).astype(np.uint16)
    if G1: # just the green 1 pixels
        out = input_array[0::2,1::2]
    if G2: # just the green 2 pixels
        out = input_array[1::2,0::2]
    if B: # just blue pixels
        out = input_array[0::2,0::2]
    if RGB2: # 2x2 array of the pixel values
        blue_pixels = input_array[0::2,0::2]
        red_pixels = input_array[1::2,1::2]
        green1_pixels = input_array[0::2,1::2]
        green2_pixels = input_array[1::2,0::2]

        a = np.concatenate((red_pixels,green1_pixels),axis = 0)
        b = np.concatenate((green2_pixels,blue_pixels ), axis = 0)
        out = np.concatenate((a,b),axis = 1)

    return out

def get_user_selected_position():

    POSITIONS = {
        "Left slide- top": {'x_pos': -25.5, 'y_pos': -95, 'z_pos': -6.9},
        "Left slide- middle": {'x_pos': -25.5, 'y_pos': -69.5, 'z_pos': -6.9},
        "Left slide- bottom": {'x_pos': -25.5, 'y_pos': -43, 'z_pos': -6.9},

        "Center slide- top": {'x_pos': -81.7, 'y_pos': -95, 'z_pos': -6.9},
        "Center slide- middle": {'x_pos': -81.7, 'y_pos': -69.5, 'z_pos': -6.9},
        "Center slide- bottom": {'x_pos': -81.7, 'y_pos': -43, 'z_pos': -6.9},

        "Right slide- top": {'x_pos': -138.5, 'y_pos': -95, 'z_pos': -6.9},
        "Right slide- middle": {'x_pos': -138.5, 'y_pos': -69.5, 'z_pos': -6.9},
        "Right slide- bottom": {'x_pos': -138.5, 'y_pos': -43, 'z_pos': -6.9}
    }

    selected_position = {}

    def on_button_click(label):
        nonlocal selected_position
        selected_position = POSITIONS[label]
        root.destroy()

    root = tk.Tk()
    root.title("Select Slide Position")
    root.geometry("600x250")

    labels = [
        ["Left slide- top", "Center slide- top", "Right slide- top"],
        ["Left slide- middle", "Center slide- middle", "Right slide- middle"],
        ["Left slide- bottom", "Center slide- bottom", "Right slide- bottom"]
    ]

    for row_idx, row in enumerate(labels):
        for col_idx, label in enumerate(row):
            btn = tk.Button(root, text=label, width=20, height=2,
                            command=lambda l=label: on_button_click(l))
            btn.grid(row=row_idx, column=col_idx, padx=5, pady=5)

    # Add instructional text below the grid (row 3 spans all 3 columns)
    instruction = tk.Label(root, text="Select a slide position to begin", font=("Arial", 12))
    instruction.grid(row=3, column=0, columnspan=3, pady=(10, 5))

    root.mainloop()
    return selected_position

# Set up serial connection
controller = CNCController(port="/dev/ttyUSB0", baudrate=115200)

# Set up camera
picam2 = Picamera2()

cam_config = picam2.create_preview_configuration(
    main= {"format": "YUV420", "size": (480,360)},#(int(2028/2),int(1520/2))}, #(480,360)},
    # lores = {"format": "XBGR8888","size":(480,360)},# (507,380),(480,360)
    raw={"format": "SRGGB12", "size": (2028,1520)},#(4056,3040)},(2028,1520),(2028,1080)
    display = "main" ,queue=False ,buffer_count=1 #, SRGGB12_CSI2P
)
cam_config["transform"] = libcamera.Transform(hflip=1, vflip=1)
picam2.configure(cam_config)

# Get user-selected position from GUI
chosen_position = get_user_selected_position()

# Home Robot
print("Homing robot...")
controller.home_grbl()

picam2.start_preview(Preview.QTGL)
picam2.start()

# Turn Light on
GPIO.setmode(GPIO.BCM)
GPIO.setup(26, GPIO.OUT)
GPIO.output(26, GPIO.HIGH)

# move to starting position
print("Moving to selected position...")
controller.move_XYZ(chosen_position)

# Focus
this_well_coords = controller.get_current_position()
print("I think I am at")
print(this_well_coords)
print("now focus z")
z_height, cap = run_autofocus_at_current_position(controller.ser, this_well_coords, picam2, autofocus_min_max=[-0.3,2],autofocus_delta_z=0.1)
print ("z focused")

# Capture Image
array_to_process = picam2.capture_array("raw")#,"lores"]) #"main","lores","raw"
array_to_process = process_raw(array_to_process, RGB= True, rgb_or_bgr=False)#, G = True) # RGB = True, 
image_to_display = cv2.cvtColor(array_to_process, cv2.COLOR_RGB2BGR)
normalized_image = image_to_display.astype(np.float32) / np.max(image_to_display)

# Save the image to Desktop with a timestamp
desktop = Path.home() / "Desktop"
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
filename = desktop / f"{timestamp}_demo.png"
cv2.imwrite(str(filename), normalized_image)
print(f"Image saved to: {filename}")

# Display the image
cv2.imshow("Image", normalized_image)
print("Data type:", normalized_image.dtype)
print("Bit depth:", normalized_image.dtype.itemsize * 8)
time.sleep(5)

# Close windows and turn off light
cv2.destroyAllWindows()
GPIO.cleanup()
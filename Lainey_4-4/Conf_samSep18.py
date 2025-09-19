#!/usr/bin/env python3

import time, serial, cv2, libcamera
import numpy as np
from picamera2 import Picamera2, Preview
from focus import run_autofocus_at_current_position
import RPi.GPIO as GPIO
from datetime import datetime
import tkinter as tk
from pathlib import Path
from camera_control import imshow_resize

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
    import tkinter as tk

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

    selected_positions = []

    root = tk.Tk()
    root.title("Select Slide Positions")
    root.geometry("600x300")

    # Dictionary to store IntVar for each checkbox
    var_dict = {}

    labels = [
        ["Left slide- top", "Center slide- top", "Right slide- top"],
        ["Left slide- middle", "Center slide- middle", "Right slide- middle"],
        ["Left slide- bottom", "Center slide- bottom", "Right slide- bottom"]
    ]

    for row_idx, row in enumerate(labels):
        for col_idx, label in enumerate(row):
            var = tk.IntVar()
            chk = tk.Checkbutton(root, text=label, variable=var)
            chk.grid(row=row_idx, column=col_idx, padx=5, pady=5, sticky="w")
            var_dict[label] = var

    def on_done():
        nonlocal selected_positions
        selected_positions = [POSITIONS[label] for label, var in var_dict.items() if var.get() == 1]
        root.destroy()

    # Add "Done" button at bottom
    done_btn = tk.Button(root, text="Done", width=15, height=2, command=on_done)
    done_btn.grid(row=4, column=0, columnspan=3, pady=15)

    # Instruction
    instruction = tk.Label(root, text="Select one or more slide positions, then click Done.", font=("Arial", 12))
    instruction.grid(row=5, column=0, columnspan=3, pady=(5, 10))

    root.mainloop()
    return selected_positions


# Set up serial connection
controller = CNCController(port="/dev/ttyUSB0", baudrate=115200)

# Set up camera
picam2 = Picamera2()

cam_config = picam2.create_preview_configuration(
    main= {"format": "YUV420", "size": (480,360)},#(int(2028/2),int(1520/2))}, #(480,360)},
    # lores = {"format": "XBGR8888","size":(480,360)},# (507,380),(480,360)
    raw={"format": "SRGGB12", "size": (2028,1520)},#(2028,1520)},#(4056,3040)},(2028,1520),(2028,1080)
    display = "main"  ,buffer_count=2 #,queue=False , SRGGB12_CSI2P
)
cam_config["transform"] = libcamera.Transform(hflip=1, vflip=1)
picam2.configure(cam_config)

imaging_config = picam2.create_preview_configuration(
    main= {"format": "YUV420", "size": (480,360)},#(int(2028/2),int(1520/2))}, #(480,360)},
    # lores = {"format": "XBGR8888","size":(480,360)},# (507,380),(480,360)
    raw={"format": "SRGGB12", "size": (4056,3040)},#(2028,1520)},#(4056,3040)},(2028,1520),(2028,1080)
    display = "main"  ,buffer_count=2 #,queue=False , SRGGB12_CSI2P
)
imaging_config["transform"] = libcamera.Transform(hflip=1, vflip=1)

# Get user-selected position from GUI
chosen_position = get_user_selected_position()
# chosen_position = [{'x_pos': -25.5, 'y_pos': -95, 'z_pos': -6.9}, 
#                    {'x_pos': -25.5, 'y_pos': -69.5, 'z_pos': -6.9}, 
#                    {'x_pos': -25.5, 'y_pos': -43, 'z_pos': -6.9}]
# chosen_position = [{'x_pos': -25.5, 'y_pos': -43, 'z_pos': -6.9}]

picam2.start_preview(Preview.QTGL)
picam2.start()

# Turn Light on
GPIO.setmode(GPIO.BCM)
GPIO.setup(26, GPIO.OUT)
GPIO.output(26, GPIO.HIGH)


# Home Robot
print("Homing robot...")
controller.home_grbl()


# Set up Desktop path for saving
desktop = Path.home() / "Desktop"

print("Moving to selected positions and capturing images...")
for idx, pos in enumerate(chosen_position): 

    # set the resolution LOW for focusing
    if idx != 0:
        picam2.stop()
        picam2.configure(cam_config)
        picam2.start()

    if idx == 0:
        x = np.arange(1024)
        y = np.arange(760)
        xx,yy = np.meshgrid(x,y)

    # Move CNC
    controller.move_XYZ(pos)
    print(f"Arrived at {pos}")

    print('running autofocus')
    # focus
    this_well_coords = controller.get_current_position()
    z_height, cap = run_autofocus_at_current_position(
        controller.ser, this_well_coords, picam2,
        autofocus_min_max=[-2, 2], autofocus_delta_z= (1/3)
    )
    this_well_coords = controller.get_current_position()

    # this attempts to move the camera to the center of mass of the image
    # hopefully thats the worms
    temp_img = picam2.capture_array("raw")
    temp_img = process_raw(temp_img,G=True)

    temp_img[temp_img<5000] = 0
    # imshow_resize("stream",temp_img)
    temp_img_sum = temp_img.sum()
    x_cms = (xx*temp_img).sum()/temp_img_sum
    y_cms = (yy*temp_img).sum()/temp_img_sum

    adjusted_coords = controller.get_current_position()
    adjusted_coords['y_pos'] = adjusted_coords['y_pos'] - list(((np.asarray(temp_img.shape[0])/2)-np.asarray([y_cms]))/114)[0]
    adjusted_coords['x_pos'] = adjusted_coords['x_pos'] + list(((np.asarray(temp_img.shape[1])/2)-np.asarray([x_cms]))/114)[0]
    controller.move_XYZ(adjusted_coords)

    print("Z focused 1/2")
    this_well_coords = controller.get_current_position()
    z_height, cap = run_autofocus_at_current_position(
        controller.ser, this_well_coords, picam2,
        autofocus_min_max=[-0.3, 0.3], autofocus_delta_z=0.1
    )
    print("Z focused 2/2")
    time.sleep(1)

    print('stopping camera')
    picam2.stop()
    # set the resolution to HIGH for imaging
    picam2.configure(imaging_config)
    print('starting camera')
    picam2.start()

    buffer_num = 2
    for i in range(buffer_num):
        array_to_process = picam2.capture_array("raw")#,"lores"]) #"main","lores","raw"

    print('capture array')
    # Capture image
    array_to_process = picam2.capture_array("raw")
    array_to_process = process_raw(array_to_process, RGB=True, rgb_or_bgr=False)
    image_to_display = cv2.cvtColor(array_to_process, cv2.COLOR_RGB2BGR)
    normalized_image = image_to_display.astype(np.float32) / np.max(image_to_display)

    # sam added this
    export_image = np.clip(normalized_image*255,a_min= 0,a_max = 255).astype(np.uint8)

    # Build unique filename: include index, timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = desktop / f"pos:{idx+1}_{timestamp}.png"

    print('wiriting image')
    # Save image
    cv2.imwrite(str(filename), export_image)
    print(f"Image saved to: {filename}")

    # show image
    cv2.imshow("Captured Image", normalized_image)
    time.sleep(1)
    cv2.destroyWindow("Captured Image")
    #cv2.destroyAllWindows()
    print('stopping camera')
    picam2.stop()
    print('starting camera')
    picam2.start()


# Close windows and turn off light
cv2.destroyAllWindows()
GPIO.cleanup()

print("End of function")